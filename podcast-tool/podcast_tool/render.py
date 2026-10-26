"""FFmpeg フィルタグラフの生成と実行（音を実際に変更する処理）。"""
from __future__ import annotations

from pathlib import Path

from .analyze import parse_ebur128
from .ffmpeg import FFmpeg
from .timeline import Timeline, envelope_expr

BITEXACT = ["-flags", "+bitexact", "-fflags", "+bitexact", "-map_metadata", "-1"]


def db2lin(db: float) -> float:
    return 10 ** (db / 20)


def layout_filter(ch_in: int, ch_out: int) -> str:
    """チャンネル変換を明示（自動変換の -3dB 等で声とBGMの比が狂わないように）。"""
    if ch_in == ch_out:
        return "anull"
    if ch_out == 1:
        w = 1.0 / ch_in
        return "pan=mono|c0=" + "+".join(f"{w:.6f}*c{i}" for i in range(ch_in))
    if ch_in == 1:
        return "pan=stereo|c0=c0|c1=c0"
    return "aformat=channel_layouts=stereo"  # 多チャンネル → ステレオは FFmpeg 標準のダウンミックス


def cleanup_chain(cfg, ch_in: int, noise_floor_db: float | None, noise_peak_db: float | None,
                  sr: int) -> tuple[str, dict]:
    """声のクリーニング・音量均しフィルタ列と、その内容の記録を返す。"""
    f, rec = [f"aresample={sr}", "aformat=sample_fmts=flt"], {}
    if cfg.flag("input.downmix_to_mono") and ch_in > 1:
        f.append(layout_filter(ch_in, 1))
        rec["downmix"] = f"{ch_in}ch → mono（等量合算）"
    if cfg.flag("cleanup.highpass.enabled"):
        hz = cfg.num("cleanup.highpass.frequency_hz")
        order = int(cfg.get("cleanup.highpass.order"))
        f += [f"highpass=f={hz:g}:poles=2"] * (order // 2)
        rec["highpass"] = f"{hz:g} Hz, {6 * order} dB/oct"
    if cfg.flag("cleanup.lowpass.enabled"):
        hz = cfg.num("cleanup.lowpass.frequency_hz")
        f.append(f"lowpass=f={hz:g}:poles=2")
        rec["lowpass"] = f"{hz:g} Hz"
    if cfg.flag("cleanup.declick.enabled"):
        f.append("adeclick")
        rec["declick"] = "adeclick（既定値）"
    nr = 0.0
    if cfg.flag("cleanup.denoise.enabled"):
        nr = cfg.num("cleanup.denoise.reduction_db")
        nf_cfg = cfg.num_or_auto("cleanup.denoise.noise_floor_db", -80, -20)
        nf = nf_cfg if nf_cfg is not None else (noise_floor_db if noise_floor_db is not None else -50.0)
        nf = max(-80.0, min(-20.0, nf))
        tn = 1 if cfg.flag("cleanup.denoise.track_noise") else 0
        f.append(f"afftdn=nr={nr:g}:nf={nf:.1f}:tn={tn}")
        rec["denoise"] = {"filter": "afftdn（FFTスペクトル減算）", "reduction_db": nr,
                          "noise_floor_db": round(nf, 1),
                          "noise_floor_source": "設定値" if nf_cfg is not None else "入力の実測（100ms RMS の下位10%）",
                          "track_noise": bool(tn)}
    if cfg.flag("leveling.dynaudnorm.enabled"):
        d = "leveling.dynaudnorm."
        m = db2lin(cfg.num(d + "max_gain_db"))
        t_db = cfg.num_or_auto(d + "threshold_db", -90, -10)
        auto = t_db is None
        if auto:
            # ノイズだけの区間を持ち上げない: ノイズ低減後のノイズのピーク推定 + 6 dB
            t_db = (noise_peak_db if noise_peak_db is not None else -56.0) - nr + 6.0
            t_db = max(-70.0, min(-20.0, t_db))
        f.append(f"dynaudnorm=f={int(cfg.num(d + 'frame_ms'))}:g={int(cfg.num(d + 'gauss_size'))}"
                 f":m={max(1.0, m):.4f}:p={cfg.num(d + 'peak'):g}:t={db2lin(t_db):.6f}")
        rec["dynaudnorm"] = {k: cfg.get(d + k) for k in ("frame_ms", "gauss_size", "max_gain_db", "peak")}
        rec["dynaudnorm"]["threshold_db"] = round(t_db, 1)
        rec["dynaudnorm"]["threshold_source"] = "自動（ノイズ低減後のノイズピーク推定 + 6 dB）" if auto else "設定値"
    if cfg.flag("leveling.compressor.enabled"):
        c = "leveling.compressor."
        f.append(f"acompressor=threshold={max(0.000977, db2lin(cfg.num(c + 'threshold_db'))):.6f}"
                 f":ratio={cfg.num(c + 'ratio'):g}:attack={cfg.num(c + 'attack_ms'):g}"
                 f":release={cfg.num(c + 'release_ms'):g}:knee={cfg.num(c + 'knee_db'):g}")
        rec["compressor"] = {k: cfg.get(c + k) for k in ("threshold_db", "ratio", "attack_ms", "release_ms", "knee_db")}
    return ",".join(f), rec


def render_clean_voice(ff: FFmpeg, src: Path, dst: Path, chain: str) -> None:
    ff.run(["-y", "-i", src, "-af", chain, "-c:a", "pcm_f32le", *BITEXACT, "-f", "wav", dst], "声のクリーニング")


def render_mix(ff: FFmpeg, cfg, tl: Timeline, voice: Path, voice_ch: int, voice_gain_db: float,
               assets: dict, dst: Path, sr: int) -> tuple[str, dict]:
    """声・OP・アイキャッチ・ED を配置してミックスし、未マスタリングの音源を書く。
    戻り値=(フィルタグラフ, ミックスのラウドネス測定値)。"""
    ch = int(cfg.num("output.channels"))
    lay = "mono" if ch == 1 else "stereo"
    T = int(round(tl.total * sr))
    fmt = f"aresample={sr},aformat=sample_fmts=fltp"
    inputs: list[Path] = [voice]
    g: list[str] = []

    # --- 声（セグメントごとに切り出して配置）---
    n = len(tl.segments)
    g.append(f"[0:a]{fmt},{layout_filter(voice_ch, ch)},volume={voice_gain_db:.3f}dB,asplit={n}"
             + "".join(f"[vs{i}]" for i in range(n)))
    for i, s in enumerate(tl.segments):
        g.append(f"[vs{i}]atrim=start_sample={round(s.src_start * sr)}:end_sample={round(s.src_end * sr)},"
                 f"asetpts=PTS-STARTPTS,adelay=delays={round(s.out_start * sr)}S:all=1[v{i}]")
    g.append("".join(f"[v{i}]" for i in range(n))
             + f"amix=inputs={n}:duration=longest:normalize=0,apad=whole_len={T},atrim=end_sample={T},asplit=2[voice][sc]")

    mix_inputs = ["[voice]"]

    # --- BGM（OP / ED）: 基準ラウドネスへ揃える → エンベロープ → 配置 ---
    bgm_labels = []
    for pl in (tl.opening, tl.ending):
        if pl is None:
            continue
        idx = len(inputs)
        inputs.append(assets[pl.name]["path"])
        a = assets[pl.name]
        g.append(f"[{idx}:a]{fmt},{layout_filter(a['channels'], ch)},volume={a['norm_gain_db']:.3f}dB,"
                 f"atrim=end_sample={round(pl.length * sr)},asetpts=PTS-STARTPTS,"
                 f"volume='{envelope_expr(pl.envelope)}':eval=frame,"
                 f"adelay=delays={round(pl.out_start * sr)}S:all=1[{pl.name}]")
        bgm_labels.append(f"[{pl.name}]")
    if bgm_labels:
        g.append("".join(bgm_labels) + f"amix=inputs={len(bgm_labels)}:duration=longest:normalize=0,"
                 f"apad=whole_len={T},atrim=end_sample={T}[bgm]")
        if cfg.flag("bgm.ducking.enabled"):
            d = "bgm.ducking."
            g.append(f"[bgm][sc]sidechaincompress=threshold={max(0.000977, db2lin(cfg.num(d + 'threshold_db'))):.6f}"
                     f":ratio={cfg.num(d + 'ratio'):g}:attack={cfg.num(d + 'attack_ms'):g}"
                     f":release={cfg.num(d + 'release_ms'):g}:knee={cfg.num(d + 'knee_db'):g}"
                     f":detection=rms:link=maximum[bgmd]")
            mix_inputs.append("[bgmd]")
        else:
            g.append("[sc]anullsink")
            mix_inputs.append("[bgm]")
    else:
        g.append("[sc]anullsink")

    # --- アイキャッチ ---
    if tl.jingles:
        idx = len(inputs)
        inputs.append(assets["jingle"]["path"])
        a = assets["jingle"]
        fi, fo = cfg.num("jingle.fade_in_sec"), cfg.num("jingle.fade_out_sec")
        L = tl.jingles[0].length
        gain = a["norm_gain_db"] + cfg.num("jingle.gain_db")
        chain = f"[{idx}:a]{fmt},{layout_filter(a['channels'], ch)},volume={gain:.3f}dB"
        if fi > 0:
            chain += f",afade=t=in:d={fi:g}"
        if fo > 0:
            chain += f",afade=t=out:st={max(0.0, L - fo):.4f}:d={min(fo, L):g}"
        m = len(tl.jingles)
        g.append(chain + f",asplit={m}" + "".join(f"[js{i}]" for i in range(m)))
        for i, j in enumerate(tl.jingles):
            g.append(f"[js{i}]adelay=delays={round(j.out_start * sr)}S:all=1[j{i}]")
            mix_inputs.append(f"[j{i}]")

    g.append("".join(mix_inputs) + f"amix=inputs={len(mix_inputs)}:duration=longest:normalize=0,"
             f"atrim=end_sample={T},aformat=channel_layouts={lay},asplit=2[out][m]")
    g.append("[m]ebur128=peak=true:framelog=quiet[mo]")  # 書き出しと同時にラウドネスを測る
    graph = ";\n".join(g)
    args = ["-y", "-loglevel", "info"]
    for p in inputs:
        args += ["-i", p]
    args += ["-filter_complex", graph.replace("\n", ""), "-map", "[out]", "-c:a", "pcm_f32le", *BITEXACT, "-f", "wav", dst,
             "-map", "[mo]", "-f", "null", "-"]
    step = "ミックス（OP・アイキャッチ・ED・ダッキング）"
    res = ff.run(args, step)
    return graph, parse_ebur128(res.stderr_text, step)


def master_chain(gain_db: float, ceiling_db: float, sr: int, bit_depth: int | None = None,
                 ch_in: int = 2, ch_out: int = 2) -> str:
    """ゲイン →（チャンネル変換）→ 4倍オーバーサンプリングでピーク制限（True Peak 近似）→ 出力レートへ。"""
    limit = min(1.0, max(0.0625, db2lin(ceiling_db)))
    last = f"aresample={sr}"
    if bit_depth == 16:
        last = f"aresample=osr={sr}:osf=s16:dither_method=triangular"
    return (f"volume={gain_db:.3f}dB,{layout_filter(ch_in, ch_out)},aresample={sr * 4},"
            f"alimiter=limit={limit:.6f}:attack=5:release=50:level=0:latency=1,{last}")


PCM = {16: "pcm_s16le", 24: "pcm_s24le", 32: "pcm_f32le"}


def render_master(ff: FFmpeg, src: Path, dst: Path, chain: str, bit_depth: int) -> None:
    ff.run(["-y", "-i", src, "-af", chain, "-c:a", PCM[bit_depth], *BITEXACT, "-f", "wav", dst],
           "マスタリング（WAV）")


def render_mp3(ff: FFmpeg, cfg, src: Path, dst: Path, chain: str) -> None:
    """MP3 はミックスから直接マスタリングして作る（WAV を再エンコードすると音量・ピークがずれるため）。"""
    ff.run(["-y", "-i", src, "-af", chain, "-c:a", "libmp3lame", "-b:a", str(cfg.get("output.publish.bitrate")),
            "-id3v2_version", "3", "-write_xing", "1", *BITEXACT, "-f", "mp3", dst], "マスタリング（MP3）")

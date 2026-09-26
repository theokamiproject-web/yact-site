"""処理全体の手順。"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import __version__, analyze, qc, render, report
from .errors import PodcastError
from .ffmpeg import FFmpeg
from .timeline import build as build_timeline, fmt

log = logging.getLogger("podcast")

AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".aif", ".aiff", ".ogg", ".opus", ".wma", ".caf"}
MAX_MASTER_ITER = 5


@dataclass
class Outputs:
    master: Path
    publish: Path
    report_json: Path
    report_txt: Path
    log: Path


def output_paths(cfg, input_path: Path) -> Outputs:
    out = cfg.dir("output_dir")
    stem = input_path.stem
    o = "output."
    return Outputs(
        master=out / f"{stem}{cfg.get(o + 'master_suffix')}.wav",
        publish=out / f"{stem}{cfg.get(o + 'publish_suffix')}.mp3",
        report_json=out / f"{stem}{cfg.get(o + 'report_suffix')}.json",
        report_txt=out / f"{stem}{cfg.get(o + 'report_suffix')}.txt",
        log=out / f"{stem}_process.log",
    )


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_assets(cfg) -> dict[str, Path]:
    assets_dir = cfg.dir("assets_dir")
    found, missing = {}, []
    for name in ("opening", "jingle", "ending"):
        if not cfg.flag(f"{name}.enabled"):
            continue
        if name == "jingle" and not (cfg.get("jingle.positions") or []):
            continue
        p = assets_dir / str(cfg.get(f"{name}.file"))
        if p.is_file():
            found[name] = p
        else:
            missing.append((name, p))
    if missing:
        lines = "\n".join(f"  - {n}: {p}" for n, p in missing)
        raise PodcastError(
            f"BGM ファイルが見つかりません:\n{lines}",
            step="事前チェック（BGM 素材）",
            hint="assets/ フォルダに上記の名前でファイルを置いてください。"
                 "使わない場合は config/podcast.yaml の該当項目（例 opening.enabled）を false にしてください。")
    return found


def process(cfg, input_path: Path, analyze_only: bool = False) -> dict:
    input_path = input_path.resolve()
    if not input_path.is_file():
        raise PodcastError(f"入力ファイルが見つかりません: {input_path}", step="事前チェック",
                           hint="input/ フォルダに音声を置き、ファイル名を正しく指定してください。")
    outs = output_paths(cfg, input_path)
    for p in (outs.master, outs.publish, outs.report_json, outs.report_txt, outs.log):
        if p.resolve() == input_path:
            raise PodcastError(f"出力先が入力ファイルと同じです: {p}", step="事前チェック",
                               hint="元音源を上書きしないよう、output_dir や suffix の設定を変えてください。")
    if not analyze_only and not cfg.flag("output.overwrite"):
        exist = [p for p in (outs.master, outs.publish) if p.exists()]
        if exist:
            raise PodcastError(f"出力ファイルが既にあります: {exist[0]}", step="事前チェック",
                               hint="output.overwrite を true にするか、既存ファイルを移動してください。")
    outs.master.parent.mkdir(parents=True, exist_ok=True)
    handler = _attach_log(outs.log)
    work = cfg.dir("work_dir") / input_path.stem
    try:
        return _process(cfg, input_path, outs, work, analyze_only)
    except PodcastError as e:
        if "ログファイル" in e.hint or not e.hint:
            e.hint = f"詳しい出力はログを見てください: {outs.log}"
        log.error(e.render(), extra={"file_only": True})  # 画面には cli 側で1回だけ表示
        raise
    except Exception:
        log.exception("予期しないエラー")
        raise
    finally:
        for p in (outs.master, outs.publish):  # 途中で失敗したときの書きかけファイルを消す
            tmp = p.with_name("." + p.stem + ".tmp" + p.suffix)
            if tmp.exists():
                tmp.unlink()
        if work.exists() and not cfg.flag("output.keep_work_files"):
            shutil.rmtree(work, ignore_errors=True)
            try:
                work.parent.rmdir()  # 空になった作業フォルダも消す
            except OSError:
                pass
        logging.getLogger("podcast").removeHandler(handler)
        handler.close()


def _attach_log(path: Path) -> logging.Handler:
    h = logging.FileHandler(path, mode="w", encoding="utf-8")
    h.setLevel(logging.DEBUG)
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.getLogger("podcast").addHandler(h)
    return h


def _process(cfg, input_path: Path, outs: Outputs, work: Path, analyze_only: bool) -> dict:
    started = datetime.now().astimezone()
    warnings: list[str] = []
    log.info("入力: %s", input_path)

    ff = FFmpeg(cfg.get("ffmpeg.path"), cfg.get("ffmpeg.ffprobe_path"))
    ff.check_capabilities()
    log.debug("FFmpeg: %s (%s)", ff.ffmpeg, ff.version)
    assets = {} if analyze_only else check_assets(cfg)

    # ---- 1. 入力解析 ----
    log.info("[1/7] 入力を解析しています…")
    src = analyze.analyze_file(ff, cfg, input_path, "入力解析")
    if src.integrated_lufs is None:
        raise PodcastError("入力のラウドネスを測定できません（ほぼ無音の可能性）。", step="入力解析",
                           hint="正しい収録ファイルか確認してください。")
    _log_analysis("入力", src)
    if src.clipping_suspected:
        warnings.append(f"入力にクリッピングの疑いがあります（サンプルピーク {src.sample_peak_dbfs:.2f} dBFS が"
                        f" {src.peak_count} 回）。収録時の音割れは後処理で完全には戻せません。")
    if src.sample_rate < 44100:
        warnings.append(f"入力のサンプルレートが低めです（{src.sample_rate} Hz）。")

    if analyze_only:
        return {"input": src.to_dict()}

    work.mkdir(parents=True, exist_ok=True)
    sr = int(cfg.num("output.master.sample_rate"))

    # ---- 2. 声のクリーニング ----
    log.info("[2/7] 声をクリーニングしています（ノイズ低減・ローカット・音量均し）…")
    chain, cleanup_rec = render.cleanup_chain(cfg, src.channels, src.noise_floor_db, src.noise_peak_db, sr)
    log.info("  フィルタ: %s", chain)
    voice = work / "voice_clean.wav"
    render.render_clean_voice(ff, input_path, voice, chain)
    voice_ch = 1 if (cfg.flag("input.downmix_to_mono") and src.channels > 1) else src.channels

    # ---- 3. クリーン後の無音解析とタイムライン ----
    log.info("[3/7] 無音区間を探し、OP・アイキャッチ・ED の位置を決めています…")
    clean = analyze.analyze_file(ff, cfg, voice, "クリーニング後の解析")
    asset_info = {}
    for name, p in assets.items():
        info = analyze.probe(ff, p)
        ld = analyze.loudness(ff, p, f"BGM 測定: {p.name}")
        if ld["integrated_lufs"] is None:
            raise PodcastError(f"BGM のラウドネスを測定できません（無音？）: {p}", step="BGM 測定")
        asset_info[name] = {"path": p, "duration": info["duration"], "channels": info["channels"],
                            "integrated_lufs": ld["integrated_lufs"], "true_peak_dbtp": ld["true_peak_dbtp"]}
    try:
        tl = build_timeline(cfg, clean.duration, clean.silences,
                            {k: v["duration"] for k, v in asset_info.items()})
    except ValueError as e:
        raise PodcastError(str(e), step="タイムライン計算",
                           hint="入力が無音でないか、silence.threshold_db の設定を確認してください。")
    warnings += tl.warnings
    for w in tl.warnings:
        log.warning("  %s", w)
    log.info("  本編: %s〜%s（冒頭 %.2f 秒・末尾 %.2f 秒の無音を除去）",
             fmt(tl.trim_start), fmt(tl.trim_end), tl.trim_start, clean.duration - tl.trim_end)
    for j in tl.jingles:
        log.info("  アイキャッチ: 本編 %s 地点の指定 → 無音 %s〜%s（%.2f 秒）で挿入、完成音源の %s",
                 fmt(j.target_main), fmt(j.silence.start - tl.trim_start), fmt(j.silence.end - tl.trim_start),
                 j.silence.duration, fmt(j.out_start))
    if tl.long_silences:
        warnings.append(f"本編中に {cfg.num('silence.long_silence_warn_sec'):g} 秒以上の無音が"
                        f" {len(tl.long_silences)} 箇所あります（削除していません。レポートの候補を確認してください）。")

    # ---- 4. 音量の基準合わせ ----
    target = cfg.num("loudness.target_lufs")
    # BS.1770 のゲートで前後の無音は計算から除外されるため、全体の測定値＝本編の値として使える
    vl = {"integrated_lufs": clean.integrated_lufs, "true_peak_dbtp": clean.true_peak_dbtp, "lra_lu": clean.lra_lu}
    if vl["integrated_lufs"] is None:
        raise PodcastError("クリーニング後の声のラウドネスを測定できません。", step="声のラウドネス測定")
    voice_gain = target - vl["integrated_lufs"]
    ref = cfg.get("bgm.reference_lufs")
    ref = target if ref is None else float(ref)
    for a in asset_info.values():
        a["norm_gain_db"] = ref - a["integrated_lufs"]

    # ---- 5. ミックス ----
    log.info("[4/7] ミックスしています（ダッキング含む）…")
    premix = work / "premix.wav"
    graph, pm = render.render_mix(ff, cfg, tl, voice, voice_ch, voice_gain, asset_info, premix, sr)
    if pm["integrated_lufs"] is None:
        raise PodcastError("ミックスのラウドネスを測定できません。", step="ミックス")

    # ---- 6. マスタリング + 書き出し ----
    log.info("[5/7] マスタリングして書き出しています…")
    tp_max = cfg.num("loudness.true_peak_max_dbtp")
    ceiling0 = tp_max - cfg.num("loudness.limiter_margin_db")
    bit = int(cfg.get("output.master.bit_depth"))
    out_ch = int(cfg.num("output.channels"))
    pub_ch = int(cfg.num("output.publish.channels"))
    pub_sr = int(cfg.num("output.publish.sample_rate"))
    tmp_master = outs.master.with_name("." + outs.master.stem + ".tmp.wav")
    tmp_mp3 = outs.publish.with_name("." + outs.publish.stem + ".tmp.mp3")

    def wav(gain, ceiling):
        render.render_master(ff, premix, tmp_master, render.master_chain(gain, ceiling, sr, bit, out_ch, out_ch), bit)
        return tmp_master

    def mp3(gain, ceiling):
        render.render_mp3(ff, cfg, premix, tmp_mp3, render.master_chain(gain, ceiling, pub_sr, None, out_ch, pub_ch))
        return tmp_mp3

    gain0 = target - pm["integrated_lufs"]
    acc = cfg.num("loudness.accuracy_lu")
    wav_res = _master_loop(ff, wav, "WAV", gain0, ceiling0, target, tp_max, acc)
    # ステレオ→モノラルは BS.1770 上 約 -3 LU になるので初期値で補正（最終値はループで実測合わせ）
    mono_comp = 3.01 if (out_ch == 2 and pub_ch == 1) else 0.0
    mp3_res = _master_loop(ff, mp3, "MP3", wav_res["gain_db"] + mono_comp, wav_res["limiter_ceiling_db"],
                           target, tp_max, acc)
    limiter_gr = (pm["true_peak_dbtp"] or 0) + wav_res["gain_db"] - wav_res["limiter_ceiling_db"]
    if limiter_gr > 6:
        warnings.append(f"リミッタで最大約 {limiter_gr:.1f} dB 圧縮しています。ピークの大きい音（笑い声・BGM）が"
                        "潰れていないか試聴してください。target_lufs を下げると緩和します。")

    # ---- 7. 品質チェック ----
    log.info("[6/7] 完成ファイルを再解析して品質チェックしています…")
    # 無音しきい値は「クリーニング後の声で使った値」を完成音源の音量に換算して使う（WAV/MP3 で判定を揃える）
    th_m = clean.silence_threshold_db + voice_gain + wav_res["gain_db"]
    th_p = clean.silence_threshold_db + voice_gain + mp3_res["gain_db"] - mono_comp  # モノラル補正分は振幅ではない
    qa_master, checks_m, long_m = qc.check_file(ff, cfg, tmp_master, "master", tl.total, 0.05, th_m,
                                                wav_res["measured"])
    qa_pub, checks_p, _ = qc.check_file(ff, cfg, tmp_mp3, "publish", tl.total, 0.1, th_p, mp3_res["measured"])
    checks = checks_m + checks_p
    for c in checks:
        if not c["ok"]:
            tag = "NG" if c["severity"] == "error" else "注意"
            warnings.append(f"品質チェック {tag} [{c['file']}] {c['check']}: {c['value']}（基準 {c['expected']}）")

    os.replace(tmp_master, outs.master)
    os.replace(tmp_mp3, outs.publish)

    # ---- 8. レポート ----
    log.info("[7/7] レポートを書き出しています…")
    data = report.build(
        cfg=cfg, version=__version__, ff=ff, started=started, input_path=input_path,
        input_sha=sha256(input_path), outs=outs, src=src, clean=clean, chain=chain, cleanup_rec=cleanup_rec,
        tl=tl, voice_loud=vl, voice_gain=voice_gain, asset_info=asset_info, premix_loud=pm,
        mastering={"master": wav_res, "publish": mp3_res}, graph=graph, qa_master=qa_master, qa_pub=qa_pub,
        checks=checks,
        long_master=long_m, warnings=warnings, limiter_gr=limiter_gr)
    report.write(data, outs.report_json, outs.report_txt)
    for w in warnings:
        log.warning("[警告] %s", w)
    log.info("完了: %s", outs.master)
    log.info("      %s", outs.publish)
    log.info("      %s", outs.report_json)
    return data


def _master_loop(ff, render_fn, label, gain, ceiling, target, tp_max, accuracy) -> dict:
    """書き出す→実測→ゲインとリミッタ上限を補正、を目標に入るまで繰り返す。"""
    iterations = []
    for _ in range(MAX_MASTER_ITER):
        path = render_fn(gain, ceiling)
        m = analyze.loudness(ff, path, f"マスタリング結果の測定（{label}）")
        if m["integrated_lufs"] is None or m["true_peak_dbtp"] is None:
            raise PodcastError(f"{label} のラウドネスを測定できません。", step="マスタリング")
        iterations.append({"gain_db": round(gain, 3), "limiter_ceiling_db": round(ceiling, 3),
                           "integrated_lufs": m["integrated_lufs"], "true_peak_dbtp": m["true_peak_dbtp"]})
        log.debug("  %s 試行 %d: gain=%.2f dB ceiling=%.2f → I=%.2f TP=%.2f", label, len(iterations),
                  gain, ceiling, m["integrated_lufs"], m["true_peak_dbtp"])
        ok_i = abs(m["integrated_lufs"] - target) <= accuracy
        ok_tp = m["true_peak_dbtp"] <= tp_max
        if ok_i and ok_tp:
            break
        if not ok_tp:
            ceiling -= (m["true_peak_dbtp"] - tp_max) + 0.1
        if not ok_i:
            gain += target - m["integrated_lufs"]
    last = iterations[-1]
    measured = dict(m)  # 最後に書き出したファイル（=完成ファイル）の実測値
    log.info("  %s: %.2f LUFS / True Peak %.2f dBTP（ゲイン %+.2f dB, リミッタ上限 %.2f dBFS, 試行 %d 回）",
             label, last["integrated_lufs"], last["true_peak_dbtp"], last["gain_db"],
             last["limiter_ceiling_db"], len(iterations))
    return {"gain_db": last["gain_db"], "limiter_ceiling_db": last["limiter_ceiling_db"], "iterations": iterations,
            "measured": measured}


def _log_analysis(label: str, a) -> None:
    log.info("  %s: 長さ %s / %d Hz / %d ch / %.1f LUFS / True Peak %.1f dBTP / LRA %.1f LU",
             label, fmt(a.duration), a.sample_rate, a.channels, a.integrated_lufs,
             a.true_peak_dbtp, a.lra_lu or 0)
    log.info("  ノイズフロア推定 %.1f dBFS / 声の大きい部分 %.1f dBFS / 無音判定しきい値 %.1f dB / 無音 %d 箇所",
             a.noise_floor_db or float("nan"), a.speech_level_db or float("nan"),
             a.silence_threshold_db, len(a.silences))

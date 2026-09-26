"""配置計算（FFmpeg に依存しない純粋な計算。単体テスト対象）。

時間の呼び方:
  source 時刻 … クリーニング済み音声（=元音源と同じ時間軸）上の秒
  main 時刻   … 冒頭無音を除いた本編の先頭を 0 とした秒（config の minutes/percent の基準）
  out 時刻    … 完成音源上の秒
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .analyze import Silence

Point = tuple  # (time_sec, gain_db or None=無音)


@dataclass
class Segment:
    src_start: float
    src_end: float
    out_start: float

    @property
    def duration(self) -> float:
        return self.src_end - self.src_start


@dataclass
class BgmPlacement:
    name: str
    out_start: float
    length: float
    envelope: list  # [(local_t, gain_db|None)]
    asset_duration: float

    @property
    def out_end(self) -> float:
        return self.out_start + self.length


@dataclass
class JinglePlacement:
    request: dict
    target_main: float
    cut_src: float
    silence: Silence
    out_start: float
    length: float


@dataclass
class Timeline:
    trim_start: float
    trim_end: float
    segments: list[Segment]
    jingles: list[JinglePlacement]
    opening: BgmPlacement | None
    ending: BgmPlacement | None
    voice_out_start: float
    voice_out_end: float
    total: float
    long_silences: list[dict]
    warnings: list[str] = field(default_factory=list)

    @property
    def main_duration(self) -> float:
        return self.trim_end - self.trim_start

    def src_to_out(self, t: float) -> float | None:
        for s in self.segments:
            if s.src_start <= t <= s.src_end:
                return s.out_start + (t - s.src_start)
        return None


def compute_trim(duration: float, silences: list[Silence], cfg) -> tuple[float, float]:
    start, end = 0.0, duration
    eps = 0.05
    if cfg.flag("silence.trim_head") and silences and silences[0].start <= eps:
        start = max(0.0, silences[0].end - cfg.num("silence.keep_head_sec"))
    if cfg.flag("silence.trim_tail") and silences and silences[-1].end >= duration - eps:
        end = min(duration, silences[-1].start + cfg.num("silence.keep_tail_sec"))
    if end - start < 1.0:
        raise ValueError("声がほとんど検出されませんでした（全体が無音と判定）。")
    return start, end


def choose_cut(target_src: float, silences: list[Silence], cfg, lo: float, hi: float) -> Silence | None:
    """指定地点付近で、会話を切らずに済む無音を選ぶ。"""
    min_sil = cfg.num("jingle.min_silence_sec")
    window = cfg.num("jingle.search_window_sec")
    weight = cfg.num("jingle.prefer_longer_weight")
    cands = [s for s in silences if s.duration >= min_sil and lo <= (s.start + s.end) / 2 <= hi]

    def score(s: Silence) -> float:
        return abs((s.start + s.end) / 2 - target_src) - weight * min(s.duration, 3.0)

    inside = [s for s in cands if abs((s.start + s.end) / 2 - target_src) <= window]
    if inside:
        return min(inside, key=score)
    if cfg.get("jingle.on_no_silence") == "nearest" and cands:
        return min(cands, key=lambda s: abs((s.start + s.end) / 2 - target_src))
    return None


def truncate_envelope(points: list, length: float, fade: float) -> list:
    """素材が短いとき、素材の終わりでフェードアウトが終わるよう切り詰める。"""
    fade = min(fade, length)
    cut = length - fade
    out = [p for p in points if p[0] < cut]
    out.append((cut, gain_at(points, cut)))
    out.append((length, None))
    return out


def gain_at(points: list, t: float) -> float | None:
    """エンベロープ上の t 秒の値（振幅で線形補間し dB で返す）。"""
    amp = _amp_at(points, t)
    return None if amp <= 0 else 20 * math.log10(amp)


def db_to_amp(db: float | None) -> float:
    return 0.0 if db is None else 10 ** (db / 20)


def _amp_at(points: list, t: float) -> float:
    if t <= points[0][0]:
        return db_to_amp(points[0][1])
    for (t0, g0), (t1, g1) in zip(points, points[1:]):
        if t0 <= t <= t1:
            a0, a1 = db_to_amp(g0), db_to_amp(g1)
            return a0 if t1 == t0 else a0 + (a1 - a0) * (t - t0) / (t1 - t0)
    return db_to_amp(points[-1][1])


def envelope_expr(points: list) -> str:
    """volume フィルタ用の式（振幅の区分線形）。カンマを含むので呼び出し側で引用する。"""
    pts = [(float(t), db_to_amp(g)) for t, g in points]
    expr = f"{pts[-1][1]:.6f}"
    for (t0, a0), (t1, a1) in reversed(list(zip(pts, pts[1:]))):
        if t1 <= t0:
            continue
        seg = f"{a0:.6f}+({a1 - a0:.6f})*(t-{t0:.4f})/{t1 - t0:.4f}"
        expr = f"if(lt(t,{t1:.4f}),{seg},{expr})"
    return f"if(lt(t,{pts[0][0]:.4f}),{pts[0][1]:.6f},{expr})"


def build(cfg, voice_duration: float, silences: list[Silence], asset_durations: dict) -> Timeline:
    warnings: list[str] = []
    trim_start, trim_end = compute_trim(voice_duration, silences, cfg)
    main_dur = trim_end - trim_start
    if cfg.flag("silence.trim_head") and trim_start == 0.0:
        warnings.append("冒頭の無音を検出できなかったため、冒頭はそのままです（ノイズが大きい場合に起こります）。")
    if cfg.flag("silence.trim_tail") and trim_end == voice_duration:
        warnings.append("末尾の無音を検出できなかったため、末尾はそのままです（ノイズが大きい場合に起こります）。")

    # 本編内部の無音（冒頭・末尾のトリム対象を除く）
    inner = [s for s in silences if s.start > trim_start + 0.01 and s.end < trim_end - 0.01]

    op_on = cfg.flag("opening.enabled")
    voice_out_start = cfg.num("opening.solo_sec") if op_on else 0.0

    # ---- アイキャッチ挿入点 ----
    cuts: list[tuple[dict, float, float, Silence]] = []  # (設定行, 指定main秒, 切る位置src秒, 無音)
    if cfg.flag("jingle.enabled"):
        positions = cfg.get("jingle.positions") or []
        # OP の BGM と ED の BGM に重ならない範囲に限定
        lo = trim_start + (cfg.num("opening.bed_sec") + cfg.num("opening.fade_out_sec") if op_on else 0) + 1.0
        hi = trim_end - (cfg.num("ending.lead_in_sec") if cfg.flag("ending.enabled") else 0) - 1.0
        min_gap = cfg.num("jingle.min_distance_sec")
        for req in positions:
            key, val = next(iter(req.items()))
            target_main = {"minutes": val * 60.0, "seconds": float(val), "percent": main_dur * val / 100.0}[key]
            label = f"{key}: {val}（本編 {fmt(target_main)} 地点）"
            if target_main >= main_dur:
                warnings.append(f"アイキャッチ {label} は本編の長さ {fmt(main_dur)} を超えるため挿入しません。")
                continue
            sil = choose_cut(trim_start + target_main, inner, cfg, lo, hi)
            if sil is None:
                warnings.append(f"アイキャッチ {label}: 前後 {cfg.num('jingle.search_window_sec'):.0f} 秒以内に"
                                f" {cfg.num('jingle.min_silence_sec')} 秒以上の無音がないため挿入しません（会話を切らないため）。")
                continue
            cut = (sil.start + sil.end) / 2
            if any(abs(cut - c[2]) < min_gap for c in cuts):
                warnings.append(f"アイキャッチ {label}: 他のアイキャッチと {min_gap:.0f} 秒以内のため挿入しません。")
                continue
            cuts.append((req, target_main, cut, sil))
        cuts.sort(key=lambda c: c[2])

    # ---- 声セグメントとアイキャッチの配置 ----
    jingle_len = asset_durations.get("jingle", 0.0)
    gap_b, gap_a = cfg.num("jingle.gap_before_sec"), cfg.num("jingle.gap_after_sec")
    segments, jingles = [], []
    cursor, src = voice_out_start, trim_start
    for req, target_main, cut, sil in cuts:
        segments.append(Segment(src, cut, cursor))
        cursor += cut - src + gap_b
        jingles.append(JinglePlacement(req, target_main, cut, sil, cursor, jingle_len))
        cursor += jingle_len + gap_a
        src = cut
    segments.append(Segment(src, trim_end, cursor))
    voice_out_end = cursor + (trim_end - src)
    total = voice_out_end

    # ---- OP ----
    opening = None
    if op_on:
        solo, tr = cfg.num("opening.solo_sec"), cfg.num("opening.duck_transition_sec")
        fi, bed, fo = cfg.num("opening.fade_in_sec"), cfg.num("opening.bed_sec"), cfg.num("opening.fade_out_sec")
        g_solo, g_bed = cfg.num("opening.solo_gain_db"), cfg.num("opening.bed_gain_db")
        pts = []
        if fi > 0:
            pts.append((0.0, None))
        pts += [(fi, g_solo), (solo - tr, g_solo), (solo, g_bed), (solo + bed, g_bed), (solo + bed + fo, None)]
        pts = _dedupe(pts)
        length = solo + bed + fo
        adur = asset_durations["opening"]
        if adur < length:
            warnings.append(f"opening の BGM（{adur:.1f} 秒）が設定上の必要長 {length:.1f} 秒より短いため、"
                            "素材の終わりでフェードアウトします。")
            if adur < solo:
                warnings.append("opening の BGM が solo_sec より短く、声が始まる前に BGM が終わります。")
            pts = truncate_envelope(pts, adur, fo)
            length = adur
        opening = BgmPlacement("opening", 0.0, length, pts, adur)
        total = max(total, length)
        if length > voice_out_end:
            warnings.append("本編が短く、OP の BGM が本編より長く続きます。")

    # ---- ED ----
    ending = None
    if cfg.flag("ending.enabled"):
        lead, fi = cfg.num("ending.lead_in_sec"), cfg.num("ending.fade_in_sec")
        rise, tail, fo = cfg.num("ending.rise_sec"), cfg.num("ending.tail_sec"), cfg.num("ending.fade_out_sec")
        g_bed, g_solo = cfg.num("ending.bed_gain_db"), cfg.num("ending.solo_gain_db")
        start = voice_out_end - lead
        floor = max(voice_out_start, jingles[-1].out_start + jingles[-1].length if jingles else 0.0,
                    opening.out_end if opening else 0.0)
        if start < floor:
            warnings.append(f"ED の開始位置を前の要素と重ならないよう {fmt(start)} → {fmt(floor)} に調整しました。")
            lead = max(0.0, voice_out_end - floor)
            start = voice_out_end - lead
        fi = min(fi, lead)
        pts = _dedupe([(0.0, None), (fi, g_bed), (lead, g_bed), (lead + rise, g_solo),
                       (lead + tail, g_solo), (lead + tail + fo, None)]) if fi > 0 else \
            _dedupe([(0.0, g_bed), (lead, g_bed), (lead + rise, g_solo), (lead + tail, g_solo), (lead + tail + fo, None)])
        length = lead + tail + fo
        adur = asset_durations["ending"]
        if adur < length:
            warnings.append(f"ending の BGM（{adur:.1f} 秒）が設定上の必要長 {length:.1f} 秒より短いため、"
                            "素材の終わりでフェードアウトします。")
            pts = truncate_envelope(pts, adur, fo)
            length = adur
        ending = BgmPlacement("ending", start, length, pts, adur)
        total = max(total, ending.out_end)

    tl = Timeline(trim_start, trim_end, segments, jingles, opening, ending,
                  voice_out_start, voice_out_end, total, [], warnings)

    # ---- 異常に長い無音（削除せず候補として報告） ----
    lim = cfg.num("silence.long_silence_warn_sec")
    used = {id(j.silence) for j in jingles}
    for s in inner:
        if s.duration >= lim and id(s) not in used:
            tl.long_silences.append({
                "main_start": round(s.start - trim_start, 2), "duration": round(s.duration, 2),
                "output_start": round(tl.src_to_out(s.start) or 0.0, 2)})
    return tl


def _dedupe(points: list) -> list:
    out = []
    for t, g in points:
        if out and t <= out[-1][0]:
            out[-1] = (out[-1][0], g)
        else:
            out.append((t, g))
    return out


def fmt(sec: float) -> str:
    sec = max(0.0, sec)
    m, s = divmod(sec, 60)
    h, m = divmod(int(m), 60)
    return f"{h}:{m:02d}:{s:05.2f}" if h else f"{m:02d}:{s:05.2f}"

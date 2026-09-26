"""音声の解析（測定のみ。音は変更しない）。"""
from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .errors import PodcastError
from .ffmpeg import FFmpeg

PROFILE_RATE = 16000       # ノイズフロア推定用に下げるサンプルレート
PROFILE_WINDOW_SEC = 0.1   # RMS を測る窓


@dataclass
class Silence:
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start

    def to_dict(self) -> dict:
        return {"start": round(self.start, 3), "end": round(self.end, 3), "duration": round(self.duration, 3)}


@dataclass
class Analysis:
    path: str
    duration: float
    sample_rate: int
    channels: int
    codec: str
    integrated_lufs: float | None
    true_peak_dbtp: float | None
    lra_lu: float | None
    sample_peak_dbfs: float | None
    peak_count: int | None
    clipping_suspected: bool
    noise_floor_db: float | None
    noise_peak_db: float | None
    speech_level_db: float | None
    silence_threshold_db: float | None
    silences: list[Silence] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["silences"] = [s.to_dict() for s in self.silences]
        for k, v in d.items():
            if isinstance(v, float):
                d[k] = round(v, 2) if math.isfinite(v) else None
        return d


def probe(ff: FFmpeg, path: Path) -> dict:
    info = ff.probe(path)
    streams = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    if not streams:
        raise PodcastError(f"音声トラックが見つかりません: {path}", step="ファイル情報の取得",
                           hint="WAV / MP3 / M4A などの音声ファイルを指定してください。")
    s = streams[0]
    dur = s.get("duration") or info.get("format", {}).get("duration")
    try:
        dur = float(dur)
    except (TypeError, ValueError):
        raise PodcastError(f"長さを取得できません: {path}", step="ファイル情報の取得")
    if dur <= 0:
        raise PodcastError(f"音声の長さが 0 秒です: {path}", step="ファイル情報の取得")
    return {
        "duration": dur,
        "sample_rate": int(s.get("sample_rate", 0)),
        "channels": int(s.get("channels", 0)),
        "codec": s.get("codec_name", "?"),
    }


def loudness(ff: FFmpeg, path: Path, step: str, prefilter: str = "") -> dict:
    """EBU R128 / ITU BS.1770 の Integrated / True Peak(4倍オーバーサンプル) / LRA。"""
    af = (prefilter + "," if prefilter else "") + "ebur128=peak=true:framelog=quiet"
    res = ff.run(["-loglevel", "info", "-i", path, "-af", af, "-f", "null", "-"], step)
    return parse_ebur128(res.stderr_text, step)


def parse_ebur128(text: str, step: str) -> dict:
    idx = text.rfind("Summary:")
    if idx < 0:
        raise PodcastError("ラウドネス測定結果を読み取れませんでした。", step=step)
    t = text[idx:]

    def grab(pat):
        m = re.search(pat, t)
        return _to_float(m.group(1)) if m else None
    i = grab(r"\bI:\s*(\S+)\s*LUFS")
    if i is not None and i <= -69.9:  # ゲートで全区間除外 = ほぼ無音
        i = None
    tp_idx = t.find("True peak:")
    tp = None
    if tp_idx >= 0:
        m = re.search(r"Peak:\s*(\S+)\s*dBFS", t[tp_idx:])
        tp = _to_float(m.group(1)) if m else None
    return {"integrated_lufs": i, "true_peak_dbtp": tp, "lra_lu": grab(r"LRA:\s*(\S+)\s*LU\b")}


def level_profile(ff: FFmpeg, path: Path, step: str) -> tuple[list[float], list[float]]:
    """100ms ごとの RMS と ピーク(dBFS) の列。ノイズフロア・無音しきい値・声の大きさの推定に使う。"""
    n = int(PROFILE_RATE * PROFILE_WINDOW_SEC)
    af = (f"aresample={PROFILE_RATE},aformat=channel_layouts=mono,asetnsamples=n={n}:p=0,"
          "astats=metadata=1:reset=1:measure_perchannel=none:measure_overall=RMS_level+Peak_level,"
          "ametadata=mode=print")
    res = ff.run(["-loglevel", "info", "-i", path, "-af", af, "-f", "null", "-"], step)
    rms, peak = [], []
    for m in re.finditer(r"lavfi\.astats\.Overall\.(RMS|Peak)_level=(\S+)", res.stderr_text):
        v = _to_float(m.group(2))
        (rms if m.group(1) == "RMS" else peak).append(float("-inf") if v is None else v)
    return rms, peak


def percentile(values: list[float], q: float) -> float | None:
    v = sorted(x for x in values if math.isfinite(x))
    if not v:
        return None
    idx = min(len(v) - 1, max(0, int(round(q / 100 * (len(v) - 1)))))
    return v[idx]


def detect(ff: FFmpeg, path: Path, threshold_db: float, min_dur: float, step: str,
           with_loudness: bool = True) -> dict:
    """1回のデコードで silencedetect・astats・ebur128(任意) をまとめて測る。"""
    parts = ["[0:a]asplit=2[x][y]",
             f"[y]aformat=channel_layouts=mono,silencedetect=noise={threshold_db:.1f}dB:d={min_dur}[s]"]
    xchain = "[x]astats=measure_perchannel=none:measure_overall=Peak_level+Peak_count"
    if with_loudness:
        xchain += ",ebur128=peak=true:framelog=quiet"
    parts.insert(1, xchain + "[l]")
    res = ff.run(["-loglevel", "info", "-i", path, "-filter_complex", ";".join(parts),
                  "-map", "[l]", "-f", "null", "-", "-map", "[s]", "-f", "null", "-"], step)
    text = res.stderr_text
    out = {"silences": _parse_silences(text)}
    pk = re.findall(r"Peak level dB:\s*(\S+)", text)
    pc = re.findall(r"Peak count:\s*(\S+)", text)
    out["sample_peak_dbfs"] = _to_float(pk[-1]) if pk else None
    out["peak_count"] = int(float(pc[-1])) if pc and _to_float(pc[-1]) is not None else None
    if with_loudness:
        out.update(parse_ebur128(text, step))
    return out


def _to_float(s: str) -> float | None:
    try:
        v = float(s)
        return v if math.isfinite(v) else (v if v < 0 else None)
    except ValueError:
        return None


def _parse_silences(text: str) -> list[Silence]:
    res: list[Silence] = []
    start = None
    for m in re.finditer(r"silence_(start|end):\s*(-?[\d.]+)", text):
        kind, t = m.group(1), max(0.0, float(m.group(2)))
        if kind == "start":
            start = t
        elif start is not None:
            res.append(Silence(start, t))
            start = None
    if start is not None:
        res.append(Silence(start, float("inf")))  # 末尾まで無音（呼び出し側で長さに置換）
    return res


def silence_threshold(cfg, noise_peak: float | None, speech_rms: float | None) -> float:
    """無音判定しきい値。silencedetect はサンプル振幅で判定するため、ノイズの「ピーク」を基準にする。"""
    fixed = cfg.num_or_auto("silence.threshold_db", -90, -10)
    if fixed is not None:
        return fixed
    lo, hi = cfg.num("silence.auto_min_db"), cfg.num("silence.auto_max_db")
    if noise_peak is None:
        return lo
    th = noise_peak + cfg.num("silence.auto_margin_db")
    if speech_rms is not None:
        th = min(th, speech_rms - 10)  # 声そのものを無音と誤判定しない
    return max(lo, min(hi, th))


def analyze_file(ff: FFmpeg, cfg, path: Path, label: str, with_loudness: bool = True,
                 threshold_db: float | None = None, known_loudness: dict | None = None) -> Analysis:
    """threshold_db を渡すと音量分布の測定を省略、known_loudness（同じファイルの測定済み値）を渡すと
    ラウドネス測定を省略する（長尺での処理時間短縮）。"""
    info = probe(ff, path)
    nf = npk = sp = None
    if threshold_db is None:
        rms, peak = level_profile(ff, path, f"{label}: 音量分布")
        nf, npk, sp = percentile(rms, 10), percentile(peak, 10), percentile(rms, 95)
        th = silence_threshold(cfg, npk, sp)
    else:
        th = threshold_db
    if known_loudness is not None:
        with_loudness = False
    d = detect(ff, path, th, cfg.num("silence.min_duration_sec"), f"{label}: 無音・ピーク・ラウドネス", with_loudness)
    if known_loudness is not None:
        d.update({k: known_loudness.get(k) for k in ("integrated_lufs", "true_peak_dbtp", "lra_lu")})
    sil = [Silence(s.start, min(s.end, info["duration"])) for s in d["silences"]]
    peak = d.get("sample_peak_dbfs")
    clip = peak is not None and peak >= -0.1 and (d.get("peak_count") or 0) >= 3
    return Analysis(
        path=str(path), duration=info["duration"], sample_rate=info["sample_rate"],
        channels=info["channels"], codec=info["codec"],
        integrated_lufs=d.get("integrated_lufs"), true_peak_dbtp=d.get("true_peak_dbtp"),
        lra_lu=d.get("lra_lu"), sample_peak_dbfs=peak, peak_count=d.get("peak_count"),
        clipping_suspected=clip, noise_floor_db=nf, noise_peak_db=npk, speech_level_db=sp,
        silence_threshold_db=th, silences=sil)

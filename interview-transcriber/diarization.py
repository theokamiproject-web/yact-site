"""話者分離（WhisperX経由の pyannote）と、話者名の解決。

pyannote のモデルは Hugging Face 上でゲート付き。HF_TOKEN と利用条件への同意が必要
（README参照）。取得できない場合は話者なしで処理を続行できるよう、呼び出し側で捕捉する。
"""
from __future__ import annotations

import string
from pathlib import Path

import yaml

UNKNOWN_SPEAKER = "話者不明"


def run_diarization(wav: Path, device: str, hf_token: str | None,
                    num_speakers: int | None = None, min_speakers: int | None = None,
                    max_speakers: int | None = None, model_name: str | None = None) -> list[dict]:
    """[{start, end, speaker}] を返す。"""
    if not hf_token:
        raise RuntimeError("HF_TOKEN が未設定です（.env に設定してください）。")
    import whisperx
    try:
        from whisperx.diarize import DiarizationPipeline
    except ImportError:  # 旧バージョン
        DiarizationPipeline = whisperx.DiarizationPipeline
    try:
        pipe = DiarizationPipeline(model_name=model_name, token=hf_token, device=device)
    except TypeError:
        pipe = DiarizationPipeline(model_name=model_name, use_auth_token=hf_token, device=device)
    audio = whisperx.load_audio(str(wav))
    df = pipe(audio, num_speakers=num_speakers, min_speakers=min_speakers, max_speakers=max_speakers)
    if isinstance(df, tuple):
        df = df[0]
    return [{"start": float(r.start), "end": float(r.end), "speaker": str(r.speaker)}
            for r in df.itertuples()]


def load_speakers(path: Path | None) -> dict[str, str]:
    """speakers.yaml → {SPEAKER_00: 名前}。空・未指定なら {}。"""
    if not path or not Path(path).exists():
        return {}
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: マッピング形式（SPEAKER_00: 名前）で書いてください")
    return {str(k): str(v) for k, v in data.items() if v not in (None, "")}


def speaker_labels(speaker_ids: list[str], mapping: dict[str, str]) -> dict[str, str]:
    """SPEAKER_xx → 表示名。未設定は 話者A, 話者B... （ID順）。"""
    labels: dict[str, str] = {}
    unnamed = [s for s in sorted(set(speaker_ids)) if s not in mapping]
    for i, sid in enumerate(unnamed):
        suffix = string.ascii_uppercase[i] if i < 26 else str(i + 1)
        labels[sid] = f"話者{suffix}"
    labels.update({s: mapping[s] for s in set(speaker_ids) if s in mapping})
    return labels


def overlap_by_speaker(diar: list[dict], start: float, end: float) -> dict[str, float]:
    out: dict[str, float] = {}
    for d in diar:
        if d["end"] <= start:
            continue
        if d["start"] >= end:
            break
        ov = min(end, d["end"]) - max(start, d["start"])
        if ov > 0:
            out[d["speaker"]] = out.get(d["speaker"], 0.0) + ov
    return out

"""話者分離（WhisperX経由の pyannote）と、話者名の解決。

pyannote のモデルは Hugging Face 上でゲート付き。HF_TOKEN と利用条件への同意が必要
（README参照）。取得できない場合は話者なしで処理を続行できるよう、呼び出し側で捕捉する。
"""
from __future__ import annotations

import string
from pathlib import Path

import yaml

UNKNOWN_SPEAKER = "話者不明"
DEFAULT_DIARIZATION_MODEL = "pyannote/speaker-diarization-community-1"


def run_diarization(wav: Path, device: str, hf_token: str | None,
                    num_speakers: int | None = None, min_speakers: int | None = None,
                    max_speakers: int | None = None, model_name: str | None = None) -> list[dict]:
    """[{start, end, speaker}] を返す。既定モデルは pyannote/speaker-diarization-community-1。"""
    model_name = model_name or DEFAULT_DIARIZATION_MODEL
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


def _load_pipeline(device: str, hf_token: str | None, model_name: str):
    if not hf_token:
        raise RuntimeError("HF_TOKEN が未設定です（.env に設定してください）。")
    import whisperx
    try:
        from whisperx.diarize import DiarizationPipeline
    except ImportError:  # 旧バージョン
        DiarizationPipeline = whisperx.DiarizationPipeline
    try:
        return DiarizationPipeline(model_name=model_name, token=hf_token, device=device)
    except TypeError:
        return DiarizationPipeline(model_name=model_name, use_auth_token=hf_token, device=device)


def make_chunk_diarizer(device: str, hf_token: str | None, model_name: str):
    """チャンク用: パイプラインを1回だけ読み込み、(音声, 開始秒, 終了秒, max_speakers) → (segments, 埋め込み|None) を返す関数。"""
    pipe = _load_pipeline(device, hf_token, model_name)

    def run(audio, start, end, max_speakers):
        emb = None
        try:
            out = pipe(audio, max_speakers=max_speakers, return_embeddings=True)
        except TypeError:
            out = pipe(audio, max_speakers=max_speakers)
        if isinstance(out, tuple):
            df, emb = out[0], out[1]
        else:
            df = out
        segs = [{"start": float(r.start), "end": float(r.end), "speaker": str(r.speaker)} for r in df.itertuples()]
        return segs, (emb or None)

    return run


def diarize(wav: Path, device: str, hf_token: str | None, num_speakers: int | None, min_speakers: int | None,
            max_speakers: int | None, model_name: str | None, *, duration: float | None, chunk_dir: Path,
            fingerprint: str | None, auto_threshold: float | None = None, chunk_sec: float | None = None,
            overlap_sec: float | None = None) -> tuple[list[dict], dict | None]:
    """標準は従来どおり一括の話者分離。音声が auto_threshold 秒（既定15分）より長いときだけ、再開可能なチャンク方式にする。
    戻り値: (segments, チャンク方式の統合レポート|None)。"""
    import diarization_chunks as dc
    model_name = model_name or DEFAULT_DIARIZATION_MODEL
    thr = dc.AUTO_THRESHOLD_SEC if auto_threshold is None else auto_threshold
    if not duration or duration <= thr:
        return run_diarization(wav, device, hf_token, num_speakers, min_speakers, max_speakers, model_name), None
    import whisperx
    dc.log(f"[話者分離] 長い音声（{duration / 60:.1f}分 > {thr / 60:.0f}分）のため、再開可能なチャンク方式で実行します"
           f"（{(chunk_sec or dc.CHUNK_SEC) / 60:.1f}分×重なり{overlap_sec or dc.OVERLAP_SEC:.0f}秒）")
    if num_speakers or min_speakers:
        dc.log("[話者分離] 注意: チャンク方式では --num-speakers / --min-speakers はチャンクに渡しません（max のみ上限として使用）")
    audio = whisperx.load_audio(str(wav))
    fn = make_chunk_diarizer(device, hf_token, model_name)
    return dc.run_chunked(audio, duration, fn, chunk_dir, fingerprint=fingerprint, model=model_name, max_speakers=max_speakers,
                          num_speakers=num_speakers, min_speakers=min_speakers, chunk_sec=chunk_sec or dc.CHUNK_SEC,
                          overlap_sec=overlap_sec or dc.OVERLAP_SEC)


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

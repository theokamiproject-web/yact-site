"""音声前処理（ffmpeg）と WhisperX 呼び出し（文字起こし・alignment）。

WhisperX は依存ライブラリとして呼ぶだけで、改造しない。各段階の結果は
cache/<stem>/ に個別保存し、再実行時は存在すれば再利用する。
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

SUPPORTED_EXT = {".mp3", ".wav", ".m4a", ".mp4", ".aac", ".flac", ".ogg", ".mov", ".webm", ".mkv"}


def log(msg: str):
    print(msg, file=sys.stderr, flush=True)


@dataclass
class ASRConfig:
    model: str = "large-v3"
    language: str = "ja"
    device: str = "auto"
    compute_type: str = "auto"
    batch_size: int = 8
    initial_prompt: str | None = None
    hf_token: str | None = None
    normalize: bool = True
    extra: dict = field(default_factory=dict)


# ------------------------------------------------------------------ ASR初期プロンプト
# 標準では initial_prompt を渡さない。明示指定したときだけ、次のどちらか一方を渡す:
#   --dictionary-prompt : dictionary.yaml の語から作った文（辞書プロンプト）
#   --neutral-prompt    : 下の中立プロンプト
# 2つは連結せず、同時指定はエラー（曖昧な動作にしない）。
#
# 中立プロンプトは、内容（話題・固有名詞・辞書語）に依存しない句読点つきの自然な文の見本。
# Whisperの initial_prompt は「直前の書き起こし」として扱われ、句読点の有無を引き継ぐ。
# 実測（Track-78・Track-79）:
#   + プロンプトなしで句点がほぼ出ない音声（Track-78: 句点0・語途中の話者境界20）では、
#     句点39・話者境界6へ大きく改善した
#   - Track-79（プロンプトなしでも句読点が出る音声）では改善は小さく、チャンク末尾に短い「はい。」が
#     別話者の独立した発言として2件増え（誘発の可能性）、英語せりふ区間の話者境界が悪化した（2→7）
# そのため標準はOFF。句点がほぼ出ない音声で --neutral-prompt を試す、という位置づけにした。
NEUTRAL_ASR_PROMPT = "はい、そうですね。ええと、それはですね、こういうことなんです。"


def resolve_asr_prompt(dictionary_prompt: str | None, use_neutral: bool = False) -> tuple[str | None, str]:
    """(initial_prompt, 種別) を返す。種別は dictionary / neutral / none。

    - 辞書プロンプトがある → それだけを渡す
    - use_neutral=True → 中立プロンプトだけを渡す
    - 両方 → ValueError（連結も優先順位による暗黙の選択もしない）
    - どちらもなし → なし（標準）
    """
    if dictionary_prompt and use_neutral:
        raise ValueError("辞書プロンプトと中立プロンプトは同時に指定できません（連結しません）")
    if dictionary_prompt:
        return dictionary_prompt, "dictionary"
    if use_neutral:
        return NEUTRAL_ASR_PROMPT, "neutral"
    return None, "none"


# ------------------------------------------------------------------ 環境
def resolve_device(device: str) -> str:
    if device != "auto":
        return device
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


def resolve_compute_type(compute_type: str, device: str) -> str:
    if compute_type != "auto":
        return compute_type
    return "float16" if device == "cuda" else "int8"


def check_ffmpeg() -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise SystemExit("ffmpeg / ffprobe が見つかりません。README の「ffmpegの導入」を参照してください。")


def probe_duration(path: Path) -> float | None:
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                              "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
        return float(out.stdout.strip())
    except Exception:
        return None


def validate_audio(path: Path) -> float:
    """STEP1: 存在・拡張子・読み込み可否を確認し、長さ(秒)を返す。"""
    if not path.is_file():
        raise SystemExit(f"音声ファイルが見つかりません: {path}")
    if path.suffix.lower() not in SUPPORTED_EXT:
        log(f"[警告] 想定外の拡張子 {path.suffix}（ffmpegで読めれば処理を続行します）")
    dur = probe_duration(path)
    if dur is None or dur <= 0:
        raise SystemExit(f"ffprobe で音声として読めませんでした: {path}")
    return dur


def fingerprint(path: Path) -> str:
    """大きいファイルでも速いように、サイズ＋先頭/末尾1MBのハッシュ。"""
    h = hashlib.sha1()
    size = path.stat().st_size
    h.update(str(size).encode())
    with path.open("rb") as f:
        h.update(f.read(1 << 20))
        if size > 2 << 20:
            f.seek(-(1 << 20), 2)
            h.update(f.read())
    return h.hexdigest()[:16]


# ------------------------------------------------------------------ STEP2 前処理
def preprocess(src: Path, temp_dir: Path, normalize: bool = True) -> Path:
    """16kHz・モノラルのWAVに変換（任意で音量正規化）。元ファイルは変更しない。"""
    temp_dir.mkdir(parents=True, exist_ok=True)
    dst = temp_dir / f"{src.stem}.{fingerprint(src)}.16k.wav"
    if dst.exists() and dst.stat().st_size > 0:
        return dst
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000"]
    if normalize:
        cmd += ["-af", "loudnorm=I=-16:TP=-1.5:LRA=11"]
    tmp = dst.with_suffix(".part.wav")
    subprocess.run(cmd + [str(tmp)], check=True)
    tmp.replace(dst)
    return dst


# ------------------------------------------------------------------ キャッシュ
def cache_load(path: Path):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def cache_save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    tmp.replace(path)


# ------------------------------------------------------------------ STEP3 文字起こし
def transcribe(wav: Path, cfg: ASRConfig) -> dict:
    import whisperx

    device = resolve_device(cfg.device)
    ctype = resolve_compute_type(cfg.compute_type, device)
    log(f"[ASR] model={cfg.model} device={device} compute_type={ctype} lang={cfg.language}")
    if device == "cpu" and cfg.model.startswith("large"):
        log("[警告] CPUでlarge系モデルは非常に遅くなります（--model small/medium も検討）")
    asr_options = {}
    if cfg.initial_prompt:
        asr_options["initial_prompt"] = cfg.initial_prompt
    model = whisperx.load_model(cfg.model, device, compute_type=ctype, language=cfg.language,
                                asr_options=asr_options or None)
    audio = whisperx.load_audio(str(wav))
    result = model.transcribe(audio, batch_size=cfg.batch_size, language=cfg.language)
    result["language"] = result.get("language") or cfg.language
    result["meta"] = {"model": cfg.model, "device": device, "compute_type": ctype,
                      "initial_prompt": cfg.initial_prompt}
    del model
    return result


# ------------------------------------------------------------------ STEP4 alignment
def align(wav: Path, whisper_result: dict, cfg: ASRConfig) -> dict:
    import whisperx

    device = resolve_device(cfg.device)
    lang = whisper_result.get("language", cfg.language)
    audio = whisperx.load_audio(str(wav))
    model_a, meta = whisperx.load_align_model(language_code=lang, device=device)
    aligned = whisperx.align(whisper_result["segments"], model_a, meta, audio, device,
                             return_char_alignments=False)
    aligned["language"] = lang
    return aligned


def mark_unaligned(whisper_result: dict) -> dict:
    """alignment失敗時のフォールバック。単語タイムスタンプなしで先へ進む。"""
    out = dict(whisper_result)
    out["segments"] = [{**s, "words": []} for s in whisper_result["segments"]]
    out["aligned"] = False
    return out

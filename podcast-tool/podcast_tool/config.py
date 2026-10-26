"""設定ファイル（podcast.yaml）の読込と検証。

数値はすべて YAML 側に置き、コードは値を読むだけにする。
キーが欠けていたら推測せずにエラーにする（再現性のため）。
"""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from typing import Any

import yaml

from .errors import ConfigError

_MISSING = object()


class Config:
    def __init__(self, data: dict, path: Path):
        self.data = data
        self.path = path
        # 基準フォルダ = config/ の1つ上（podcast-tool/）
        self.root = path.parent.parent if path.parent.name == "config" else path.parent
        self.sha256 = hashlib.sha256(path.read_bytes()).hexdigest()

    def get(self, dotted: str, default: Any = _MISSING) -> Any:
        node: Any = self.data
        for key in dotted.split("."):
            if not isinstance(node, dict) or key not in node:
                if default is not _MISSING:
                    return default
                raise ConfigError(
                    f"設定項目 '{dotted}' がありません（{self.path}）",
                    hint="同梱の config/podcast.yaml を参考に項目を追加してください。",
                )
            node = node[key]
        return node

    def num(self, dotted: str, lo: float | None = None, hi: float | None = None) -> float:
        v = self.get(dotted)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ConfigError(f"設定項目 '{dotted}' は数値にしてください（現在: {v!r}）")
        if (lo is not None and v < lo) or (hi is not None and v > hi):
            raise ConfigError(f"設定項目 '{dotted}' = {v} は範囲外です（{lo} 〜 {hi}）")
        return float(v)

    def flag(self, dotted: str) -> bool:
        v = self.get(dotted)
        if not isinstance(v, bool):
            raise ConfigError(f"設定項目 '{dotted}' は true / false にしてください（現在: {v!r}）")
        return v

    def num_or_auto(self, dotted: str, lo: float, hi: float) -> float | None:
        v = self.get(dotted)
        if isinstance(v, str) and v.strip().lower() == "auto":
            return None
        return self.num(dotted, lo, hi)

    def dir(self, key: str) -> Path:
        p = Path(self.get(f"paths.{key}"))
        return p if p.is_absolute() else (self.root / p)

    def snapshot(self) -> dict:
        return copy.deepcopy(self.data)


def load_config(path: Path) -> Config:
    if not path.exists():
        raise ConfigError(f"設定ファイルが見つかりません: {path}",
                          hint="podcast-tool/config/podcast.yaml を置くか、--config で指定してください。")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(f"設定ファイルの書式エラー: {e}",
                          hint="インデント（半角スペース）や「:」の後のスペースを確認してください。")
    if not isinstance(data, dict):
        raise ConfigError("設定ファイルの中身が空か、形式が正しくありません。")
    cfg = Config(data, path.resolve())
    validate(cfg)
    return cfg


def validate(cfg: Config) -> None:
    """起動直後に全項目を検査し、処理途中で設定ミスが判明する事態を避ける。"""
    c = cfg
    c.num("loudness.target_lufs", -40, -5)
    c.num("loudness.true_peak_max_dbtp", -12, 0)
    c.num("loudness.limiter_margin_db", 0, 3)
    c.num("loudness.accuracy_lu", 0.05, 2)
    c.num("loudness.tolerance_lu", 0.1, 5)
    ch = c.num("output.channels", 1, 2)
    c.num("output.publish.channels", 1, 2)
    if int(ch) != ch:
        raise ConfigError("output.channels は 1 か 2 にしてください。")
    if c.get("output.master.bit_depth") not in (16, 24, 32):
        raise ConfigError("output.master.bit_depth は 16 / 24 / 32 のいずれかにしてください。")
    c.num("output.master.sample_rate", 8000, 192000)
    c.num("output.publish.sample_rate", 8000, 48000)
    br = str(c.get("output.publish.bitrate"))
    if not br.rstrip("kK").isdigit():
        raise ConfigError(f"output.publish.bitrate の形式が不正です: {br}（例: 128k）")
    for k in ("master_suffix", "publish_suffix", "report_suffix"):
        c.get(f"output.{k}")
    c.flag("output.overwrite")
    c.flag("output.keep_work_files")
    c.flag("input.downmix_to_mono")

    c.flag("cleanup.highpass.enabled")
    c.num("cleanup.highpass.frequency_hz", 20, 300)
    if c.get("cleanup.highpass.order") not in (2, 4):
        raise ConfigError("cleanup.highpass.order は 2 か 4 にしてください。")
    c.flag("cleanup.lowpass.enabled")
    c.num("cleanup.lowpass.frequency_hz", 4000, 22000)
    c.flag("cleanup.denoise.enabled")
    c.num("cleanup.denoise.reduction_db", 0.01, 40)
    c.num_or_auto("cleanup.denoise.noise_floor_db", -80, -20)
    c.flag("cleanup.denoise.track_noise")
    c.flag("cleanup.declick.enabled")

    c.flag("leveling.dynaudnorm.enabled")
    c.num("leveling.dynaudnorm.frame_ms", 10, 8000)
    g = c.num("leveling.dynaudnorm.gauss_size", 3, 301)
    if int(g) % 2 == 0:
        raise ConfigError("leveling.dynaudnorm.gauss_size は奇数にしてください。")
    c.num("leveling.dynaudnorm.max_gain_db", 0, 30)
    c.num("leveling.dynaudnorm.peak", 0.1, 1.0)
    c.num_or_auto("leveling.dynaudnorm.threshold_db", -90, -10)
    c.flag("leveling.compressor.enabled")
    c.num("leveling.compressor.threshold_db", -60, 0)
    c.num("leveling.compressor.ratio", 1, 20)
    c.num("leveling.compressor.attack_ms", 0.01, 2000)
    c.num("leveling.compressor.release_ms", 0.01, 9000)
    c.num("leveling.compressor.knee_db", 1, 8)

    c.num_or_auto("silence.threshold_db", -90, -10)
    c.num("silence.auto_margin_db", 0, 40)
    c.num("silence.auto_min_db", -90, -10)
    c.num("silence.auto_max_db", -90, -10)
    c.num("silence.min_duration_sec", 0.05, 10)
    c.flag("silence.trim_head")
    c.flag("silence.trim_tail")
    c.num("silence.keep_head_sec", 0, 10)
    c.num("silence.keep_tail_sec", 0, 10)
    c.num("silence.long_silence_warn_sec", 0.5, 600)

    ref = c.get("bgm.reference_lufs")
    if ref is not None:
        c.num("bgm.reference_lufs", -40, -5)
    c.flag("bgm.ducking.enabled")
    c.num("bgm.ducking.threshold_db", -60, 0)
    c.num("bgm.ducking.ratio", 1, 20)
    c.num("bgm.ducking.attack_ms", 0.01, 2000)
    c.num("bgm.ducking.release_ms", 0.01, 9000)
    c.num("bgm.ducking.knee_db", 1, 8)

    c.flag("opening.enabled")
    c.get("opening.file")
    solo = c.num("opening.solo_sec", 0, 600)
    c.num("opening.solo_gain_db", -60, 12)
    fi = c.num("opening.fade_in_sec", 0, 60)
    tr = c.num("opening.duck_transition_sec", 0, 60)
    c.num("opening.bed_gain_db", -60, 12)
    c.num("opening.bed_sec", 0, 600)
    c.num("opening.fade_out_sec", 0.01, 60)
    if fi + tr > solo and c.flag("opening.enabled"):
        raise ConfigError("opening.fade_in_sec + duck_transition_sec が solo_sec を超えています。")

    c.flag("jingle.enabled")
    c.get("jingle.file")
    c.num("jingle.gain_db", -60, 12)
    positions = c.get("jingle.positions")
    if positions is None:
        positions = []
    if not isinstance(positions, list):
        raise ConfigError("jingle.positions はリスト（- percent: 50 など）にしてください。")
    for i, p in enumerate(positions):
        if not isinstance(p, dict) or len(p) != 1 or next(iter(p)) not in ("minutes", "seconds", "percent"):
            raise ConfigError(
                f"jingle.positions[{i}] の形式が不正です: {p!r}",
                hint="各行を「- minutes: 10」「- seconds: 90」「- percent: 50」のいずれかにしてください。")
        v = next(iter(p.values()))
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
            raise ConfigError(f"jingle.positions[{i}] の値が不正です: {v!r}")
        if "percent" in p and v > 100:
            raise ConfigError(f"jingle.positions[{i}] percent は 0〜100 にしてください。")
    c.num("jingle.search_window_sec", 0, 3600)
    c.num("jingle.min_silence_sec", 0.05, 30)
    c.num("jingle.prefer_longer_weight", 0, 1000)
    if c.get("jingle.on_no_silence") not in ("skip", "nearest"):
        raise ConfigError("jingle.on_no_silence は skip か nearest にしてください。")
    c.num("jingle.min_distance_sec", 0, 36000)
    c.num("jingle.gap_before_sec", 0, 30)
    c.num("jingle.gap_after_sec", 0, 30)
    c.num("jingle.fade_in_sec", 0, 30)
    c.num("jingle.fade_out_sec", 0, 30)

    c.flag("ending.enabled")
    c.get("ending.file")
    c.num("ending.lead_in_sec", 0, 600)
    c.num("ending.fade_in_sec", 0, 60)
    c.num("ending.bed_gain_db", -60, 12)
    rise = c.num("ending.rise_sec", 0, 60)
    tail = c.num("ending.tail_sec", 0, 600)
    c.num("ending.solo_gain_db", -60, 12)
    c.num("ending.fade_out_sec", 0.01, 60)
    if rise > tail:
        raise ConfigError("ending.rise_sec は ending.tail_sec 以下にしてください。")

    for k in ("assets_dir", "input_dir", "output_dir", "work_dir"):
        c.get(f"paths.{k}")
    c.get("ffmpeg.path")
    c.get("ffmpeg.ffprobe_path")

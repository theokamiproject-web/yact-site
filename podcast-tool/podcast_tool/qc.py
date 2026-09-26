"""完成ファイルの品質チェック（書き出したファイルを再解析して設定値と照合）。"""
from __future__ import annotations

from pathlib import Path

from .analyze import Analysis, analyze_file
from .ffmpeg import FFmpeg


def check_file(ff: FFmpeg, cfg, path: Path, label: str, expected_duration: float,
               duration_tol: float, silence_threshold_db: float | None = None,
               loudness: dict | None = None) -> tuple[Analysis, list[dict], list[dict]]:
    """loudness: マスタリング工程で「この完成ファイル自体」を測定した値（再測定の省略用）。"""
    a = analyze_file(ff, cfg, path, f"品質チェック({label})", threshold_db=silence_threshold_db,
                     known_loudness=loudness)
    target = cfg.num("loudness.target_lufs")
    tol = cfg.num("loudness.tolerance_lu")
    tp_max = cfg.num("loudness.true_peak_max_dbtp")
    lim = cfg.num("silence.long_silence_warn_sec")

    checks = []

    def add(name, ok, value, expect, severity="error"):
        checks.append({"file": label, "check": name, "ok": bool(ok), "severity": severity,
                       "value": value, "expected": expect})

    i = a.integrated_lufs
    add("Integrated Loudness", i is not None and abs(i - target) <= tol,
        None if i is None else round(i, 2), f"{target} ±{tol} LUFS")
    tp = a.true_peak_dbtp
    add("True Peak", tp is not None and tp <= tp_max + 0.05, None if tp is None else round(tp, 2), f"≤ {tp_max} dBTP")
    pk = a.sample_peak_dbfs
    add("クリッピング（サンプルピーク）", pk is None or pk < -0.01,
        None if pk is None else round(pk, 2), "< 0 dBFS")
    add("長さ", abs(a.duration - expected_duration) <= duration_tol,
        round(a.duration, 3), f"{expected_duration:.3f} ±{duration_tol} 秒")

    # 冒頭（BGM の立ち上がり前）と末尾（フェードアウト後）の無音は正常なので除外
    long_sil = [s.to_dict() for s in a.silences
                if s.duration >= lim and s.start > 0.05 and s.end < a.duration - 0.05]
    # 「間」は作品の一部なので削除も不合格判定もしない（注意として報告）
    add("長すぎる無音", not long_sil, len(long_sil), f"{lim} 秒以上の無音が 0 件", severity="warning")
    return a, checks, long_sil

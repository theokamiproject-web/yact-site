"""処理レポート（JSON = 機械向けの全記録 / TXT = 人が読む要約）。"""
from __future__ import annotations

import json
from pathlib import Path

from .timeline import fmt


def _r(x, n=2):
    return None if x is None else round(x, n)


def _loud(a) -> dict:
    return {"integrated_lufs": _r(a.integrated_lufs), "true_peak_dbtp": _r(a.true_peak_dbtp),
            "lra_lu": _r(a.lra_lu), "sample_peak_dbfs": _r(a.sample_peak_dbfs)}


def build(*, cfg, version, ff, started, input_path, input_sha, outs, src, clean, chain, cleanup_rec, tl,
          voice_loud, voice_gain, asset_info, premix_loud, mastering, graph, qa_master, qa_pub, checks,
          long_master, warnings, limiter_gr) -> dict:
    target = cfg.num("loudness.target_lufs")
    tp_max = cfg.num("loudness.true_peak_max_dbtp")
    op = tl.opening
    ed = tl.ending
    return {
        "tool": {"name": "podcast-tool", "version": version},
        "processed_at": started.isoformat(timespec="seconds"),
        "ffmpeg_version": ff.version,
        "config": {"file": str(cfg.path), "sha256": cfg.sha256, "values": cfg.snapshot()},
        "input": {"file": str(input_path), "sha256": input_sha, "analysis": src.to_dict()},
        "outputs": {"master": str(outs.master), "publish": str(outs.publish),
                    "report_txt": str(outs.report_txt), "log": str(outs.log)},
        "loudness": {
            "target": {"integrated_lufs": target, "true_peak_max_dbtp": tp_max},
            "before": _loud(src),
            "voice_after_cleanup": {"integrated_lufs": _r(voice_loud["integrated_lufs"]),
                                    "true_peak_dbtp": _r(voice_loud["true_peak_dbtp"]),
                                    "lra_lu": _r(voice_loud["lra_lu"])},
            "after_master": _loud(qa_master),
            "after_publish": _loud(qa_pub),
        },
        "processing": {
            "cleanup": cleanup_rec,
            "cleanup_filter": chain,
            "voice_gain_db": _r(voice_gain),
            "bgm_normalization": {
                k: {"file": str(v["path"]), "duration": _r(v["duration"]), "measured_lufs": _r(v["integrated_lufs"]),
                    "gain_to_reference_db": _r(v["norm_gain_db"])} for k, v in asset_info.items()},
            "ducking": cfg.snapshot()["bgm"]["ducking"],
            "mix_premaster": {k: _r(v) for k, v in premix_loud.items()},
            "mastering": {"method": "gain + 4x oversampled alimiter（WAV と MP3 を個別に実測合わせ）",
                          **mastering,
                          "limiter_gain_reduction_estimate_db": _r(max(0.0, limiter_gr))},
            "mix_filtergraph": graph,
        },
        "silence": {
            "threshold_db_after_cleanup": _r(clean.silence_threshold_db),
            "head_removed_sec": _r(tl.trim_start, 3),
            "tail_removed_sec": _r(clean.duration - tl.trim_end, 3),
            "long_silence_candidates": tl.long_silences,
            "long_silences_in_master": long_master,
        },
        "placements": {
            "opening": None if op is None else {
                "file": str(asset_info["opening"]["path"]), "out_start": 0.0, "out_end": _r(op.out_end, 3),
                "voice_starts_at": _r(tl.voice_out_start, 3), "envelope": op.envelope},
            "voice": [{"src_start": _r(s.src_start, 3), "src_end": _r(s.src_end, 3),
                       "out_start": _r(s.out_start, 3), "out_end": _r(s.out_start + s.duration, 3)}
                      for s in tl.segments],
            "jingles": [{"request": j.request, "target_main_sec": _r(j.target_main, 3),
                         "used_silence_main": {"start": _r(j.silence.start - tl.trim_start, 3),
                                               "end": _r(j.silence.end - tl.trim_start, 3)},
                         "cut_main_sec": _r(j.cut_src - tl.trim_start, 3),
                         "out_start": _r(j.out_start, 3), "out_end": _r(j.out_start + j.length, 3)}
                        for j in tl.jingles],
            "ending": None if ed is None else {
                "file": str(asset_info["ending"]["path"]), "out_start": _r(ed.out_start, 3),
                "out_end": _r(ed.out_end, 3), "voice_ends_at": _r(tl.voice_out_end, 3), "envelope": ed.envelope},
        },
        "durations": {"input": _r(src.duration, 3), "main_voice": _r(tl.main_duration, 3),
                      "planned": _r(tl.total, 3), "master": _r(qa_master.duration, 3),
                      "publish": _r(qa_pub.duration, 3)},
        "qc": {"passed": all(c["ok"] or c["severity"] != "error" for c in checks), "checks": checks},
        "warnings": warnings,
        "ffmpeg_commands": [{"step": c["step"], "returncode": c["returncode"], "sec": c["sec"]} for c in ff.commands],
    }


def write(data: dict, json_path: Path, txt_path: Path) -> None:
    tmp = json_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(json_path)
    txt_path.write_text(to_text(data), encoding="utf-8")


def to_text(d: dict) -> str:
    L = d["loudness"]
    p = d["placements"]
    out = []
    w = out.append
    w("=== ポッドキャスト処理レポート ===")
    w(f"処理日時   : {d['processed_at']}")
    w(f"入力       : {d['input']['file']}")
    w(f"完成(WAV)  : {d['outputs']['master']}")
    w(f"完成(MP3)  : {d['outputs']['publish']}")
    w(f"最終尺     : {fmt(d['durations']['master'])}（入力 {fmt(d['durations']['input'])} / 本編 {fmt(d['durations']['main_voice'])}）")
    w("")
    w("--- ラウドネス ---")
    w(f"目標       : {L['target']['integrated_lufs']} LUFS / True Peak ≤ {L['target']['true_peak_max_dbtp']} dBTP")
    for key, name in (("before", "処理前"), ("after_master", "処理後 WAV"), ("after_publish", "処理後 MP3")):
        x = L[key]
        w(f"{name:<10}: {x['integrated_lufs']} LUFS / TP {x['true_peak_dbtp']} dBTP / LRA {x['lra_lu']} LU"
          f" / サンプルピーク {x['sample_peak_dbfs']} dBFS")
    w("")
    w("--- 実行した処理 ---")
    for k, v in d["processing"]["cleanup"].items():
        w(f"{k:<11}: {json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else v}")
    w(f"声のゲイン : {d['processing']['voice_gain_db']:+} dB（本編を目標ラウドネスへ）")
    m = d["processing"]["mastering"]
    for k, name in (("master", "WAV"), ("publish", "MP3")):
        x = m[k]
        w(f"マスタリング({name}): ゲイン {x['gain_db']:+} dB / リミッタ上限 {x['limiter_ceiling_db']} dBFS"
          f"（4倍オーバーサンプル）/ 試行 {len(x['iterations'])} 回")
    w(f"リミッタ推定最大圧縮量: {m['limiter_gain_reduction_estimate_db']} dB")
    s = d["silence"]
    w(f"無音トリム : 冒頭 {s['head_removed_sec']} 秒 / 末尾 {s['tail_removed_sec']} 秒")
    w("")
    w("--- 配置（完成音源上の時刻）---")
    if p["opening"]:
        w(f"OP         : {fmt(0)}〜{fmt(p['opening']['out_end'])}（声の開始 {fmt(p['opening']['voice_starts_at'])}）")
    for i, j in enumerate(p["jingles"], 1):
        w(f"アイキャッチ{i}: {fmt(j['out_start'])}〜{fmt(j['out_end'])}（指定 {j['request']} = 本編 {fmt(j['target_main_sec'])}"
          f" → 本編 {fmt(j['cut_main_sec'])} の無音で挿入）")
    if p["ending"]:
        w(f"ED         : {fmt(p['ending']['out_start'])}〜{fmt(p['ending']['out_end'])}（声の終了 {fmt(p['ending']['voice_ends_at'])}）")
    if s["long_silence_candidates"]:
        w("")
        w("--- 長すぎる無音の候補（削除していません）---")
        for c in s["long_silence_candidates"]:
            w(f"本編 {fmt(c['main_start'])} から {c['duration']} 秒（完成音源 {fmt(c['output_start'])}）")
    w("")
    w("--- 品質チェック ---")
    for c in d["qc"]["checks"]:
        tag = "OK" if c["ok"] else ("NG" if c["severity"] == "error" else "注意")
        w(f"[{tag}] {c['file']:<8} {c['check']}: {c['value']}（基準 {c['expected']}）")
    w("")
    w("--- 警告 ---")
    w("\n".join(f"・{x}" for x in d["warnings"]) if d["warnings"] else "なし")
    return "\n".join(out) + "\n"

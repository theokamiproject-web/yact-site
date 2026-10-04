"""長い音声の話者分離を、短いチャンクに分けて再開可能に実行し、チャンク間で話者を対応付けて統合する。

背景: 55分音声を1回のpyannote diarizationで処理すると約50分かかり、クラウド環境の再起動で完了前に止まった。
そこで音声を 5〜10分のチャンク（30秒の重なり）に分け、チャンクごとに結果を保存する。再起動後は未完了チャンクから再開する。

重要: pyannote の SPEAKER_00 はチャンクごとに独立している。**番号が同じでも同一人物とはみなさない。**
統合は ①重なり区間での同時発話時間 ②話者埋め込みのコサイン類似度 ③1チャンク内の別話者は別人（1対1）
で対応付け、自信がない人物は無理にまとめず「チャンク間speaker対応 要確認」として報告する。
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Callable

import numpy as np

STATE_VERSION = 1
CHUNK_SEC = 300.0            # 1チャンクの長さ（5分）。1チャンクが約4〜5分で終わるサイズ
OVERLAP_SEC = 30.0           # チャンク間の重なり
AUTO_THRESHOLD_SEC = 900.0   # これより長い音声だけチャンク方式（短い音声は従来どおり一括）

# ---- 対応付けの閾値
MIN_OVERLAP_EVIDENCE_SEC = 2.0   # 重なり区間での発話がこれ未満なら時刻の証拠にしない
TIME_RATIO_OK = 0.6              # その話者の重なり区間の発話のうち、同じ全体話者と同時に話している割合
EMB_CONTRADICT = 0.45            # 時刻が一致しても、埋め込み類似度がこれ未満なら矛盾（確信なし）
EMB_ONLY_OK = 0.70               # 時刻の証拠が弱いとき、埋め込みだけで採用する類似度
EMB_MARGIN = 0.10                # 〃 次点との差
EMB_RELATIVE_OK = 0.60           # 〃 他の全体話者との差が大きい（EMB_RELATIVE_MARGIN）ときは、この類似度でも採用
EMB_RELATIVE_MARGIN = 0.30
EMB_CLEARLY_DIFFERENT = 0.50     # 全ての既存話者との類似度がこれ未満なら「新しい人物」と確信してよい

Diarizer = Callable[[np.ndarray, float, float, "int | None"], "tuple[list[dict], dict | None]"]


def log(msg: str):
    import sys
    print(msg, file=sys.stderr, flush=True)


# ------------------------------------------------------------------ チャンク計画
def plan_chunks(duration: float, chunk_sec: float = CHUNK_SEC, overlap_sec: float = OVERLAP_SEC) -> list[dict]:
    """[{index, start, end}]。隣り合うチャンクは overlap_sec だけ重なる。末尾の極端に短いチャンクは前のチャンクに吸収する。"""
    if chunk_sec <= overlap_sec * 2:
        raise ValueError("chunk_sec は overlap_sec の2倍より長くしてください")
    step = chunk_sec - overlap_sec
    chunks, s = [], 0.0
    while True:
        e = min(s + chunk_sec, duration)
        chunks.append({"start": round(s, 3), "end": round(e, 3)})
        if e >= duration - 1e-6:
            break
        s += step
    if len(chunks) > 1 and chunks[-1]["end"] - chunks[-1]["start"] < overlap_sec * 2:
        chunks.pop()
        chunks[-1]["end"] = round(duration, 3)
    for i, c in enumerate(chunks):
        c["index"] = i
    return chunks


def _chunk_file(d: Path, i: int) -> Path:
    return d / f"chunk_{i:03d}.json"


def _save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    tmp.replace(path)


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - 壊れたファイルは未完了扱い
        return None


# ------------------------------------------------------------------ 実行（保存・再開）
def run_chunked(audio: np.ndarray, duration: float, diarize_fn: Diarizer, chunk_dir: Path, *,
                fingerprint: str | None, model: str, max_speakers: int | None = None, num_speakers: int | None = None,
                min_speakers: int | None = None, chunk_sec: float = CHUNK_SEC, overlap_sec: float = OVERLAP_SEC,
                sample_rate: int = 16000, logger=log) -> tuple[list[dict], dict]:
    """チャンクごとに diarize_fn(音声, 開始秒, 終了秒, max_speakers) -> (相対時刻のsegments, 埋め込みdict|None) を呼び、
    各チャンク終了直後に chunk_NNN.json と state.json を保存する。保存済みのチャンクは再実行しない。"""
    chunk_dir = Path(chunk_dir)
    plan = plan_chunks(duration, chunk_sec, overlap_sec)
    settings = {"version": STATE_VERSION, "source_audio_fingerprint": fingerprint, "model": model,
                "num_speakers": num_speakers, "min_speakers": min_speakers, "max_speakers": max_speakers,
                "chunk_sec": chunk_sec, "overlap_sec": overlap_sec, "duration": round(duration, 2)}
    state_path = chunk_dir / "state.json"
    state = _load(state_path)
    if state is not None and any(state.get(k) != v for k, v in settings.items()):
        logger("[話者分離] 音声・モデル・設定が変わったため、古いチャンクのキャッシュは使いません")
        shutil.rmtree(chunk_dir, ignore_errors=True)
        state = None
    if state is None and chunk_dir.exists() and any(chunk_dir.glob("chunk_*.json")):
        logger("[話者分離] 検証できない古いチャンクのキャッシュ（state.json なし）は使いません")
        shutil.rmtree(chunk_dir, ignore_errors=True)
    chunk_dir.mkdir(parents=True, exist_ok=True)
    state = {**settings, "total_chunks": len(plan), "chunks": [{k: c[k] for k in ("index", "start", "end")} for c in plan],
             "completed_chunks": [], "current_chunk": None, "note": (
                 "チャンクごとの話者分離。min/num_speakers はチャンクには渡さず（チャンクに全員が出るとは限らない）、"
                 "max_speakers だけを上限として渡す")}
    done = []
    for c in plan:
        saved = _load(_chunk_file(chunk_dir, c["index"]))
        if saved and saved.get("index") == c["index"] and abs(saved.get("start", -1) - c["start"]) < 1e-3 \
                and abs(saved.get("end", -1) - c["end"]) < 1e-3 and "segments" in saved:
            done.append(saved)
            state["completed_chunks"].append(c["index"])
    _save(state_path, state)
    if done:
        logger(f"[話者分離] 保存済みチャンク {len(done)}/{len(plan)} を再利用し、未完了チャンクから再開します")
    done_idx = {d["index"] for d in done}
    by_idx = {d["index"]: d for d in done}
    for c in plan:
        if c["index"] in done_idx:
            continue
        state["current_chunk"] = c["index"]
        _save(state_path, state)
        t0 = time.time()
        a, b = int(c["start"] * sample_rate), int(c["end"] * sample_rate)
        segs, emb = diarize_fn(audio[a:b], c["start"], c["end"], max_speakers)
        rec = {"index": c["index"], "start": c["start"], "end": c["end"], "elapsed_sec": round(time.time() - t0, 1),
               "segments": [{"start": round(c["start"] + float(s["start"]), 3), "end": round(c["start"] + float(s["end"]), 3),
                             "speaker": str(s["speaker"])} for s in segs],
               "embeddings": ({str(k): [float(x) for x in v] for k, v in emb.items()} if emb else None)}
        _save(_chunk_file(chunk_dir, c["index"]), rec)      # 各チャンク終了直後に保存
        by_idx[c["index"]] = rec
        state["completed_chunks"].append(c["index"])
        state["completed_chunks"].sort()
        state["current_chunk"] = None
        _save(state_path, state)
        logger(f"[話者分離] チャンク {c['index'] + 1}/{len(plan)} 完了 "
               f"（{c['start']:.0f}〜{c['end']:.0f}秒、{rec['elapsed_sec']}秒）")
    chunks = [by_idx[c["index"]] for c in plan]
    segments, report = merge_chunks(chunks, duration)
    report["total_chunks"] = len(plan)
    _save(chunk_dir / "merge_report.json", report)
    return segments, report


# ------------------------------------------------------------------ 統合（チャンク間のspeaker対応）
def _clip(segs: list[dict], a: float, b: float) -> list[dict]:
    out = []
    for s in segs:
        lo, hi = max(s["start"], a), min(s["end"], b)
        if hi - lo > 1e-6:
            out.append({**s, "start": lo, "end": hi})
    return out


def _intersection(x: list[dict], y: list[dict]) -> float:
    tot = 0.0
    for p in x:
        for q in y:
            ov = min(p["end"], q["end"]) - max(p["start"], q["start"])
            if ov > 0:
                tot += ov
    return tot


def _cos(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    return 0.0 if na == 0 or nb == 0 else float(np.dot(a, b) / (na * nb))


def _fmt(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def merge_chunks(chunks: list[dict], duration: float) -> tuple[list[dict], dict]:
    """チャンクごとの結果（絶対時刻・チャンク内のspeaker ID）を、全体で一貫したspeaker IDの1つの結果に統合する。"""
    chunks = sorted(chunks, key=lambda c: c["index"])
    cut = [0.0] + [(chunks[k]["start"] + chunks[k - 1]["end"]) / 2 for k in range(1, len(chunks))] + [duration]
    glob: dict[str, dict] = {}         # 全体speaker -> {"sum": 埋め込みの重み付き和|None, "w": 重み}
    matches, unresolved = [], []
    assembled: list[list[dict]] = []   # チャンクごとの、全体speaker名に直した（切り出す前の）segments

    def new_global(emb, dur) -> str:
        name = f"SPEAKER_{len(glob):02d}"
        glob[name] = {"sum": None if emb is None else emb * dur, "w": dur}
        return name

    def centroid(g: str):
        s = glob[g]["sum"]
        return None if s is None else s / max(glob[g]["w"], 1e-9)

    for k, ch in enumerate(chunks):
        segs = ch["segments"]
        locs = sorted({s["speaker"] for s in segs}, key=lambda sp: min(s["start"] for s in segs if s["speaker"] == sp))
        embs = {sp: (np.array(v, dtype=float) if v else None) for sp, v in (ch.get("embeddings") or {}).items()}
        total = {sp: sum(s["end"] - s["start"] for s in segs if s["speaker"] == sp) for sp in locs}
        mapping: dict[str, str] = {}
        if k == 0:
            for sp in locs:
                mapping[sp] = new_global(embs.get(sp), total[sp])
        else:
            a, b = ch["start"], chunks[k - 1]["end"]            # 重なり区間
            prev = _clip(assembled[k - 1], a, b)
            cur = _clip(segs, a, b)
            cand: list[tuple[int, float, str, str, dict]] = []
            info: dict[str, dict] = {}
            for sp in locs:
                mine = [s for s in cur if s["speaker"] == sp]
                ov = sum(s["end"] - s["start"] for s in mine)
                rows = {}
                for g in glob:
                    inter = _intersection(mine, [s for s in prev if s["speaker"] == g]) if ov > 0 else 0.0
                    p = inter / ov if ov > 0 else 0.0
                    e1, e2 = embs.get(sp), centroid(g)
                    sim = _cos(e1, e2) if e1 is not None and e2 is not None else None
                    rows[g] = {"time": round(p, 3), "inter": round(inter, 2), "sim": None if sim is None else round(sim, 3)}
                info[sp] = {"ov": ov, "rows": rows}
                for g, r in rows.items():
                    time_ok = ov >= MIN_OVERLAP_EVIDENCE_SEC and r["inter"] >= MIN_OVERLAP_EVIDENCE_SEC and r["time"] >= TIME_RATIO_OK
                    if time_ok and (r["sim"] is None or r["sim"] >= EMB_CONTRADICT):
                        cand.append((0, r["time"] + (r["sim"] or 0.0), sp, g, r))
                    elif r["sim"] is not None and r["sim"] >= EMB_RELATIVE_OK and not time_ok:
                        best_other = max((rr["sim"] for gg, rr in rows.items() if gg != g and rr["sim"] is not None), default=-1.0)
                        gap = r["sim"] - best_other                  # 次点の全体話者より明確に高いときだけ
                        if (r["sim"] >= EMB_ONLY_OK and gap >= EMB_MARGIN) or (r["sim"] >= EMB_RELATIVE_OK and gap >= EMB_RELATIVE_MARGIN):
                            cand.append((1, r["sim"], sp, g, r))
            used_g: set[str] = set()
            for tier, score, sp, g, r in sorted(cand, key=lambda c: (c[0], -c[1])):
                if sp in mapping or g in used_g:
                    continue                                    # 1対1（同じチャンクの別話者を同じ人物にしない）
                mapping[sp] = g
                used_g.add(g)
                matches.append({"chunk": k, "local": sp, "global": g, "tier": "時刻一致" if tier == 0 else "埋め込み",
                                "time": r["time"], "sim": r["sim"]})
            for sp in locs:
                if sp in mapping:
                    continue
                rows = info[sp]["rows"]
                sims = [r["sim"] for r in rows.values() if r["sim"] is not None]
                has_emb = bool(sims)
                clearly_new = has_emb and max(sims) < EMB_CLEARLY_DIFFERENT and not any(
                    r["time"] >= TIME_RATIO_OK and r["inter"] >= MIN_OVERLAP_EVIDENCE_SEC for r in rows.values())
                name = new_global(embs.get(sp), total[sp])
                mapping[sp] = name
                if clearly_new:
                    matches.append({"chunk": k, "local": sp, "global": name, "tier": "新しい話者（埋め込みが既存の全員と明確に異なる）",
                                    "time": None, "sim": round(max(sims), 3)})
                else:
                    best = sorted(((g, r) for g, r in rows.items()), key=lambda x: -((x[1]["sim"] or 0) + x[1]["time"]))[:2]
                    first = min(s["start"] for s in segs if s["speaker"] == sp)
                    unresolved.append({
                        "chunk": k, "local": sp, "treated_as": name, "speech_sec": round(total[sp], 1), "start": round(first, 1),
                        "candidates": [{"global": g, "time": r["time"], "sim": r["sim"]} for g, r in best],
                        "reason": "埋め込みがない" if not has_emb else "時刻・埋め込みの証拠が不足または矛盾"})
            for sp, g in mapping.items():                       # 代表埋め込みの更新（対応付けできた話者のみ）
                e = embs.get(sp)
                if e is not None and glob[g]["sum"] is not None and any(m["chunk"] == k and m["local"] == sp and m["global"] == g
                                                                        and m["tier"] in ("時刻一致", "埋め込み") for m in matches):
                    glob[g]["sum"] = glob[g]["sum"] + e * total[sp]
                    glob[g]["w"] += total[sp]
                elif e is not None and glob[g]["sum"] is None:
                    glob[g]["sum"], glob[g]["w"] = e * total[sp], total[sp]
        assembled.append([{**s, "speaker": mapping[s["speaker"]]} for s in segs])

    # ---- 二重出力を避けて切り出し（重なり区間の中点で担当を切り替える）
    out: list[dict] = []
    for k in range(len(chunks)):
        for s in _clip(assembled[k], cut[k], cut[k + 1]):
            out.append({"start": round(s["start"], 3), "end": round(s["end"], 3), "speaker": s["speaker"]})
    out.sort(key=lambda s: (s["start"], s["end"], s["speaker"]))
    joined: list[dict] = []
    cuts = set(round(c, 3) for c in cut[1:-1])
    for s in out:   # 切り出し位置で分断された同一話者の発話だけをつなぐ（それ以外は触らない）
        j = next((x for x in reversed(joined[-8:]) if x["speaker"] == s["speaker"] and abs(x["end"] - s["start"]) < 0.01
                  and round(x["end"], 3) in cuts), None)
        if j is not None:
            j["end"] = s["end"]
        else:
            joined.append(dict(s))
    notes = []
    for u in unresolved:
        cands = "、".join(f"{c['global']}（時刻一致 {c['time']}／埋め込み類似度 {c['sim'] if c['sim'] is not None else 'なし'}）" for c in u["candidates"])
        notes.append(f"チャンク間speaker対応 要確認: チャンク{u['chunk'] + 1}（{_fmt(u['start'])}付近〜）の{u['local']}（約{u['speech_sec']}秒）は、"
                     f"既存の話者と同一人物か確信が持てなかったため、別の話者（{u['treated_as']}）として扱っています。"
                     f"近い候補: {cands}（{u['reason']}）。同じ人物なら、speakers.yaml で同じ名前を割り当てると統合できます。")
    return joined, {"speakers": sorted(glob), "matches": matches, "unresolved": unresolved, "notes": notes,
                    "cut_points": [round(c, 2) for c in cut[1:-1]], "duration": round(duration, 2)}

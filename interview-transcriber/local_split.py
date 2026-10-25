"""localスピーカー内の複数人物の混在を分析する（Step 1: レポートのみ。話者ラベル・transcriptは一切書き換えない）。

背景: pyannoteのlocal speaker（チャンク内のSPEAKER_xx）は1人とは限らない（Track-81 chunk9 local_00 は C→B が混在）。
local全体を全体話者へ対応付けるだけでは、混在localを一括で付け替えてしまう。
そこで localの中の『他の話者と重ならない1.5秒以上の単独区間（anchor）』の声紋を、人物ごとの代表embeddingと比べ、
複数のanchorがまとまって切り替わる場合だけ『分割候補』としてレポートする。

- 1区間だけで話者は確定しない。短い相槌・overlap・無音はanchorにしない。
- HIGH でも書き換えない（このモジュールはレポートを返すだけ）。
- 判定できない区間（境界未確定ゾーン）はどの話者にも割り当てない。
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

import numpy as np

# ---- anchor
ANCHOR_MIN_SEC = 1.5         # anchor候補の最短（これ未満はspeaker確定に使わない）
ANCHOR_GAP_SEC = 0.3         # 同じlocalのsegmentをつなぐ隙間
OTHER_PAD_SEC = 0.1          # 他localの発話の前後の余裕
EMBED_MAX_SEC = 10.0         # 長いanchorは先頭10秒だけ

# ---- confidence（anchor単位）
HIGH_MARGIN = 0.20
MEDIUM_MARGIN = 0.10
LOW_MARGIN = 0.05
MIN_TOP1 = 0.40

# ---- block / split
BLOCK_MIN_ANCHORS = 2
BLOCK_MIN_SEC = 4.0
UNSTABLE_WINDOW_SEC = 60.0   # この間に speaker候補が2回を超えて入れ替わる → unstable
UNSTABLE_CHANGES = 3
SHARED_MIN_RATIO = 0.6       # 隣接チャンクの2つのanchorが、短いほうの60%以上重なる → 同じ音声
SINGLE_MIN_CONFIDENT_RATIO = 0.5   # 『1人のlocal』と言うには、MEDIUM以上のanchorがanchor総秒の過半数を占める必要がある
SIMUL_MIN_SEC = 2.0          # 他の（人物が確定している）localと、blockの区間で同時に話す秒数

_RANK = {"UNKNOWN": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}

Embedder = Callable[[float, float], np.ndarray]


# ------------------------------------------------------------------ anchor抽出
def _merge(iv: list[tuple[float, float]], gap: float) -> list[list[float]]:
    out: list[list[float]] = []
    for a, b in sorted(iv):
        if out and a - out[-1][1] <= gap + 1e-9:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def _subtract(iv: list[list[float]], others: list[tuple[float, float]]) -> list[list[float]]:
    res = []
    for a, b in iv:
        cur = [[a, b]]
        for oa, ob in others:
            nxt = []
            for x, y in cur:
                if ob <= x or oa >= y:
                    nxt.append([x, y])
                else:
                    if oa > x:
                        nxt.append([x, oa])
                    if ob < y:
                        nxt.append([ob, y])
            cur = nxt
        res += cur
    return res


def extract_anchor_spans(segments: list[dict], local: str) -> tuple[list[tuple[float, float]], float]:
    """1つのchunkの全segmentsから、local の anchor区間 [(start, end)] と localの発話合計秒を返す。
    ①同じlocalのsegmentを隙間0.3秒以下でつなぐ ②他localの発話（前後0.1秒）を除外 ③1.5秒以上だけ残す。"""
    own = _merge([(s["start"], s["end"]) for s in segments if s["speaker"] == local], ANCHOR_GAP_SEC)
    others = [(a - OTHER_PAD_SEC, b + OTHER_PAD_SEC) for a, b in _merge([(s["start"], s["end"]) for s in segments if s["speaker"] != local], 0.0)]
    clean = _subtract(own, others)
    speech = sum(b - a for a, b in own)
    return [(a, b) for a, b in clean if b - a >= ANCHOR_MIN_SEC], speech


# ------------------------------------------------------------------ 判定
def confidence_of(margin: float, top1: float) -> str:
    """anchor単位。HIGH: margin>=0.20 かつ top1>=0.40 / MEDIUM: 0.10<=margin<0.20 / LOW: 0.05<=margin<0.10 /
    UNKNOWN: margin<0.05 または top1<0.40。"""
    m, t = round(margin, 6), round(top1, 6)
    if m < LOW_MARGIN or t < MIN_TOP1:
        return "UNKNOWN"
    if m >= HIGH_MARGIN:
        return "HIGH"
    if m >= MEDIUM_MARGIN:
        return "MEDIUM"
    return "LOW"


def _cos(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    return 0.0 if na == 0 or nb == 0 else float(np.dot(a, b) / (na * nb))


def classify_embedding(emb: np.ndarray, refs: dict[str, np.ndarray]) -> dict:
    sims = sorted(((p, _cos(emb, v)) for p, v in refs.items()), key=lambda kv: -kv[1])
    (p1, s1), (p2, s2) = sims[0], (sims[1] if len(sims) > 1 else (None, 0.0))
    margin = s1 - s2
    return {"top1": p1, "top1_sim": round(s1, 4), "top2": p2, "top2_sim": round(s2, 4), "margin": round(margin, 4),
            "confidence": confidence_of(margin, s1)}


def analyze_anchors(chunks: list[dict], embed: Embedder, refs: dict[str, np.ndarray]) -> tuple[list[dict], dict]:
    """全chunk・全localのanchorを作って判定する。(anchorのリスト, {(chunk, local): 発話秒})"""
    anchors, speech = [], {}
    for ch in chunks:
        k = ch["index"]
        for local in sorted({s["speaker"] for s in ch["segments"]}):
            spans, sp = extract_anchor_spans(ch["segments"], local)
            speech[(k, local)] = sp
            for a, b in spans:
                e = embed(a, min(b, a + EMBED_MAX_SEC))
                r = classify_embedding(e, refs)
                anchors.append({"chunk": k, "local": local, "start": round(a, 3), "end": round(b, 3), "duration": round(b - a, 3), **r,
                                "label": None if r["confidence"] == "UNKNOWN" else r["top1"], "shared_with": []})
    return anchors, speech


def build_refs(chunks: list[dict], embed: Embedder, persons: dict[str, list[tuple[int, str]]],
               samples: dict[str, list] | None = None) -> tuple[dict[str, np.ndarray], list[str]]:
    """人物ごとの代表embedding。人間が聞き比べたサンプル（samples、wav）があればその平均を使う。
    無ければ、人間確認済みのanchor（chunk, local）のlocalの単独区間（anchor）のembeddingの平均（長さで重み付け）。
    どちらも取れない人物は参照にしない（警告を返す）。"""
    by_chunk = {c["index"]: c for c in chunks}
    refs, warns = {}, []
    for name, nodes in persons.items():
        files = [f for f in (samples or {}).get(name, []) if Path(f).exists()]
        if files and hasattr(embed, "file"):
            refs[name] = np.mean([embed.file(f) for f in files], axis=0)
            continue
        acc, wsum, used = None, 0.0, 0
        for k, local in nodes:
            ch = by_chunk.get(k)
            if ch is None:
                continue
            spans, _ = extract_anchor_spans(ch["segments"], local)
            for a, b in spans:
                e = embed(a, min(b, a + EMBED_MAX_SEC))
                w = min(b - a, EMBED_MAX_SEC)
                acc = e * w if acc is None else acc + e * w
                wsum += w
                used += 1
        if acc is None:
            warns.append(f"人物{name}は、指定されたlocalに単独区間（1.5秒以上）が無く、参照にできません")
        else:
            refs[name] = acc / wsum
    return refs, warns


# ------------------------------------------------------------------ 共有anchor（隣接chunkで同じ音声）
def _same_audio(a: dict, b: dict) -> bool:
    inter = min(a["end"], b["end"]) - max(a["start"], b["start"])
    return inter > 0 and inter >= SHARED_MIN_RATIO * min(a["duration"], b["duration"])


def link_shared(anchors: list[dict]) -> list[tuple[tuple, tuple]]:
    """隣接chunkの、同じ音声（時間が60%以上重なる）の anchor 同士をつなぎ、shared_with に記録する。localのペアを返す。"""
    by_chunk: dict[int, list[dict]] = {}
    for a in anchors:
        by_chunk.setdefault(a["chunk"], []).append(a)
    pairs = set()
    for k, lst in by_chunk.items():
        for a in lst:
            for b in by_chunk.get(k + 1, []):
                if _same_audio(a, b):
                    a["shared_with"].append(f"chunk{b['chunk']}:{b['local']}")
                    b["shared_with"].append(f"chunk{a['chunk']}:{a['local']}")
                    pairs.add(((a["chunk"], a["local"]), (b["chunk"], b["local"])))
    return sorted(pairs)


def _dedupe(anchors: list[dict]) -> list[dict]:
    """同じ音声のanchorを1つの証拠として数える（confidenceが高い／長いほうを残す）。"""
    keep: list[dict] = []
    for a in sorted(anchors, key=lambda x: (-_RANK[x["confidence"]], -x["duration"], x["chunk"])):
        if not any(_same_audio(a, b) for b in keep):
            keep.append(a)
    return sorted(keep, key=lambda x: x["start"])


# ------------------------------------------------------------------ block・不安定・分割
def build_blocks(anchors: list[dict]) -> tuple[list[dict], bool, list[dict]]:
    """時間順のanchor（UNKNOWNは使わない）から、同じ speaker候補が連続する block を作る。
    返り値: (blocks, unstable, changes)。60秒以内に speaker候補が2回を超えて入れ替わる → unstable。"""
    seq = [a for a in sorted(anchors, key=lambda x: x["start"]) if a["label"] is not None]
    blocks: list[dict] = []
    for a in seq:
        if blocks and blocks[-1]["person"] == a["label"]:
            blocks[-1]["anchors"].append(a)
        else:
            blocks.append({"person": a["label"], "anchors": [a]})
    changes = [{"time": b["anchors"][0]["start"], "from": blocks[i]["person"], "to": b["person"]} for i, b in enumerate(blocks[1:])]
    unstable = any(changes[i + UNSTABLE_CHANGES - 1]["time"] - changes[i]["time"] <= UNSTABLE_WINDOW_SEC
                   for i in range(len(changes) - UNSTABLE_CHANGES + 1))
    out = []
    for b in blocks:
        an = b["anchors"]
        n_high = sum(1 for a in an if a["confidence"] == "HIGH")
        n_med = sum(1 for a in an if a["confidence"] == "MEDIUM")
        sec = round(sum(a["duration"] for a in an), 3)
        valid = len(an) >= BLOCK_MIN_ANCHORS and sec >= BLOCK_MIN_SEC and (n_high >= 1 or n_med >= 2)
        out.append({"person": b["person"], "start": an[0]["start"], "end": an[-1]["end"], "anchors": len(an), "total_sec": sec,
                    "high": n_high, "medium": n_med, "valid": valid,
                    "anchor_list": [{k: a.get(k) for k in ("chunk", "local", "start", "end", "duration", "top1", "top1_sim", "top2", "top2_sim", "margin", "confidence", "shared_with")} for a in an],
                    "high_ok": len(an) >= BLOCK_MIN_ANCHORS and sec >= BLOCK_MIN_SEC and n_high >= 1})
    return out, unstable, changes


def _overlap_sec(segs: list[dict], a: float, b: float) -> float:
    return sum(max(0.0, min(s["end"], b) - max(s["start"], a)) for s in segs)


def assess_unit(anchors: list[dict], members: list[tuple[int, str]], seg_by_chunk: dict[int, list[dict]],
                verified: dict[tuple, str]) -> dict:
    """1つの単位（local、または隣接chunkで同じ音声を共有する2つのlocalをまとめたもの）を評価する。
    verified: {(chunk, local): 人物}（このlocal分析で、単一の人物と確認できたもの）。同時発話の矛盾検査に使う。"""
    pooled = _dedupe(anchors)
    blocks, unstable, changes = build_blocks(pooled)
    warnings: list[str] = []
    persons_ge_medium = {a["label"] for a in pooled if a["label"] and _RANK[a["confidence"]] >= _RANK["MEDIUM"]}
    total_anchor_sec = sum(a["duration"] for a in pooled)
    res = {"members": [f"chunk{k}:{l}" for k, l in members], "anchors": pooled, "blocks": blocks, "changes": changes,
           "proposed_splits": [], "unresolved_zones": [], "warnings": warnings, "unstable": unstable,
           "mixed_suspected": False, "state": "", "confidence": "UNKNOWN", "evidence_state": "ok"}
    if len(pooled) < 2 or total_anchor_sec < BLOCK_MIN_SEC:
        res.update(state="insufficient_evidence", evidence_state="insufficient_evidence", confidence="UNKNOWN")
        warnings.append("判定に使える単独区間（anchor）が不足（2本以上・合計4秒以上が必要）")
        return res
    if unstable:
        res.update(state="unstable", confidence="UNKNOWN")
        warnings.append(f"{int(UNSTABLE_WINDOW_SEC)}秒以内にspeaker候補が{UNSTABLE_CHANGES - 1}回を超えて入れ替わる。local全体を判定不能として扱う")
        return res
    valid = [b for b in blocks if b["valid"]]
    persons_valid = {b["person"] for b in valid}
    res["mixed_suspected"] = len(persons_ge_medium) >= 2
    # 隣り合う有効blockのうち、人物が異なるもの（間に入る根拠不足のblockは境界未確定ゾーンに含める）
    cand = [(valid[i], valid[i + 1]) for i in range(len(valid) - 1) if valid[i]["person"] != valid[i + 1]["person"]]
    for prev, nxt in cand:
        zone = {"start": prev["end"], "end": nxt["start"]}
        speech_in_zone = round(_zone_speech(seg_by_chunk, members, zone), 2)
        high = prev["high_ok"] and nxt["high_ok"]
        why = [f"前: {prev['person']}（anchor {prev['anchors']}本・{prev['total_sec']}秒・HIGH {prev['high']}）",
               f"後: {nxt['person']}（anchor {nxt['anchors']}本・{nxt['total_sec']}秒・HIGH {nxt['high']}）"]
        conf = "HIGH" if high else "MEDIUM"
        conflicts = []
        for blk in (prev, nxt):                                   # 同時発話制約: 同じchunkで同時に話す、人物が確認済みの別localが同じ人物ではないか
            for k, l in members:
                for (k2, l2), person in verified.items():
                    if k2 == k and (k2, l2) not in members and person == blk["person"]:
                        o = _overlap_sec([s for s in seg_by_chunk.get(k, []) if s["speaker"] == l2], blk["start"], blk["end"])
                        if o >= SIMUL_MIN_SEC:
                            conflicts.append(f"chunk{k}:{l2}（人物{person}と確認）が{blk['person']}ブロックと{o:.1f}秒同時に話している")
        if conflicts:
            conf = "MEDIUM" if conf == "HIGH" else conf
            why += ["同時発話制約に矛盾の可能性: " + "; ".join(conflicts)]
            warnings += conflicts
        res["proposed_splits"].append({"from_person": prev["person"], "to_person": nxt["person"], "confidence": conf,
                                       "zone_start": zone["start"], "zone_end": zone["end"], "zone_sec": round(zone["end"] - zone["start"], 2),
                                       "speech_in_zone_sec": speech_in_zone, "assigned_to": None, "why": why,
                                       "conflicts": conflicts, "applied": False,
                                       "prev_block": prev, "next_block": nxt, "unit_unstable": unstable,
                                       "members": [f"chunk{k}:{l}" for k, l in members]})
        res["unresolved_zones"].append({"start": zone["start"], "end": zone["end"], "speech_sec": speech_in_zone, "assigned_to": None,
                                        "reason": "境界未確定（最後の前speaker anchorの終了〜最初の後speaker anchorの開始）"})
    if res["proposed_splits"]:
        best = max(res["proposed_splits"], key=lambda p: _RANK[p["confidence"]])
        res.update(state="split_proposal", confidence=best["confidence"])
    elif res["mixed_suspected"]:
        res.update(state="mixed_suspected", confidence="LOW")
        warnings.append("複数人物のanchorがあるが、片側の根拠が不足（各側 anchor2本以上・4秒以上・HIGHまたはMEDIUM2本が必要）")
    elif persons_valid:
        top = max(valid, key=lambda b: b["total_sec"])
        confident = sum(a["duration"] for a in pooled if _RANK[a["confidence"]] >= _RANK["MEDIUM"])
        if confident < SINGLE_MIN_CONFIDENT_RATIO * total_anchor_sec:
            res.update(state="insufficient_evidence", evidence_state="insufficient_evidence", confidence="UNKNOWN")
            warnings.append(f"MEDIUM以上のanchorがanchor総秒の{SINGLE_MIN_CONFIDENT_RATIO:.0%}未満（{confident:.1f}/{total_anchor_sec:.1f}秒）で、"
                            "1人のlocalとも判定できない")
        else:
            res.update(state="single_person", confidence="HIGH" if top["high_ok"] else "MEDIUM")
    else:
        res.update(state="insufficient_evidence", evidence_state="insufficient_evidence", confidence="UNKNOWN")
        warnings.append("有効なblock（anchor2本以上・4秒以上・HIGH1本またはMEDIUM2本）が無い")
    return res


def _zone_speech(seg_by_chunk: dict[int, list[dict]], members: list[tuple[int, str]], zone: dict) -> float:
    """境界未確定ゾーンに含まれる、メンバーlocalの発話秒。隣接chunkで同じ音声を二重に数えないよう、区間の和集合で数える。"""
    iv = [(max(s["start"], zone["start"]), min(s["end"], zone["end"])) for k, l in members for s in seg_by_chunk.get(k, [])
          if s["speaker"] == l and min(s["end"], zone["end"]) > max(s["start"], zone["start"])]
    return sum(b - a for a, b in _merge(iv, 0.0))


# ------------------------------------------------------------------ 全体
def analyze(chunks: list[dict], embed: Embedder, refs: dict[str, np.ndarray], declared: dict[str, list[tuple[int, str]]] | None = None) -> dict:
    """全chunk・全localを分析する。transcript・話者ラベルは変更しない。
    declared: 人間確認済みの人物とlocal（警告にだけ使う。判定の根拠にはしない）。"""
    if len(refs) < 2:
        raise ValueError("参照話者が2人以上必要です（--speaker-constraints で2人以上の人物を指定してください）")
    anchors, speech = analyze_anchors(chunks, embed, refs)
    pairs = link_shared(anchors)
    seg_by_chunk = {c["index"]: c["segments"] for c in chunks}
    by_local: dict[tuple, list[dict]] = {}
    for a in anchors:
        by_local.setdefault((a["chunk"], a["local"]), []).append(a)
    locals_ = sorted(speech)
    # 1回目: localごと（人物が単一と確認できたものを、同時発話の検査に使う）
    verified: dict[tuple, str] = {}
    first = {}
    for key in locals_:
        r = assess_unit(by_local.get(key, []), [key], seg_by_chunk, {})
        first[key] = r
        if r["state"] == "single_person":
            verified[key] = max((b for b in r["blocks"] if b["valid"]), key=lambda b: b["total_sec"])["person"]
    singles = {key: assess_unit(by_local.get(key, []), [key], seg_by_chunk, verified) for key in locals_}
    pooled_units = {}
    for p, q in pairs:                                   # 隣接chunkで同じ音声を共有するlocalの組（共有anchorは1つの証拠）
        pooled_units[(p, q)] = assess_unit(by_local.get(p, []) + by_local.get(q, []), [p, q], seg_by_chunk, verified)
    decl = {(k, l): name for name, nodes in (declared or {}).items() for k, l in nodes}
    entries = []
    for key in locals_:
        r = singles[key]
        e = {"chunk": key[0], "local": key[1], "speech_sec": round(speech[key], 2),
             "anchor_count": len(by_local.get(key, [])), "anchor_sec": round(sum(a["duration"] for a in by_local.get(key, [])), 2),
             "mixed_suspected": r["mixed_suspected"], "state": r["state"], "confidence": r["confidence"], "evidence_state": r["evidence_state"],
             "unstable": r["unstable"], "anchors": r["anchors"], "blocks": r["blocks"], "proposed_splits": r["proposed_splits"],
             "unresolved_zones": r["unresolved_zones"], "warnings": list(r["warnings"]),
             "evidence_sources": sorted({f"chunk{a['chunk']}:{a['local']}" for a in r["anchors"]}), "pooled_with": []}
        if key in decl:
            e["declared_person"] = decl[key]
            e["warnings"].append(f"人間確認済みの人物{decl[key]}として指定されたlocal"
                                 + ("。ただしこの方式では単独区間が足りず検証できない（insufficient_evidence）" if r["evidence_state"] != "ok" else ""))
        entries.append(e)
    idx = {(e["chunk"], e["local"]): e for e in entries}
    for (p, q), r in pooled_units.items():
        shared = [a for a in r["anchors"] if a["shared_with"]]
        info = {"unit": r["members"], "state": r["state"], "confidence": r["confidence"], "mixed_suspected": r["mixed_suspected"],
                "unstable": r["unstable"], "blocks": r["blocks"], "proposed_splits": r["proposed_splits"],
                "unresolved_zones": r["unresolved_zones"], "warnings": r["warnings"],
                "shared_anchors": [{"start": a["start"], "end": a["end"], "sources": [f"chunk{a['chunk']}:{a['local']}"] + a["shared_with"]} for a in shared]}
        for key in (p, q):
            idx[key]["pooled_with"].append(info)
    # 重複のない分割提案（同じ境界ゾーンは1つにまとめる）
    proposals: list[dict] = []
    def add(prop, unit):
        for q in proposals:
            if abs(q["zone_start"] - prop["zone_start"]) < 1.0 and abs(q["zone_end"] - prop["zone_end"]) < 1.0 \
                    and q["from_person"] == prop["from_person"] and q["to_person"] == prop["to_person"]:
                q["units"].append(unit)
                q["members_all"] = sorted(set(q["members_all"]) | set(prop["members"]))
                if _RANK[prop["confidence"]] > _RANK[q["confidence"]]:
                    q.update(confidence=prop["confidence"], prev_block=prop["prev_block"], next_block=prop["next_block"],
                             conflicts=prop["conflicts"], why=prop["why"])
                return
        proposals.append({**prop, "units": [unit], "members_all": sorted(prop["members"])})
    for key, r in list(singles.items()):
        for pr in r["proposed_splits"]:
            add(pr, r["members"])
    for key, r in pooled_units.items():
        for pr in r["proposed_splits"]:
            add(pr, r["members"])
    proposals.sort(key=lambda p: (-_RANK[p["confidence"]], p["zone_start"]))
    cnt = lambda c: sum(1 for a in anchors if a["confidence"] == c)
    summary = {
        "locals": len(entries), "anchors": len(anchors), "anchor_sec": round(sum(a["duration"] for a in anchors), 1),
        "local_speech_sec": round(sum(speech.values()), 1),
        "anchor_high": cnt("HIGH"), "anchor_medium": cnt("MEDIUM"), "anchor_low": cnt("LOW"), "anchor_unknown": cnt("UNKNOWN"),
        "mixed_suspected_locals": sum(1 for e in entries if e["mixed_suspected"]),
        "high_split_proposals": sum(1 for p in proposals if p["confidence"] == "HIGH"),
        "medium_split_proposals": sum(1 for p in proposals if p["confidence"] == "MEDIUM"),
        "unstable_locals": sum(1 for e in entries if e["unstable"]),
        "insufficient_evidence_locals": sum(1 for e in entries if e["evidence_state"] == "insufficient_evidence"),
        "shared_anchor_links": len(pairs)}
    return {"summary": summary, "locals": entries, "proposed_splits": proposals,
            "thresholds": {"anchor_min_sec": ANCHOR_MIN_SEC, "gap_sec": ANCHOR_GAP_SEC, "embed_max_sec": EMBED_MAX_SEC,
                           "high_margin": HIGH_MARGIN, "medium_margin": MEDIUM_MARGIN, "low_margin": LOW_MARGIN, "min_top1": MIN_TOP1,
                           "block_min_anchors": BLOCK_MIN_ANCHORS, "block_min_sec": BLOCK_MIN_SEC,
                           "unstable": f"{UNSTABLE_CHANGES}回以上の入れ替わりが{UNSTABLE_WINDOW_SEC}秒以内"},
            "reference_persons": sorted(refs), "applied": False,
            "note": "分析のみ。transcript・話者ラベル・diarization結果は変更していません。"}


# ------------------------------------------------------------------ 実行（音声からembedding）
def make_embedder(wav_path, model: str = "pyannote/wespeaker-voxceleb-resnet34-LM", device: str = "cpu") -> Embedder:
    import torch
    import whisperx
    from pyannote.audio.pipelines.speaker_verification import PretrainedSpeakerEmbedding
    em = PretrainedSpeakerEmbedding(model, device=torch.device(device))
    audio = whisperx.load_audio(str(wav_path))
    sr = 16000

    def embed(a: float, b: float) -> np.ndarray:
        x = torch.tensor(audio[int(max(0.0, a) * sr):int(b * sr)])[None, None]
        return np.asarray(em(x)[0]).ravel()

    def embed_file(path) -> np.ndarray:                # 人間が聞き比べた代表サンプル（wav）
        x = torch.tensor(whisperx.load_audio(str(path)))[None, None]
        return np.asarray(em(x)[0]).ravel()
    embed.file = embed_file
    return embed


def run_local_split(chunk_dir, wav_path, constraints: dict, embed: Embedder | None = None, only_persons: list[str] | None = None) -> dict:
    """保存済みチャンクと音声から分析する（ASR・alignment・diarizationは実行しない）。"""
    import diarization_chunks as dc
    state = dc._load(dc.Path(chunk_dir) / "state.json")
    if not state:
        raise FileNotFoundError("保存済みのチャンク（state.json）がありません")
    chunks = [dc._load(dc._chunk_file(dc.Path(chunk_dir), c["index"])) for c in state["chunks"]]
    if any(c is None or "segments" not in c for c in chunks):
        raise FileNotFoundError("保存済みのチャンクが揃っていません")
    embed = embed or make_embedder(wav_path)
    persons = constraints["persons"]
    refs, warns = build_refs(chunks, embed, persons, constraints.get("samples"))
    if only_persons:                                   # 感度分析: 参照話者を絞る（絞った場合、他の人物の声は絞った人物のどちらかに寄る）
        refs = {n: v for n, v in refs.items() if n in only_persons}
        warns.append(f"参照話者を {', '.join(sorted(refs))} に絞った感度分析です")
    rep = analyze(chunks, embed, refs, declared=persons)
    src = {n: ("聞き比べサンプル" if any(Path(f).exists() for f in (constraints.get("samples") or {}).get(n, [])) else "anchor") for n in refs}
    rep["reference_source"] = src
    rep["check_points"] = check_points(rep, constraints.get("check_points") or [])
    rep["warnings"] = warns + [f"参照話者は {', '.join(sorted(refs))} のみ（constraintsに無い話者はtop2に含まれない）"]
    return rep


def check_points(rep: dict, points: list[dict]) -> list[dict]:
    """人間確認済みの時刻・人物（constraintsの check_points）と、その時刻を含むanchorの判定が一致するか（コード上の特別ルールではなく、突き合わせだけ）。"""
    out = []
    for p in points:
        t, who = float(p["time"]), str(p["person"])
        hit = [a for a in (x for e in rep["locals"] for x in e["anchors"]) if a["start"] - 0.5 <= t <= a["end"] + 0.5]
        seen, rows = set(), []
        for a in hit:
            key = (a["start"], a["end"], a["top1"])
            if key in seen:
                continue
            seen.add(key)
            rows.append({"anchor": f"{a['start']:.1f}-{a['end']:.1f}", "chunk_local": f"chunk{a['chunk']}:{a['local']}", "top1": a["top1"],
                         "margin": a["margin"], "confidence": a["confidence"], "match": a["top1"] == who})
        out.append({"time": t, "expected": who, "note": p.get("note", ""), "anchors": rows,
                    "match": bool(rows) and all(r["match"] for r in rows if r["confidence"] != "UNKNOWN") and any(r["confidence"] != "UNKNOWN" for r in rows)})
    return out


# ------------------------------------------------------------------ レポート出力
def _t(sec: float) -> str:
    return f"{int(sec // 60):02d}:{sec % 60:04.1f}（{sec:.0f}秒）"


def write_reports(rep: dict, out_dir) -> tuple[Path, Path]:
    """local_split_report.json と local_split_review.md を書く（transcript・話者ラベルには触れない）。"""
    import json
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    jp, mp = out_dir / "local_split_report.json", out_dir / "local_split_review.md"
    jp.write_text(json.dumps(rep, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    sm = rep["summary"]
    L = ["# local_split_review.md — localスピーカー内の複数人物の混在（分析のみ）", "",
         "**注意: まだtranscript・話者ラベルへ反映していません。HIGH でも書き換えていません（Step 1・レポートのみ）。**",
         "判定できない区間（境界未確定ゾーン）は、どの話者にも割り当てていません。", "",
         "## 全体", "", "| 項目 | 値 |", "|---|---|",
         f"| local総数 | {sm['locals']} |", f"| anchor総数 | {sm['anchors']} |",
         f"| anchorカバー時間 | {sm['anchor_sec']}秒 / local発話 {sm['local_speech_sec']}秒（{sm['anchor_sec'] / max(sm['local_speech_sec'], 1):.0%}） |",
         f"| anchor HIGH / MEDIUM / LOW / UNKNOWN | {sm['anchor_high']} / {sm['anchor_medium']} / {sm['anchor_low']} / {sm['anchor_unknown']} |",
         f"| mixed_suspected local | {sm['mixed_suspected_locals']} |", f"| HIGH split proposal | {sm['high_split_proposals']} |",
         f"| MEDIUM proposal | {sm['medium_split_proposals']} |", f"| unstable local | {sm['unstable_locals']} |",
         f"| evidence不足 local | {sm['insufficient_evidence_locals']} |", f"| 隣接chunkの共有anchorでつながったlocal組 | {sm['shared_anchor_links']} |", "",
         f"参照話者: {', '.join(rep['reference_persons'])}　参照の作り方: {rep.get('reference_source')}", ""]
    for w in rep.get("warnings", []):
        L.append(f"- 注意: {w}")
    L += ["", "## 人間確認済みの時刻との突き合わせ", ""]
    for c in rep.get("check_points", []):
        L.append(f"- {c['time']:.0f}秒付近（人間確認: {c['expected']}　{c['note']}）: " + ("**一致**" if c["match"] else "**不一致または判定なし**"))
        for r in c["anchors"]:
            L.append(f"  - anchor {r['anchor']}（{r['chunk_local']}）: {r['top1']} / {r['confidence']}（margin {r['margin']}）")
    if not rep.get("check_points"):
        L.append("（指定なし）")

    def local_section(e):
        out = [f"### chunk{e['chunk']} {e['local']}（発話{e['speech_sec']}秒・anchor {e['anchor_count']}本）", "",
               f"状態: **{e['state']}**　confidence: **{e['confidence']}**　mixed_suspected: {str(e['mixed_suspected']).lower()}"
               + (f"　人間確認済みの人物: {e['declared_person']}" if e.get("declared_person") else ""), "",
               "anchor:", "", "| 区間 | 長さ | top1 | sim | top2 | sim | margin | confidence | 共有 |", "|---|---|---|---|---|---|---|---|---|"]
        for a in e["anchors"]:
            out.append(f"| {_t(a['start'])}〜{_t(a['end'])} | {a['duration']:.1f}s | {a['top1']} | {a['top1_sim']} | {a['top2']} | {a['top2_sim']} | "
                       f"{a['margin']} | {a['confidence']} | {', '.join(a['shared_with'])} |")
        out += ["", "block:", ""]
        for b in e["blocks"]:
            out.append(f"- {b['person']} block {_t(b['start'])}〜{_t(b['end'])}（anchor {b['anchors']}本・{b['total_sec']}秒・HIGH {b['high']}・MEDIUM {b['medium']}）"
                       + ("　有効" if b["valid"] else "　根拠不足"))
        for p in e["proposed_splits"]:
            out += ["", f"提案（このlocal単独）: {p['from_person']} → 境界未確定ゾーン → {p['to_person']}（{p['confidence']}）　ゾーン {_t(p['zone_start'])}〜{_t(p['zone_end'])}"]
        for pw in e["pooled_with"]:
            for p in pw["proposed_splits"]:
                out += ["", f"提案（{' + '.join(pw['unit'])} の共有証拠を含む）: {p['from_person']} → 境界未確定ゾーン → {p['to_person']}（**{p['confidence']}**）",
                        f"- 境界未確定: {_t(p['zone_start'])}〜{_t(p['zone_end'])}（{p['zone_sec']}秒、うち発話 {p['speech_in_zone_sec']}秒はどちらにも割り当てない）"]
                out += [f"- {w}" for w in p["why"]]
            for sa in pw["shared_anchors"]:
                out.append(f"- 共有anchor（1つの証拠として数える）: {_t(sa['start'])}〜{_t(sa['end'])}　{', '.join(sa['sources'])}")
        for w in e["warnings"]:
            out.append(f"- 注意: {w}")
        out += ["", "注意: まだtranscriptへ反映していない", ""]
        return out
    cp_keys = []
    for c in rep.get("check_points", []):
        for r in c["anchors"]:
            k, l = r["chunk_local"][5:].split(":", 1)
            if (int(k), l) not in cp_keys:
                cp_keys.append((int(k), l))
    byk = {(e["chunk"], e["local"]): e for e in rep["locals"]}
    if cp_keys:
        L += ["", "## 人間確認済みの時刻を含むlocalの詳細（ケーススタディ）", ""]
        for key in cp_keys:
            if key in byk:
                L += local_section(byk[key])
    L += ["", "## HIGH split proposal（代表・最大10件）", ""]
    highs = [p for p in rep["proposed_splits"] if p["confidence"] == "HIGH"][:10]
    if not highs:
        L.append("該当なし。")
    by = {(e["chunk"], e["local"]): e for e in rep["locals"]}
    done = set()
    for p in highs:
        L.append(f"- {p['from_person']} → {p['to_person']}　ゾーン {_t(p['zone_start'])}〜{_t(p['zone_end'])}　対象: " + " / ".join(" + ".join(u) for u in p["units"]))
    for p in highs:
        u = p["units"][0]
        k = tuple([u[-1].split(":")[0][5:], u[-1].split(":", 1)[1]])
        key = (int(k[0]), k[1])
        if key in by and key not in done:
            done.add(key)
            L += [""] + local_section(by[key])
    L += ["", "## MEDIUM proposal", ""]
    meds = [p for p in rep["proposed_splits"] if p["confidence"] == "MEDIUM"]
    for p in meds:
        L.append(f"- {p['from_person']} → {p['to_person']}　ゾーン {_t(p['zone_start'])}〜{_t(p['zone_end'])}　対象: " + " / ".join(" + ".join(u) for u in p["units"])
                 + ("　注意: " + "; ".join(p["conflicts"]) if p["conflicts"] else ""))
    if not meds:
        L.append("該当なし。")
    L += ["", "## mixed_suspected（提案には届かない）", ""]
    for e in rep["locals"]:
        if e["mixed_suspected"] and not e["proposed_splits"]:
            L.append(f"- chunk{e['chunk']} {e['local']}（{e['state']}）: " + "; ".join(e["warnings"][:2]))
    L += ["", "## unstable / evidence不足", ""]
    for e in rep["locals"]:
        if e["unstable"]:
            L.append(f"- unstable: chunk{e['chunk']} {e['local']}")
    ins = [e for e in rep["locals"] if e["evidence_state"] == "insufficient_evidence"]
    L.append(f"- insufficient_evidence: {len(ins)} local（" + ", ".join(f"chunk{e['chunk']}:{e['local'][-2:]}" for e in ins[:30]) + ("…" if len(ins) > 30 else "") + "）")
    for e in rep["locals"]:
        if e.get("declared_person") and e["evidence_state"] == "insufficient_evidence":
            L.append(f"  - chunk{e['chunk']} {e['local']}: 人間確認済みの人物{e['declared_person']}だが、この方式では **insufficient_evidence**（判定に適用しない）")
    L += ["", "## 全local一覧", "", "| chunk:local | 発話 | anchor | 状態 | confidence | mixed |", "|---|---|---|---|---|---|"]
    for e in rep["locals"]:
        L.append(f"| {e['chunk']}:{e['local'][-2:]} | {e['speech_sec']}s | {e['anchor_count']} | {e['state']} | {e['confidence']} | {str(e['mixed_suspected']).lower()} |")
    L += ["", "注意: まだtranscriptへ反映していない（分析のみ）。話者ラベル・turn・01/02/03は変更していません。"]
    mp.write_text("\n".join(L) + "\n", encoding="utf-8")
    return jp, mp


# ------------------------------------------------------------------ Step 2: 適用（opt-in: --apply-local-split）
APPLY_MIN_ANCHORS = 2        # MEDIUM適用: 切替の両側ともanchor2本以上
APPLY_MIN_SEC = 4.0          # 〃 両側とも合計4秒以上


def person_globals(persons: dict[str, list[tuple[int, str]]], mappings: list[dict], chunks: list[dict]) -> tuple[dict[str, str], dict[str, dict]]:
    """人物（人間確認済みのanchor local）→ 全体話者。anchor localの発話量が最も多い全体話者を、その人物の全体話者とする。
    返り値: (人物→全体話者, 人物→{全体話者: 発話秒})。人物のanchorが複数の全体話者に分かれている場合は、そのまま記録する（統合はしない）。"""
    by = {c["index"]: c for c in chunks}
    out, detail = {}, {}
    for name, nodes in persons.items():
        acc: dict[str, float] = {}
        for k, l in nodes:
            if k >= len(mappings) or l not in mappings[k]:
                continue
            sp = sum(s["end"] - s["start"] for s in by[k]["segments"] if s["speaker"] == l)
            acc[mappings[k][l]] = acc.get(mappings[k][l], 0.0) + sp
        if acc:
            out[name] = max(acc, key=lambda g: acc[g])
            detail[name] = {g: round(v, 1) for g, v in acc.items()}
    return out, detail


def _block_brief(b: dict) -> dict:
    return {k: b[k] for k in ("person", "start", "end", "anchors", "total_sec", "high", "medium", "valid")}


def plan_apply(rep: dict, persons: dict[str, list[tuple[int, str]]], mappings: list[dict], chunks: list[dict]) -> dict:
    """分析結果から、書き換えてよいsplit proposalを一般ルールで選び、sub-segment（localの時間範囲）単位のoverridesを作る。
    適用するのは HIGH、および『両側のblockが十分な根拠を持つ』MEDIUM（各側 anchor2本以上・合計4秒以上・同時発話に矛盾なし・unstableでない・
    両側の人物の全体話者が既知）だけ。それ以外はreviewに残す。境界未確定ゾーンは現在の割り当てを維持し、UNRESOLVED SPLIT ZONEとして記録する。
    人間確認の結果などはここには埋め込まない。"""
    pg, pg_detail = person_globals(persons, mappings, chunks)
    seg_by = {c["index"]: c["segments"] for c in chunks}
    applied, skipped, overrides, zones = [], [], [], []
    taken: dict[tuple, list[tuple[float, float, str]]] = {}
    for i, p in enumerate(rep["proposed_splits"], 1):
        pid = f"S{i}"
        prev, nxt = p["prev_block"], p["next_block"]
        reasons = []
        if p["confidence"] not in ("HIGH", "MEDIUM"):
            reasons.append(f"confidence {p['confidence']} は適用対象外")
        for nm, b in (("切替前", prev), ("切替後", nxt)):
            if b["anchors"] < APPLY_MIN_ANCHORS or b["total_sec"] < APPLY_MIN_SEC:
                reasons.append(f"{nm}のblockの根拠が不足（anchor {b['anchors']}本・{b['total_sec']}秒）")
        if p.get("unit_unstable"):
            reasons.append("unstable")
        if p["conflicts"]:
            reasons.append("同時発話制約に矛盾: " + "; ".join(p["conflicts"]))
        for person in (p["from_person"], p["to_person"]):
            if person not in pg:
                reasons.append(f"人物{person}の全体話者が不明（identity不足）")
        zone = {"proposal": pid, "start": p["zone_start"], "end": p["zone_end"], "duration": round(p["zone_end"] - p["zone_start"], 2),
                "speech_sec": p["speech_in_zone_sec"], "prev_speaker": p["from_person"], "next_speaker": p["to_person"],
                "members": p["members_all"], "current_speaker_policy": "現在のspeaker assignmentを維持（UNKNOWN化しない）"}
        zones.append(zone)
        ovs = []
        if not reasons:
            for blk in (prev, nxt):
                g = pg[blk["person"]]
                for m in p["members_all"]:
                    k, l = int(m[5:].split(":", 1)[0]), m.split(":", 1)[1]
                    if k >= len(mappings) or l not in mappings[k]:
                        continue
                    cur = mappings[k][l]
                    has = [s for s in seg_by.get(k, []) if s["speaker"] == l and min(s["end"], blk["end"]) - max(s["start"], blk["start"]) > 1e-6]
                    if not has or cur == g:
                        continue
                    # 変更先の全体話者が、同じchunkの別localとして同時に話していないか（同時発話制約）
                    sim = [o for l2, g2 in mappings[k].items() if g2 == g and l2 != l
                           for o in [sum(max(0.0, min(s["end"], blk["end"]) - max(s["start"], blk["start"])) for s in seg_by.get(k, []) if s["speaker"] == l2)] if o >= SIMUL_MIN_SEC]
                    if sim:
                        reasons.append(f"chunk{k}:{l} を{g}（人物{blk['person']}）へ変える範囲で、別のlocalが{g}として{sim[0]:.1f}秒同時に話している")
                        break
                    ovs.append({"chunk": k, "local": l, "start": blk["start"], "end": blk["end"], "speaker": g, "person": blk["person"],
                                "from_global": cur, "proposal": pid})
        if not reasons:
            for o in ovs:                                   # 同じlocalの同じ範囲を別の人物にする重複は適用しない
                for a, b, g in taken.get((o["chunk"], o["local"]), []):
                    if min(b, o["end"]) - max(a, o["start"]) > 1e-6 and g != o["speaker"]:
                        reasons.append(f"chunk{o['chunk']}:{o['local']} の同じ範囲が別の提案で{g}にされている")
        if reasons:
            skipped.append({"proposal": pid, "from_person": p["from_person"], "to_person": p["to_person"], "confidence": p["confidence"],
                            "zone_start": p["zone_start"], "zone_end": p["zone_end"], "reasons": reasons})
            continue
        new = []
        for o in ovs:
            if not any(abs(x["start"] - o["start"]) < 1e-6 and abs(x["end"] - o["end"]) < 1e-6 and x["chunk"] == o["chunk"] and x["local"] == o["local"] and x["speaker"] == o["speaker"] for x in overrides):
                overrides.append(o)
                taken.setdefault((o["chunk"], o["local"]), []).append((o["start"], o["end"], o["speaker"]))
                new.append(o)
        applied.append({"proposal": pid, "confidence": p["confidence"], "from_person": p["from_person"], "to_person": p["to_person"],
                        "zone_start": p["zone_start"], "zone_end": p["zone_end"], "units": p["units"],
                        "prev_block": _block_brief(prev), "next_block": _block_brief(nxt),
                        "prev_anchors": prev["anchor_list"], "next_anchors": nxt["anchor_list"],
                        "shared_anchors": [a for a in prev["anchor_list"] + nxt["anchor_list"] if a["shared_with"]],
                        "simultaneous_constraint": "違反なし", "overrides": new,
                        "changed_ranges": len(new), "noop": not new, "why": p["why"]})
    # 提案に至らなかったmixed_suspectedもreviewに残す
    mixed = [{"chunk": e["chunk"], "local": e["local"], "state": e["state"], "warnings": e["warnings"][:2]}
             for e in rep["locals"] if e["mixed_suspected"] and not e["proposed_splits"]]
    return {"person_globals": pg, "person_global_detail": pg_detail, "applied": applied, "skipped": skipped, "overrides": overrides,
            "unresolved_zones": zones, "mixed_suspected_not_applied": mixed}


def annotate_original_speakers(turns: list[dict], original_diar: list[dict], names: dict[str, str] | None = None) -> int:
    """各turnに、変更前（元のdiarization）での話者を original_speaker_id に残し、変わったものに local_split_changed を付ける。変更したturn数を返す。"""
    from diarization import overlap_by_speaker
    diar = sorted(original_diar, key=lambda d: d["start"])
    n = 0
    for t in turns:
        ov = overlap_by_speaker(diar, t["start"], max(t["end"], t["start"] + 0.05))
        orig = max(ov, key=lambda k: ov[k]) if ov and sum(ov.values()) / max(t["end"] - t["start"], 0.05) >= 0.3 else None
        t["original_speaker_id"] = orig
        t["original_speaker_name"] = (names or {}).get(orig) if orig else None
        t["local_split_changed"] = bool(orig and t.get("speaker_id") and orig != t["speaker_id"])
        n += t["local_split_changed"]
    return n


def zone_turn_report(plan: dict, turns: list[dict], chunks: list[dict]) -> None:
    """UNRESOLVED SPLIT ZONE ごとに、そのlocalの発話にあたるturn数と現在のspeaker（変更していない）を数える。"""
    by = {c["index"]: c["segments"] for c in chunks}
    for z in plan["unresolved_zones"]:
        sp = []
        for m in z["members"]:
            k, l = int(m[5:].split(":", 1)[0]), m.split(":", 1)[1]
            sp += [(s["start"], s["end"]) for s in by.get(k, []) if s["speaker"] == l and min(s["end"], z["end"]) > max(s["start"], z["start"])]
        sp = _merge(sp, 0.0)
        cnt: dict[str, int] = {}
        n = 0
        for t in turns:
            if t["end"] < z["start"] or t["start"] > z["end"]:
                continue
            d = max(t["end"] - t["start"], 0.05)
            o = sum(max(0.0, min(t["end"], b) - max(t["start"], a)) for a, b in sp)
            if o / d >= 0.5:
                n += 1
                nm = t.get("speaker_name") or t.get("speaker_id") or "不明"
                cnt[nm] = cnt.get(nm, 0) + 1
        z["turns"], z["current_speakers"] = n, cnt


def write_apply_reports(plan: dict, turns: list[dict], out_dir, n_changed: int) -> tuple[Path, Path]:
    """local_split_applied.json（機械可読）と local_split_changes.md（人が読む変更記録）。通常結果と混ぜない運用を推奨する。"""
    import json
    out_dir = Path(out_dir)
    jp, mp = out_dir / "local_split_applied.json", out_dir / "local_split_changes.md"
    changed = [{"id": t.get("id"), "start": t["start"], "end": t["end"], "original_speaker_id": t.get("original_speaker_id"),
                "original_speaker_name": t.get("original_speaker_name"), "speaker_id": t.get("speaker_id"), "speaker_name": t.get("speaker_name"),
                "text": (t.get("raw_text") or "")[:60]} for t in turns if t.get("local_split_changed")]
    data = {**plan, "changed_turns": changed, "summary": {
        "applied_high": sum(1 for a in plan["applied"] if a["confidence"] == "HIGH" and not a["noop"]),
        "applied_medium": sum(1 for a in plan["applied"] if a["confidence"] == "MEDIUM" and not a["noop"]),
        "applied_noop": sum(1 for a in plan["applied"] if a["noop"]), "skipped": len(plan["skipped"]),
        "changed_turns": n_changed, "unresolved_zones": len(plan["unresolved_zones"]),
        "unresolved_zone_sec": round(sum(z["duration"] for z in plan["unresolved_zones"]), 1),
        "unresolved_zone_turns": sum(z.get("turns", 0) for z in plan["unresolved_zones"])}}
    jp.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    sm = data["summary"]
    L = ["# local_split_changes.md — `--apply-local-split` による話者の変更記録（検証機能）", "",
         "**通常結果とは別の出力ディレクトリで運用してください（標準の出力に混ぜない）。** 既定OFFのopt-in機能です。",
         "適用したのは、HIGH proposal、および両側blockが十分な根拠を持つMEDIUM proposalだけです。**境界未確定ゾーンは現在の割り当てを維持**（UNKNOWN化していません）。", "",
         "| 項目 | 値 |", "|---|---|", f"| HIGH適用（変更あり） | {sm['applied_high']} |", f"| MEDIUM適用（変更あり） | {sm['applied_medium']} |",
         f"| 適用対象だが変更なし（すでに同じ話者） | {sm['applied_noop']} |", f"| 適用しなかったproposal | {sm['skipped']} |",
         f"| 変更したturn数 | {sm['changed_turns']} |", f"| UNRESOLVED SPLIT ZONE | {sm['unresolved_zones']}件・{sm['unresolved_zone_sec']}秒・turn {sm['unresolved_zone_turns']} |", "",
         f"人物→全体話者: {plan['person_globals']}（anchorの発話量が最大の全体話者。内訳 {plan['person_global_detail']}）", ""]

    def tc(sec): return f"{int(sec // 3600):02d}:{int(sec % 3600 // 60):02d}:{sec % 60:04.1f}"
    L += ["## 適用した変更", ""]
    if not plan["applied"]:
        L.append("なし。")
    for a in plan["applied"]:
        L += [f"### {a['proposal']}　{a['from_person']} → {a['to_person']}（**{a['confidence']}**）" + ("　※変更なし（すでに同じ話者）" if a["noop"] else ""), ""]
        for o in a["overrides"]:
            L += [f"- タイムコード: {tc(o['start'])}〜{tc(o['end'])}（chunk{o['chunk']}:{o['local']}）", f"  - BEFORE: speaker {o['from_global']}", f"  - AFTER: speaker {o['speaker']}（人物{o['person']}）"]
        for nm, blk, ans in (("切替前", a["prev_block"], a["prev_anchors"]), ("切替後", a["next_block"], a["next_anchors"])):
            L.append(f"- 根拠（{nm}・人物{blk['person']}）: anchor {blk['anchors']}本・合計{blk['total_sec']}秒・HIGH {blk['high']} / MEDIUM {blk['medium']}　block {tc(blk['start'])}〜{tc(blk['end'])}")
            L.append("  - margin: " + ", ".join(f"{x['margin']}({x['confidence']})" for x in ans))
        if a["shared_anchors"]:
            L.append("- shared evidence（隣接chunkで同じ音声。1つの証拠として数えた）: " + ", ".join(f"{tc(x['start'])}〜{tc(x['end'])} {'/'.join(x['shared_with'])}" for x in a["shared_anchors"]))
        L += [f"- simultaneous constraint: {a['simultaneous_constraint']}",
              f"- **UNRESOLVED SPLIT ZONE**: {tc(a['zone_start'])}〜{tc(a['zone_end'])}（{a['zone_end'] - a['zone_start']:.1f}秒）。現在のspeaker assignmentを維持", ""]
    L += ["## UNRESOLVED SPLIT ZONE（境界未確定。変更していません。UNKNOWN化もしていません）", "",
          "| proposal | start | end | 長さ | 発話 | turn数 | 現在のspeaker | 前block | 後block |", "|---|---|---|---|---|---|---|---|---|"]
    for z in plan["unresolved_zones"]:
        L.append(f"| {z['proposal']} | {tc(z['start'])} | {tc(z['end'])} | {z['duration']}s | {z['speech_sec']}s | {z.get('turns', '-')} | "
                 f"{z.get('current_speakers', {})} | {z['prev_speaker']} | {z['next_speaker']} |")
    L += ["", "※ 将来の別opt-in（例: `--unknown-local-split-boundaries`）で話者不明にする案だけを残しています。**今回は実装していません。**", "",
          "## 適用しなかったproposal（review）", ""]
    for s_ in plan["skipped"]:
        L.append(f"- {s_['from_person']}→{s_['to_person']}（{s_['confidence']}）{tc(s_['zone_start'])}〜{tc(s_['zone_end'])}: " + " / ".join(s_["reasons"]))
    if not plan["skipped"]:
        L.append("なし。")
    L += ["", "## mixed_suspected（提案に届かず、自動変更していません）", ""]
    for m in plan["mixed_suspected_not_applied"]:
        L.append(f"- chunk{m['chunk']}:{m['local']}（{m['state']}）: " + "; ".join(m["warnings"]))
    if not plan["mixed_suspected_not_applied"]:
        L.append("なし。")
    L += ["", "## 変更したturn", "", "| id | 時刻 | BEFORE | AFTER | 冒頭 |", "|---|---|---|---|---|"]
    for c in changed:
        L.append(f"| {c['id']} | {tc(c['start'])} | {c['original_speaker_name'] or c['original_speaker_id']} | {c['speaker_name'] or c['speaker_id']} | {c['text'][:30]} |")
    mp.write_text("\n".join(L) + "\n", encoding="utf-8")
    return jp, mp

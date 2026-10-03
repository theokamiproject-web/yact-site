"""WhisperX の alignment 結果＋話者区間 → 発言(turn)リスト → Markdown / JSON。

turn は「同一話者の連続した発話のまとまり」で、最小の追跡単位。各turnは
開始/終了時刻・元のセグメント番号・文字単位の単語タイムスタンプを持つ。
編集（clean / magazine）は turn の id 単位で行い、タイムコードとの対応を失わない。
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from diarization import UNKNOWN_SPEAKER, overlap_by_speaker, speaker_labels
from text_utils import (
    UNCLEAR_RE, close_paragraph, ends_with_question, fmt_ts, is_backchannel, join_fragments,
    is_unfinished_fragment, rule_clean, tidy_punct,
)

SENT_END = "。？！?!"

# 同一話者の発言を同じブロックにまとめる最大の時間差（秒）。暫定値: 実音声(Track-78)で
# 通常の継続・応答は中央値0.16秒・最大0.7秒、発言の切れ目は2.4秒以上と二極化していたため。
DEFAULT_MERGE_GAP = 2.0
# 直前が助詞・接続表現などで終わる「明らかな断片」の続きに限り許す、やや長い時間差（秒）。
DEFAULT_FRAGMENT_GAP = 3.0


def effective_gap(prev_end: float, next_start: float, prev_pause: float) -> float:
    """2つの発言の間の実質的な無音（秒）。

    WhisperX は文間の無音を句読点トークンの長さに含めるため、前の発言の end には無音が入り得る。
    そのぶん（prev_pause）も加える。時刻の逆転は0として扱う。
    """
    return max(0.0, next_start - prev_end) + (prev_pause or 0.0)


def turn_gap(prev: dict, nxt: dict) -> float:
    return effective_gap(prev["end"], nxt["start"], prev.get("pause_after"))



NO_SPACE_LANGS = {"ja", "zh"}


# ------------------------------------------------------------------ tokens
def _tokens_from_aligned(aligned: dict, wr_segments: list[dict] | None) -> list[dict]:
    """alignment結果を 文字/単語トークン列 [{t,start,end,score,seg}] に平坦化。"""
    joiner = "" if aligned.get("language", "ja") in NO_SPACE_LANGS else " "
    tokens: list[dict] = []
    for si, seg in enumerate(aligned["segments"]):
        words = seg.get("words") or []
        logprob = _find_logprob(seg, wr_segments)
        if words:
            for wi, w in enumerate(words):
                t = w["word"] + (joiner if joiner and wi < len(words) - 1 else "")
                tokens.append({"t": t, "start": w.get("start"), "end": w.get("end"),
                               "score": w.get("score"), "seg": si, "logprob": logprob})
        else:  # alignment不能: 文字数で時間を按分
            text = seg["text"].strip()
            n = max(1, len(text))
            dur = (seg["end"] - seg["start"]) / n
            for i, ch in enumerate(text):
                tokens.append({"t": ch, "start": seg["start"] + i * dur, "end": seg["start"] + (i + 1) * dur,
                               "score": None, "seg": si, "logprob": logprob, "approx": True})
    # 時刻欠落（数字等）を前後から補間
    last_end = 0.0
    for i, tk in enumerate(tokens):
        if tk["start"] is None:
            nxt = next((x["start"] for x in tokens[i + 1:] if x["start"] is not None), last_end)
            tk["start"], tk["end"] = last_end, max(last_end, nxt)
        last_end = tk["end"] if tk["end"] is not None else tk["start"]
    return tokens


def _find_logprob(seg: dict, wr_segments: list[dict] | None):
    if "avg_logprob" in seg:
        return seg["avg_logprob"]
    for w in wr_segments or []:
        if w["start"] - 1.0 <= seg["start"] and seg["end"] <= w["end"] + 1.0:
            return w.get("avg_logprob")
    return None


def _assign_token_speakers(tokens: list[dict], diar: list[dict]) -> None:
    diar = sorted(diar, key=lambda d: d["start"])
    for tk in tokens:
        ov = overlap_by_speaker(diar, tk["start"], max(tk["end"], tk["start"] + 0.01))
        tk["speaker"] = max(ov, key=ov.get) if ov else None


def _split_sentence_by_speaker(sent: list[dict], min_run_sec: float, min_chars: int = 4) -> list[list[dict]]:
    """1文の中の話者交替を扱う。短い区間（診断の揺れの可能性が高い）は長い隣接区間へ吸収し、
    十分長い区間だけを別発言として分ける。"""
    runs: list[list[dict]] = []
    for tk in sent:
        if runs and runs[-1][0]["speaker"] == tk["speaker"]:
            runs[-1].append(tk)
        else:
            runs.append([tk])
    while len(runs) > 1:
        short = [k for k, r in enumerate(runs)
                 if (r[-1]["end"] - r[0]["start"]) < min_run_sec or len(r) < min_chars]
        if not short:
            break
        k = min(short, key=lambda k: runs[k][-1]["end"] - runs[k][0]["start"])
        nbrs = [j for j in (k - 1, k + 1) if 0 <= j < len(runs)]
        j = max(nbrs, key=lambda j: runs[j][-1]["end"] - runs[j][0]["start"])
        for tk in runs[k]:
            tk["speaker"] = runs[j][0]["speaker"]
        lo, hi = sorted((j, k))
        runs[lo:hi + 1] = [runs[lo] + runs[hi]]
    return runs


# ------------------------------------------------------------------ turns
def build_turns(aligned: dict, diar: list[dict] | None, whisper_segments: list[dict] | None = None,
                merge_gap: float | None = None, max_chars: int = 140, min_run_sec: float = 0.6,
                mark_unclear_logprob: float | None = None) -> list[dict]:
    tokens = _tokens_from_aligned(aligned, whisper_segments)
    if not tokens:
        return []
    diarized = bool(diar)
    if diarized:
        _assign_token_speakers(tokens, diar)
    else:
        for tk in tokens:
            tk["speaker"] = None
    if merge_gap is None:
        merge_gap = DEFAULT_MERGE_GAP if diarized else 0.6

    # 1) 文末で文に分割 → 文内の話者交替を整理して単位にする
    sentences: list[list[dict]] = []
    cur: list[dict] = []
    for tk in tokens:
        cur.append(tk)
        if tk["t"].strip()[-1:] in SENT_END and tk["t"].strip():
            sentences.append(cur)
            cur = []
    if cur:
        sentences.append(cur)
    units: list[list[dict]] = []
    cuts: list[tuple[bool, bool]] = []  # (cut_start, cut_end): 話者交替で文の途中から始まる / 文の終わり前に切れる
    for sent in sentences:
        runs = _split_sentence_by_speaker(sent, min_run_sec) if diarized else [sent]
        for i, r in enumerate(runs):
            units.append(r)
            cuts.append((i > 0, i < len(runs) - 1))

    # 2) unit → turn（話者決定と信頼度）
    def make(unit: list[dict]) -> dict:
        start, end = unit[0]["start"], unit[-1]["end"]
        text = "".join(t["t"] for t in unit).strip()
        spk = unit[0]["speaker"]
        info = {"speaker_id": spk, "speaker_uncertain": False, "speaker_guess": None}
        if diarized:
            ov = overlap_by_speaker(sorted(diar, key=lambda d: d["start"]), start, max(end, start + 0.05))
            ranked = sorted(ov.items(), key=lambda kv: -kv[1])
            span = max(end - start, 0.05)
            if not ranked or sum(ov.values()) / span < 0.3:
                info.update(speaker_id=None, speaker_uncertain=True)
            elif len(ranked) > 1 and ranked[1][1] >= 0.7 * ranked[0][1] and ranked[1][1] >= 0.3:
                # 重なり発話等で判定が割れる: 人物を確定しない
                info.update(speaker_id=None, speaker_uncertain=True, speaker_guess=ranked[0][0])
        lp = [t["logprob"] for t in unit if t.get("logprob") is not None]
        # WhisperXは文間の無音を句読点トークンの長さに含めるため、末尾の句読点の長さを「間」とみなす
        pause = 0.0
        for tk in reversed(unit):
            if tk["t"].strip() and tk["t"].strip()[-1] in "。、？！?!,.":
                pause += tk["end"] - tk["start"]
            else:
                break
        return {"_pause": pause, "speaker_id": info["speaker_id"], "speaker_uncertain": info["speaker_uncertain"],
                "speaker_guess": info["speaker_guess"], "start": round(start, 3), "end": round(end, 3),
                "raw_text": text,
                "segment_ids": sorted({t["seg"] for t in unit}),
                "words": [[t["t"], round(t["start"], 3), round(t["end"], 3), t["score"]] for t in unit],
                "avg_logprob": (sum(lp) / len(lp)) if lp else None}

    raw_units = []
    for u, (cs, ce) in zip(units, cuts):
        if "".join(t["t"] for t in u).strip():
            m = make(u)
            m["cut_start"], m["cut_end"] = cs, ce
            raw_units.append(m)

    # 3) 同一話者・短い間隔・長すぎない範囲で結合（別話者が挟まれば結合しない）
    turns: list[dict] = []
    for u in raw_units:
        p = turns[-1] if turns else None
        if (p and p["speaker_id"] == u["speaker_id"] and not u["speaker_uncertain"]
                and not p["speaker_uncertain"]
                and effective_gap(p["end"], u["start"], p["_pause"]) <= merge_gap
                and len(p["raw_text"]) + len(u["raw_text"]) <= max_chars):
            p["raw_text"] += u["raw_text"]
            p["end"] = u["end"]
            p["_pause"] = u["_pause"]
            p["cut_end"] = u["cut_end"]
            p["segment_ids"] = sorted(set(p["segment_ids"]) | set(u["segment_ids"]))
            p["words"] += u["words"]
            lps = [x for x in (p["avg_logprob"], u["avg_logprob"]) if x is not None]
            p["avg_logprob"] = sum(lps) / len(lps) if lps else None
        else:
            turns.append(u)
    for i, t in enumerate(turns):
        t["id"] = i
        t["pause_after"] = round(t.pop("_pause", 0.0), 3)
        t["unclear"] = []
        t["low_confidence"] = t["avg_logprob"] is not None and t["avg_logprob"] < -1.0
        if mark_unclear_logprob is not None and t["avg_logprob"] is not None \
                and t["avg_logprob"] < mark_unclear_logprob:
            # オプトイン: 低信頼の発言は本文を [聞き取り不明] に置換し、原文は JSON に退避
            t["unclear"].append({"start": t["start"], "original": t["raw_text"]})
            t["raw_text"] = f"[聞き取り不明 {fmt_ts(t['start'])}]"
    return turns


def apply_speaker_names(turns: list[dict], mapping: dict[str, str]) -> dict[str, str]:
    ids = [t["speaker_id"] for t in turns if t["speaker_id"]]
    labels = speaker_labels(ids, mapping)
    for t in turns:
        t["speaker_name"] = labels.get(t["speaker_id"], UNKNOWN_SPEAKER) if t["speaker_id"] else UNKNOWN_SPEAKER
    return labels


# ------------------------------------------------------------------ clean
def apply_clean(turns: list[dict]) -> None:
    """ルールベースの軽い整文。聞き手の単純な相槌は clean_dropped にする。"""
    for i, t in enumerate(turns):
        t["clean_text"] = rule_clean(t["raw_text"])
        t["clean_dropped"] = False
    for i, t in enumerate(turns):
        text = t["clean_text"]
        prev = turns[i - 1] if i else None
        answers_question = bool(prev and prev["speaker_id"] != t["speaker_id"]
                                and ends_with_question(prev["clean_text"] or prev["raw_text"]))
        if not text.strip(" 。、"):
            t["clean_dropped"], t["clean_text"] = True, ""
        elif t["speaker_id"] is not None and is_backchannel(text) and "？" not in text and "?" not in text and not answers_question \
                and not UNCLEAR_RE.search(text):
            t["clean_dropped"], t["clean_text"] = True, ""


# ------------------------------------------------------------------ render
def render_raw(turns: list[dict], title: str, labels: dict[str, str]) -> str:
    out = [f"# 逐語録（{title}）", ""]
    out += ["話者の割り当て: " + (" / ".join(f"{k}={v}" for k, v in sorted(labels.items())) or "なし（話者分離なし）"), "",
            "※ 音声認識の出力をそのまま保持した編集前の記録です。", ""]
    for t in turns:
        out += [fmt_ts(t["start"]), "", f"{t['speaker_name']}：", t["raw_text"], ""]
    return "\n".join(out)


def render_clean(turns: list[dict], title: str, timestamps: bool = False) -> str:
    """02: 発言(turn)単位。別turnを勝手に結合しない（削除された相槌は飛ばすだけ）。"""
    out = [f"# 軽い整文版（{title}）", "",
           "> フィラー・語頭の言い直し・重複・単独の相槌のみを整理した版です（ルールベース、外部LLM不使用）。", ""]
    for t in turns:
        text = (t.get("clean_text") or "").strip()
        if t.get("clean_dropped") or not text:
            continue
        out += [f"{t['speaker_name']}：", text]
        if timestamps:
            out += ["", f"[{fmt_ts(t['start'])}]"]
        out.append("")
    return "\n".join(out)


def magazine_blocks(turns: list[dict], text_key: str = "edited_text", para_min: int = 120,
                    para_max: int = 240, para_pause: float = 1.0,
                    merge_gap: float = DEFAULT_MERGE_GAP, fragment_gap: float = DEFAULT_FRAGMENT_GAP) -> list[dict]:
    """同一話者の連続発言を1ブロックに結合し、長ければ段落に分ける。

    結合する条件（すべて満たすときだけ）:
      - 同じ話者（話者不明は結合しない）
      - 発言間の時間差が merge_gap 以下（直前が明らかな断片なら fragment_gap 以下）
      - 間に「別話者の採用発言」も「話者不明の発言」も挟まらない
        （単独の相槌・フィラーとして削除された *話者が確定済みの* 発言は壁にしない）
    条件を満たさなければ、同じ話者でも新しいブロック（話者名を再掲）にする。
    turn の ids / start を段落ごとに保持し、元のタイムコードへ遡れる。
    """
    blocks: list[dict] = []
    prev_turn = None
    barrier = False
    for t in turns:
        text = (t.get(text_key) or "").strip()
        if not text:
            if t["speaker_id"] is None:  # 削除された話者不明の発言は、別人の発言だった可能性があるので壁にする
                barrier = True
            continue
        b = blocks[-1] if blocks else None
        same = (b is not None and t["speaker_id"] is not None and b["speaker_id"] == t["speaker_id"]
                and not barrier)
        if same:
            last = b["paras"][-1]
            limit = fragment_gap if (last["cut_end"] or is_unfinished_fragment(last["text"])) else merge_gap
            same = turn_gap(prev_turn, t) <= limit
        if same:
            para = b["paras"][-1]
            ends_sentence = para["text"][-1:] in "。？！?!」"
            long_pause = (prev_turn.get("pause_after") or 0.0) >= para_pause
            if ends_sentence and ((len(para["text"]) >= para_min and long_pause) or len(para["text"]) >= para_max):
                b["paras"].append({"text": text, "start": t["start"], "ids": [t["id"]],
                                   "cut_end": bool(t.get("cut_end"))})
            else:
                para["text"] = join_fragments(para["text"], text)
                para["ids"].append(t["id"])
                para["cut_end"] = bool(t.get("cut_end"))
        else:
            blocks.append({"speaker_id": t["speaker_id"], "speaker_name": t["speaker_name"],
                           "paras": [{"text": text, "start": t["start"], "ids": [t["id"]],
                                      "cut_end": bool(t.get("cut_end"))}]})
        prev_turn = t
        barrier = False
    for b in blocks:
        for p in b["paras"]:
            p["text"] = close_paragraph(tidy_punct(p["text"]), p["cut_end"])
    return blocks


def render_magazine(turns: list[dict], title: str, timestamps: bool = False, note: str | None = None,
                    merge_gap: float = DEFAULT_MERGE_GAP, fragment_gap: float = DEFAULT_FRAGMENT_GAP) -> str:
    out = [f"# 対談（{title}）", ""]
    if note:
        out += [f"> {note}", ""]
    for b in magazine_blocks(turns, merge_gap=merge_gap, fragment_gap=fragment_gap):
        out.append(f"{b['speaker_name']}：")
        for i, p in enumerate(b["paras"]):
            out.append(p["text"])
            if timestamps:
                out += ["", f"[{fmt_ts(p['start'])}]"]
            out.append("")
    return "\n".join(out)


# ------------------------------------------------------------------ JSON
def write_json(path: Path, turns: list[dict], include_words: bool = True) -> None:
    keys = ["id", "speaker_id", "speaker_name", "speaker_uncertain", "speaker_guess", "start", "end",
            "raw_text", "clean_text", "edited_text", "clean_dropped", "edited_dropped",
            "edit_source", "cut_start", "cut_end", "segment_ids", "low_confidence", "avg_logprob", "unclear", "llm_rejected_text"]
    rows = []
    for t in turns:
        row = {k: t.get(k) for k in keys if k in t or k in ("edited_text",)}
        if include_words:
            row["words"] = t.get("words")
        rows.append(row)
    Path(path).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

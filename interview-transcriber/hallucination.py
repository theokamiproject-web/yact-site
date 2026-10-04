"""ASR幻覚・脱落の検出（PHASE 2）。

方針: **正しい短い発話を消すほうが危険**。「反復だから HIGH」ではなく、反復の種類を分類してから確信度を決める。
  - HIGH      : 人間確認なしでも自動不採用が比較的安全なもの（典型ASR幻覚・明白な異常反復）。02/03 から除く。01_raw と raw_text は不変
  - MEDIUM    : 強く怪しいが実発話の可能性がある。削除しない
  - LOW       : 確認価値はあるが根拠が弱い。削除しない
  - NON_SPEECH: 笑い声などの非言語発声の反復。幻覚ではない可能性が高い。削除しない（参考表示のみ）
検出は発言(turn)単位ではなく、**連続する最大3発言の窓**でも行う（ASR/話者分離が1つの幻覚を複数発言に
割ると、発言単位の検査をすり抜けるため）。窓は検査専用で、transcript自体は結合しない。
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from text_utils import is_backchannel
from transcript_builder import turn_gap

HIGH, MEDIUM, LOW, NON_SPEECH = "HIGH", "MEDIUM", "LOW", "NON_SPEECH"

# ---- 既知の典型幻覚定型句（比較は 空白・句読点・長音符を除き小文字化した文字列で行う）
HIGH_PHRASES = [
    "ご視聴ありがとうございました", "ご視聴ありがとうございます", "ご視聴いただきありがとうございました",
    "最後までご視聴", "チャンネル登録", "高評価", "字幕作成", "字幕提供",
    "thankyouforwatching", "thanksforwatching", "subtitlesby",
]
# 通常の発話でも言い得る語。音声末尾など限られた条件のときだけ MEDIUM（要確認）にする
WEAK_PHRASES = [
    "ご清聴ありがとうございました", "ご清聴ありがとうございます", "ありがとうございました",
    "お疲れ様でした", "お疲れさまでした", "おやすみなさい",
]

# ---- 反復ループ
LOOP_MAX_UNIT = 40            # 句・文の長さの反復（「居た時と居なかったですよね」13字など）も対象にする
CHAIN_CAP = 40                # 反復検査用の時系列windowに入れる最大発言数
SIM_THRESHOLD = 0.85          # 言い回しが少し違う反復の類似度（difflib）
NATURAL_UNITS = {"はい", "そう", "うん", "いや", "ええ", "まあ", "ああ", "えー", "なるほど", "そうそう", "いやいや", "はいはい"}
# 笑い声・非言語発声（「ははは」「あっはっは」「ふふ」「へへ」「ひひ」「わはは」「うふふ」「ええええ」…）の構成文字。
# 特定の語を例外にするのではなく、**この文字だけでできた単位の反復**を言語的な反復ループとは別の種類として扱う。
VOCAL_CHARS = set("はひふへほわあうえおっんハヒフヘホワアウエオッン")

_SKIP = re.compile(r"[\s、。，．,.!?！？・…「」『』（）()\[\]ー〜~\-:：;；]")
_PUNCT_END = "。、？！?!,.…"


@dataclass
class Finding:
    kind: str            # phrase / weak_phrase / loop / tail_short / boundary
    confidence: str      # HIGH / MEDIUM / LOW
    turn_ids: list[int]
    reason: str
    text: str = ""       # 対象テキスト（元の表記）
    action: str = "review"          # "reject"（HIGHのみ）/ "review"
    ops: dict[int, tuple[int, int, str]] = field(default_factory=dict)  # turn_id -> (start, end, replacement)
    detail: dict = field(default_factory=dict)


# ------------------------------------------------------------------ 文字列の正規化と位置対応
def sq_map(text: str) -> tuple[str, list[int]]:
    """比較用の正規化文字列と、各文字が元の文字列の何文字目かの対応。"""
    sq, idx = [], []
    for i, ch in enumerate(text):
        for c in unicodedata.normalize("NFKC", ch):
            if not _SKIP.match(c):
                sq.append(c.lower())
                idx.append(i)
    return "".join(sq), idx


def _windows(turns: list[dict], max_gap: float, max_size: int = 3):
    """検査専用の窓: 現在 / 前+現在 / 現在+次 / 前+現在+次 に相当する、連続する最大3発言。"""
    n = len(turns)
    for s in range(n):
        yield [s]
        e = s
        while e + 1 < n and e - s + 1 < max_size and turn_gap(turns[e], turns[e + 1]) <= max_gap:
            e += 1
            yield list(range(s, e + 1))


def _concat(turns: list[dict], ids: list[int]):
    parts, sq, pos = [], [], 0
    for i in ids:
        s, idx = sq_map(turns[i]["raw_text"])
        parts.append((i, s, idx, pos))
        sq.append(s)
        pos += len(s)
    return "".join(sq), parts


def _locate(parts, a: int, b: int) -> dict[int, tuple[int, int]]:
    """窓の連結文字列上の範囲 [a,b) を、各発言の元文字列上の範囲に直す。"""
    out = {}
    for tid, s, idx, off in parts:
        lo, hi = max(a, off), min(b, off + len(s))
        if lo < hi:
            out[tid] = (idx[lo - off], idx[hi - 1 - off] + 1)
    return out


def _extend_punct(raw: str, end: int) -> int:
    while end < len(raw) and raw[end] in "。！!？?、":
        end += 1
    return end


# ------------------------------------------------------------------ 2-1 定型句（複数発言にまたがっても検出）
def detect_phrases(turns: list[dict], max_gap: float = 3.0) -> list[Finding]:
    """既知の典型幻覚定型句（HIGH）。連続する最大3発言の窓で検査するため、複数の発言に割れていても検出できる。"""
    found: dict[tuple, Finding] = {}
    for ids in _windows(turns, max_gap):
        sq, parts = _concat(turns, ids)
        for phrase in HIGH_PHRASES:
            for m in re.finditer(re.escape(phrase), sq):
                loc = _locate(parts, m.start(), m.end())
                if ids[0] not in loc or ids[-1] not in loc:  # 窓の両端の発言にかかる最小の窓だけを採用（重複回避）
                    continue
                key = (phrase, tuple(sorted((t, a, b) for t, (a, b) in loc.items())))
                if key in found:
                    continue
                text = "｜".join(turns[t]["raw_text"][a:b] for t, (a, b) in sorted(loc.items()))
                f = Finding(kind="phrase", confidence=HIGH, turn_ids=sorted(loc), text=text, action="reject",
                            reason=f"既知の典型的な幻覚定型句「{phrase}」" + ("（複数の発言に分かれています）" if len(loc) > 1 else ""),
                            detail={"phrase": phrase, "split_turns": len(loc)})
                for t, (a, b) in loc.items():
                    f.ops[t] = (a, _extend_punct(turns[t]["raw_text"], b), "")
                found[key] = f
    return list(found.values())


# ------------------------------------------------------------------ 2-2 反復ループ（特定語のブラックリストではない）
def is_vocal(unit: str) -> bool:
    """笑い声などの非言語発声だけでできた単位か（「は」「はは」「っは」「あは」「ふふ」「へへ」「ええ」…）。"""
    u = unicodedata.normalize("NFKC", unit)
    return bool(u) and all(c in VOCAL_CHARS for c in u)


def _is_natural(unit: str) -> bool:
    return unit in NATURAL_UNITS or (len(unit) == 4 and unit[:2] == unit[2:] and unit[:2] in NATURAL_UNITS) or is_backchannel(unit)


def _classify_run(unit: str, r: int) -> str | None:
    """反復の種類を先に決め、その種類ごとに確信度を決める。
    非言語発声(笑い声) → NON_SPEECH（幻覚としては扱わない）／ 相槌・自然な言い回し → 簡単に不採用にしない／
    語句・文の異常反復 → HIGH／MEDIUM。"""
    L = len(unit)
    if is_vocal(unit):
        return NON_SPEECH if L * r >= 8 else None
    if _is_natural(unit):
        return HIGH if r >= 12 else (MEDIUM if r >= 6 else None)  # 「はい」「そうそう」等は簡単に不採用にしない
    if L == 1:
        return MEDIUM if r >= 8 else None
    if r >= 6 and L * r >= 12:
        return HIGH
    if L >= 6 and r >= 5:                                         # 句・文の長さの単位が5回以上連続するのは自然な発話ではない
        return HIGH
    if r >= 4:
        return MEDIUM
    return None


def _chains(turns: list[dict], max_gap: float, cap: int = CHAIN_CAP):
    """時系列で近い（隙間 max_gap 秒以内）発言の連なり。反復検査専用のwindowで、transcript自体は結合しない。
    4発言以上の連なりだけを返す（3発言以下は _windows が見る）。長い連なりは cap 発言ずつ（8発言重ねて）区切る。"""
    n, i = len(turns), 0
    while i < n:
        j = i
        while j + 1 < n and turn_gap(turns[j], turns[j + 1]) <= max_gap:
            j += 1
        if j - i + 1 > 3:
            s = i
            while True:
                e = min(j, s + cap - 1)
                yield list(range(s, e + 1))
                if e == j:
                    break
                s = e - 7
        i = j + 1


def _make_loop(turns, loc, unit, r, chars, method, conf, ids_chain=None) -> "Finding":
    text = "｜".join(turns[t]["raw_text"][a:b] for t, (a, b) in sorted(loc.items()))
    spk = len({turns[t].get("speaker_id") for t in loc})
    if conf == NON_SPEECH:
        f = Finding(kind="laughter_repeat", confidence=NON_SPEECH, turn_ids=sorted(loc), text=text,
                    reason=f"非言語の発声（笑い声など）「{unit}」の反復 {r} 回。幻覚ではない可能性が高いため削除していません")
    else:
        what = "語句・文" if len(unit) >= 5 else "短い語句"
        f = Finding(kind="loop", confidence=conf, turn_ids=sorted(loc), text=text,
                    reason=f"同じ{what}「{unit}」が {r} 回連続しています（不自然な反復" + ("・言い回しの揺れを含む" if method == "similar" else "")
                    + ("・複数の発言／話者にまたがる" if len(loc) > 1 else "") + "）")
    f.detail = {"unit": unit, "repeats": r, "chars": chars, "method": method, "speakers": spk, "loc": dict(loc)}
    return f


def _find_exact_loops(turns, ids, parts, sq, found, minimal: bool):
    for m in re.finditer(r"(.{1,%d}?)\1{3,}" % LOOP_MAX_UNIT, sq):
        unit, run = m.group(1), m.group(0)
        r = len(run) // len(unit)
        conf = _classify_run(unit, r)
        if conf is None:
            continue
        loc = _locate(parts, m.start(), m.end())
        if minimal and (ids[0] not in loc or ids[-1] not in loc):
            continue
        key = ("exact", tuple(sorted((t, a, b) for t, (a, b) in loc.items())))
        if key in found:
            continue
        if conf == HIGH and len(unit) < 5 and r < 12:
            raw_run = "".join(turns[t]["raw_text"][a:b] for t, (a, b) in sorted(loc.items()))
            if re.search(r"[、，,。？！?!]", raw_run.rstrip("、，,。？！?!")):
                conf = MEDIUM      # 句読点で区切られた短い語句の反復（「たまたま、たまたま、たまたま」）は話者の意図的な強調の可能性。削除しない
        f = _make_loop(turns, loc, unit, r, len(run), "exact", conf)
        if conf == HIGH:
            f.action = "reject"
            first = True
            for t, (a, b) in sorted(loc.items()):  # 反復は1回分だけ残して畳む（原文は raw に残る）
                f.ops[t] = (a, _extend_punct(turns[t]["raw_text"], b), unit if first else "")
                first = False
        found[key] = f


def _sentences(turns, ids):
    """各発言を文末（。？！）で分けた断片 (turn_id, 開始, 終了, 正規化文字列)。発言をまたいで結合しない。"""
    out = []
    for tid in ids:
        raw = turns[tid]["raw_text"]
        pos = 0
        for m in re.finditer(r"[^。？！?!]+[。？！?!]*", raw):
            sq = sq_map(m.group(0))[0]
            if sq:
                out.append((tid, m.start(), m.end(), sq))
    return out


def _find_similar_loops(turns, ids, found):
    """言い回しが少し揺れた反復（編集距離・類似度）。短い断片(5字以下)は飛ばして、似た文が連続する回数を数える。"""
    import difflib
    sents = [x for x in _sentences(turns, ids) if len(x[3]) >= 6 and not is_vocal(x[3])]
    i = 0
    while i < len(sents):
        j = i + 1
        while j < len(sents) and difflib.SequenceMatcher(None, sents[i][3], sents[j][3]).ratio() >= SIM_THRESHOLD:
            j += 1
        r = j - i
        if r >= 4:
            unit = sents[i][3]
            conf = _classify_run(unit, r)
            if conf is not None and conf != NON_SPEECH:
                loc: dict[int, tuple[int, int]] = {}
                for tid, a, b, _ in sents[i:j]:
                    lo, hi = loc.get(tid, (a, b))
                    loc[tid] = (min(lo, a), max(hi, b))
                key = ("similar", tuple(sorted((t, a, b) for t, (a, b) in loc.items())))
                if key not in found:
                    f = _make_loop(turns, loc, unit, r, sum(len(x[3]) for x in sents[i:j]), "similar", conf)
                    if conf == HIGH:
                        f.action = "reject"
                        first_tid, first_b = sents[i][0], sents[i][2]
                        for tid in sorted({x[0] for x in sents[i:j]}):   # 最初の1回だけ残して、似た繰り返しを畳む
                            pieces = [x for x in sents[i:j] if x[0] == tid]
                            a = first_b if tid == first_tid else pieces[0][1]
                            b = pieces[-1][2]
                            if a < b:
                                f.ops[tid] = (a, b, "")
                    found[key] = f
        i = j if r >= 4 else i + 1


def _dedupe_contained(findings: list["Finding"]) -> list["Finding"]:
    """大きな反復の一部にすぎない finding（同じ事象を窓ごとに数えたもの）を除く。"""
    def size(f):  # 同程度の大きさなら、正確な一致（exact）を優先する
        return sum(b - a for a, b in f.detail["loc"].values()) + (3 if f.detail.get("method") == "exact" else 0)
    order = sorted(range(len(findings)), key=lambda k: (-size(findings[k]), k))
    kept: list[Finding] = []
    for k in order:
        f = findings[k]
        loc = f.detail["loc"]
        if any(all(t in g.detail["loc"] and g.detail["loc"][t][0] <= a + 2 and b <= g.detail["loc"][t][1] + 2
                   for t, (a, b) in loc.items()) for g in kept):
            continue
        kept.append(f)
    return sorted(kept, key=lambda f: (f.turn_ids[0], f.kind))


def detect_loops(turns: list[dict], max_gap: float = 3.0) -> list[Finding]:
    """反復（語句・文・笑い声）の検出。検査用の時系列window（連続する最大3発言／長い連なりは最大40発言）で行い、
    句読点・？！・空白・改行・speaker境界・segment境界の違いは正規化して無視する（transcriptは結合しない）。
    speakerをまたぐだけでは幻覚扱いしない（回数・長さ・種類で決める）。"""
    found: dict[tuple, Finding] = {}
    for ids in _windows(turns, max_gap):
        sq, parts = _concat(turns, ids)
        _find_exact_loops(turns, ids, parts, sq, found, minimal=True)
    for ids in _chains(turns, max_gap):
        sq, parts = _concat(turns, ids)
        _find_exact_loops(turns, ids, parts, sq, found, minimal=False)
        _find_similar_loops(turns, ids, found)
    for ids in _windows(turns, max_gap):
        if len(ids) > 1:
            _find_similar_loops(turns, ids, found)
    return _dedupe_contained(list(found.values()))


# ------------------------------------------------------------------ 2-3 音声末尾・長い無音直前の怪しい発話（要確認のみ）
def _tail_info(t: dict, nxt: dict | None, audio_dur: float | None, chunk_end: bool, audio_end: bool) -> dict:
    speech_end = t.get("speech_end", t["end"])
    gap = (nxt["start"] - speech_end) if nxt else ((audio_dur - speech_end) if audio_dur else None)
    return {"start": t["start"], "speaker": t.get("speaker_name", ""), "text": t["raw_text"],
            "duration": round(max(0.0, speech_end - t["start"]), 2), "silence_after": None if gap is None else round(gap, 1),
            "chunk_end": chunk_end, "audio_end": audio_end}


def _weak_phrase_at_end(turns: list[dict], live: list[int], max_gap: float) -> Finding | None:
    """音声末尾の挨拶的な定型句（通常の発話でも言い得る語）。末尾の最大3発言の窓で、複数発言に割れていても検出する。"""
    last = live[-1]
    for size in (1, 2, 3):
        ids = [i for i in live[-size:]]
        if len(ids) < size or any(turn_gap(turns[x], turns[y]) > max_gap for x, y in zip(ids, ids[1:])):
            break
        sq, parts = _concat(turns, ids)
        if len(sq) > 30:
            break
        for phrase in WEAK_PHRASES:
            for m in re.finditer(re.escape(phrase), sq):
                loc = _locate(parts, m.start(), m.end())
                if last in loc and ids[0] in loc:
                    text = "｜".join(turns[t]["raw_text"][a:b] for t, (a, b) in sorted(loc.items()))
                    return Finding("tail_short", MEDIUM, sorted(loc),
                                   f"音声末尾の挨拶的な短文「{phrase}」" + ("（複数の発言に分かれています）" if len(loc) > 1 else "")
                                   + "。実際の発言の可能性もあるため削除していません", text,
                                   detail={**_tail_info(turns[last], None, None, bool(turns[last].get("chunk_end")), True),
                                           "phrase": phrase, "split_turns": len(loc)})
    return None


def detect_tail(turns: list[dict], audio_dur: float | None = None, silence_sec: float = 3.0,
                short_chars: int = 6, lp_thresh: float = -0.5,
                skip_ids: set[int] | None = None, max_gap: float = 3.0) -> list[Finding]:
    skip_ids = set(skip_ids or ())
    texts = [sq_map(t["raw_text"])[0] for t in turns]
    live = [i for i, s in enumerate(texts) if s]
    if not live:
        return []
    last = live[-1]
    out = []
    weak = _weak_phrase_at_end(turns, live, max_gap)
    if weak and not (set(weak.turn_ids) & skip_ids):
        # 窓の中の最後の発言について、音声末尾の定型句として報告済みにする
        weak.detail.update(_tail_info(turns[last], None, audio_dur, bool(turns[last].get("chunk_end")), True))
        out.append(weak)
        skip_ids |= set(weak.turn_ids)
    for k, i in enumerate(live):
        t, sq = turns[i], texts[i]
        if i in skip_ids:
            continue
        speech_end = t.get("speech_end", t["end"])
        dur = max(0.0, speech_end - t["start"])
        nxt = turns[live[k + 1]] if k + 1 < len(live) else None
        gap = (nxt["start"] - speech_end) if nxt else ((audio_dur - speech_end) if audio_dur else None)
        long_sil = gap is not None and gap >= silence_sec
        chunk_end, audio_end = bool(t.get("chunk_end")), i == last
        lp = t.get("avg_logprob")
        short = len(sq) <= short_chars                      # 音声末尾（MEDIUM）の対象: 6文字以下の短い発言
        tiny = len(sq) <= 3 or is_backchannel(t["raw_text"])  # LOW の対象: 相槌語・ごく短い発言（実在の短文は拾わない）
        detail = _tail_info(t, nxt, audio_dur, chunk_end, audio_end)
        if audio_end and short and (chunk_end or long_sil or (lp is not None and lp < lp_thresh)):
            out.append(Finding("tail_short", MEDIUM, [i], "音声末尾の短い発言（チャンク末尾・長い無音の直前・低信頼のいずれか）。"
                               "実際の発話の可能性もあるため削除していません", t["raw_text"], detail=detail))
        elif tiny and chunk_end and long_sil:
            out.append(Finding("tail_short", LOW, [i], "長い無音の直前、チャンク末尾にある短い発言（相槌の誘発の可能性。"
                               "実際の発話の可能性もあるため削除していません）", t["raw_text"], detail=detail))
    return out


# ------------------------------------------------------------------ 2-5 speaker境界付近の断片（要確認のみ。付け替え・つなぎ直しはしない）
def detect_boundary(turns: list[dict], max_gap: float = 1.0, short_chars: int = 6) -> list[Finding]:
    out = []
    for i in range(len(turns) - 1):
        a, b = turns[i], turns[i + 1]
        if a.get("cut_end") and b.get("cut_start") and turn_gap(a, b) <= max_gap:
            sa, sb = sq_map(a["raw_text"])[0], sq_map(b["raw_text"])[0]
            short = len(sa) <= short_chars or len(sb) <= short_chars
            out.append(Finding("boundary", LOW, [i, i + 1], "文（語）の途中で話者が切り替わった可能性があります"
                               + ("（短い断片）" if short else "") + "。話者の付け替え・文字列のつなぎ直しはしていません",
                               f"…{a['raw_text'][-10:]}｜{b['raw_text'][:10]}…",
                               detail={"short_fragment": short, "from": a.get("speaker_name", ""), "to": b.get("speaker_name", "")}))
    return out


# ------------------------------------------------------------------ 2-6 孤立した挨拶的定型句（文脈の重なりがあるときだけ要確認）
ISOLATION_SEC = 5.0


def detect_isolated_weak(turns: list[dict], audio_dur: float | None = None, skip_ids: set[int] | None = None) -> list[Finding]:
    """「ありがとうございました」などは普通の実発話として非常に多いので、**文字列だけでは判定しない**。
    発言の末尾にあるその句が、次の文脈の重なりを複数もつときだけ要確認にする（削除はしない）:
      iso  : 直前の発話（同じ発言内の前の文字、または前の発言）から 5秒以上離れて孤立している
      chunk: チャンク末尾／音声末尾
      unk  : 話者が不明・不確実
      lowlp: 認識信頼度が低い（avg_logprob < -0.5）
      short: 句以外の文字が6字以下（極端に短い孤立断片）
    iso か chunk のどちらかを含み、合計3つ以上で MEDIUM、2つで LOW。"""
    skip_ids = set(skip_ids or ())
    live = [i for i, t in enumerate(turns) if sq_map(t["raw_text"])[0]]
    last = live[-1] if live else None
    out = []
    for i in live:
        if i in skip_ids:
            continue
        t = turns[i]
        sq, idx = sq_map(t["raw_text"])
        hit = None
        for phrase in WEAK_PHRASES:
            if sq.endswith(phrase) and (hit is None or len(phrase) > len(hit)):
                hit = phrase
        if hit is None:
            continue
        a_raw = idx[len(sq) - len(hit)]
        words = t.get("words") or []
        gap = None
        if words and "".join(w[0] for w in words) == t["raw_text"] and words[a_raw][1] is not None:
            start_ph = words[a_raw][1]
            prev_end = None
            for w in words[:a_raw]:
                if w[0].strip() and w[0] not in _PUNCT_END and w[2] is not None:
                    prev_end = w[2]
            if prev_end is not None:
                gap = start_ph - prev_end
            else:
                k = live.index(i)
                if k:
                    gap = start_ph - turns[live[k - 1]].get("speech_end", turns[live[k - 1]]["end"])
        sig = {}
        sig["iso"] = gap is not None and gap >= ISOLATION_SEC
        sig["chunk"] = bool(t.get("chunk_end")) or i == last
        sig["unk"] = t.get("speaker_id") is None or bool(t.get("speaker_uncertain"))
        lp = t.get("avg_logprob")
        sig["lowlp"] = lp is not None and lp < -0.5
        sig["short"] = len(sq) - len(hit) <= 6
        n = sum(sig.values())
        if not (sig["iso"] or sig["chunk"]) or n < 2:
            continue
        names = {"iso": f"直前の発話から{gap:.0f}秒離れて孤立" if gap is not None else "", "chunk": "チャンク末尾／音声末尾",
                 "unk": "話者が不明・不確実", "lowlp": f"認識信頼度が低い（logprob {lp:.2f}）" if lp is not None else "",
                 "short": "句以外の文字が6字以下"}
        why = "、".join(names[k] for k, v in sig.items() if v)
        end = t.get("speech_end", t["end"])
        out.append(Finding("weak_phrase", MEDIUM if n >= 3 else LOW, [i],
                           f"通常の発話でも言い得る挨拶「{hit}」ですが、次の文脈が重なっています: {why}。"
                           "実際の発言の可能性もあるため削除していません", t["raw_text"],
                           detail={"phrase": hit, "signals": [k for k, v in sig.items() if v], "gap_before": None if gap is None else round(gap, 1),
                                   "start": t["start"], "duration": round(max(0.0, end - t["start"]), 1)}))
    return out


# ------------------------------------------------------------------ まとめ
def detect(turns: list[dict], audio_dur: float | None = None, max_gap: float = 3.0) -> list[Finding]:
    phrases = detect_phrases(turns, max_gap)
    loops = detect_loops(turns, max_gap)
    tail = detect_tail(turns, audio_dur, skip_ids={t for f in phrases for t in f.turn_ids}, max_gap=max_gap)
    weak = detect_isolated_weak(turns, audio_dur, skip_ids={t for f in phrases + tail for t in f.turn_ids})
    return phrases + loops + tail + weak + detect_boundary(turns)


def apply_rejections(turns: list[dict], findings: list[Finding], reject: bool = True) -> None:
    """HIGH の不採用箇所を各発言の reject_ops に記録し、全findingを発言の hallucination に要約して持たせる。
    raw_text は変更しない（01_raw とJSONの raw_text は常に原文）。"""
    for t in turns:
        t["hallucination"] = []
        t["reject_ops"] = []
    for f in findings:
        for tid in f.turn_ids:
            turns[tid]["hallucination"].append({"confidence": f.confidence, "kind": f.kind, "reason": f.reason,
                                                "action": f.action if reject else "review"})
        if reject and f.action == "reject":
            for tid, (a, b, rep) in f.ops.items():
                turns[tid]["reject_ops"].append([a, b, rep])


# ------------------------------------------------------------------ 2-4 ASR未転写候補（削除ではなく警告）
def untranscribed_regions(turns: list[dict], diar: list[dict], min_sec: float, duration: float | None = None,
                          dilate: float = 0.3, merge_gap: float = 0.5, grid: float = 0.05):
    """話者分離が発話ありとした区間のうち、ASRの文字が無い区間を話者ごとに返す。

    被覆は句読点以外の文字の時刻から作る（WhisperXは文間の無音を句読点の長さに含めるため）。
    HIGH幻覚として不採用にした文字は「文字なし」として扱う（実際の発話が転写されていないため）。
    """
    import numpy as np
    total = max([duration or 0.0] + [d["end"] for d in diar] + [t["end"] for t in turns]) + 1.0  # 音声長が短くても区間を落とさない
    n = int(total / grid) + 2
    cov_all, cov_kept = np.zeros(n, bool), np.zeros(n, bool)
    for t in turns:
        words = t.get("words") or []
        rejected = set()
        if t.get("reject_ops") and "".join(w[0] for w in words) == t["raw_text"]:
            pos = 0
            starts = []
            for w in words:
                starts.append(pos)
                pos += len(w[0])
            for a, b, _ in t["reject_ops"]:
                rejected.update(i for i, p in enumerate(starts) if a <= p < b)
        for i, w in enumerate(words):
            ch = w[0].strip()
            if not ch or ch[-1] in _PUNCT_END or w[1] is None:
                continue
            a, b = int(max(0, w[1] - dilate) / grid), int((w[2] + dilate) / grid) + 1
            cov_all[a:b] = True
            if i not in rejected:
                cov_kept[a:b] = True
    speakers = sorted({d["speaker"] for d in diar})
    rows = []
    speech_union = np.zeros(n, bool)
    for d in diar:
        speech_union[int(round(d["start"] / grid)):int(round(d["end"] / grid))] = True
    missing_union = speech_union & ~cov_kept
    for spk in speakers:
        sp = np.zeros(n, bool)
        for d in diar:
            if d["speaker"] == spk:
                sp[int(round(d["start"] / grid)):int(round(d["end"] / grid))] = True
        miss = sp & ~cov_kept
        runs, i = [], 0
        while i < n:
            if miss[i]:
                j = i
                while j < n and miss[j]:
                    j += 1
                runs.append([i * grid, j * grid])
                i = j
            else:
                i += 1
        merged = []
        for r in runs:
            if merged and r[0] - merged[-1][1] <= merge_gap:
                merged[-1][1] = r[1]
            else:
                merged.append(r)
        for a, b in merged:
            if b - a >= min_sec:
                ia, ib = int(round(a / grid)), int(round(b / grid))
                rows.append({"start": round(a, 1), "end": round(b, 1), "duration": round(b - a, 1), "speaker": spk,
                             "rejected_text": bool((cov_all & ~cov_kept)[ia:ib].any())})
    rows.sort(key=lambda r: (r["start"], r["speaker"]))
    speech_sec = speech_union.sum() * grid
    summary = {"speech_sec": round(float(speech_sec), 1), "untranscribed_sec": round(float(missing_union.sum() * grid), 1),
               "ratio": round(float(missing_union.sum() / max(speech_union.sum(), 1)), 3), "min_sec": min_sec,
               "regions": len(rows)}
    return rows, summary


def count_events(findings: list[Finding], turns: list[dict], confidence: str, gap: float = 1.0) -> int:
    """同じ出来事を窓ごとに重複して数えないための事象数（時間範囲が重なる／gap秒以内で隣接する finding を1つにまとめる）。"""
    iv = sorted((turns[f.turn_ids[0]]["start"], turns[f.turn_ids[-1]]["end"]) for f in findings if f.confidence == confidence)
    n, end = 0, None
    for a, b in iv:
        if end is None or a > end + gap:
            n += 1
            end = b
        else:
            end = max(end, b)
    return n

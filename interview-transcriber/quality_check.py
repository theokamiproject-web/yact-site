"""raw と edited を比較し、発言の逸脱を検出して review_required.md を出す。

検出は機械的なヒューリスティック。「問題なし」は「正しい」の保証ではない。
severity: high=自動で採用しない（LLM編集をclean版へ差し戻す）/ medium・low=人の確認用。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from text_utils import (
    UNCLEAR_RE, fmt_ts, is_backchannel, nfkc, number_diff, proper_noun_candidates, squash,
    strip_fillers_aggressive, unit_category,
)

HIGH, MEDIUM, LOW = "high", "medium", "low"

# 意見の強弱・ぼかしを担う語。増減したら要確認
HEDGES = ["たぶん", "多分", "おそらく", "かもしれ", "くらい", "ぐらい", "だいたい", "絶対", "必ず",
          "と思い", "と思う", "と思って", "じゃないか", "ほぼ", "一応"]
NEGATIONS = ["ない", "ません", "ず", "じゃなく", "ではなく", "なかった", "ぬ"]
HALLUCINATIONS = ["ご視聴ありがとうございました", "チャンネル登録", "ご清聴ありがとうございました",
                  "字幕", "おやすみなさい"]


@dataclass
class Issue:
    turn_id: int | None
    start: float | None
    severity: str
    kind: str
    reason: str
    speaker: str = ""
    raw: str = ""
    edited: str = ""
    extra: dict = field(default_factory=dict)


def _ngrams(text: str, n: int = 6) -> set[str]:
    s = squash(text)
    return {s[i:i + n] for i in range(max(0, len(s) - n + 1))}


def check_turn(turn: dict, edited: str, speaker_names: Iterable[str] = (),
               dictionary_terms: list[str] | None = None, neighbors: list[dict] | None = None) -> list[Issue]:
    """1発言ぶんの rawtext → edited を検査する。"""
    raw = turn["raw_text"]
    base = dict(turn_id=turn["id"], start=turn.get("start"), speaker=turn.get("speaker_name", ""),
                raw=raw, edited=edited)
    issues: list[Issue] = []

    def add(sev: str, kind: str, reason: str, **extra):
        issues.append(Issue(severity=sev, kind=kind, reason=reason, extra=extra, **base))

    # 1-4 数字・年月日・金額
    added, missing = number_diff(raw, edited)
    if edited.strip():  # 削除された発言は削除量チェック側で扱う
        for v, u in added:
            cat = unit_category(u)
            add(HIGH, f"{cat}の追加", f"原文に存在しない{cat}「{v}{u}」が追加されています。")
        for v, u in missing:
            cat = unit_category(u)
            if added:
                add(HIGH, f"{cat}の変更", f"原文の{cat}「{v}{u}」が編集後に見当たりません（別の数値に変更された可能性）。")
            else:
                add(MEDIUM, f"{cat}の欠落", f"原文の{cat}「{v}{u}」が編集後に見当たりません。")

    # 5 固有名詞
    raw_sq = squash(raw)
    for pn in sorted(proper_noun_candidates(edited, dictionary_terms)):
        if squash(pn) not in raw_sq:
            add(HIGH, "固有名詞の追加", f"原文に存在しない固有名詞らしき語「{pn}」が編集後に現れています。")

    # 6 話者の混入（本文に他話者のラベル／他話者の発言の流入）
    for name in speaker_names:
        if name and (edited.lstrip().startswith((f"{name}：", f"{name}:"))
                     or f"\n{name}：" in edited):
            add(HIGH, "話者ラベル混入", f"本文中に話者ラベル「{name}：」が含まれています（発言の移動の疑い）。")
    own = _ngrams(raw)
    for nb in neighbors or []:
        if nb["id"] == turn["id"] or nb.get("speaker_id") == turn.get("speaker_id"):
            continue
        leaked = (_ngrams(edited) - own) & _ngrams(nb["raw_text"])
        if len(leaked) >= 3:
            add(HIGH, "別話者の発言混入", f"別の話者（{nb.get('speaker_name','')}・id={nb['id']}）の発言に由来する文言が混入しています。")
            break

    # 7 大量削除（基準=フィラー除去後の原文）
    base_len = len(squash(strip_fillers_aggressive(raw)))
    ed_len = len(squash(edited))
    if base_len >= 25 and ed_len < base_len * 0.55:
        add(MEDIUM, "大量削除", f"フィラー除去後の原文 {base_len} 字に対し、編集後は {ed_len} 字です。")
    if base_len >= 40 and ed_len == 0:
        add(HIGH, "発言の全削除", f"{base_len} 字の発言が全て削除されています。")
    elif base_len >= 6 and ed_len == 0 and not is_backchannel(raw):
        add(MEDIUM, "発言の削除", "相槌ではない発言（フィラー除去後 {} 字）が削除されています。".format(base_len))

    # 8 [聞き取り不明] の補完
    raw_m, ed_m = UNCLEAR_RE.findall(raw), UNCLEAR_RE.findall(edited)
    if raw_m and sorted(raw_m) != sorted(ed_m) and edited.strip():
        add(HIGH, "聞き取り不明の補完", f"原文の {raw_m} が編集後に保持されていません（推測で補完された可能性）。")
    if ed_m and not raw_m:
        add(HIGH, "聞き取り不明の追加", "原文にない [聞き取り不明] が追加されています。")

    # 9 意味の変化（簡易）
    if edited.strip():
        for h in HEDGES:
            a, b = nfkc(raw).count(h), nfkc(edited).count(h)
            if a != b:
                add(MEDIUM, "ニュアンス変化", f"断定・ぼかし表現「{h}」が原文 {a} 回 → 編集後 {b} 回に変わっています（意見の強弱が変わった可能性）。")
        if sum(raw.count(n) for n in ("ない", "ません", "なかった")) != \
                sum(edited.count(n) for n in ("ない", "ません", "なかった")):
            add(HIGH, "否定表現の増減", "否定表現（ない／ません）の数が原文と編集後で異なります（意味反転の可能性）。")
        # 内容語の保持率: 原文の文字2-gramが編集後にどれだけ残るか
        ra, ea = _ngrams(strip_fillers_aggressive(raw), 2), _ngrams(edited, 2)
        if len(ra) >= 12:
            kept = len(ra & ea) / len(ra)
            if kept < 0.5:
                add(MEDIUM, "内容の乖離", f"原文の表現の保持率が {kept:.0%} と低く、書き換えられた可能性があります。")

    return issues


def check_global(turns: list[dict], edited_key: str = "edited_text") -> list[Issue]:
    issues: list[Issue] = []
    raw_len = sum(len(squash(strip_fillers_aggressive(t["raw_text"]))) for t in turns)
    ed_len = sum(len(squash(t.get(edited_key) or "")) for t in turns)
    if raw_len >= 300 and ed_len < raw_len * 0.6:
        issues.append(Issue(None, None, MEDIUM, "全体の大量削除",
                            f"全体で、フィラー除去後の原文 {raw_len} 字 → 編集後 {ed_len} 字（{ed_len / raw_len:.0%}）です。"))
    return issues


def check_all(turns: list[dict], speaker_names: Iterable[str] = (),
              dictionary_terms: list[str] | None = None, edited_key: str = "edited_text") -> list[Issue]:
    issues: list[Issue] = []
    for i, t in enumerate(turns):
        lo, hi = max(0, i - 3), min(len(turns), i + 4)
        issues += check_turn(t, t.get(edited_key) or "", speaker_names, dictionary_terms,
                             turns[lo:hi])
    issues += check_global(turns, edited_key)
    return issues


def check_raw(turns: list[dict]) -> list[Issue]:
    """編集前の逐語録に対する確認事項（認識の幻覚・低信頼・話者不確実）。"""
    issues: list[Issue] = []
    for t in turns:
        base = dict(turn_id=t["id"], start=t["start"], speaker=t.get("speaker_name", ""),
                    raw=t["raw_text"], edited="")
        for h in HALLUCINATIONS:
            if h in t["raw_text"]:
                issues.append(Issue(severity=LOW, kind="音声認識の幻覚疑い",
                                    reason=f"無音区間で出やすい定型句「{h}」を含みます。実際の発言か音声で確認してください。", **base))
        if t.get("low_confidence"):
            issues.append(Issue(severity=LOW, kind="認識信頼度が低い",
                                reason=f"音声認識の平均対数確率が低い区間です（avg_logprob={t['avg_logprob']:.2f}）。聞き取り違いの可能性があります。", **base))
        if t.get("speaker_uncertain"):
            g = t.get("speaker_guess")
            issues.append(Issue(severity=MEDIUM, kind="話者判定が不確実",
                                reason="話者分離の結果が曖昧なため、人物を確定していません"
                                       + (f"（最有力: {g}）。" if g else "。"), **base))
    return issues


def write_review(path, issues: list[Issue], extra_notes: list[str] | None = None,
                 dictionary_candidates: list[dict] | None = None):
    order = {HIGH: 0, MEDIUM: 1, LOW: 2}
    issues = sorted(issues, key=lambda i: (order[i.severity], i.start if i.start is not None else -1))
    lines = ["# 要確認", ""]
    if extra_notes:
        lines += ["## 処理に関する注意", ""] + [f"- {n}" for n in extra_notes] + [""]
    if not issues and not dictionary_candidates:
        lines += ["自動チェックで検出された問題はありません。（ただし機械的な検査であり、正確性の保証ではありません。）", ""]
    label = {HIGH: "重要", MEDIUM: "要確認", LOW: "参考"}
    for i in issues:
        ts = fmt_ts(i.start) if i.start is not None else "全体"
        lines += [f"## {ts}　[{label[i.severity]}] {i.kind}", ""]
        if i.speaker:
            lines += [f"話者: {i.speaker}　(発言ID {i.turn_id})", ""]
        if i.raw:
            lines += ["RAW:", f"> {i.raw}", ""]
        if i.edited or i.extra.get("rejected"):
            lines += ["EDITED:", f"> {i.edited}", ""]
        if i.extra.get("rejected"):
            lines += ["LLMの提案（不採用・clean版へ差し戻し）:", f"> {i.extra['rejected']}", ""]
        lines += [f"理由：\n{i.reason}", ""]
    if dictionary_candidates:
        lines += ["## 辞書による修正候補（自動置換はしていません）", ""]
        for c in dictionary_candidates:
            lines += [f"- {fmt_ts(c['start'])} {c['speaker']}: 「{c['found']}」→ 辞書「{c['term']}」？（類似度 {c['score']:.2f}）"]
        lines.append("")
    from pathlib import Path
    Path(path).write_text("\n".join(lines), encoding="utf-8")

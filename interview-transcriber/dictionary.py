"""固有名詞辞書（dictionary.yaml）。

用途は2つだけ:
  1. WhisperX の initial_prompt に語を渡す（認識の手がかり）
  2. 認識結果に「似た別表記」があれば *候補として* review_required.md に出す

辞書にあるという理由だけで本文を置換することはしない。
"""
from __future__ import annotations

from difflib import SequenceMatcher
from pathlib import Path

import yaml

from text_utils import nfkc


def load_dictionary(path: Path | None) -> dict[str, list[str]]:
    if not path or not Path(path).exists():
        return {}
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    out: dict[str, list[str]] = {}
    for cat, items in data.items():
        if isinstance(items, list):
            out[str(cat)] = [str(x) for x in items if x]
    return out


def all_terms(d: dict[str, list[str]]) -> list[str]:
    seen: list[str] = []
    for items in d.values():
        for t in items:
            if t not in seen:
                seen.append(t)
    return seen


def build_initial_prompt(terms: list[str], max_chars: int = 120) -> str | None:
    """Whisperの初期プロンプト。長すぎると逆効果なので上限を設ける。"""
    if not terms:
        return None
    out = "対談の書き起こし。固有名詞："
    for t in terms:
        if len(out) + len(t) + 1 > max_chars:
            break
        out += t + "、"
    return out.rstrip("、") + "。"


def find_candidates(turns: list[dict], terms: list[str], threshold: float = 0.75) -> list[dict]:
    """辞書語に『似ているが一致しない』語句を探す。置換はしない。"""
    cands: list[dict] = []
    terms = [t for t in terms if len(t) >= 3]
    for turn in turns:
        text = nfkc(turn["raw_text"])
        for term in terms:
            tn = nfkc(term)
            if tn in text:
                continue
            L = len(tn)
            best = None
            for size in (L - 1, L, L + 1):
                for i in range(0, max(0, len(text) - size + 1)):
                    w = text[i:i + size]
                    r = SequenceMatcher(None, w, tn).ratio()
                    if r >= threshold and (best is None or r > best[0]):
                        best = (r, w)
            if best:
                cands.append({"start": turn["start"], "speaker": turn.get("speaker_name", ""),
                              "found": best[1], "term": term, "score": best[0],
                              "turn_id": turn["id"]})
    return cands

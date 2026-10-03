"""日本語テキスト処理の共通ユーティリティ（フィラー除去・数字抽出・正規化）。

ここのルールは「安全側」に倒してある。迷う表現は消さず、LLM編集と
quality_check の確認に回す。
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter

UNCLEAR_RE = re.compile(r"\[聞き取り不明[^\]]*\]")
CLAUSE_END = "、。？！?!"


def fmt_ts(sec: float | None) -> str:
    """秒 → HH:MM:SS"""
    if sec is None:
        return "--:--:--"
    sec = max(0, int(sec))
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def nfkc(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def squash(text: str) -> str:
    """比較用: NFKC・空白/句読点/記号を除去"""
    t = nfkc(text)
    return re.sub(r"[\s、。，．,.!?！？・…「」『』（）()\[\]ー〜~-]", "", t)


# ---------------------------------------------------------------- フィラー
# 引き延ばし形・明らかなフィラー（文節頭にあれば読点の有無を問わず除去）
_FILLER_ALWAYS = (
    r"えー+っと|えーっと|えっと|ええっと|ええと|えーと|えー+|ええー+|"
    r"あのー+|あのう|そのー+|うーん|んー+|うー+ん|あー+|"
    r"まあー+|なんかー+"
)
# 読点を伴うときだけ除去（「あの人」「その後」などの実語と区別する）
_FILLER_COMMA = (
    r"まあ|ま|なんか|なんていうか|なんというか|なんて言うか|なんて言うんですかね|"
    r"あの|その|ほら|こう|ね|なんだろう|なんだろうな|あのね"
)
_RE_FILLER_ALWAYS = re.compile(rf"(?:^|(?<=[、。？！?!]))(?:{_FILLER_ALWAYS})(?:、|,)?")
_RE_FILLER_COMMA = re.compile(rf"(?:^|(?<=[、。？！?!]))(?:{_FILLER_COMMA})(?:、|,)")

_NO_DEDUP = {"はい", "ええ", "うん", "そう", "いや", "ない"}


def _dedupe_repeats(text: str) -> str:
    """『それが、それが』→『それが』（2文字以上の語句の直接反復のみ）"""
    pat = re.compile(r"([^、。？！?!]{2,}?)、(?=\1)")
    prev = None
    while prev != text:
        prev = text

        def repl(m: re.Match) -> str:
            return "" if m.group(1) not in _NO_DEDUP else m.group(0)

        text = pat.sub(repl, text)
    return text


def rule_clean(text: str) -> str:
    """フィラー除去・直接反復の整理・読点の整形。意味のある語は消さない。"""
    if not text:
        return text
    markers: list[str] = []

    def stash(m: re.Match) -> str:
        markers.append(m.group(0))
        return f"\u0000{len(markers) - 1}\u0000"

    t = UNCLEAR_RE.sub(stash, text)
    prev = None
    while prev != t:
        prev = t
        t = _RE_FILLER_ALWAYS.sub("", t)
        t = _RE_FILLER_COMMA.sub("", t)
    t = _dedupe_repeats(t)
    t = re.sub(r"^[、,\s]+", "", t)
    t = re.sub(r"、{2,}", "、", t)
    t = re.sub(r"、([。？！?!])", r"\1", t)
    t = re.sub(r"\u0000(\d+)\u0000", lambda m: markers[int(m.group(1))], t)
    return t.strip()


def strip_fillers_aggressive(text: str) -> str:
    """削除量チェックの基準長を出すための強めのフィラー除去。出力には使わない。"""
    t = rule_clean(text)
    t = re.sub(r"(なんというか|なんていうか|ですね|ですよね)(?=[、。])", "", t)
    return t


# ---------------------------------------------------------------- 相槌
_BACKCHANNELS = {
    "はい", "はいはい", "ええ", "えー", "うん", "うんうん", "うーん", "そう", "そうそう",
    "そうですね", "そうですか", "そうなんですね", "そうなんですか", "そうですよね", "なるほど",
    "なるほどね", "なるほどなるほど", "ああ", "あー", "あーあー", "へえ", "へー", "ふーん",
    "ですね", "そうだね", "そっか", "そうか", "ああそうですか", "ああなるほど", "ああそうなんですね",
}


def is_backchannel(text: str) -> bool:
    body = squash(text)
    return bool(body) and len(body) <= 12 and body in _BACKCHANNELS


def ends_with_question(text: str) -> bool:
    return nfkc(text.strip()).rstrip("」』)） ").endswith(("?", "か。", "かな。", "かね。")) or "？" in text[-3:]


# ---------------------------------------------------------------- 数字
_KD = {"〇": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_KU = {"十": 10, "百": 100, "千": 1000}
_KB = {"万": 10**4, "億": 10**8}
UNITS = "年月日円時分秒歳才人回個本台枚件名倍割%％週間度番階"
_KANJI_NUM = "〇零一二三四五六七八九十百千万億"
NUM_RE = re.compile(
    rf"(?P<ar>\d+(?:\.\d+)?)(?P<armul>[万億千百])?|(?P<kj>[{_KANJI_NUM}]+)"
)


def kanji_to_int(s: str) -> int | None:
    """漢数字列を整数へ。位取りなし（二〇二四）と位取りあり（二千二十四）の両対応。"""
    if not s:
        return None
    if all(c in _KD for c in s):  # 二〇二四 型
        return int("".join(str(_KD[c]) for c in s))
    total, section, num = 0, 0, 0
    for c in s:
        if c in _KD:
            num = num * 10 + _KD[c]
        elif c in _KU:
            section += (num or 1) * _KU[c]
            num = 0
        elif c in _KB:
            total += (section + num or 1) * _KB[c]
            section = num = 0
        else:
            return None
    return total + section + num


def extract_numbers(text: str) -> list[tuple[int | float, str]]:
    """(正規化した数値, 直後の単位) のリスト。全角・漢数字・カンマを正規化して比較可能にする。"""
    t = UNCLEAR_RE.sub(" ", nfkc(text))
    t = re.sub(r"(?<=\d),(?=\d{3})", "", t)
    out: list[tuple[int | float, str]] = []
    for m in NUM_RE.finditer(t):
        end = m.end()
        nxt = t[end] if end < len(t) else ""
        if m.group("ar") is not None:
            v: int | float = float(m.group("ar")) if "." in m.group("ar") else int(m.group("ar"))
            if m.group("armul"):
                v = v * {"万": 10**4, "億": 10**8, "千": 1000, "百": 100}[m.group("armul")]
        else:
            kj = m.group("kj")
            v2 = kanji_to_int(kj)
            if v2 is None:
                continue
            # 単独の漢数字は『一緒』『十分』等の一般語が多いので、単位が付くときだけ数として扱う
            if len(kj) == 1 and not (nxt and nxt in UNITS):
                continue
            v = v2
        out.append((v, nxt if (nxt and nxt in UNITS) else ""))
    return out


def unit_category(unit: str) -> str:
    if unit and unit in "年月日":
        return "年月日"
    if unit == "円":
        return "金額"
    return "数字"


def number_diff(raw: str, edited: str) -> tuple[list, list]:
    """(editedで追加された数値, rawから欠けた数値) を返す。"""
    a, b = Counter(extract_numbers(raw)), Counter(extract_numbers(edited))
    return list((b - a).elements()), list((a - b).elements())


# ---------------------------------------------------------------- 固有名詞候補
_RE_KATAKANA = re.compile(r"[ァ-ヴー]{3,}")
_RE_LATIN = re.compile(r"[A-Za-z][A-Za-z0-9&.\-]{1,}")
_RE_KANJI_PN = re.compile(
    r"[一-龥々〆ヶ]{1,6}(?:市|県|町|村|区|郡|都|府|島|山|川|駅|劇場|劇団|大学|高校|中学校|小学校|"
    r"学校|会社|協会|財団|企画|座|館|ホール|センター|祭|賞)"
)
_RE_PERSON = re.compile(r"[一-龥々]{1,4}(?:さん|氏|先生|監督|くん|ちゃん)")


def proper_noun_candidates(text: str, dictionary_terms: list[str] | None = None) -> set[str]:
    t = UNCLEAR_RE.sub(" ", nfkc(text))
    found: set[str] = set()
    for rx in (_RE_KATAKANA, _RE_LATIN, _RE_KANJI_PN):
        found.update(m.group(0) for m in rx.finditer(t))
    found.update(m.group(0) for m in _RE_PERSON.finditer(t))
    for term in dictionary_terms or []:
        if term and nfkc(term) in t:
            found.add(nfkc(term))
    return found

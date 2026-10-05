"""短い応答の吸収を安全側へ（人間確認 Track-81 R24・R22 を正解とする）。
「短いから前後の話者へ吸収」はしない。独立した応答・overlap・pyannoteの支持があるものは残し、
前後が同一話者で語の断片であることが明らかな場合だけ前後へ戻す。迷ったら残して review_required で要確認。"""
import pytest

import quality_check as qc
import transcript_builder as tb
from helpers import make_aligned


def build(text, segs, **kw):
    """text を 0.1秒/文字 で並べ、segs=[(speaker, 開始文字位置, 終了文字位置)] を pyannote 区間とする"""
    al, _ = make_aligned([("SPEAKER_00", text)], 0.1)
    diar = [{"start": a * 0.1, "end": b * 0.1, "speaker": s} for s, a, b in segs]
    return tb.build_turns(al, diar, None, **kw)


def seq(turns):
    return [(t["speaker_id"], t["raw_text"]) for t in turns]


# ---------------------------------------------------------------- R24型: 別話者の「うーん」を消さない
def test_r24_backchannel_between_the_same_speaker_is_kept():
    text = "それは多分いかなって焼くうーん俺が違ったら面白いと思うんだよね"
    i = text.index("うーん")
    n = len(text)
    turns = build(text, [("SPEAKER_03", 0, i), ("SPEAKER_01", i, i + 3), ("SPEAKER_03", i + 3, n)])
    assert ("SPEAKER_01", "うーん") in seq(turns)                      # 別話者の「うーん」は独立した応答として残る
    assert [t["speaker_id"] for t in turns] == ["SPEAKER_03", "SPEAKER_01", "SPEAKER_03"]


@pytest.mark.parametrize("word", ["はい", "うん", "そう", "ええ", "いや", "へえ", "なるほど", "うーん", "あ"])
def test_independent_short_responses_are_never_absorbed(word):
    text = "この企画はもともと三人で始めたんですよ" + word + "それで少しずつ広がっていきました"
    i = text.index(word, 10)
    n = len(text)
    turns = build(text, [("SPEAKER_00", 0, i), ("SPEAKER_01", i, i + len(word)), ("SPEAKER_00", i + len(word), n)])
    assert ("SPEAKER_01", word) in seq(turns)


def test_short_response_is_kept_even_without_pyannote_support_and_flagged_for_review():
    text = "この企画はもともと三人で始めたんですよはいそれで少しずつ広がっていきました"
    i = text.index("はい", 10)
    turns = build(text, [("SPEAKER_00", 0, i), ("SPEAKER_01", i, i + 2), ("SPEAKER_00", i + 2, len(text))])
    t = next(t for t in turns if t["raw_text"] == "はい")
    assert t["short_kept"] is True and t["speaker_id"] == "SPEAKER_01"


# ---------------------------------------------------------------- R22型: 別人の発言を前後の話者へ吸収しない
def test_r22_other_speakers_utterance_is_not_absorbed_into_the_previous_speaker():
    text = "それうちの話そうですよ蜂蜜アメ"
    segs = [("SPEAKER_01", 0, 6), ("SPEAKER_02", 6, 8), ("SPEAKER_01", 8, 11), ("SPEAKER_00", 11, 13), ("SPEAKER_01", 13, 15)]
    turns = build(text, segs)
    who = {t["raw_text"]: t["speaker_id"] for t in turns}
    assert who.get("そう") == "SPEAKER_02"                              # 「そう」（別話者）は残る
    assert any(t["speaker_id"] == "SPEAKER_00" for t in turns)          # 蜂蜜（A）は、短いからというだけでBへ吸収しない
    assert not any("そうですよ蜂蜜アメ" in t["raw_text"] and t["speaker_id"] == "SPEAKER_01" for t in turns)


def test_short_run_of_another_speaker_is_not_absorbed_just_because_it_is_short():
    text = "最初はそんなに大きなことをやろうとは思ってなかったんですよ蜂蜜それで広がった"
    i = text.index("蜂蜜")
    turns = build(text, [("SPEAKER_00", 0, i), ("SPEAKER_01", i, i + 2), ("SPEAKER_00", i + 2, len(text))])
    assert ("SPEAKER_01", "蜂蜜") in seq(turns)


# ---------------------------------------------------------------- 語の断片だけは、強い根拠がある場合に限り前後へ戻す
def test_non_word_fragment_between_the_same_speaker_may_be_smoothed():
    # A:オファ B:ー A:について（Bの「ー」は独立した発話として成立しない）。語単位割当を切って、断片の平滑化だけを見る
    text = "そういえばあのオファーについて聞いたんですけどね"
    i = text.index("ー")
    n = len(text)
    turns = build(text, [("SPEAKER_00", 0, i), ("SPEAKER_01", i, i + 1), ("SPEAKER_00", i + 1, n)], word_vote=False)
    assert [t["speaker_id"] for t in turns] == ["SPEAKER_00"] and turns[0]["raw_text"] == text


def test_fragment_with_pyannote_support_is_not_smoothed():
    text = "そういえばあのオファーについて聞いたんですけどね"
    i = text.index("ー")
    n = len(text)
    # Bの区間が0.5秒（十分に長い）で、その短い区間を覆っている = 独立した発話の支持あり
    al, _ = make_aligned([("SPEAKER_00", text)], 0.1)
    diar = [{"start": 0.0, "end": i * 0.1, "speaker": "SPEAKER_00"}, {"start": i * 0.1 - 0.2, "end": i * 0.1 + 0.4, "speaker": "SPEAKER_01"},
            {"start": i * 0.1 + 0.4, "end": n * 0.1, "speaker": "SPEAKER_00"}]
    turns = tb.build_turns(al, diar, None, word_vote=False)
    assert any(t["speaker_id"] == "SPEAKER_01" for t in turns)


def test_fragment_inside_overlap_is_not_smoothed():
    text = "そういえばあのオファーについて聞いたんですけどね"
    i = text.index("ー")
    n = len(text)
    al, _ = make_aligned([("SPEAKER_00", text)], 0.1)
    diar = [{"start": 0.0, "end": n * 0.1, "speaker": "SPEAKER_00"}, {"start": i * 0.1, "end": i * 0.1 + 0.1, "speaker": "SPEAKER_01"}]
    turns = tb.build_turns(al, diar, None, word_vote=False)
    assert all(t["speaker_id"] in ("SPEAKER_00", None) for t in turns)       # 重なりは別人扱いにせず、確定もしない（吸収の対象外）


def test_low_confidence_fragment_is_kept_when_neighbors_differ():
    text = "それは本当にそうなんですよねえ今日は楽しかったです"
    i = text.index("本当")
    turns = build(text, [("SPEAKER_00", 0, i), ("SPEAKER_01", i, i + 2), ("SPEAKER_02", i + 2, len(text))])
    assert any(t["speaker_id"] == "SPEAKER_01" for t in turns)                # 前後が別人 → 吸収しない


def test_long_runs_are_unchanged():
    text = "最初はそんなに大きなことをやろうとは思っていなかったんですよね。そうだったんですか。"
    i = text.index("そうだったんですか")
    turns = build(text, [("SPEAKER_00", 0, i), ("SPEAKER_01", i, len(text) + 10)])
    assert [t["speaker_id"] for t in turns] == ["SPEAKER_00", "SPEAKER_01"]


# ---------------------------------------------------------------- review_required
def test_short_kept_turns_are_listed_for_review():
    text = "この企画はもともと三人で始めたんですよはいそれで少しずつ広がっていきました"
    i = text.index("はい", 10)
    turns = build(text, [("SPEAKER_00", 0, i), ("SPEAKER_01", i, i + 2), ("SPEAKER_00", i + 2, len(text))])
    for t in turns:
        t["speaker_name"] = t["speaker_id"]
    md = "\n".join(qc._render_short_turns(turns))
    assert "短い別話者" in md and "はい" in md and "吸収していません" in md

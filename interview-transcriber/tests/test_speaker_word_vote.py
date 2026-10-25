"""話者割当の境界処理: 日本語の語（形態素）の途中でspeakerを分けない。短い実在の応答・overlap・話者不明は無理に統合しない。
Track-81 の調査: 語の内部にある話者境界は142件。原因は『1文字=1wordの文字ごとの話者割当 × 文字時刻とpyannote境界の100〜300msのずれ』。"""
import pytest

import transcript_builder as tb
from helpers import make_aligned

pytestmark = pytest.mark.skipif(not tb.word_vote_available(), reason="janome 未導入")


def aligned_text(text, char_dur=0.1):
    al, _ = make_aligned([("SPEAKER_00", text)], char_dur)
    return al


def at(text, ch, char_dur=0.1, nth=0):
    """text の中で ch（nth番目）が始まる時刻"""
    return text.index(ch) * char_dur if nth == 0 else None


def build(text, diar, **kw):
    return tb.build_turns(aligned_text(text), diar, None, **kw)


TEXT = "今日はその話をしてそれから本当に死ぬかと思った。"


def midword_diar():
    t = TEXT.index("本") * 0.1
    cut = t + 0.06            # 「本」の途中でpyannoteが切り替わる（文字時刻とのずれ）
    end = len(TEXT) * 0.1 + 1.0
    return [{"start": 0.0, "end": cut, "speaker": "SPEAKER_00"}, {"start": cut, "end": end, "speaker": "SPEAKER_01"}]


def test_baseline_character_level_assignment_splits_inside_a_word():
    turns = build(TEXT, midword_diar(), word_vote=False)          # 従来: 文字ごと
    assert turns[0]["raw_text"].endswith("本") and turns[1]["raw_text"].startswith("当に")


def test_word_vote_keeps_a_japanese_word_in_one_speaker():
    turns = build(TEXT, midword_diar())
    assert len(turns) == 2 and turns[0]["speaker_id"] == "SPEAKER_00" and turns[1]["speaker_id"] == "SPEAKER_01"
    assert turns[0]["raw_text"].endswith("それから") and turns[1]["raw_text"].startswith("本当に")     # 「本当に」が分断されない
    assert turns[0]["raw_text"] + turns[1]["raw_text"] == TEXT                                          # 文字は増減しない（作文しない）


def test_word_vote_moves_the_boundary_to_the_side_with_more_evidence():
    # 「本」の大半がSPEAKER_00と重なるなら、語全体がSPEAKER_00になる
    t = TEXT.index("本") * 0.1
    cut = t + 0.2             # 「本当に」(0.3秒)のうち 0.2秒 がSPEAKER_00
    diar = [{"start": 0.0, "end": cut, "speaker": "SPEAKER_00"}, {"start": cut, "end": len(TEXT) * 0.1 + 1, "speaker": "SPEAKER_01"}]
    turns = build(TEXT, diar)
    assert turns[0]["raw_text"].endswith("それから本当に") and turns[1]["raw_text"].startswith("死ぬ")


def test_real_speaker_change_at_a_word_boundary_is_kept():
    t = TEXT.index("本") * 0.1
    diar = [{"start": 0.0, "end": t, "speaker": "SPEAKER_00"}, {"start": t, "end": len(TEXT) * 0.1 + 1, "speaker": "SPEAKER_01"}]
    turns = build(TEXT, diar)
    assert [x["speaker_id"] for x in turns] == ["SPEAKER_00", "SPEAKER_01"] and turns[1]["raw_text"].startswith("本当に")


def test_very_short_flip_a_b_a_is_still_smoothed():
    text = "最初はそんなに大きなことをやろうとは思ってなかったんですよね。"
    t = text.index("大") * 0.1
    diar = [{"start": 0.0, "end": t, "speaker": "SPEAKER_00"}, {"start": t, "end": t + 0.15, "speaker": "SPEAKER_01"},
            {"start": t + 0.15, "end": len(text) * 0.1 + 1, "speaker": "SPEAKER_00"}]
    turns = build(text, diar)
    assert len(turns) == 1 and turns[0]["speaker_id"] == "SPEAKER_00"


def test_independent_short_replies_are_kept_as_their_own_turns():
    # 独立した「はい。」「うん。」は、別話者の実在の応答として残す
    al, diar = make_aligned([("SPEAKER_00", "この企画はもともと三人で始めたんです。"), ("SPEAKER_01", "はい。"),
                             ("SPEAKER_00", "それで少しずつ広がっていきました。"), ("SPEAKER_01", "うん。"),
                             ("SPEAKER_00", "いまは十人くらいです。")])
    turns = tb.build_turns(al, diar, None)
    pairs = [(t["speaker_id"], t["raw_text"]) for t in turns]
    assert ("SPEAKER_01", "はい。") in pairs and ("SPEAKER_01", "うん。") in pairs


def test_overlap_is_not_forced_into_one_speaker():
    text = "それは本当にそうなんですよねえ。"
    end = len(text) * 0.1 + 1
    diar = [{"start": 0.0, "end": end, "speaker": "SPEAKER_00"}, {"start": 0.0, "end": end, "speaker": "SPEAKER_01"}]
    turns = build(text, diar)
    assert all(t["speaker_id"] is None and t["speaker_uncertain"] for t in turns)       # 人物を確定しない


def test_speaker_unknown_is_not_assigned_without_evidence():
    text = "それは本当にそうなんですよねえ。"
    turns = build(text, [{"start": 100.0, "end": 110.0, "speaker": "SPEAKER_00"}])    # この区間にpyannoteの発話なし
    assert all(t["speaker_id"] is None for t in turns)


def test_without_janome_it_falls_back_to_the_previous_behavior(monkeypatch):
    monkeypatch.setattr(tb, "_JanomeTokenizer", None)
    assert not tb.word_vote_available()
    turns = build(TEXT, midword_diar())
    assert turns[0]["raw_text"].endswith("本")                                           # 文字単位のまま（エラーにしない）


def test_non_japanese_is_not_affected():
    al = aligned_text("hello world again")
    al["language"] = "en"
    turns = tb.build_turns(al, [{"start": 0, "end": 5, "speaker": "SPEAKER_00"}], None)
    assert turns and turns[0]["speaker_id"] == "SPEAKER_00"


def test_long_vocal_run_is_not_forced_into_one_speaker():
    # 2人が重なって出している長い「ぉぉぉぉ…」（語ではない）は、語単位の多数決で1人にまとめない
    text = "それは" + "ぉ" * 20 + "ですよね。"
    t = (3 + 10) * 0.1
    diar = [{"start": 0.0, "end": t, "speaker": "SPEAKER_00"}, {"start": t, "end": len(text) * 0.1 + 1, "speaker": "SPEAKER_01"}]
    turns = build(text, diar)
    assert {x["speaker_id"] for x in turns} == {"SPEAKER_00", "SPEAKER_01"}

"""PHASE 2: 幻覚検出（隣接発言をまたぐ定型句・反復ループ・音声末尾/無音直前・未転写・話者境界）。"""
import pytest

import hallucination as hal
import transcript_builder as tb
from hallucination import HIGH, LOW, MEDIUM


def T(i, text, start, end=None, spk="S0", **kw):
    end = start + 1.0 if end is None else end
    t = {"id": i, "speaker_id": spk, "speaker_name": spk, "start": start, "end": end, "speech_end": end,
         "pause_after": 0.0, "raw_text": text, "edited_text": text, "clean_text": text}
    t.update(kw)
    return t


def kinds(fs, conf=None):
    return [(f.kind, f.confidence) for f in fs if conf is None or f.confidence == conf]


def high(fs):
    return [f for f in fs if f.confidence == HIGH]


# ---------------------------------------------------------------- 1) 定型句
def test_known_phrase_in_a_single_turn_is_high():
    turns = [T(0, "今日は楽しかったです。", 0), T(1, "ご視聴ありがとうございました。", 10)]
    fs = hal.detect_phrases(turns)
    assert len(fs) == 1 and fs[0].confidence == HIGH and fs[0].action == "reject" and fs[0].turn_ids == [1]


def test_phrase_split_across_two_turns_is_detected():
    # Track-78: 「ご視聴ありがとうござ」(話者B) + 「いました。」(話者不明)
    turns = [T(0, "作んないと。", 0), T(1, "ご視聴ありがとうござ", 3.0, 5.0, spk="B"), T(2, "いました。", 5.1, 6.0, spk="X")]
    fs = hal.detect_phrases(turns)
    assert len(fs) == 1 and fs[0].turn_ids == [1, 2] and fs[0].confidence == HIGH
    assert "複数の発言" in fs[0].reason and "｜" in fs[0].text


def test_phrase_split_across_three_turns_is_detected():
    turns = [T(0, "ご視聴", 0), T(1, "ありがとう", 1.1), T(2, "ございました", 2.2)]
    fs = hal.detect_phrases(turns)
    assert len(fs) == 1 and fs[0].turn_ids == [0, 1, 2] and fs[0].confidence == HIGH


def test_phrase_pieces_far_apart_are_not_joined():
    turns = [T(0, "ご視聴ありがとうござ", 0), T(1, "いました", 30.0)]   # 30秒離れている → 窓に入れない
    assert hal.detect_phrases(turns) == []


def test_each_phrase_is_reported_once_not_per_window():
    turns = [T(0, "前の発言です。", 0), T(1, "ご視聴ありがとうございました", 2), T(2, "次の発言です。", 4)]
    assert len(hal.detect_phrases(turns)) == 1


# ---------------------------------------------------------------- 2) 反復ループ
@pytest.mark.parametrize("unit,n", [("奥を", 8), ("そのまま", 7), ("ABC", 6), ("あれは", 9)])
def test_abnormal_repetition_loop_is_detected_without_a_blacklist(unit, n):
    turns = [T(0, "これごめん、" + unit * n, 0)]
    fs = hal.detect_loops(turns)
    assert len(fs) == 1 and fs[0].confidence == HIGH and fs[0].detail["unit"].lower() == unit.lower()


def test_loop_is_collapsed_to_one_unit_and_raw_is_untouched():
    turns = [T(0, "Let'sparty!これごめん、" + "奥を" * 8, 0)]
    fs = hal.detect_loops(turns)
    hal.apply_rejections(turns, fs)
    assert turns[0]["raw_text"].endswith("奥を" * 8)                       # 原文は不変
    from text_utils import apply_reject_ops
    assert apply_reject_ops(turns[0]["raw_text"], turns[0]["reject_ops"]) == "Let'sparty!これごめん、奥を"


def test_loop_split_across_turns_is_detected():
    turns = [T(0, "奥を奥を奥を", 0), T(1, "奥を奥を奥を奥を", 1.1)]
    fs = [f for f in hal.detect_loops(turns) if f.confidence == HIGH]
    assert len(fs) == 1 and fs[0].turn_ids == [0, 1]


@pytest.mark.parametrize("text", ["はい、はい", "そうそう", "いやいや", "そうそうそう", "はいはいはい", "なるほど、なるほど",
                                  "パーティー！パーティー！パーティー！", "ははははは", "本当に、本当に素晴らしい"])
def test_natural_repetition_is_not_flagged(text):
    assert hal.detect_loops([T(0, text, 0)]) == []


def test_natural_unit_burst_is_review_only_never_rejected():
    fs = hal.detect_loops([T(0, "はい" * 7, 0)])                       # 「はい」×7 は不自然だが即削除はしない
    assert fs and all(f.confidence != HIGH and f.action == "review" for f in fs)
    hal.apply_rejections([T(0, "はい" * 7, 0)], fs)


# ---------------------------------------------------------------- 3) 音声末尾・長い無音直前（要確認のみ）
def test_short_turn_at_audio_end_is_medium_and_not_rejected():
    turns = [T(0, "今日はありがとうございます。いろいろお話ができました。", 0, 8, chunk_end=True),
             T(1, "はい。", 9.0, 9.3, spk="S1", chunk_end=True)]
    fs = hal.detect_tail(turns, audio_dur=30.0)
    assert [(f.confidence, f.turn_ids) for f in fs] == [(MEDIUM, [1])]
    assert fs[0].action == "review" and fs[0].detail["audio_end"] and fs[0].detail["chunk_end"]
    hal.apply_rejections(turns, fs)
    assert turns[1]["reject_ops"] == []


def test_short_backchannel_before_long_silence_is_low_and_not_rejected():
    turns = [T(0, "最初の話題について説明します。", 0, 8), T(1, "はい。", 8.5, 8.8, spk="S1", chunk_end=True),
             T(2, "次の話題です。ここからが本題です。", 20.0, 28.0)]
    fs = hal.detect_tail(turns, audio_dur=40.0)
    assert [(f.confidence, f.turn_ids) for f in fs] == [(LOW, [1])] and fs[0].action == "review"
    assert fs[0].detail["silence_after"] >= 3.0 and fs[0].detail["audio_end"] is False


def test_flagged_short_turns_carry_the_requested_details():
    turns = [T(0, "長めの発言がここにあります。", 0, 6), T(1, "はい。", 7.0, 7.4, spk="S1", chunk_end=True)]
    d = hal.detect_tail(turns, audio_dur=60.0)[0].detail
    for k in ("start", "speaker", "text", "duration", "silence_after", "chunk_end", "audio_end"):
        assert k in d


def test_short_backchannel_mid_conversation_is_not_flagged():
    turns = [T(0, "最初の話題です。", 0, 4), T(1, "はい。", 4.2, 4.5, spk="S1", chunk_end=True), T(2, "ここから続きの話をゆっくり説明します。", 5.0, 9.0)]
    assert hal.detect_tail(turns, audio_dur=20.0) == []                     # 無音が短い・末尾でもない


def test_real_short_sentence_before_silence_is_not_flagged_low():
    # 実在の短文（作んないと。）は LOW の対象にしない（相槌語・3文字以下だけ）
    turns = [T(0, "前の話です。", 0, 4), T(1, "作んないと。", 4.5, 5.4, chunk_end=True), T(2, "次の話題はこちらになりますのでお聞きください。", 20.0, 26.0)]
    assert hal.detect_tail(turns, audio_dur=40.0) == []


def test_weak_phrase_only_matters_at_audio_end():
    mid = [T(0, "ありがとうございました。", 0, 3), T(1, "続きの話をします。いろいろあります。", 4.0, 9.0)]
    assert hal.detect(mid, audio_dur=20.0) == []                              # 通常の会話の「ありがとうございました」
    end = [T(0, "今日の話は以上です。", 0, 3), T(1, "ありがとうござ", 3.5, 4.5, chunk_end=True), T(2, "いました。", 4.6, 5.2, chunk_end=True)]
    fs = hal.detect(end, audio_dur=30.0)
    assert [(f.confidence, f.kind) for f in fs if f.kind == "tail_short"] == [(MEDIUM, "tail_short")]
    assert not high(fs)


# ---------------------------------------------------------------- 4) 部分不採用: 実在の語を巻き込まない
def test_high_rejection_trims_only_the_hallucinated_span():
    turns = [T(0, "作んないと。", 0, 2), T(1, "作んないと。ご視聴ありがとうござ", 5, 7, spk="B"), T(2, "いました。", 7.1, 8, spk="X")]
    hal.apply_rejections(turns, hal.detect(turns, audio_dur=30.0))
    tb.apply_clean(turns)
    assert turns[1]["raw_text"] == "作んないと。ご視聴ありがとうござ"                  # 原文は不変
    assert turns[1]["clean_text"] == "作んないと。" and not turns[1]["clean_dropped"]  # 実在部分は残す
    assert turns[2]["clean_dropped"] and turns[2]["drop_reason"] == "hallucination"    # 全体が幻覚の発言だけ除外


def test_suspect_tail_backchannel_is_not_dropped_by_the_backchannel_rule():
    turns = [T(0, "長めの発言がここにあります。", 0, 6), T(1, "はい。", 7.0, 7.4, spk="S1", chunk_end=True)]
    hal.apply_rejections(turns, hal.detect(turns, audio_dur=60.0))
    tb.apply_clean(turns)
    assert turns[1]["clean_text"] == "はい。" and not turns[1]["clean_dropped"]
    plain = [T(0, "長めの発言がここにあります。", 0, 6), T(1, "はい。", 6.2, 6.5, spk="S1"), T(2, "続きです。", 6.8, 9)]
    tb.apply_clean(plain)
    assert plain[1]["clean_dropped"]                                           # 普通の単独相槌は従来どおり削除


def test_keep_hallucinations_does_not_reject():
    turns = [T(0, "ご視聴ありがとうございました", 0)]
    hal.apply_rejections(turns, hal.detect(turns), reject=False)
    assert turns[0]["reject_ops"] == [] and turns[0]["hallucination"][0]["action"] == "review"


# ---------------------------------------------------------------- 5) speaker境界
def test_speaker_boundary_fragments_are_flagged_but_never_changed():
    turns = [T(0, "本当にもう成功書い", 0, 3, spk="A", cut_end=True), T(1, "てないですから。", 3.0, 4.5, spk="B", cut_start=True)]
    fs = hal.detect_boundary(turns)
    assert [(f.confidence, f.turn_ids) for f in fs] == [(LOW, [0, 1])] and "付け替え" in fs[0].reason
    before = [dict(t) for t in turns]
    hal.apply_rejections(turns, fs)
    assert [t["raw_text"] for t in turns] == [t["raw_text"] for t in before]
    assert [t["speaker_id"] for t in turns] == ["A", "B"]


# ---------------------------------------------------------------- 6) ASR未転写
def _words(text, start, per=0.1):
    return [[ch, round(start + i * per, 3), round(start + (i + 1) * per, 3), 0.9] for i, ch in enumerate(text)]


def test_untranscribed_regions_are_reported_and_configurable():
    turns = [T(0, "最初だけ話しました。", 0, 1.0, words=_words("最初だけ話しました。", 0.0))]
    diar = [{"start": 0.0, "end": 10.0, "speaker": "SPEAKER_00"}, {"start": 12.0, "end": 12.8, "speaker": "SPEAKER_01"}]
    rows, summ = hal.untranscribed_regions(turns, diar, min_sec=1.5, duration=15.0)
    assert len(rows) == 1 and rows[0]["speaker"] == "SPEAKER_00" and rows[0]["duration"] >= 8.0   # 12.0〜12.8 は短いので出ない
    assert rows[0]["rejected_text"] is False       # 幻覚の不採用が無ければ「不採用あり」と表示しない
    assert 0.5 < summ["ratio"] < 1.0
    rows2, _ = hal.untranscribed_regions(turns, diar, min_sec=0.5, duration=15.0)
    assert len(rows2) == 2                                                      # 最小秒数を下げると短い区間も出る
    assert hal.untranscribed_regions(turns, diar, min_sec=20.0, duration=15.0)[0] == []


def test_punctuation_stretch_does_not_hide_untranscribed_speech():
    # 句点トークンが無音（実際は発話あり）を覆っていても、句読点は被覆に数えない
    words = _words("はい", 0.0) + [["。", 0.2, 5.0, 0.9]]
    turns = [T(0, "はい。", 0, 5.0, words=words)]
    rows, _ = hal.untranscribed_regions(turns, [{"start": 0.0, "end": 5.0, "speaker": "SPEAKER_00"}], 1.5, 6.0)
    assert len(rows) == 1


def test_rejected_hallucination_text_counts_as_untranscribed():
    turns = [T(0, "ご視聴ありがとうございました。", 0, 3, words=_words("ご視聴ありがとうございました。", 0.0, 0.2))]
    hal.apply_rejections(turns, hal.detect(turns))
    rows, _ = hal.untranscribed_regions(turns, [{"start": 0.0, "end": 3.0, "speaker": "SPEAKER_00"}], 1.5, 4.0)
    assert len(rows) == 1 and rows[0]["rejected_text"] is True


# ---------------------------------------------------------------- 7) 正常な対談を幻覚扱いしない
def test_normal_dialogue_is_not_flagged_as_hallucination():
    lines = ["最初はそんなに大きなことをやろうとは思ってなかったんですよね。", "そうだったんですか？", "はい。でも地域で活動しているうちに、続けられるんじゃないかと思って。",
             "それで2024年の10月に始めたんです。参加者は30人くらいでした。", "なるほど。", "ありがとうございます。今日はよろしくお願いします。"]
    turns = [T(i, x, i * 4.0, i * 4.0 + 3.0, spk="A" if i % 2 == 0 else "B") for i, x in enumerate(lines)]
    fs = hal.detect(turns, audio_dur=30.0)
    assert [f for f in fs if f.kind in ("phrase", "loop")] == []
    assert not any(f.confidence == HIGH for f in fs)

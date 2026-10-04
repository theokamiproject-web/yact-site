"""PHASE 2 改善: Track-81 の人間確認済み（P1〜P4）を正解データとする回帰テスト。
実音声の文字列そのものは使わず、同じ構造（笑い声の長い反復／同一文の反復が句読点・segment・speakerで割れる／
無音の後に孤立した挨拶）を合成して確認する。"""
import pytest

import hallucination as hal
import quality_check as qc
import transcript_builder as tb
from hallucination import HIGH, LOW, MEDIUM, NON_SPEECH
from text_utils import apply_reject_ops


def T(i, text, start, end=None, spk="S0", **kw):
    end = start + 1.0 if end is None else end
    t = {"id": i, "speaker_id": spk, "speaker_name": spk, "speaker_uncertain": False, "start": start, "end": end,
         "speech_end": end, "pause_after": 0.0, "raw_text": text, "edited_text": text, "clean_text": text}
    t.update(kw)
    return t


def high(fs):
    return [f for f in fs if f.confidence == HIGH]


# ============================================================ P1: 笑い声は幻覚ではない
LAUGH = ["あっはっはっはっはっはっはっは", "っはっはっはっはっはっはっはっはっはっは", "はっはっはっはっはっはっはっは", "ははははははははは",
         "あははははははははは", "ふふふふふふふふ", "へへへへへへへへ", "ひひひひひひひひ", "わはははははははは", "うふふふふふふふふ", "えへへへへへへへへ"]


@pytest.mark.parametrize("text", LAUGH)
def test_p1_laughter_is_never_high_and_never_rejected(text):
    turns = [T(0, "そうですよね。" + text, 0, 8)]
    fs = hal.detect(turns, audio_dur=30.0)
    assert not high(fs)
    assert all(f.action == "review" for f in fs)
    assert any(f.confidence == NON_SPEECH and f.kind == "laughter_repeat" for f in fs)
    hal.apply_rejections(turns, fs)
    assert turns[0]["reject_ops"] == []


def test_p1_long_laughter_split_over_many_turns_is_one_event_and_survives_clean():
    laugh = "っは" * 20
    turns = [T(0, "俺もそうさそうですよね。あっはっはっはっはっはっはっは", 0, 5, spk="D"),
             T(1, laugh, 5.1, 9.0, spk="A"), T(2, laugh, 9.1, 11.0, spk="E"), T(3, "は" + "っは" * 10, 11.1, 14.0, spk="A"),
             T(4, laugh, 14.1, 18.0, spk="D"), T(5, "っはっはっはっはアパートの建て壊しが決まるのに", 18.1, 28.0, spk="B")]
    fs = hal.detect(turns, audio_dur=60.0)
    assert not high(fs)
    assert hal.count_events(fs, turns, NON_SPEECH) == 1                    # 窓ごとに重複して数えない
    hal.apply_rejections(turns, fs)
    raw = [t["raw_text"] for t in turns]
    tb.apply_clean(turns)
    assert [t["raw_text"] for t in turns] == raw                           # rawは不変
    for t in turns[1:5]:
        assert t["reject_ops"] == [] and not t["clean_dropped"] and "は" in t["clean_text"]   # 02からも消えない・作文もしない
        assert t["clean_text"] == t["raw_text"]


def test_p1_short_laughter_is_not_treated_as_hallucination():
    for text in ["ははは", "あはは。", "ふふふ", "はっはっは"]:
        assert hal.detect([T(0, "それは面白いですね。" + text, 0, 4)], audio_dur=20.0) == []


def test_p1_laughter_is_shown_for_reference_in_the_review():
    turns = [T(0, "あっはっは" + "っは" * 12, 0, 6)]
    fs = hal.detect(turns, audio_dur=20.0)
    hal.apply_rejections(turns, fs)
    md = "\n".join(qc._render_findings(fs, turns, keep=False))
    assert "NON_SPEECH" in md and "笑い声" in md and "削除していません" in md and "自動不採用**" not in md.split("### ")[1]


def test_vocal_repetition_is_not_a_narrow_hardcode():
    # 「笑」という文字や特定の語ではなく、非言語の文字だけでできた単位であれば同じ扱い（任意の組み合わせ）
    assert hal.is_vocal("っは") and hal.is_vocal("あは") and hal.is_vocal("ふふ") and hal.is_vocal("へへ") and hal.is_vocal("ハハ")
    assert not hal.is_vocal("はい") and not hal.is_vocal("奥を") and not hal.is_vocal("居た時と")


# ============================================================ P2: 同一文の異常反復（句読点・segment・speakerが違っても）
SENT = "居た時と居なかったですよね"


def test_p2_same_sentence_repeated_six_times_is_high():
    turns = [T(0, "この世界中にもいなかったから。", 0, 4), T(1, (SENT + "?") * 6, 5, 12)]
    fs = high(hal.detect_loops(turns))
    assert len(fs) == 1 and fs[0].detail["unit"] == SENT and fs[0].detail["repeats"] >= 6 and fs[0].action == "reject"
    hal.apply_rejections(turns, fs)
    assert apply_reject_ops(turns[1]["raw_text"], turns[1]["reject_ops"]).count(SENT) == 1   # 1回分だけ残す
    assert turns[1]["raw_text"].count(SENT) == 6                                          # 原文は不変


def test_p2_differences_in_punctuation_and_whitespace_are_normalized():
    text = f"{SENT}?{SENT}。{SENT}！{SENT}、{SENT} {SENT}\n{SENT}…"
    fs = high(hal.detect_loops([T(0, text, 0, 12)]))
    assert len(fs) == 1 and fs[0].detail["repeats"] >= 6


def test_p2_repetition_split_into_fragments_across_segments_and_speakers_is_detected():
    pieces = [(SENT[:4], "A"), (SENT[4:] + "?", "A"), (SENT + "?", "B"), (SENT[:6], "B"), (SENT[6:] + "?", "A"),
              (SENT + "?", "C"), (SENT[:3], "C"), (SENT[3:] + "?", "A"), (SENT + "?", "B")]
    turns = [T(i, txt, 10 + i * 1.2, 10 + i * 1.2 + 1.0, spk=s) for i, (txt, s) in enumerate(pieces)]
    fs = high(hal.detect(turns, audio_dur=60.0))
    assert fs and len({tid for f in fs for tid in f.turn_ids}) >= 5
    assert hal.count_events(fs, turns, HIGH) == 1                       # 同じ事象を窓ごとに数えない
    assert all(t["raw_text"] == txt for t, (txt, _) in zip(turns, pieces))   # transcriptは勝手に結合しない


def test_p2_crossing_speakers_alone_is_not_a_hallucination():
    turns = [T(0, SENT + "?", 0, 2, spk="A"), T(1, SENT + "。", 2.2, 4, spk="B")]   # 聞き返し・オウム返しは2回まで自然
    assert hal.detect(turns, audio_dur=30.0) == []


def test_p2_similar_but_not_identical_repetition_is_detected_by_similarity():
    sents = ["それはちょっと難しいと思います。", "それはちょっと難しいと思いますね。", "それはちょっと難しいと思います。",
             "それはちょっと難しいんだと思います。", "それはちょっと難しいと思います。", "それはちょっと難しいと思いますよ。"]
    turns = [T(i, s, i * 2.0, i * 2.0 + 1.8, spk="A" if i % 2 else "B") for i, s in enumerate(sents)]
    fs = high(hal.detect_loops(turns))
    assert fs and any(f.detail["method"] in ("similar", "exact") for f in fs)


@pytest.mark.parametrize("text", ["はい、はい", "はい、はい、はい", "そうそう", "そうそうそう", "いやいや", "いやいやいや", "はいはいはいはい",
                                  "うんうん、うんうん", "なるほど、なるほど、なるほど"])
def test_p2_natural_repetition_is_not_high(text):
    turns = [T(0, text, 0, 3)]
    assert not high(hal.detect(turns, audio_dur=30.0))


def test_p2_natural_unit_burst_is_not_rejected_until_extreme():
    assert not high(hal.detect_loops([T(0, "はい" * 7, 0, 5)]))


# ============================================================ P4: 孤立した「ありがとうございました。」は要確認（文字列だけでは判定しない）
def _timed(text, spans):
    """文字ごとの時刻つき words。spans: [(文字数, 開始, 1文字の長さ), ...]"""
    words, pos = [], 0
    for n, start, step in spans:
        for k in range(n):
            ch = text[pos + k]
            if ch in "。、？！":
                words.append([ch, start + k * step, start + k * step + 0.1, 0.9])
            else:
                words.append([ch, start + k * step, start + k * step + step, 0.9])
        pos += n
    return words


def test_p4_isolated_phrase_after_long_silence_at_chunk_end_is_flagged_for_review_only():
    text = "がするありがとうございました。"
    words = _timed(text, [(1, 1143.0, 0.5), (1, 1151.8, 0.5), (1, 1153.1, 0.5), (len(text) - 3, 1181.1, 0.12)])
    turns = [T(0, "てやったわけじゃない、大黒さんが川岡さん、札幌さんが松本さん、結果おばあさんが晴翔さん。", 1132.5, 1142.9, spk="D"),
             T(1, text, 1142.96, 1182.8, spk=None, speaker_uncertain=True, chunk_end=True, avg_logprob=-0.66, words=words),
             T(2, "次の話題に移りますけど、ここからは別の話をします。", 1190.0, 1196.0, spk="A")]
    turns[1]["speaker_id"] = None
    fs = hal.detect(turns, audio_dur=1300.0)
    hit = [f for f in fs if f.kind == "weak_phrase"]
    assert len(hit) == 1 and hit[0].confidence == MEDIUM and hit[0].turn_ids == [1] and hit[0].action == "review"
    assert not high(fs)
    hal.apply_rejections(turns, fs)
    assert turns[1]["reject_ops"] == []                                       # 自動削除しない
    tb.apply_clean(turns)
    assert "ありがとうございました" in turns[1]["clean_text"]


def test_p4_same_string_in_normal_conversation_is_not_flagged_and_never_high():
    lines = ["今日は本当にありがとうございました。", "こちらこそありがとうございました。", "また来月もお願いします。"]
    turns = [T(i, x, i * 4.0, i * 4.0 + 3.0, spk="A" if i % 2 == 0 else "B", avg_logprob=-0.2) for i, x in enumerate(lines)]
    fs = hal.detect(turns, audio_dur=40.0)
    assert [f for f in fs if f.kind == "weak_phrase"] == [] and not high(fs)


def test_p4_phrase_alone_is_not_enough_even_with_a_known_speaker_and_a_pause():
    # 沈黙の後の実発言（話者が確定し、チャンク末尾でもない）は文字列だけでは要確認にしない
    turns = [T(0, "最初の話です。", 0, 4), T(1, "ありがとうございました。", 20.0, 22.0, avg_logprob=-0.1), T(2, "では次の話題です。ここからです。", 23.0, 28.0)]
    fs = hal.detect(turns, audio_dur=60.0)
    assert [f for f in fs if f.kind == "weak_phrase" and f.confidence in (HIGH, MEDIUM)] == []


def test_p4_review_report_lists_the_weak_phrase_with_its_signals():
    text = "がするありがとうございました。"
    words = _timed(text, [(1, 100.0, 0.5), (1, 108.0, 0.5), (1, 109.0, 0.5), (len(text) - 3, 140.0, 0.12)])
    turns = [T(0, "前の発言です。", 90, 96), T(1, text, 96.5, 142, spk=None, speaker_name="話者不明", speaker_uncertain=True, chunk_end=True, avg_logprob=-0.66, words=words),
             T(2, "ここから別の話題に入ります。", 150, 156)]
    fs = hal.detect(turns, audio_dur=300.0)
    hal.apply_rejections(turns, fs)
    md = "\n".join(qc._render_findings(fs, turns, keep=False))
    assert "孤立した挨拶的定型句" in md and "削除していません" in md


# ============================================================ 既存の正常な対談は大量に幻覚扱いされない
def test_large_normal_dialogue_has_no_high_and_no_medium():
    base = ["最初はそんなに大きなことをやろうとは思ってなかったんですよね。", "そうだったんですか？", "はい、はい。でも地域で活動しているうちに続けられると思って。",
            "それで2024年の10月に始めたんです。参加者は30人くらいでした。", "なるほど。そうそう、そうなんですよ。", "ははは。それは大変でしたね。",
            "いやいや、本当に助かりました。ありがとうございました。", "こちらこそ。また相談させてください。", "あっはっは。ええ、ぜひお願いします。",
            "うんうん。そうですね。", "ふふ、確かにそうですね。", "ありがとうございます。今日はよろしくお願いします。"]
    turns = [T(i, base[i % len(base)], i * 5.0, i * 5.0 + 4.0, spk="A" if i % 2 == 0 else "B", avg_logprob=-0.25) for i in range(48)]
    fs = [f for f in hal.detect(turns, audio_dur=300.0) if f.kind != "boundary"]
    assert [f for f in fs if f.confidence in (HIGH, MEDIUM)] == []


def test_known_phrase_and_pure_loop_hallucinations_are_still_high():
    assert high(hal.detect_phrases([T(0, "ご視聴ありがとうございました。", 0)]))
    assert high(hal.detect_loops([T(0, "これごめん、" + "奥を" * 8, 0)]))


def test_comma_separated_short_repetition_is_review_only():
    # 「たまたま、たまたま、たまたま」のように読点で区切った強調的な反復は、実発話の可能性があるので自動不採用にしない
    fs = hal.detect_loops([T(0, "たまたま、たまたま、たまたま、たまたま", 0, 5)])
    assert fs and not high(fs) and all(f.action == "review" for f in fs)
    assert high(hal.detect_loops([T(0, "奥を" * 8, 0, 5)]))               # 句読点のない機械的な反復はHIGHのまま

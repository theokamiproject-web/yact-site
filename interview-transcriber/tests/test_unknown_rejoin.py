"""話者不明の安全な再結合（候補2）。不明を既知話者へ吸収せず、細切れの同一発話を『話者不明のまま』文字連結だけで再結合する。
自動で変えるのは HIGH のみ。MEDIUM は要確認、LOW は変更なし。"""
import transcript_builder as tb


def T(spk, text, a, b, **kw):
    t = {"speaker_id": spk, "speaker_uncertain": spk is None, "speaker_guess": kw.get("guess"), "start": a, "end": b,
         "raw_text": text, "_pause": 0.0, "chunk_end": False, "speech_end": b, "cut_start": False, "cut_end": False,
         "short_kept": kw.get("short", False), "segment_ids": [0], "words": [[c, a, b, 1.0] for c in text],
         "avg_logprob": None}
    return t


def run(turns, diar):
    st = tb.rejoin_unknown_turns(turns, diar)
    return turns, st


QUIET = [{"start": 0.0, "end": 0.1, "speaker": "SPEAKER_09"}]   # 重なり・支持なし


def test_unknown_unknown_safe_join_stays_unknown():
    turns, st = run([T(None, "そうです", 1.0, 1.4), T(None, "よ", 1.45, 1.6)], QUIET)
    assert [(t["speaker_id"], t["raw_text"]) for t in turns] == [(None, "そうですよ")]
    assert st["HIGH"] == 1 and turns[0]["unknown_joined"] == 2


def test_no_join_when_a_strong_known_speaker_is_between():
    turns, st = run([T(None, "蜂蜜", 1.0, 1.4), T("SPEAKER_01", "それは私が作った料理でして", 1.45, 3.0), T(None, "アメ", 3.05, 3.3)], QUIET)
    assert len(turns) == 3 and st == {"HIGH": 0, "MEDIUM": 0, "LOW": 0}


def test_r22_type_unknown_both_ends_known_fragments_between_joins_high():
    # 不明「そうです」/B「よ」(断片)/不明「蜂蜜」 -> 不明のまま連結
    turns, st = run([T(None, "そうで", 1.0, 1.3), T("SPEAKER_01", "す", 1.32, 1.4, short=True), T(None, "よ蜂蜜", 1.42, 1.9)], QUIET)
    assert len(turns) == 1 and turns[0]["speaker_id"] is None and turns[0]["raw_text"] == "そうです" + "よ蜂蜜"
    assert st["HIGH"] == 1


def test_r22_one_sided_chain_is_only_a_review_candidate():
    turns, st = run([T(None, "そうで", 1.0, 1.3), T("SPEAKER_01", "すよ", 1.32, 1.5, short=True),
                     T("SPEAKER_00", "蜂蜜を入れた飴を作って今日は持ってきたんですよ", 1.6, 4.0)], QUIET)
    assert len(turns) == 3                                             # 自動では変えない
    c = turns[0]["unknown_candidate"]
    assert c["confidence"] == "MEDIUM" and c["candidate_text"] == "そうですよ"
    assert turns[1]["speaker_id"] == "SPEAKER_01"                      # 既知の発話は奪わない


def test_r24_type_backchannel_between_unknowns_is_kept():
    turns, st = run([T(None, "それは", 1.0, 1.3), T("SPEAKER_01", "うーん", 1.32, 1.8, short=True), T(None, "面白いと思う", 1.85, 2.6)], QUIET)
    assert [t["raw_text"] for t in turns] == ["それは", "うーん", "面白いと思う"]
    assert turns[0]["unknown_candidate"]["confidence"] == "LOW"
    assert st["LOW"] == 1


def test_independent_hai_is_kept():
    turns, st = run([T(None, "ええ", 1.0, 1.2), T("SPEAKER_01", "はい", 1.22, 1.4, short=True), T(None, "そう", 1.45, 1.6)], QUIET)
    assert [t["raw_text"] for t in turns] == ["ええ", "はい", "そう"]
    assert st["LOW"] == 1 and st["HIGH"] == 0


def test_overlap_is_not_force_merged():
    diar = [{"start": 1.0, "end": 1.5, "speaker": "SPEAKER_01"}, {"start": 1.0, "end": 1.5, "speaker": "SPEAKER_02"}]
    turns, st = run([T(None, "それは", 1.0, 1.25), T(None, "ですよ", 1.3, 1.5)], diar)
    assert len(turns) == 2 and st["HIGH"] == 0


def test_unknown_with_speaker_guess_is_not_auto_joined():
    turns, st = run([T(None, "それは", 1.0, 1.25, guess="SPEAKER_01"), T(None, "ですよ", 1.3, 1.5)], QUIET)
    assert len(turns) == 2 and st["MEDIUM"] == 1


def test_pyannote_supported_known_utterance_is_not_converted():
    diar = [{"start": 1.3, "end": 2.0, "speaker": "SPEAKER_01"}]
    turns, st = run([T(None, "それは", 1.0, 1.28), T("SPEAKER_01", "ええと", 1.3, 1.9, short=True), T(None, "思う", 1.95, 2.2)], diar)
    assert len(turns) == 3 and turns[1]["speaker_id"] == "SPEAKER_01"
    assert st["LOW"] == 1


def test_long_gap_is_low_and_unchanged():
    turns, st = run([T(None, "そうです", 1.0, 1.4), T(None, "よ", 2.4, 2.5)], QUIET)
    assert len(turns) == 2 and st["LOW"] == 1


def test_medium_gap_is_review_candidate():
    turns, st = run([T(None, "そうです", 1.0, 1.4), T(None, "よ", 1.8, 1.9)], QUIET)
    assert len(turns) == 2 and st["MEDIUM"] == 1
    assert turns[0]["unknown_candidate"]["candidate_text"] == "そうですよ"


def test_unknown_stays_unknown_never_assigned_to_a_neighbour():
    turns, _ = run([T("SPEAKER_00", "はじめます。", 0.0, 1.0), T(None, "そうで", 1.2, 1.5), T(None, "すよ", 1.55, 1.8),
                    T("SPEAKER_00", "それでね", 2.0, 2.6)], QUIET)
    assert [t["speaker_id"] for t in turns] == ["SPEAKER_00", None, "SPEAKER_00"]
    assert turns[1]["raw_text"] == "そうですよ"


def test_no_diarization_does_nothing():
    turns = [T(None, "あ", 1.0, 1.1), T(None, "い", 1.15, 1.2)]
    assert tb.rejoin_unknown_turns(turns, None) == {"HIGH": 0, "MEDIUM": 0, "LOW": 0} and len(turns) == 2

"""チャンク間speaker対応（候補3）。人間確認済みの同一人物（F=B）・別人（B≠C）を、単純なラベル置換ではなく
『誤った対応の連鎖を付け替えて再統合』で満たす。同一チャンクで同時に話す2人は同一人物にしない。"""
import numpy as np

import diarization_chunks as dc

B_EMB, C_EMB = [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]
X_EMB = [0.7, 0.7, 0.0]       # 二人分（BとC）を含んでしまったlocal
Z_EMB = [0.6, 0.8, 0.0]       # 実はBだが、埋め込みはCに近い（FがCに0.83、Bに0.56だった状況）


def ch(i, a, b, segs, embs):
    return {"index": i, "start": a, "end": b, "embeddings": embs,
            "segments": [{"start": s, "end": e, "speaker": sp} for sp, s, e in segs]}


def scenario():
    """chunk1のlocal 00 は、前チャンクのBとCの両方と重なる（二人分）。時刻一致でBに付くが、chunk2では
    同時に話す別人Zが現れ、証拠が足りず新しい話者（F）になる。"""
    c0 = ch(0, 0, 100, [("SPEAKER_00", 0, 40), ("SPEAKER_00", 70, 88), ("SPEAKER_01", 40, 70), ("SPEAKER_01", 88, 100)],
            {"SPEAKER_00": B_EMB, "SPEAKER_01": C_EMB})
    c1 = ch(1, 70, 170, [("SPEAKER_00", 70, 100), ("SPEAKER_00", 110, 120), ("SPEAKER_00", 150, 170)], {"SPEAKER_00": X_EMB})
    c2 = ch(2, 140, 240, [("SPEAKER_00", 140, 170), ("SPEAKER_00", 175, 235), ("SPEAKER_01", 180, 240)],
            {"SPEAKER_00": X_EMB, "SPEAKER_01": Z_EMB})
    return [c0, c1, c2]


CONS = {"persons": {"B": [(0, "SPEAKER_00"), (2, "SPEAKER_01")], "C": [(0, "SPEAKER_01")]}}


def maps_of(rep):
    return rep["mappings"]


def test_without_constraints_the_new_speaker_is_registered_separately():
    segs, rep = dc.merge_chunks(scenario(), 240.0)
    m = maps_of(rep)
    assert m[2]["SPEAKER_01"] not in (m[0]["SPEAKER_00"], m[0]["SPEAKER_01"])        # 前提: Zが新規話者（F）
    assert len(rep["speakers"]) == 3


def test_f_equals_b_constraint_merges_by_reassigning_the_wrong_chain_not_by_renaming():
    segs, rep = dc.merge_chunks(scenario(), 240.0, constraints=CONS)
    m = maps_of(rep)
    b, c = m[0]["SPEAKER_00"], m[0]["SPEAKER_01"]
    assert m[2]["SPEAKER_01"] == b                                                    # F(Z)=B
    assert len(rep["speakers"]) == 2                                                  # Fは別話者として残らない
    # 同時に話す chunk2 の local 00 はBではない: 誤ってBへ付いていた連鎖（chunk1, chunk2）をCへ付け替えた
    assert m[2]["SPEAKER_00"] == c and m[1]["SPEAKER_00"] == c
    assert any(r["action"] == "付け替え" for r in rep["repairs"]) and any(r["action"] == "統合" for r in rep["repairs"])


def test_b_not_equal_c_is_kept():
    _, rep = dc.merge_chunks(scenario(), 240.0, constraints=CONS)
    m = maps_of(rep)
    assert m[0]["SPEAKER_00"] != m[0]["SPEAKER_01"]
    assert not any(r["action"] == "違反" for r in rep["repairs"])


def test_b_not_equal_c_violation_is_reported_not_silently_merged():
    cons = {"persons": {"B": [(0, "SPEAKER_00")], "C": [(0, "SPEAKER_00")]}}
    _, rep = dc.merge_chunks(scenario(), 240.0, constraints=cons)
    assert any(r["action"] == "違反" for r in rep["repairs"])


def test_speakers_coexisting_in_a_chunk_are_never_merged_even_if_constraint_says_same_person():
    # 同じ人物と指定されたanchorが同じチャンクに併存（同時に話している）→ 統合せず保留
    cons = {"persons": {"P": [(2, "SPEAKER_00"), (2, "SPEAKER_01")]}}
    _, rep = dc.merge_chunks(scenario(), 240.0, constraints=cons)
    m = maps_of(rep)
    assert m[2]["SPEAKER_00"] != m[2]["SPEAKER_01"]
    assert any(r["action"] == "保留" for r in rep["repairs"])


def test_simultaneous_speakers_with_identical_embeddings_stay_separate_in_one_chunk():
    c0 = ch(0, 0, 100, [("SPEAKER_00", 0, 90), ("SPEAKER_01", 10, 80)], {"SPEAKER_00": B_EMB, "SPEAKER_01": B_EMB})
    _, rep = dc.merge_chunks([c0], 100.0)
    assert rep["mappings"][0]["SPEAKER_00"] != rep["mappings"][0]["SPEAKER_01"]


def test_e_is_not_merged_into_c_when_they_coexist():
    e_emb = [0.1, 0.95, 0.0]                      # Cに似ている（0.69程度の類似度に相当）
    c0 = ch(0, 0, 100, [("SPEAKER_00", 0, 90), ("SPEAKER_01", 20, 60)], {"SPEAKER_00": C_EMB, "SPEAKER_01": e_emb})
    cons = {"persons": {"C": [(0, "SPEAKER_00")], "E": [(0, "SPEAKER_01")]}}
    _, rep = dc.merge_chunks([c0], 100.0, constraints=cons)
    m = rep["mappings"][0]
    assert m["SPEAKER_00"] != m["SPEAKER_01"] and len(rep["speakers"]) == 2


def test_multi_chunk_centroid_rejoins_a_speaker_absent_in_the_overlap():
    # Bはchunk1に現れず、chunk2で重なり区間の証拠なしに戻る → 複数チャンクで育てた代表埋め込みで同じ話者に
    c0 = ch(0, 0, 100, [("SPEAKER_00", 0, 60), ("SPEAKER_01", 60, 100)], {"SPEAKER_00": B_EMB, "SPEAKER_01": C_EMB})
    c1 = ch(1, 70, 170, [("SPEAKER_00", 70, 170)], {"SPEAKER_00": C_EMB})
    c2 = ch(2, 140, 240, [("SPEAKER_00", 140, 170), ("SPEAKER_01", 190, 240)], {"SPEAKER_00": C_EMB, "SPEAKER_01": [0.97, 0.05, 0.0]})
    _, rep = dc.merge_chunks([c0, c1, c2], 240.0)
    m = rep["mappings"]
    assert m[2]["SPEAKER_01"] == m[0]["SPEAKER_00"]


def test_temporary_embedding_drop_still_uses_time_continuity():
    c0 = ch(0, 0, 100, [("SPEAKER_00", 0, 100)], {"SPEAKER_00": B_EMB})
    c1 = ch(1, 70, 170, [("SPEAKER_00", 70, 170)], {"SPEAKER_00": [0.6, 0.8, 0.0]})      # 類似度0.6に低下
    _, rep = dc.merge_chunks([c0, c1], 170.0)
    assert rep["mappings"][1]["SPEAKER_00"] == rep["mappings"][0]["SPEAKER_00"]


def test_constraints_change_only_labels_not_segment_times():
    a, _ = dc.merge_chunks(scenario(), 240.0)
    b, _ = dc.merge_chunks(scenario(), 240.0, constraints=CONS)
    def covered(segs):      # 話者を無視した発話区間（0.5秒刻みで発話中か）。ラベルが変わると同じ話者の継ぎ目の結合だけが変わる
        return [any(x["start"] <= t < x["end"] for x in segs) for t in np.arange(0, 240, 0.5)]
    assert covered(a) == covered(b)


def test_r24_and_r22_turn_structure_is_unaffected_by_relabeling():
    import transcript_builder as tb
    from helpers import make_aligned
    text = "それは多分いかなって焼くうーん俺が違ったら面白いと思うんだよね"
    i, n = text.index("うーん"), len(text)
    al, _ = make_aligned([("SPEAKER_00", text)], 0.1)
    for who in ("SPEAKER_01", "SPEAKER_02"):                   # 付け替えで「うーん」の話者ラベルが変わっても構造は同じ
        diar = [{"start": 0, "end": i * .1, "speaker": "SPEAKER_03"}, {"start": i * .1, "end": (i + 3) * .1, "speaker": who},
                {"start": (i + 3) * .1, "end": n * .1, "speaker": "SPEAKER_03"}]
        turns = tb.build_turns(al, diar, None)
        assert [t["speaker_id"] for t in turns] == ["SPEAKER_03", who, "SPEAKER_03"]
        assert turns[1]["raw_text"] == "うーん"
    text2 = "それうちの話そうですよ蜂蜜アメ"
    al2, _ = make_aligned([("SPEAKER_00", text2)], 0.1)
    segs = [("SPEAKER_01", 0, 6), ("SPEAKER_02", 6, 8), ("SPEAKER_01", 8, 11), ("SPEAKER_00", 11, 13), ("SPEAKER_01", 13, 15)]
    turns = tb.build_turns(al2, [{"start": a * .1, "end": b * .1, "speaker": s} for s, a, b in segs], None)
    assert not any("そうですよ蜂蜜アメ" in t["raw_text"] and t["speaker_id"] == "SPEAKER_01" for t in turns)


def test_load_constraints_roundtrip(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("persons:\n  B:\n    - {chunk: 0, local: SPEAKER_00}\n    - {chunk: 9, local: SPEAKER_03}\n", encoding="utf-8")
    assert dc.load_constraints(p) == {"persons": {"B": [(0, "SPEAKER_00"), (9, "SPEAKER_03")]}}
    assert dc.load_constraints(tmp_path / "none.yaml") is None

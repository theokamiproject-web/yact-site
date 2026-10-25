"""--apply-local-split（Step 2・検証機能・既定OFF）。HIGH、および両側blockが十分な根拠を持つMEDIUMだけを、
sub-segment（localの時間範囲）単位で反映する。境界未確定ゾーンは現在の割り当てを維持し、UNRESOLVED SPLIT ZONEとして出す。"""
import json

import numpy as np
import pytest

import diarization_chunks as dc
import local_split as ls
import transcript_builder as tb
from helpers import make_aligned

B, C = np.array([1.0, 0.0]), np.array([0.0, 1.0])
REFS = {"B": B, "C": C}


def vec(person, strength="high"):
    t = {"high": 0.05, "medium": 0.85}[strength]
    return np.array([1.0, t]) if person == "B" else np.array([t, 1.0])


def embedder(timeline):
    def embed(a, b):
        m = (a + b) / 2
        for x, y, e in timeline:
            if x <= m < y:
                return e
        return np.array([1.0, 1.0])
    return embed


def chunk(index, segs, start=0.0, end=600.0):
    return {"index": index, "start": start, "end": end, "embeddings": None,
            "segments": [{"start": a, "end": b, "speaker": s} for s, a, b in segs]}


def setup(c_strength="high", c_anchors=2, extra=()):
    """local L は 100〜123秒 が B の声、300〜313秒 が C の声（途中に短い発話）。local K は C のanchor用、M はその他。"""
    segs = [("L", 100, 103), ("L", 110, 113), ("L", 120, 123), ("L", 200, 201), ("L", 300, 303)]
    if c_anchors >= 2:
        segs.append(("L", 310, 313))
    segs += [("K", 500, 504), ("K", 510, 514), ("M", 20, 60)] + list(extra)
    ch = chunk(0, segs)
    e = embedder([(90, 150, vec("B")), (150, 400, vec("C", c_strength)), (490, 600, vec("C"))])
    rep = ls.analyze([ch], e, REFS)
    base, mrep = dc.merge_chunks([ch], 600.0)
    maps = mrep["mappings"]
    persons = {"B": [(0, "L")], "C": [(0, "K")]}
    return ch, rep, base, maps, persons


def plan_for(**kw):
    ch, rep, base, maps, persons = setup(**kw)
    return ch, rep, base, maps, persons, ls.plan_apply(rep, persons, maps, [ch])


def brief(person, start, end, anchors=2, sec=6.0, high=2, medium=0):
    return {"person": person, "start": start, "end": end, "anchors": anchors, "total_sec": sec, "high": high, "medium": medium, "valid": True,
            "high_ok": high >= 1, "anchor_list": []}


def prop(conf="MEDIUM", prev=None, nxt=None, conflicts=(), unstable=False, members=("chunk0:L",)):
    return {"confidence": conf, "from_person": "B", "to_person": "C", "zone_start": 123.0, "zone_end": 300.0, "zone_sec": 177.0,
            "speech_in_zone_sec": 1.0, "assigned_to": None, "why": [], "conflicts": list(conflicts), "applied": False,
            "prev_block": prev or brief("B", 100, 123), "next_block": nxt or brief("C", 300, 313), "unit_unstable": unstable,
            "members": list(members), "members_all": list(members), "units": [list(members)]}


# ------------------------------------------------------------------ 適用される
def test_high_proposal_is_applied_to_the_confirmed_block_only():
    ch, rep, base, maps, persons, plan = plan_for()
    assert rep["proposed_splits"][0]["confidence"] == "HIGH"
    (a,) = plan["applied"]
    gk = maps[0]["K"]
    assert a["confidence"] == "HIGH" and [(o["start"], o["end"], o["speaker"]) for o in plan["overrides"]] == [(300.0, 313.0, gk)]


def test_medium_proposal_with_valid_blocks_on_both_sides_is_applied():
    ch, rep, base, maps, persons, plan = plan_for(c_strength="medium")
    assert rep["proposed_splits"][0]["confidence"] == "MEDIUM"
    assert [a["confidence"] for a in plan["applied"]] == ["MEDIUM"] and plan["overrides"]


def test_the_whole_local_is_never_reassigned():
    ch, rep, base, maps, persons, plan = plan_for()
    segs, _ = dc.merge_chunks([ch], 600.0, overrides=plan["overrides"])
    gl, gk = maps[0]["L"], maps[0]["K"]
    by = lambda a, b: {s["speaker"] for s in segs if s["start"] >= a - 1e-6 and s["end"] <= b + 1e-6}
    assert by(100, 123) == {gl} and by(300, 313) == {gk}                    # Bの声の範囲はそのまま、Cの声の範囲だけ付け替え
    assert {s["speaker"] for s in base if s["start"] in (100, 300)} == {gl}   # 元はlocal全体が同じ全体話者


# ------------------------------------------------------------------ 適用されない
def test_medium_with_too_few_anchors_or_seconds_is_not_applied():
    ch, rep, base, maps, persons = setup()
    for nxt in (brief("C", 300, 313, anchors=1, sec=6.0), brief("C", 300, 313, anchors=2, sec=3.9)):
        plan = ls.plan_apply({"proposed_splits": [prop(nxt=nxt)], "locals": []}, persons, maps, [ch])
        assert plan["overrides"] == [] and plan["skipped"] and "不足" in plan["skipped"][0]["reasons"][0]


def test_mixed_suspected_only_is_not_applied_and_is_left_for_review():
    ch, rep, base, maps, persons, plan = plan_for(c_anchors=1)
    loc = next(e for e in rep["locals"] if e["local"] == "L")
    assert loc["mixed_suspected"] and rep["proposed_splits"] == []
    assert plan["overrides"] == [] and any(m["local"] == "L" for m in plan["mixed_suspected_not_applied"])


def test_unstable_is_not_applied():
    ch, rep, base, maps, persons = setup()
    plan = ls.plan_apply({"proposed_splits": [prop(unstable=True)], "locals": []}, persons, maps, [ch])
    assert plan["overrides"] == [] and "unstable" in plan["skipped"][0]["reasons"]
    # 実際に C,B,C,B と揺れるlocalは提案自体が出ない
    segs = [("L", 100, 103), ("L", 120, 123), ("L", 140, 143), ("L", 160, 163)]
    ch2 = chunk(0, segs + [("K", 500, 504)])
    e = embedder([(90, 110, vec("C")), (110, 130, vec("B")), (130, 150, vec("C")), (150, 200, vec("B")), (490, 600, vec("C"))])
    r2 = ls.analyze([ch2], e, REFS)
    assert r2["proposed_splits"] == [] and next(x for x in r2["locals"] if x["local"] == "L")["unstable"]


def test_low_and_unknown_never_form_a_proposal():
    segs = [("L", 100, 103), ("L", 110, 113), ("L", 300, 303), ("L", 310, 313), ("K", 500, 504)]
    ch = chunk(0, segs)
    ambiguous = np.array([1.0, 0.97])                       # margin が小さい → UNKNOWN
    rep = ls.analyze([ch], embedder([(90, 150, ambiguous), (290, 400, ambiguous), (490, 600, vec("C"))]), REFS)
    assert rep["proposed_splits"] == []


def test_simultaneous_speech_constraint_violation_is_not_applied():
    ch, rep, base, maps, persons = setup()
    gk = maps[0]["K"]
    # 変更先（人物C=gk）が、同じchunkの別local K として、変更範囲と同時に話している
    ch["segments"].append({"start": 300, "end": 312, "speaker": "K"})
    plan = ls.plan_apply({"proposed_splits": [prop()], "locals": []}, persons, maps, [ch])
    assert plan["overrides"] == [] and "同時に話している" in " ".join(plan["skipped"][0]["reasons"]) and gk


def test_proposal_with_recorded_conflict_or_unknown_identity_is_not_applied():
    ch, rep, base, maps, persons = setup()
    p1 = ls.plan_apply({"proposed_splits": [prop(conflicts=["chunk0:M が同時に話している"])], "locals": []}, persons, maps, [ch])
    p2 = ls.plan_apply({"proposed_splits": [prop()], "locals": []}, {"B": persons["B"]}, maps, [ch])      # Cの全体話者が不明
    assert p1["overrides"] == [] and p2["overrides"] == [] and "identity" in " ".join(p2["skipped"][0]["reasons"])


def test_insufficient_evidence_local_is_not_applied():
    ch = chunk(0, [("L", 100, 101), ("K", 500, 504), ("K", 510, 514)])
    rep = ls.analyze([ch], embedder([(490, 600, vec("C")), (90, 150, vec("B"))]), REFS)
    assert next(e for e in rep["locals"] if e["local"] == "L")["evidence_state"] == "insufficient_evidence" and rep["proposed_splits"] == []


# ------------------------------------------------------------------ 境界未確定ゾーン・変更記録
def test_unresolved_zone_keeps_the_current_speaker_and_is_reported(tmp_path):
    ch, rep, base, maps, persons, plan = plan_for()
    segs, _ = dc.merge_chunks([ch], 600.0, overrides=plan["overrides"])
    gl = maps[0]["L"]
    assert {s["speaker"] for s in segs if 199 <= s["start"] < 202} == {gl}              # ゾーン内の発話は現在の話者のまま（UNKNOWNにもしない）
    (z,) = plan["unresolved_zones"]
    assert (z["start"], z["end"]) == (123.0, 300.0) and z["prev_speaker"] == "B" and z["next_speaker"] == "C" and "UNKNOWN化しない" in z["current_speaker_policy"]
    turns = [{"id": 1, "start": 200.0, "end": 201.0, "speaker_id": gl, "speaker_name": "話者B", "raw_text": "ゾーン内"}]
    ls.zone_turn_report(plan, turns, [ch])
    assert plan["unresolved_zones"][0]["turns"] == 1 and plan["unresolved_zones"][0]["current_speakers"] == {"話者B": 1}
    ls.write_apply_reports({k: v for k, v in plan.items() if k not in ("segments", "chunks")}, turns, tmp_path, 0)
    md = (tmp_path / "local_split_changes.md").read_text(encoding="utf-8")
    assert "UNRESOLVED SPLIT ZONE" in md and "UNKNOWN化していません" in md
    data = json.loads((tmp_path / "local_split_applied.json").read_text(encoding="utf-8"))
    assert data["unresolved_zones"][0]["duration"] == 177.0 and data["summary"]["applied_high"] == 1


def test_original_speaker_is_tracked_per_turn():
    turns = [{"id": 1, "start": 300.0, "end": 312.0, "speaker_id": "SPEAKER_02"}, {"id": 2, "start": 100.0, "end": 110.0, "speaker_id": "SPEAKER_01"}]
    orig = [{"start": 290.0, "end": 320.0, "speaker": "SPEAKER_01"}, {"start": 95.0, "end": 115.0, "speaker": "SPEAKER_01"}]
    n = ls.annotate_original_speakers(turns, orig, {"SPEAKER_01": "話者B", "SPEAKER_02": "話者C"})
    assert n == 1 and turns[0]["original_speaker_id"] == "SPEAKER_01" and turns[0]["local_split_changed"] and turns[0]["original_speaker_name"] == "話者B"
    assert not turns[1]["local_split_changed"]


# ------------------------------------------------------------------ P1〜P4 / M1・M2 の構造（一般ルール。実データの値は埋め込まない）
def test_b_c_b_inside_one_local_changes_only_the_middle_c_block():
    segs = [("L", 100, 103), ("L", 110, 113), ("L", 200, 203), ("L", 210, 213), ("L", 300, 303), ("L", 310, 313), ("K", 500, 504), ("K", 510, 514)]
    ch = chunk(0, segs)
    e = embedder([(90, 150, vec("B")), (190, 250, vec("C")), (290, 400, vec("B")), (490, 600, vec("C"))])
    rep = ls.analyze([ch], e, REFS)
    assert sorted(p["to_person"] for p in rep["proposed_splits"]) == ["B", "C"]               # B→C と C→B の2つの提案
    _, mrep = dc.merge_chunks([ch], 600.0)
    plan = ls.plan_apply(rep, {"B": [(0, "L")], "C": [(0, "K")]}, mrep["mappings"], [ch])
    assert [(o["start"], o["end"]) for o in plan["overrides"]] == [(200.0, 213.0)] and len(plan["applied"]) == 2   # Bのblockは既にB（変更なし）
    assert sum(1 for a in plan["applied"] if a["noop"]) == 1


def test_c_to_third_person_assigns_each_confirmed_block_to_its_person():
    segs = [("L", 100, 103), ("L", 110, 113), ("L", 300, 303), ("L", 310, 313), ("K", 500, 504), ("K", 510, 514), ("E", 700, 704), ("E", 710, 714)]
    ch = chunk(0, segs, 0, 800)
    c3 = np.array([0.0, 1.0, 0.0])
    e = embedder([(90, 150, c3), (290, 400, np.array([0.0, 0.0, 1.0])), (490, 600, c3), (690, 800, np.array([0.0, 0.0, 1.0]))])
    refs3 = {"B": np.array([1.0, 0.0, 0.0]), "C": np.array([0.0, 1.0, 0.0]), "E": np.array([0.0, 0.0, 1.0])}
    rep = ls.analyze([ch], e, refs3)
    _, mrep = dc.merge_chunks([ch], 800.0)
    plan = ls.plan_apply(rep, {"C": [(0, "K")], "E": [(0, "E")]}, mrep["mappings"], [ch])
    assert [(o["start"], o["person"]) for o in plan["overrides"]] == [(100.0, "C"), (300.0, "E")]      # 確定した2つのblockだけ（ゾーン 113〜300 は触らない）


def test_tiny_boundary_zone_changes_both_blocks_when_the_local_belongs_to_a_third_speaker():
    segs = [("L", 100, 104), ("L", 105, 109), ("L", 109.5, 113), ("L", 114, 117), ("L", 117.8, 121), ("L", 122, 125),
            ("K", 500, 504), ("K", 510, 514), ("B1", 700, 704), ("B1", 710, 714)]
    ch = chunk(0, segs, 0, 800)
    e = embedder([(90, 118.5, vec("C")), (118.5, 150, vec("B")), (490, 600, vec("C")), (690, 800, vec("B"))])
    rep = ls.analyze([ch], e, REFS)
    _, mrep = dc.merge_chunks([ch], 800.0)
    maps = mrep["mappings"]
    plan = ls.plan_apply(rep, {"C": [(0, "K")], "B": [(0, "B1")]}, maps, [ch])
    assert {o["speaker"] for o in plan["overrides"]} == {maps[0]["K"], maps[0]["B1"]}              # 前後の確定blockを、それぞれの人物へ
    assert [round(z["duration"], 1) for z in plan["unresolved_zones"]] == [0.8] and plan["applied"][0]["confidence"] == "HIGH"


def test_pooled_two_chunk_medium_changes_only_the_confirmed_block_and_keeps_the_zone():
    """隣接chunkで同じ音声を共有する2つのlocal。MEDIUM（両側有効）で、確定したblockだけ付け替え、ゾーンは現在の話者のまま。"""
    c0 = chunk(0, [("X", 100, 103), ("X", 110, 113), ("X", 130, 133), ("K", 500, 504), ("K", 510, 514), ("B1", 20, 60)], 0, 300)
    c1 = chunk(1, [("Y", 130, 133), ("Y", 300, 303), ("Y", 310, 313), ("K", 500, 504), ("B1", 20, 60)], 130, 600)
    e = embedder([(90, 200, vec("C", "medium")), (290, 400, vec("B", "medium")), (490, 600, vec("C"))])
    rep = ls.analyze([c0, c1], e, REFS)
    _, mrep = dc.merge_chunks([c0, c1], 600.0)
    maps = mrep["mappings"]
    persons = {"C": [(0, "K")], "B": [(1, "B1")]}
    plan = ls.plan_apply(rep, persons, maps, [c0, c1])
    meds = [a for a in plan["applied"] if a["confidence"] == "MEDIUM"]
    assert meds and all(o["chunk"] in (0, 1) for o in plan["overrides"])
    assert all(z["prev_speaker"] != z["next_speaker"] for z in plan["unresolved_zones"])


# ------------------------------------------------------------------ 回帰・OFF
def test_option_off_leaves_existing_behavior_unchanged():
    import transcribe_interview as cli
    a = cli.parse_args(["x.wav"])
    assert a.apply_local_split is False and a.analyze_local_split is False
    ch, rep, base, maps, persons = setup()
    s0, r0 = dc.merge_chunks([ch], 600.0)
    s1, r1 = dc.merge_chunks([ch], 600.0, overrides=None)
    s2, _ = dc.merge_chunks([ch], 600.0, overrides=[])
    assert s0 == s1 == s2 and r1["overrides"] == []
    al, _ = make_aligned([("SPEAKER_00", "こんにちは今日はよろしく")], 0.1)
    turns = tb.build_turns(al, [{"start": 0, "end": 2, "speaker": "SPEAKER_00"}], None)
    assert all("original_speaker_id" not in t for t in turns)                 # OFFのときは変更履歴のキーも付かない


def test_r24_short_response_between_the_same_speaker_survives_a_sub_segment_override():
    text = "それは多分いかなって焼くうーん俺が違ったら面白いと思うんだよね"
    i, n = text.index("うーん"), len(text)
    al, _ = make_aligned([("SPEAKER_00", text)], 0.1)
    diar = [{"start": 0, "end": i * .1, "speaker": "SPEAKER_03"}, {"start": i * .1, "end": (i + 3) * .1, "speaker": "SPEAKER_01"},
            {"start": (i + 3) * .1, "end": n * .1, "speaker": "SPEAKER_03"}]
    ch = {"index": 0, "start": 0.0, "end": n * .1 + 1, "embeddings": None, "segments": diar}
    # 「うーん」は境界未確定ゾーン（現在の話者のまま）。ゾーンの外のDの発話の一部だけを別話者へ付け替えても、短い応答は消えない
    segs, _ = dc.merge_chunks([ch], n * .1 + 1, overrides=[{"chunk": 0, "local": "SPEAKER_03", "start": 0.0, "end": 0.5, "speaker": "SPEAKER_09"}])
    turns = tb.build_turns(al, segs, None)
    assert any(t["raw_text"] == "うーん" and t["speaker_id"] for t in turns)


def test_r22_wholesale_absorption_does_not_come_back_with_overrides():
    text = "それうちの話そうですよ蜂蜜アメ"
    al, _ = make_aligned([("SPEAKER_00", text)], 0.1)
    s = [("SPEAKER_01", 0, 6), ("SPEAKER_02", 6, 8), ("SPEAKER_01", 8, 11), ("SPEAKER_00", 11, 13), ("SPEAKER_01", 13, 15)]
    ch = {"index": 0, "start": 0.0, "end": 2.0, "embeddings": None, "segments": [{"start": a * .1, "end": b * .1, "speaker": sp} for sp, a, b in s]}
    segs, _ = dc.merge_chunks([ch], 2.0, overrides=[])
    turns = tb.build_turns(al, segs, None)
    assert not any("そうですよ蜂蜜アメ" in t["raw_text"] and t["speaker_id"] for t in turns)

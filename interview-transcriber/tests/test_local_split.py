"""local speaker内の複数人物の混在の分析（Step 1: レポートのみ。話者ラベル・transcriptは書き換えない）。"""
import json
import subprocess
import sys

import numpy as np
import pytest

import local_split as ls

B, C = np.array([1.0, 0.0]), np.array([0.0, 1.0])
REFS = {"B": B, "C": C}


def vec(person, strength="high"):
    """person の声に近いembedding。strength: high→margin大 / medium→margin 0.10〜0.20 / low→0.05〜0.10"""
    t = {"high": 0.05, "medium": 0.85, "low": 0.93}[strength]
    return np.array([1.0, t]) if person == "B" else np.array([t, 1.0])


def embedder(timeline):
    """timeline=[(開始, 終了, embedding)]。呼び出し区間の中点が入る行のembeddingを返す。呼び出しを記録する。"""
    calls = []

    def embed(a, b):
        calls.append((a, b))
        m = (a + b) / 2
        for x, y, e in timeline:
            if x <= m < y:
                return e
        return np.array([1.0, 1.0])
    embed.calls = calls
    return embed


def chunk(index, segs, start=0.0, end=3000.0):
    return {"index": index, "start": start, "end": end, "segments": [{"start": a, "end": b, "speaker": s} for s, a, b in segs]}


# ------------------------------------------------------------------ anchor抽出
def test_anchor_shorter_than_1_5_sec_is_excluded():
    spans, _ = ls.extract_anchor_spans([{"start": 0, "end": 1.4, "speaker": "L"}, {"start": 10, "end": 11.5, "speaker": "L"}], "L")
    assert spans == [(10, 11.5)]


def test_overlap_with_another_local_is_excluded():
    segs = [{"start": 0, "end": 10, "speaker": "L"}, {"start": 3, "end": 7, "speaker": "M"}]
    spans, _ = ls.extract_anchor_spans(segs, "L")
    assert all(not (a < 7.1 and b > 2.9) for a, b in spans)        # 他localの発話（前後0.1秒）を含まない
    assert spans == [] or all(b - a >= 1.5 for a, b in spans)


def test_gap_up_to_0_3_sec_is_joined_and_longer_gap_is_not():
    near = [{"start": 0, "end": 1, "speaker": "L"}, {"start": 1.3, "end": 2.6, "speaker": "L"}]
    far = [{"start": 0, "end": 1, "speaker": "L"}, {"start": 1.31, "end": 2.6, "speaker": "L"}]
    assert ls.extract_anchor_spans(near, "L")[0] == [(0, 2.6)]
    assert ls.extract_anchor_spans(far, "L")[0] == []


def test_long_anchor_is_embedded_from_the_first_10_seconds_only():
    e = embedder([(0, 100, vec("B"))])
    ls.analyze_anchors([chunk(0, [("L", 0, 40)])], e, REFS)
    assert e.calls == [(0.0, 10.0)]


# ------------------------------------------------------------------ confidence
@pytest.mark.parametrize("margin,top1,expected", [
    (0.20, 0.40, "HIGH"), (0.2001, 0.9, "HIGH"), (0.1999, 0.9, "MEDIUM"),
    (0.10, 0.9, "MEDIUM"), (0.0999, 0.9, "LOW"), (0.05, 0.9, "LOW"),
    (0.0499, 0.9, "UNKNOWN"), (0.0, 0.9, "UNKNOWN"),
    (0.5, 0.3999, "UNKNOWN"), (0.5, 0.40, "HIGH"),
])
def test_confidence_boundaries(margin, top1, expected):
    assert ls.confidence_of(margin, top1) == expected


# ------------------------------------------------------------------ block・不安定・分割
def anchors_for(labels, starts, dur=2.5, conf="HIGH"):
    return [{"chunk": 0, "local": "L", "start": s, "end": s + dur, "duration": dur, "label": lab, "top1": lab, "confidence": conf,
             "shared_with": []} for lab, s in zip(labels, starts)]


def test_c_c_c_makes_one_valid_block():
    blocks, unstable, _ = ls.build_blocks(anchors_for("CCC", [0, 10, 20]))
    assert len(blocks) == 1 and blocks[0]["person"] == "C" and blocks[0]["valid"] and not unstable


def test_block_needs_two_anchors_four_sec_and_high_or_two_mediums():
    one = ls.build_blocks(anchors_for("C", [0], dur=5.0))[0][0]
    assert not one["valid"]                                                 # 1本だけ
    short = ls.build_blocks(anchors_for("CC", [0, 10], dur=1.9))[0][0]
    assert not short["valid"]                                               # 合計4秒未満
    lows = ls.build_blocks(anchors_for("CC", [0, 10], dur=2.5, conf="LOW"))[0][0]
    assert not lows["valid"]                                                # HIGHもMEDIUMもない
    meds = ls.build_blocks(anchors_for("CC", [0, 10], dur=2.5, conf="MEDIUM"))[0][0]
    assert meds["valid"] and not meds["high_ok"]                            # MEDIUM 2本は有効（ただしHIGHではない）


def test_c_b_c_b_within_60_sec_is_unstable_and_has_no_split_proposal():
    an = anchors_for("CBCB", [0, 15, 30, 45])
    _, unstable, _ = ls.build_blocks(an)
    assert unstable
    r = ls.assess_unit(an, [(0, "L")], {0: []}, {})
    assert r["state"] == "unstable" and r["confidence"] == "UNKNOWN" and r["proposed_splits"] == []


def test_slow_alternation_is_not_unstable():
    assert not ls.build_blocks(anchors_for("CBCB", [0, 100, 200, 300]))[1]


def two_sided(n_prev=2, n_next=2, high_next=True):
    an = anchors_for("C" * n_prev, [100 + 10 * i for i in range(n_prev)])
    an += anchors_for("B" * n_next, [300 + 10 * i for i in range(n_next)], conf="HIGH" if high_next else "MEDIUM")
    return an


def test_only_one_anchor_on_one_side_does_not_split_but_is_mixed_suspected():
    an = two_sided(n_prev=1)
    r = ls.assess_unit(an, [(0, "L")], {0: []}, {})
    assert r["proposed_splits"] == [] and r["mixed_suspected"] and r["state"] == "mixed_suspected" and r["confidence"] == "LOW"


def test_both_sides_two_anchors_four_sec_and_high_gives_high_proposal_with_unresolved_zone():
    segs = {0: [{"start": 100, "end": 400, "speaker": "L"}]}
    r = ls.assess_unit(two_sided(), [(0, "L")], segs, {})
    (p,) = r["proposed_splits"]
    assert p["confidence"] == "HIGH" and (p["from_person"], p["to_person"]) == ("C", "B")
    assert p["zone_start"] == 112.5 and p["zone_end"] == 300                     # 最後の前anchorの終了〜最初の後anchorの開始
    assert p["assigned_to"] is None and p["applied"] is False                   # ゾーンはどの話者にも割り当てない
    assert r["unresolved_zones"][0]["assigned_to"] is None
    assert p["speech_in_zone_sec"] == pytest.approx(187.5)


def test_medium_only_side_is_a_medium_proposal_not_high():
    r = ls.assess_unit(two_sided(high_next=False), [(0, "L")], {0: []}, {})
    assert [p["confidence"] for p in r["proposed_splits"]] == ["MEDIUM"]


def test_same_person_on_both_sides_is_not_a_split():
    an = anchors_for("CC", [0, 10]) + anchors_for("CC", [300, 310])
    r = ls.assess_unit(an, [(0, "L")], {0: []}, {})
    assert r["proposed_splits"] == []


def test_split_is_downgraded_when_it_contradicts_simultaneous_speaker():
    segs = {0: [{"start": 300, "end": 330, "speaker": "OTHER"}]}                 # Bのblockと同時に、人物Bと確認済みの別localが話している
    r = ls.assess_unit(two_sided(), [(0, "L")], segs, {(0, "OTHER"): "B"})
    (p,) = r["proposed_splits"]
    assert p["confidence"] == "MEDIUM" and p["conflicts"]


def test_insufficient_evidence_when_no_usable_anchor():
    r = ls.assess_unit([], [(9, "SPEAKER_03")], {9: []}, {})
    assert r["state"] == "insufficient_evidence" and r["evidence_state"] == "insufficient_evidence" and r["confidence"] == "UNKNOWN"


def test_weakly_identified_local_is_not_called_single_person():
    an = anchors_for("CC", [0, 10], dur=2.5, conf="MEDIUM") + anchors_for("CCCCC", [100, 110, 120, 130, 140], dur=3.0, conf="LOW")
    r = ls.assess_unit(an, [(0, "L")], {0: []}, {})
    assert r["state"] == "insufficient_evidence"                              # MEDIUM以上が過半数にならない


# ------------------------------------------------------------------ 共有anchor
def test_shared_anchor_is_counted_once():
    a = {"chunk": 8, "local": "X", "start": 100.0, "end": 103.0, "duration": 3.0, "label": "C", "top1": "C", "confidence": "MEDIUM", "shared_with": []}
    b = {"chunk": 9, "local": "Y", "start": 100.0, "end": 103.0, "duration": 3.0, "label": "C", "top1": "C", "confidence": "HIGH", "shared_with": []}
    ls.link_shared([a, b])
    assert a["shared_with"] == ["chunk9:Y"] and b["shared_with"] == ["chunk8:X"]
    kept = ls._dedupe([a, b])
    assert len(kept) == 1 and kept[0]["confidence"] == "HIGH"
    blocks = ls.build_blocks(kept + anchors_for("C", [200], dur=2.5))[0]
    assert blocks[0]["anchors"] == 2                                          # 二重に数えない（3本にならない）


def test_adjacent_chunks_overlapping_audio_pools_evidence_for_a_split():
    """chunk0 local X（C→）と chunk1 local Y（→B）が、共有する音声（同じ区間）でつながる。各localだけでは片側の根拠が不足だが、まとめるとHIGH。"""
    tl = [(100, 112, vec("C")), (112, 140, vec("C")), (140, 330, vec("B"))]
    e = embedder([(100, 140, vec("C")), (140, 400, vec("B"))])
    c0 = chunk(0, [("X", 100, 103), ("X", 120, 123), ("X", 130, 133)], 0, 300)       # C側の単独区間3本
    c1 = chunk(1, [("Y", 130, 133), ("Y", 300, 303), ("Y", 330, 333)], 130, 400)      # 共有（130〜133）＋B側2本
    rep = ls.analyze([c0, c1], e, REFS)
    ex = next(x for x in rep["locals"] if x["local"] == "X")
    ey = next(x for x in rep["locals"] if x["local"] == "Y")
    assert ex["state"] != "split_proposal" and ey["state"] != "split_proposal"
    highs = [p for p in rep["proposed_splits"] if p["confidence"] == "HIGH"]
    assert len(highs) == 1 and highs[0]["from_person"] == "C" and highs[0]["to_person"] == "B"
    assert rep["summary"]["shared_anchor_links"] == 1 and rep["applied"] is False


# ------------------------------------------------------------------ 全体・レポート
def test_analyze_needs_at_least_two_reference_persons():
    with pytest.raises(ValueError):
        ls.analyze([chunk(0, [("L", 0, 5)])], embedder([]), {"B": B})


def test_report_files_are_written_and_nothing_is_applied(tmp_path):
    e = embedder([(0, 400, vec("B"))])
    ch = [chunk(0, [("L", 0, 5), ("L", 20, 25)])]
    before = json.dumps(ch)
    rep = ls.analyze(ch, e, REFS, declared={"B": [(0, "L")]})
    jp, mp = ls.write_reports(rep, tmp_path)
    data = json.loads(jp.read_text(encoding="utf-8"))
    assert data["applied"] is False and "まだtranscriptへ反映していない" in mp.read_text(encoding="utf-8")
    e0 = data["locals"][0]
    for k in ("mixed_suspected", "anchors", "blocks", "proposed_splits", "confidence", "unresolved_zones", "evidence_sources", "warnings"):
        assert k in e0
    assert json.dumps(ch) == before                                           # 入力（diarizationのチャンク）を書き換えない


def test_check_points_compare_with_human_confirmed_time():
    e = embedder([(0, 400, vec("B"))])
    rep = ls.analyze([chunk(0, [("L", 0, 5), ("L", 20, 25)])], e, REFS)
    cp = ls.check_points(rep, [{"time": 2, "person": "B"}, {"time": 22, "person": "C"}])
    assert cp[0]["match"] is True and cp[1]["match"] is False


def test_f_chain_like_local_without_good_anchors_is_insufficient_evidence():
    e = embedder([(0, 400, vec("B"))])
    rep = ls.analyze([chunk(9, [("SPEAKER_03", 0, 1.0), ("SPEAKER_03", 5, 6.0), ("SPEAKER_00", 0, 50)])], e, REFS, declared={"B": [(9, "SPEAKER_03")]})
    f = next(x for x in rep["locals"] if x["local"] == "SPEAKER_03")
    assert f["evidence_state"] == "insufficient_evidence" and f["state"] == "insufficient_evidence"
    assert any("insufficient_evidence" in w for w in f["warnings"])


# ------------------------------------------------------------------ オプションOFFで既存挙動不変
def test_option_defaults_to_off_and_module_is_not_loaded_in_normal_runs():
    import transcribe_interview as cli
    a = cli.parse_args(["x.wav"])
    assert a.analyze_local_split is False and a.local_split_refs is None and a.local_split_persons is None
    out = subprocess.run([sys.executable, "-c", "import transcribe_interview, sys; print('local_split' in sys.modules)"],
                         capture_output=True, text=True, cwd=str(__import__('pathlib').Path(__file__).resolve().parent.parent))
    assert out.stdout.strip().endswith("False")

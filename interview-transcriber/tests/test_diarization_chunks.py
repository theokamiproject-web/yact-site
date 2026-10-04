"""長い音声の再開可能なチャンク方式の話者分離（diarization_chunks.py）。実音声・pyannote 不要（偽のdiarizerを使う）。"""
import json
import sys
import types

import numpy as np
import pytest

import diarization as dz
import diarization_chunks as dc

DUR = 700.0   # chunk 300 / overlap 30 → 3チャンク: 0-300 / 270-570 / 540-700
TRUTH = [("A", 0, 100), ("B", 100, 150), ("A", 150, 200), ("A", 250, 298), ("B", 298, 400),
         ("C", 400, 500), ("B", 500, 566), ("C", 566, 700)]
# 実際の人物 → チャンクごとの（独立した）ローカルSPEAKER ID。番号が同じでも同一人物ではない。
LOCAL = [{"A": "SPEAKER_00", "B": "SPEAKER_01", "C": "SPEAKER_02"},
         {"A": "SPEAKER_02", "B": "SPEAKER_00", "C": "SPEAKER_01"},
         {"A": "SPEAKER_01", "B": "SPEAKER_02", "C": "SPEAKER_00"}]
VEC = {"A": np.array([1.0, 0, 0, 0]), "B": np.array([0, 1.0, 0, 0]), "C": np.array([0, 0, 1.0, 0]), "D": np.array([0, 0, 0, 1.0])}


def chunk_index(start):
    return min(range(3), key=lambda i: abs([0.0, 270.0, 540.0][i] - start))


class Fake:
    def __init__(self, with_emb=True, fail_at=None, truth=TRUTH, emb_override=None):
        self.calls, self.with_emb, self.fail_at, self.truth, self.emb_override = [], with_emb, fail_at, truth, emb_override or {}

    def __call__(self, audio, start, end, max_speakers):
        i = chunk_index(start)
        if self.fail_at == i:
            raise RuntimeError("cloud restarted")      # 環境の再起動を模す
        self.calls.append(i)
        segs, used = [], set()
        for person, a, b in self.truth:
            lo, hi = max(a, start), min(b, end)
            if hi - lo > 0.01:
                lab = LOCAL[i].get(person, "SPEAKER_03")
                segs.append({"start": lo - start, "end": hi - start, "speaker": lab})
                used.add((person, lab))
        emb = None
        if self.with_emb:
            emb = {}
            for person, lab in used:
                v = self.emb_override.get((i, person), VEC[person])
                emb[lab] = (v + 0.01).tolist()
        return segs, emb


def run(tmp_path, fn, fp="fp1", **kw):
    audio = np.zeros(int(DUR * 16000), dtype=np.float32)
    return dc.run_chunked(audio, DUR, fn, tmp_path / "diarization_chunks", fingerprint=fp, model="m", max_speakers=4,
                          logger=lambda m: None, **kw)


def person_at(t):
    return next(p for p, a, b in TRUTH if a <= t < b)


def label_to_person(segs):
    """統合結果の各セグメントの中点の実際の人物 → 全体speaker名。人物と全体speakerが1対1か検証するための対応。"""
    m = {}
    for s in segs:
        m.setdefault(s["speaker"], set()).add(person_at((s["start"] + s["end"]) / 2))
    return m


# ---------------------------------------------------------------- 計画
def test_plan_has_overlap_and_covers_the_whole_audio():
    plan = dc.plan_chunks(DUR, 300, 30)
    assert [(c["start"], c["end"]) for c in plan] == [(0, 300), (270, 570), (540, 700)]
    assert dc.plan_chunks(3308, 300, 30)[-1]["end"] == 3308 and len(dc.plan_chunks(3308, 300, 30)) == 13
    tail = dc.plan_chunks(590, 300, 30)             # 末尾が極端に短いチャンクは前に吸収
    assert [(c["start"], c["end"]) for c in tail] == [(0, 300), (270, 590)]


# ---------------------------------------------------------------- 1) 3チャンク中2つ完了後に停止 → 3つ目から再開
def test_resume_from_the_unfinished_chunk_after_a_crash(tmp_path):
    first = Fake(fail_at=2)
    with pytest.raises(RuntimeError):
        run(tmp_path, first)
    d = tmp_path / "diarization_chunks"
    assert first.calls == [0, 1]
    assert sorted(p.name for p in d.glob("chunk_*.json")) == ["chunk_000.json", "chunk_001.json"]   # 各チャンク終了直後に保存
    st = json.loads((d / "state.json").read_text())
    assert st["completed_chunks"] == [0, 1] and st["current_chunk"] == 2 and st["total_chunks"] == 3
    assert st["source_audio_fingerprint"] == "fp1" and st["model"] == "m" and st["max_speakers"] == 4
    assert [(c["start"], c["end"]) for c in st["chunks"]] == [(0, 300), (270, 570), (540, 700)]
    second = Fake()
    segs, rep = run(tmp_path, second)
    # 2) 完了済みchunkは再実行しない
    assert second.calls == [2]
    assert (d / "chunk_002.json").exists() and (d / "merge_report.json").exists() and segs


def test_fully_completed_run_does_not_call_the_diarizer_again(tmp_path):
    run(tmp_path, Fake())
    again = Fake()
    run(tmp_path, again)
    assert again.calls == []


# ---------------------------------------------------------------- 3) 音声が変わったら古いキャッシュを使わない
@pytest.mark.parametrize("change", [{"fp": "other"}, {"chunk_sec": 280.0}, {"overlap_sec": 20.0}])
def test_stale_chunk_cache_is_not_used_when_the_source_or_settings_change(tmp_path, change):
    run(tmp_path, Fake())
    f = Fake()
    kw = dict(change)
    fp = kw.pop("fp", "fp1")
    run(tmp_path, f, fp=fp, **kw) if kw else run(tmp_path, f, fp=fp)
    assert len(f.calls) >= 3                       # 全チャンクをやり直す


def test_chunk_files_without_state_are_not_trusted(tmp_path):
    d = tmp_path / "diarization_chunks"
    d.mkdir()
    (d / "chunk_000.json").write_text(json.dumps({"index": 0, "start": 0.0, "end": 300.0, "segments": [], "embeddings": None}))
    f = Fake()
    run(tmp_path, f)
    assert f.calls == [0, 1, 2]


# ---------------------------------------------------------------- 4) 重なり部分が二重に出力されない
@pytest.mark.parametrize("with_emb", [True, False])
def test_overlap_is_not_output_twice_and_times_are_absolute(tmp_path, with_emb):
    segs, rep = run(tmp_path, Fake(with_emb=with_emb))
    by = {}
    for s in segs:
        assert 0 <= s["start"] < s["end"] <= DUR + 1e-6                      # 元音声全体の絶対時刻（7）
        by.setdefault(s["speaker"], []).append(s)
    for lst in by.values():                                                   # 同じ話者の時間が重ならない（二重出力なし）
        lst.sort(key=lambda s: s["start"])
        assert all(a["end"] <= b["start"] + 1e-6 for a, b in zip(lst, lst[1:]))
    covered = sum(s["end"] - s["start"] for s in segs)
    assert covered == pytest.approx(sum(b - a for _, a, b in TRUTH), abs=0.05)   # 合計がちょうど元の発話時間
    assert not any(a["speaker"] == b["speaker"] and abs(a["end"] - b["start"]) < 0.01 for a, b in zip(segs, segs[1:])
                   if round(a["end"], 1) in {round(c, 1) for c in rep["cut_points"]})   # 切り出し位置で分断されていない
    assert rep["cut_points"] == [285.0, 555.0]


# ---------------------------------------------------------------- 5) チャンクごとのSPEAKER_00を無条件に同一人物扱いしない
@pytest.mark.parametrize("with_emb", [True, False])
def test_same_local_id_in_different_chunks_is_not_assumed_to_be_the_same_person(tmp_path, with_emb):
    segs, rep = run(tmp_path, Fake(with_emb=with_emb))
    m = label_to_person(segs)
    assert all(len(v) == 1 for v in m.values()), m                           # 1つの全体speakerは1人の実際の人物だけ
    assert len({next(iter(v)) for v in m.values()}) == len(m) == 3           # 3人が3つの全体speakerに（過不足なし）
    if with_emb:
        assert rep["unresolved"] == []
    else:   # 埋め込みが無いとき、チャンク1で初めて登場するC（重なり区間では無言）は証拠が無いので要確認になる（Cだけ）
        assert [u["chunk"] for u in rep["unresolved"]] == [1]
    # 番号どおりに結合していたら誤る: チャンク1のSPEAKER_00 は実際はB、チャンク0のSPEAKER_00 はA
    raw1 = json.loads((tmp_path / "diarization_chunks" / "chunk_001.json").read_text())
    assert "SPEAKER_00" in {s["speaker"] for s in raw1["segments"]}      # チャンク1にも SPEAKER_00 はあるが…
    assert any(m["local"] != m["global"] for m in rep["matches"] if m["chunk"] == 1)               # 対応は番号のままではない


def test_embedding_only_match_when_there_is_no_overlap_evidence(tmp_path):
    # 重なり区間で誰も話していない音声: 時刻の証拠が無くても、埋め込みが明確ならつなぐ。
    truth = [("A", 0, 200), ("B", 200, 260), ("A", 330, 420), ("B", 420, 520), ("A", 600, 700)]   # 270〜300 は無音
    segs, rep = run(tmp_path, Fake(truth=truth))
    assert rep["unresolved"] == []
    by = {}
    for s in segs:
        by.setdefault(s["speaker"], []).append(s)
    assert len(by) == 2


# ---------------------------------------------------------------- 6) 統合に自信がなければ要確認にし、無理にまとめない
def test_no_evidence_and_no_embeddings_is_flagged_and_not_merged(tmp_path):
    truth = [("A", 0, 200), ("B", 200, 260), ("A", 330, 420), ("B", 420, 520), ("A", 600, 700)]   # 重なり区間は無音
    segs, rep = run(tmp_path, Fake(with_emb=False, truth=truth))
    assert rep["unresolved"], "証拠が無いのに同一人物としてまとめている"
    assert any("チャンク間speaker対応 要確認" in n for n in rep["notes"])
    assert len({s["speaker"] for s in segs}) > 2                                # 別の話者として扱った（無理にまとめない）


def test_contradicting_embedding_blocks_the_time_based_match(tmp_path):
    # 重なり区間の時刻はBと一致するが、埋め込みが全く違う → 同一人物と断定しない
    segs, rep = run(tmp_path, Fake(emb_override={(2, "B"): np.array([0, 0, 0, 1.0])}))
    assert any(u["chunk"] == 2 for u in rep["unresolved"])
    assert any("チャンク間speaker対応 要確認" in n for n in rep["notes"])


def test_new_speaker_clearly_different_by_embedding_is_not_flagged(tmp_path):
    truth = TRUTH[:-1] + [("C", 566, 600), ("D", 600, 700)]
    segs, rep = run(tmp_path, Fake(truth=truth))
    assert rep["unresolved"] == []
    assert len({s["speaker"] for s in segs}) == 4


def test_each_global_speaker_is_used_once_per_chunk(tmp_path):
    segs, rep = run(tmp_path, Fake())
    for k in (1, 2):
        g = [m["global"] for m in rep["matches"] if m["chunk"] == k]
        assert len(g) == len(set(g))


# ---------------------------------------------------------------- 標準は従来どおり（短い音源は一括）
def test_short_audio_uses_the_single_pass_diarization(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(dz, "run_diarization", lambda *a, **k: (calls.append(a), [{"start": 0.0, "end": 1.0, "speaker": "SPEAKER_00"}])[1])
    segs, info = dz.diarize(tmp_path / "x.wav", "cpu", "tok", None, None, None, "m", duration=600.0,
                            chunk_dir=tmp_path / "c", fingerprint="f")
    assert len(calls) == 1 and info is None and segs == [{"start": 0.0, "end": 1.0, "speaker": "SPEAKER_00"}]
    assert not (tmp_path / "c").exists()


def test_long_audio_is_chunked_and_saved_per_chunk(tmp_path, monkeypatch):
    fake_wx = types.ModuleType("whisperx")
    fake_wx.load_audio = lambda p: np.zeros(int(DUR * 16000), dtype=np.float32)
    monkeypatch.setitem(sys.modules, "whisperx", fake_wx)
    f = Fake()
    monkeypatch.setattr(dz, "make_chunk_diarizer", lambda *a, **k: f)
    monkeypatch.setattr(dz, "run_diarization", lambda *a, **k: pytest.fail("長い音声を一括で処理してはいけない"))
    segs, info = dz.diarize(tmp_path / "x.wav", "cpu", "tok", None, None, 4, "m", duration=DUR, chunk_dir=tmp_path / "c",
                            fingerprint="f", auto_threshold=600.0)
    assert info is not None and f.calls == [0, 1, 2] and (tmp_path / "c" / "chunk_002.json").exists() and segs


def test_relative_embedding_rule_matches_a_clearly_closest_speaker_without_time_evidence(tmp_path):
    truth = [("A", 0, 200), ("B", 200, 260), ("A", 330, 420), ("B", 420, 520), ("A", 600, 700)]   # 重なり区間は無音
    b_like = 0.65 * VEC["B"] + np.sqrt(1 - 0.65 ** 2) * VEC["D"]                                  # Bと類似度0.65（他とは約0）
    segs, rep = run(tmp_path, Fake(truth=truth, emb_override={(1, "B"): b_like}))
    assert not [u for u in rep["unresolved"] if u["local"] == LOCAL[1]["B"] and u["chunk"] == 1]
    assert len({s["speaker"] for s in segs}) == 2

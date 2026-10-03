import json
import re
from pathlib import Path

import pytest

import editor
import quality_check as qc
import transcribe_interview as cli
import transcript_builder as tb
from helpers import FakeLLM, make_aligned
from text_utils import extract_numbers, is_backchannel, number_diff, rule_clean

LINES = [
    ("SPEAKER_00", "えー、まあ、最初はですね、なんというか、そんな大きなことを、まあ、やろうとは思ってなかったんですよね。"),
    ("SPEAKER_01", "そうだったんですか？"),
    ("SPEAKER_00", "そうなんですよ。"),
    ("SPEAKER_00", "始めたのは2024年の10月で、参加者は30人くらいでした。"),
    ("SPEAKER_01", "はい。"),
    ("SPEAKER_00", "予算は50万円くらいで、来年の5月くらいにまた開催したいと思っています。"),
]


# ------------------------------------------------------------ text rules
def test_spec_example_filler_removal():
    out = rule_clean(LINES[0][1])
    assert "えー" not in out and "まあ" not in out and "なんというか" not in out
    assert out == "最初はですね、そんな大きなことを、やろうとは思ってなかったんですよね。"


def test_demonstrative_ano_is_kept():
    assert rule_clean("あの人が来ました。") == "あの人が来ました。"


def test_number_normalization():
    assert extract_numbers("二〇二四年の三月、百万円、1,200円") == [(2024, "年"), (3, "月"), (1000000, "円"), (1200, "円")]
    assert extract_numbers("一緒に万が一") == []  # 単位の付かない単独の漢数字は数として扱わない


def test_backchannel():
    assert is_backchannel("そうですね。") and not is_backchannel("そうだったんですか？")


# ------------------------------------------------------------ builder
def build(lines=LINES, **kw):
    aligned, diar = make_aligned(lines)
    turns = tb.build_turns(aligned, diar, **kw)
    tb.apply_speaker_names(turns, {"SPEAKER_00": "真坂", "SPEAKER_01": "寺戸"})
    tb.apply_clean(turns)
    return turns


def test_turns_follow_speakers_and_keep_timecodes():
    turns = build()
    assert [t["speaker_name"] for t in turns][:3] == ["真坂", "寺戸", "真坂"]
    assert all(t["start"] < t["end"] for t in turns)
    assert all(t["words"] for t in turns)  # 追跡用の単語タイムスタンプ


def test_same_speaker_fragments_merge_but_not_across_other_speaker():
    lines = [("SPEAKER_00", "最初は、"), ("SPEAKER_00", "そんなに大きなことを、"),
             ("SPEAKER_01", "そうなんですね。"), ("SPEAKER_00", "やろうと思ってなかったんですよ。")]
    aligned, diar = make_aligned(lines)
    turns = tb.build_turns(aligned, diar)
    assert [t["speaker_id"] for t in turns] == ["SPEAKER_00", "SPEAKER_01", "SPEAKER_00"]
    assert turns[0]["raw_text"] == "最初は、そんなに大きなことを、"


def test_backchannel_dropped_but_answer_to_question_kept():
    turns = build()
    by = {t["raw_text"]: t for t in turns}
    assert by["はい。"]["clean_dropped"] is True
    assert by["そうだったんですか？"]["clean_dropped"] is False
    answer = next(t for t in turns if t["raw_text"].startswith("そうなんですよ。"))  # 質問への返答は残す
    assert answer["clean_dropped"] is False


def test_unknown_speakers_are_not_forced():
    aligned, _ = make_aligned(LINES)
    turns = tb.build_turns(aligned, None)
    tb.apply_speaker_names(turns, {})
    tb.apply_clean(turns)
    assert {t["speaker_name"] for t in turns} == {"話者不明"}
    assert not any(t["clean_dropped"] for t in turns if t["raw_text"] == "はい。")


def test_unnamed_speakers_get_letters():
    turns = build()
    tb.apply_speaker_names(turns, {})
    assert {t["speaker_name"] for t in turns} == {"話者A", "話者B"}


# ------------------------------------------------------------ quality check
def mk(raw, i=0, spk="真坂"):
    return {"id": i, "speaker_id": spk, "speaker_name": spk, "start": 1932.0, "raw_text": raw}


def kinds(issues):
    return {i.kind for i in issues}


def test_detects_date_added_spec_example():
    iss = qc.check_turn(mk("来年の5月くらい"), "来年5月15日")
    assert "年月日の追加" in kinds(iss) and any(i.severity == qc.HIGH for i in iss)


def test_detects_changed_amount_and_number():
    assert "金額の変更" in kinds(qc.check_turn(mk("予算は50万円です"), "予算は500万円です"))
    assert "数字の変更" in kinds(qc.check_turn(mk("30人くらい"), "20人くらい"))


def test_notation_change_is_not_flagged():
    assert not [i for i in qc.check_turn(mk("二〇二四年の三月"), "2024年3月")
                if i.kind.endswith(("追加", "変更", "欠落"))]


def test_detects_new_proper_noun():
    assert "固有名詞の追加" in kinds(qc.check_turn(mk("劇場でやりました"), "ノアノオモチャバコでやりました"))


def test_detects_hedge_removed_and_negation_flip():
    assert "ニュアンス変化" in kinds(qc.check_turn(mk("たぶん来年やると思います"), "来年やります"))
    assert "否定表現の増減" in kinds(qc.check_turn(mk("それはやらないです"), "それはやるです"))


def test_detects_unclear_filled_and_mass_deletion():
    raw = "あの件は[聞き取り不明 00:12:34]でした"
    assert "聞き取り不明の補完" in kinds(qc.check_turn(mk(raw), "あの件は予算の問題でした"))
    long = "これは本当に長い発言で、いろいろな内容を含んでいて、削除されると困る大事な話なのです。" * 2
    assert "大量削除" in kinds(qc.check_turn(mk(long), "大事な話です"))


def test_detects_speaker_leak():
    neighbors = [mk("まず企画の背景から、地域の拠点づくりについてお話しします", 0, "寺戸"), mk("x", 1)]
    iss = qc.check_turn(mk("はい", 1), "まず企画の背景から、地域の拠点づくりについてお話しします", ["寺戸"], neighbors=neighbors)
    assert "別話者の発言混入" in kinds(iss)
    assert "話者ラベル混入" in kinds(qc.check_turn(mk("はい"), "寺戸：はい", ["寺戸"]))


def test_clean_pass_has_no_issue():
    assert not qc.check_turn(mk("えー、2024年の10月です。"), "2024年の10月です。")


# ------------------------------------------------------------ chunking
def test_chunks_cover_each_turn_once_with_context_overlap():
    turns = [{"id": i, "speaker_id": f"S{i % 2}", "speaker_name": "a", "raw_text": "あ" * 100 + "。",
              "pause_after": 0.0} for i in range(300)]  # 約3万字
    chunks = editor.build_chunks(turns, target_chars=2500, max_chars=3600)
    ids = [t["id"] for c in chunks for t in c["target"]]
    assert ids == list(range(300))
    assert all(sum(len(t["raw_text"]) for t in c["target"]) <= 3600 for c in chunks)
    assert chunks[0]["context"] == [] and all(c["context"] for c in chunks[1:])
    assert chunks[1]["context"][-1]["id"] == chunks[1]["target"][0]["id"] - 1


def test_chunk_boundary_prefers_pause_and_speaker_change():
    turns = [{"id": i, "speaker_id": "S0", "speaker_name": "a", "raw_text": "あ" * 100 + "。", "pause_after": 0.1}
             for i in range(60)]
    turns[27]["pause_after"] = 3.0
    turns[27]["speaker_id"] = "S0"
    turns[28]["speaker_id"] = "S1"
    chunks = editor.build_chunks(turns, target_chars=2800, max_chars=4000)
    assert chunks[0]["target"][-1]["id"] == 27


def test_parse_output_ignores_foreign_ids_and_duplicates():
    out = editor.parse_output("[1] 本文A\n[99] 余計\n[1] 重複\n[2] <削除>\n[3] 本文C", [1, 2, 3])
    assert out == {1: "本文A", 2: "", 3: "本文C"}


# ------------------------------------------------------------ end to end (偽LLM)
def run_cli(tmp_path, monkeypatch, llm_url, extra=()):
    """キャッシュだけで実行（音声・WhisperX不要）。"""
    aligned, diar = make_aligned(LINES)
    cdir = tmp_path / "cache" / "talk"
    cdir.mkdir(parents=True)
    (cdir / "whisper_result.json").write_text(json.dumps({"segments": aligned["segments"], "language": "ja"}))
    (cdir / "aligned_result.json").write_text(json.dumps(aligned))
    (cdir / "diarization_result.json").write_text(json.dumps({"key": {}, "segments": diar}))
    spk = tmp_path / "speakers.yaml"
    spk.write_text("SPEAKER_00: 真坂\nSPEAKER_01: 寺戸\n", encoding="utf-8")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", llm_url)
    monkeypatch.setattr("editor.time.sleep", lambda s: None)
    out = tmp_path / "out"
    rc = cli.main([str(tmp_path / "talk.m4a"), "--skip-transcription", "--cache-dir", str(tmp_path / "cache"),
                   "--output-dir", str(out), "--speakers", str(spk), "--dictionary", str(tmp_path / "none.yaml"),
                   *extra])
    return rc, out


def echo_clean(user):
    """行ごとに rule_clean 相当を返す、行儀の良い偽LLM。"""
    out = []
    sec = False
    for ln in user.splitlines():
        if ln.startswith("【編集対象"):
            sec = True
            continue
        m = re.match(r"\[(\d+)\] [^:]+: (.*)", ln)
        if sec and m:
            t = rule_clean(m.group(2))
            out.append(f"[{m.group(1)}] {'<削除>' if t in ('はい。',) else t}")
    return "\n".join(out)


def test_e2e_good_llm(tmp_path, monkeypatch):
    llm = FakeLLM(echo_clean)
    try:
        rc, out = run_cli(tmp_path, monkeypatch, llm.url)
    finally:
        llm.close()
    assert rc == 0 and llm.calls and llm.calls[0]["key"] == "test-key"
    assert "原文にない情報を追加しない" in llm.calls[0]["system"] and "要約しない" in llm.calls[0]["system"]
    for f in ["01_raw_transcript.md", "02_clean_transcript.md", "03_magazine_interview.md",
              "transcript.json", "review_required.md"]:
        assert (out / f).exists(), f
    data = json.loads((out / "transcript.json").read_text())
    assert data[0]["raw_text"].startswith("えー") and data[0]["edit_source"] == "llm"
    assert data[0]["start"] == 0.0 and data[0]["speaker_name"] == "真坂"
    mag = (out / "03_magazine_interview.md").read_text()
    assert "真坂：\n最初はですね" in mag and "[00:" not in mag  # 既定ではタイムコードなし
    assert "はい。\n" not in mag.replace("そうなんですよ。", "")


def test_e2e_bad_llm_is_rejected_and_reported(tmp_path, monkeypatch):
    def bad(user):
        return echo_clean(user).replace("来年の5月くらい", "来年5月15日").replace("50万円", "500万円")
    llm = FakeLLM(bad)
    try:
        rc, out = run_cli(tmp_path, monkeypatch, llm.url, ["--timestamps"])
    finally:
        llm.close()
    data = json.loads((out / "transcript.json").read_text())
    rejected = [d for d in data if d["edit_source"] == "llm-rejected"]
    assert rejected and "15日" in rejected[0]["llm_rejected_text"] and "15日" not in rejected[0]["edited_text"]
    review = (out / "review_required.md").read_text()
    assert "来年5月15日" in review and "原文に存在しない" in review and "RAW:" in review and "EDITED:" in review
    assert "15日" not in (out / "03_magazine_interview.md").read_text()
    assert "[00:00:" in (out / "03_magazine_interview.md").read_text()  # --timestamps


def test_e2e_llm_failure_falls_back_and_keeps_going(tmp_path, monkeypatch):
    def boom(user):
        raise RuntimeError("quota")
    llm = FakeLLM(boom)
    try:
        rc, out = run_cli(tmp_path, monkeypatch, llm.url)
    finally:
        llm.close()
    assert rc == 0
    data = json.loads((out / "transcript.json").read_text())
    assert all(d["edit_source"] == "rule-fallback" for d in data)
    assert "LLM編集に失敗" in (out / "review_required.md").read_text()


def test_e2e_edit_resume_uses_cache(tmp_path, monkeypatch):
    llm = FakeLLM(echo_clean)
    try:
        run_cli(tmp_path, monkeypatch, llm.url)
        n = len(llm.calls)
        # 出力と同じ cache を使って再編集 → LLMは呼ばれない
        (tmp_path / "out" / "03_magazine_interview.md").unlink()
        cli.main([str(tmp_path / "talk.m4a"), "--skip-transcription", "--cache-dir", str(tmp_path / "cache"),
                  "--output-dir", str(tmp_path / "out"), "--dictionary", str(tmp_path / "none.yaml")])
        assert len(llm.calls) == n
        assert (tmp_path / "out" / "03_magazine_interview.md").exists()
    finally:
        llm.close()


def test_raw_only_and_skip_edit(tmp_path, monkeypatch):
    rc, out = run_cli(tmp_path, monkeypatch, "http://127.0.0.1:1", ["--raw-only"])
    assert (out / "01_raw_transcript.md").exists() and not (out / "02_clean_transcript.md").exists()
    rc, out2 = run_cli(tmp_path / "b" if (tmp_path / "b").mkdir() is None else tmp_path, monkeypatch,
                       "http://127.0.0.1:1", ["--skip-edit"])
    assert (out2 / "02_clean_transcript.md").exists() and not (out2 / "03_magazine_interview.md").exists()

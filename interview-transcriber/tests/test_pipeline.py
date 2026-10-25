import json
import re
from pathlib import Path

import pytest

import editor
import whisperx_runner as wx_runner
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
def run_cli(tmp_path, monkeypatch, llm_url, extra=(), editor="claude"):
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
                   *(["--editor", editor] if editor else []), *extra])
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
                  "--output-dir", str(tmp_path / "out"), "--dictionary", str(tmp_path / "none.yaml"),
                  "--editor", "claude"])
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


# ------------------------------------------------------------ 無料・ルールベースが標準
def test_default_run_never_calls_paid_api_even_if_key_is_set(tmp_path, monkeypatch):
    llm = FakeLLM(echo_clean)
    try:
        rc, out = run_cli(tmp_path, monkeypatch, llm.url, editor=None)  # --editor 指定なし
    finally:
        llm.close()
    assert rc == 0 and llm.calls == []
    data = json.loads((out / "transcript.json").read_text())
    assert {d["edit_source"] for d in data} == {"rule"}
    assert (out / "03_magazine_interview.md").exists()


def test_default_run_completes_without_any_keys_or_hf_token(tmp_path, monkeypatch):
    """キャッシュに話者分離が無い＝HF_TOKENなし相当でも、最後まで完走し話者不明で出力する。"""
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "HF_TOKEN", "EDITOR_PROVIDER", "LOCAL_LLM_BASE_URL"):
        monkeypatch.delenv(k, raising=False)
    aligned, _ = make_aligned(LINES)
    cdir = tmp_path / "cache" / "talk"
    cdir.mkdir(parents=True)
    (cdir / "whisper_result.json").write_text(json.dumps({"segments": aligned["segments"], "language": "ja"}))
    (cdir / "aligned_result.json").write_text(json.dumps(aligned))
    out = tmp_path / "out"
    rc = cli.main([str(tmp_path / "talk.m4a"), "--skip-transcription", "--cache-dir", str(tmp_path / "cache"),
                   "--output-dir", str(out), "--dictionary", str(tmp_path / "none.yaml")])
    assert rc == 0
    for f in ["01_raw_transcript.md", "02_clean_transcript.md", "03_magazine_interview.md",
              "transcript.json", "review_required.md"]:
        assert (out / f).exists(), f
    assert "話者不明" in (out / "03_magazine_interview.md").read_text()


def test_explicit_unreachable_llm_falls_back_to_rule(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "")  # local 指定だが未設定 → エラーにせずルール整文
    rc, out = run_cli(tmp_path, monkeypatch, "http://127.0.0.1:1", editor="local")
    assert rc == 0 and (out / "03_magazine_interview.md").exists()
    assert "初期化できませんでした" in (out / "review_required.md").read_text()


# ------------------------------------------------------------ ルールベース整文の強化
def test_restart_and_stutter_cleanup():
    assert rule_clean("や、やろうとは、あの、思ってなかったんですよね。") == "やろうとは、思ってなかったんですよね。"
    assert rule_clean("この、この企画について。") == "この企画について。"
    assert rule_clean("はい、はいはい。") == "はい、はいはい。"  # 相槌の反復は触らない


def test_backchannel_sequences():
    assert is_backchannel("はいはい。") and is_backchannel("ええ、なるほど。")
    assert not is_backchannel("はい、参加者は30人でした。")


def test_spec_magazine_example_fragments_are_joined():
    """仕様の例: 3つの細切れ発言が1つの読みやすい発言になる（語句は足さない）。"""
    lines = [("SPEAKER_00", "えー、最初は、"), ("SPEAKER_00", "まあ、そんな大きなことを、"),
             ("SPEAKER_00", "やろうとは、あの、思ってなかったんですよね。")]
    aligned, diar = make_aligned(lines)
    turns = tb.build_turns(aligned, diar, merge_gap=0.0)  # 細切れのまま
    tb.apply_speaker_names(turns, {"SPEAKER_00": "真坂"})
    tb.apply_clean(turns)
    for t in turns:
        t["edited_text"] = editor.tidy_punct(t["clean_text"])
    mag = tb.render_magazine(turns, "x")
    assert "真坂：\n最初は、そんな大きなことを、やろうとは、思ってなかったんですよね。" in mag
    assert mag.count("真坂：") == 1


def test_magazine_does_not_merge_across_other_speaker_and_drops_backchannel():
    turns = build()
    for t in turns:
        t["edited_text"] = editor.tidy_punct(t["clean_text"])
    mag = tb.render_magazine(turns, "x")
    # 真坂 → 寺戸(質問) → 真坂(返答+続き)。寺戸の単独相槌「はい」は削除され、前後の真坂は結合される
    assert mag.count("真坂：") == 2 and mag.count("寺戸：") == 1
    assert "寺戸：\nはい" not in mag and "そうだったんですか？" in mag


def test_long_monologue_is_split_into_paragraphs_keeping_one_label():
    sent = "地域で活動しているうちに、これはもっと続けられるんじゃないかと思うようになりました。"
    lines = [("SPEAKER_00", sent)] * 8
    aligned, diar = make_aligned(lines)
    turns = tb.build_turns(aligned, diar, merge_gap=0.0)
    tb.apply_speaker_names(turns, {"SPEAKER_00": "真坂"})
    tb.apply_clean(turns)
    for t in turns:
        t["edited_text"] = t["clean_text"]
    blocks = tb.magazine_blocks(turns)
    assert len(blocks) == 1 and len(blocks[0]["paras"]) >= 2
    assert sum(len(p["ids"]) for p in blocks[0]["paras"]) == len(turns)  # 全turnを保持（追跡可能）
    assert all(len(p["text"]) <= 260 for p in blocks[0]["paras"])


def test_clean_is_per_turn_not_merged():
    turns = build()
    clean = tb.render_clean(turns, "x")
    assert clean.count("真坂：") == 3  # turnをまたいだ結合はしない


def test_join_fragments_adds_comma_only_after_connective_endings():
    from text_utils import join_fragments
    assert join_fragments("最初は", "そんな大きなことを") == "最初は、そんな大きなことを"
    assert join_fragments("そんな大きなことを", "やろうと") == "そんな大きなことをやろうと"
    assert join_fragments("やりました。", "次に") == "やりました。次に"


def test_punctuation_tidy_and_paragraph_close():
    assert editor.tidy_punct("それは，本当です。。 ね?") == "それは、本当です。ね？"
    # 仕様変更(PHASE1): 末尾の読点を句点へ置換しない。確実に終わっている文にだけ句点を付ける
    assert tb.close_paragraph("続きます、") == "続きます、"
    assert tb.close_paragraph("続きます") == "続きます。"


# ============================================================ PHASE 1
# ---- 1) 辞書は既定ではWhisperXの initial_prompt に渡さない
def _run_with_fake_whisperx(tmp_path, monkeypatch, lines, extra=(), dict_terms=("由利本荘市", "アキタウミヨコ"),
                            hf_token="dummy", fake_diar=True, extra_diar=()):
    """WhisperX/ffmpeg を差し替えて main を実行し、ASRに渡された initial_prompt を捕捉する。"""
    import whisperx_runner as wx
    import diarization as dz
    seen = {}
    aligned, diar = make_aligned(lines)
    (tmp_path / "talk.m4a").write_bytes(b"dummy")
    dic = tmp_path / "dictionary.yaml"
    dic.write_text("places:\n" + "".join(f"  - {t}\n" for t in dict_terms), encoding="utf-8")
    monkeypatch.setattr(wx, "check_ffmpeg", lambda: None)
    monkeypatch.setattr(wx, "validate_audio", lambda p: 10.0)
    monkeypatch.setattr(wx, "preprocess", lambda *a, **k: tmp_path / "x.wav")

    def fake_transcribe(wav, cfg):
        seen["prompt"] = cfg.initial_prompt
        seen["calls"] = seen.get("calls", 0) + 1
        return {"segments": aligned["segments"], "language": "ja"}

    monkeypatch.setattr(wx, "transcribe", fake_transcribe)
    monkeypatch.setattr(wx, "align", lambda *a, **k: aligned)
    if fake_diar:
        monkeypatch.setattr(dz, "run_diarization", lambda *a, **k: diar + list(extra_diar))
    if hf_token:
        monkeypatch.setenv("HF_TOKEN", hf_token)
    else:
        monkeypatch.delenv("HF_TOKEN", raising=False)
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "EDITOR_PROVIDER"):
        monkeypatch.delenv(k, raising=False)
    out = tmp_path / "out"
    rc = cli.main([str(tmp_path / "talk.m4a"), "--cache-dir", str(tmp_path / "cache"), "--output-dir", str(out),
                   "--speakers", str(tmp_path / "none.yaml"), "--dictionary", str(dic), *extra])
    return rc, out, seen


def test_default_run_passes_no_initial_prompt(tmp_path, monkeypatch):
    rc, out, seen = _run_with_fake_whisperx(tmp_path, monkeypatch, [("SPEAKER_00", "由利本荘市で始めました。")])
    assert rc == 0 and seen["prompt"] is None          # 標準: initial_prompt なし（辞書があっても渡さない）
    assert (out / "03_magazine_interview.md").exists()  # APIキーなしでも完走


def test_dictionary_still_used_for_candidates_without_prompt(tmp_path, monkeypatch):
    """辞書はASRに渡さなくても、似た表記の『候補』提示には使われる（自動置換はしない）。"""
    rc, out, seen = _run_with_fake_whisperx(tmp_path, monkeypatch, [("SPEAKER_00", "由利本庄市で始めました。")])
    assert seen["prompt"] is None  # 辞書はASRに渡さない
    assert "辞書による修正候補" in (out / "review_required.md").read_text()
    assert "由利本庄市で始めました" in (out / "01_raw_transcript.md").read_text()  # 本文は置換されない


def test_dictionary_prompt_only_with_explicit_option(tmp_path, monkeypatch):
    rc, out, seen = _run_with_fake_whisperx(tmp_path, monkeypatch, [("SPEAKER_00", "始めました。")],
                                            extra=["--dictionary-prompt"])
    assert rc == 0 and seen["prompt"] and "由利本荘市" in seen["prompt"]
    assert wx_runner.NEUTRAL_ASR_PROMPT not in seen["prompt"]  # 辞書プロンプトは中立プロンプトと連結しない


# ---- 2) 離れた同一話者発言は結合しない
def mt(i, spk, text, start, end, pause=0.0):
    return {"id": i, "speaker_id": spk, "speaker_name": spk, "start": start, "end": end,
            "pause_after": pause, "edited_text": text}


def test_magazine_merges_same_speaker_with_short_gap():
    # A: 同一話者で0.5秒間隔 → 結合候補
    turns = [mt(0, "S0", "最初は、", 10.0, 11.0), mt(1, "S0", "そんな大きなことをやろうとは思ってなかったんです。", 11.5, 15.0)]
    blocks = tb.magazine_blocks(turns)
    assert len(blocks) == 1 and blocks[0]["paras"][0]["ids"] == [0, 1]


def test_magazine_never_merges_same_speaker_with_21s_gap():
    # B: 同一話者でも21秒間隔 → 絶対に結合しない（実音声 01:00→01:24 の再現）
    turns = [mt(0, "S0", "外して付けるようには作られてないってこと？", 60.8, 63.1, 0.02),
             mt(1, "S0", "でっかい姿見買ったら死ぬかと思ったの。", 84.5, 90.0)]
    blocks = tb.magazine_blocks(turns)
    assert len(blocks) == 2 and [b["paras"][0]["ids"] for b in blocks] == [[0], [1]]
    assert "外して付けるようには作られてないってこと？でっかい" not in tb.render_magazine(
        [{**t, "text": t["edited_text"]} for t in turns], "x")


def test_gap_threshold_is_configurable_and_fragment_gets_more_tolerance():
    done = [mt(0, "S0", "終わりました。", 0.0, 1.0), mt(1, "S0", "次です。", 3.5, 4.0)]      # 完結文＋2.5秒
    frag = [mt(0, "S0", "それで、そのときに", 0.0, 1.0), mt(1, "S0", "思ったんです。", 3.5, 4.0)]  # 断片＋2.5秒
    assert len(tb.magazine_blocks(done)) == 2            # 既定2.0秒 < 2.5秒 → 分ける
    assert len(tb.magazine_blocks(frag)) == 1            # 明らかな断片の続きは3.0秒まで許容
    assert len(tb.magazine_blocks(done, merge_gap=3.0)) == 1   # 設定で変更可能
    assert len(tb.magazine_blocks(frag, fragment_gap=1.0)) == 2


def test_unknown_speaker_turn_between_is_a_barrier():
    turns = [mt(0, "S0", "前半です。", 0.0, 1.0), {**mt(1, None, "", 1.2, 1.5), "speaker_name": "話者不明"},
             mt(2, "S0", "後半です。", 1.6, 2.5)]
    assert len(tb.magazine_blocks(turns)) == 2           # 削除された話者不明の発言は壁
    turns[1] = {**mt(1, "S1", "", 1.2, 1.5)}              # 確定済み話者の削除相槌は壁にしない
    assert len(tb.magazine_blocks(turns)) == 1


def test_turn_building_does_not_merge_sentences_21s_apart():
    lines = [("SPEAKER_00", "外して付けるようには作られてないってこと？"),
             ("SPEAKER_00", "でっかい姿見買ったら死ぬかと思ったの。", 21.0)]
    aligned, diar = make_aligned(lines)
    turns = tb.build_turns(aligned, diar)
    assert len(turns) == 2 and turns[1]["start"] - turns[0]["end"] > 20
    near = make_aligned([("SPEAKER_00", "一つ目です。"), ("SPEAKER_00", "二つ目です。", 0.5)])
    assert len(tb.build_turns(near[0], near[1])) == 1       # 短い間隔は従来どおり結合


# ---- 3) 不完全な断片に句点を付けない
@pytest.mark.parametrize("frag", [
    "それで、そのときに", "本当にもう成功書い", "木に直接水", "ご視聴ありがとうござ",
    "来年やりたいけど", "忙しかったので", "それはそうなんだけれども", "あの、その", "やろうとは、",
])
def test_incomplete_fragments_get_no_period(frag):
    assert tb.close_paragraph(frag.rstrip("、")) == frag.rstrip("、")


@pytest.mark.parametrize("sent", [
    "最初は、そんな大きなことをやろうとは思ってなかったんですよね", "そうなんですよ", "始めたのは去年です",
    "参加者は30人くらいでした", "ご確認ください", "それは難しいと思います",
])
def test_complete_sentences_still_get_period(sent):
    assert tb.close_paragraph(sent) == sent + "。"


def test_existing_terminators_are_left_alone_and_punct_tidy_intact():
    assert tb.close_paragraph("そうでした。") == "そうでした。" and tb.close_paragraph("本当？") == "本当？"
    assert editor.tidy_punct("それは，本当です。。 ね?") == "それは、本当です。ね？"


def test_magazine_does_not_complete_a_cut_off_fragment():
    """00:27 話者A『…成功書い』→ 話者B『てないですから。』（単語の途中で話者が切れた例）"""
    lines = [("SPEAKER_00", "ちょっとバラさないと出ないですけど、本当にもう成功書い"), ("SPEAKER_01", "てないですから。")]
    aligned, diar = make_aligned(lines)
    turns = tb.build_turns(aligned, diar)
    tb.apply_speaker_names(turns, {})
    tb.apply_clean(turns)
    for t in turns:
        t["edited_text"] = editor.tidy_punct(t["clean_text"])
    mag = tb.render_magazine(turns, "x")
    assert "成功書い\n" in mag and "成功書い。" not in mag
    assert "てないですから。" in mag


# ---- 3b) 話者交替で文が途中で切れた発言（構造的事実）には、語尾がそれらしくても句点を付けない
def test_turns_are_flagged_when_cut_mid_sentence_by_speaker_change():
    aligned, diar = make_aligned([("SPEAKER_00", "それはたぶんどっちかだ"), ("SPEAKER_01", "と思いますよ、本当に。")])
    turns = tb.build_turns(aligned, diar)
    assert [t["cut_end"] for t in turns] == [True, False] and [t["cut_start"] for t in turns] == [False, True]
    # 文末（。）で終わってから話者が替わる場合は切れていない
    aligned, diar = make_aligned([("SPEAKER_00", "どっちかです。"), ("SPEAKER_01", "そうですか。")])
    assert not any(t["cut_end"] or t["cut_start"] for t in tb.build_turns(aligned, diar))


def test_cut_turn_with_confident_looking_ending_gets_no_period():
    # 実音声(Track-78)で起きた「…どっちかだ。」「…ーあります。」の再現
    cut = {**mt(0, "S0", "どっちかだ", 0.0, 1.0), "cut_end": True}
    whole = {**mt(0, "S0", "どっちかだ", 0.0, 1.0), "cut_end": False}
    assert tb.magazine_blocks([cut])[0]["paras"][0]["text"] == "どっちかだ"
    assert tb.magazine_blocks([whole])[0]["paras"][0]["text"] == "どっちかだ。"
    assert tb.close_paragraph("あります", cut_end=True) == "あります"


def test_cut_turn_continuation_gets_fragment_gap_tolerance():
    a = {**mt(0, "S0", "それはどっちかだ", 0.0, 1.0), "cut_end": True}
    b = mt(1, "S0", "と思います。", 3.0, 4.0)       # 2.0秒後 → 通常上限(2.0)と同値、断片なので3.0まで許容
    c = mt(2, "S0", "と思います。", 3.5, 4.0)       # 2.5秒後
    assert len(tb.magazine_blocks([a, b])) == 1 and len(tb.magazine_blocks([a, c])) == 1
    d = mt(3, "S0", "と思います。", 9.0, 10.0)      # 8秒後 → 分ける
    assert len(tb.magazine_blocks([a, d])) == 2


# ============================================================ 初期プロンプト（R1: 標準はなし／中立・辞書は明示指定のみ）
def _dictionary_terms():
    import dictionary as dm
    return dm.all_terms(dm.load_dictionary(Path(__file__).resolve().parent.parent / "config" / "dictionary.yaml"))


def test_neutral_prompt_contains_no_dictionary_or_content_words():
    p = wx_runner.NEUTRAL_ASR_PROMPT
    assert p and len(p) <= 40                                    # 短い
    for term in _dictionary_terms():                             # 辞書語（人名・地名・団体名・企画名）を含まない
        assert term not in p
    import re
    assert not re.search(r"[ァ-ヴ]{2,}|[A-Za-z0-9０-９]", p)       # カタカナ語・英数字（固有名詞になりやすい）を含まない
    assert "ください" not in p and "してください" not in p        # 指示文にしない（実測で欠落・幻覚が増えたため）
    assert "。" in p and "、" in p                                # 句読点つきの自然な文の見本


def test_resolve_asr_prompt_has_no_ambiguity():
    r = wx_runner.resolve_asr_prompt
    assert r(None, False) == (None, "none")                                    # 標準
    assert r(None, True) == (wx_runner.NEUTRAL_ASR_PROMPT, "neutral")          # --neutral-prompt
    assert r("辞書の文", False) == ("辞書の文", "dictionary")                   # --dictionary-prompt
    with pytest.raises(ValueError):                                            # 両方は曖昧にせずエラー
        r("辞書の文", True)


def test_neutral_prompt_only_with_explicit_option(tmp_path, monkeypatch):
    rc, out, seen = _run_with_fake_whisperx(tmp_path, monkeypatch, [("SPEAKER_00", "由利本荘市で始めました。")],
                                            extra=["--neutral-prompt"])
    assert rc == 0 and seen["prompt"] == wx_runner.NEUTRAL_ASR_PROMPT
    for term in ("由利本荘市", "アキタウミヨコ"):  # 辞書があっても、辞書語は中立プロンプトに混ざらない
        assert term not in seen["prompt"]


def test_dictionary_and_neutral_prompt_together_is_an_error(tmp_path, monkeypatch, capsys):
    with pytest.raises(SystemExit) as e:
        _run_with_fake_whisperx(tmp_path, monkeypatch, [("SPEAKER_00", "始めました。")],
                                extra=["--dictionary-prompt", "--neutral-prompt"])
    assert e.value.code == 2 and "not allowed with" in capsys.readouterr().err


def test_default_run_completes_without_hf_token_or_api_keys(tmp_path, monkeypatch):
    """HF_TOKEN なし（話者分離は本物の run_diarization が失敗）でも、APIキーなしでも、最後まで完走する。"""
    rc, out, seen = _run_with_fake_whisperx(tmp_path, monkeypatch, [("SPEAKER_00", "始めました。")],
                                            hf_token=None, fake_diar=False)
    assert rc == 0 and seen["prompt"] is None
    for f in ["01_raw_transcript.md", "02_clean_transcript.md", "03_magazine_interview.md",
              "transcript.json", "review_required.md"]:
        assert (out / f).exists(), f
    assert "話者不明" in (out / "03_magazine_interview.md").read_text()
    assert "話者分離に失敗" in (out / "review_required.md").read_text()


def test_changing_prompt_mode_invalidates_asr_cache(tmp_path, monkeypatch):
    """プロンプト設定を変えたら、キャッシュ済みのASR結果を再利用せず再実行する。"""
    lines = [("SPEAKER_00", "始めました。")]
    rc, out, seen = _run_with_fake_whisperx(tmp_path, monkeypatch, lines)
    assert seen["calls"] == 1 and seen["prompt"] is None
    # 同じキャッシュで設定だけ変更（_run_with_fake_whisperx は同じ tmp_path を使う）
    rc, out, seen2 = _run_with_fake_whisperx(tmp_path, monkeypatch, lines, extra=["--neutral-prompt"])
    assert seen2["calls"] == 1 and seen2["prompt"] == wx_runner.NEUTRAL_ASR_PROMPT   # 再実行された


# ============================================================ PHASE 2（統合）: 幻覚・脱落の検出
SPLIT_PHRASE_LINES = [("SPEAKER_00", "最初の話題について説明します。"), ("SPEAKER_01", "なるほど、そうなんですね。"),
                      ("SPEAKER_00", "作んないと。ご視聴ありがとうござ"), ("SPEAKER_01", "いました。")]


def test_high_hallucination_is_rejected_from_clean_and_magazine_but_kept_in_raw_and_json(tmp_path, monkeypatch):
    rc, out, _ = _run_with_fake_whisperx(tmp_path, monkeypatch, SPLIT_PHRASE_LINES)
    raw, clean, mag = [(out / f).read_text() for f in ("01_raw_transcript.md", "02_clean_transcript.md", "03_magazine_interview.md")]
    # 逐語録は原文のまま。語（形態素）単位の話者割当により、語の途中（ござ|いました）だった境界は語の切れ目（ござい|ました）に動く
    assert "ご視聴ありがとうござい" in raw and "ました。" in raw
    assert "ご視聴" not in clean and "ご視聴" not in mag                 # 02/03 からは HIGH だけ除く
    assert "作んないと。" in mag                                         # 同じ発言の実在部分は残す
    data = json.loads((out / "transcript.json").read_text())
    assert any("ご視聴ありがとうござい" in d["raw_text"] for d in data)   # JSONのraw_textも原文
    assert any(d["reject_ops"] for d in data) and any(d["drop_reason"] == "hallucination" for d in data)
    review = (out / "review_required.md").read_text()
    assert "[HIGH] 既知の幻覚定型句" in review and "自動不採用" in review and "複数の発言に分かれています" in review


def test_keep_hallucinations_option_leaves_high_candidates_in_place(tmp_path, monkeypatch):
    rc, out, _ = _run_with_fake_whisperx(tmp_path, monkeypatch, SPLIT_PHRASE_LINES, extra=["--keep-hallucinations"])
    assert "ご視聴" in (out / "03_magazine_interview.md").read_text()
    assert "--keep-hallucinations のため除外していません" in (out / "review_required.md").read_text()


def test_untranscribed_section_lists_diarized_speech_without_text(tmp_path, monkeypatch):
    extra = [{"start": 30.0, "end": 36.0, "speaker": "SPEAKER_00"}]
    lines = [("SPEAKER_00", "最初の話題について説明します。"), ("SPEAKER_01", "なるほど、そうなんですね。")]
    rc, out, _ = _run_with_fake_whisperx(tmp_path, monkeypatch, lines, extra_diar=extra)
    review = (out / "review_required.md").read_text()
    assert "## ASR未転写候補" in review and "発話区間: 6.0秒" in review and "ASRテキスト: なし" in review
    assert "SPEAKER_00" in review and "00:00:30〜00:00:36" in review


def test_min_untranscribed_sec_is_configurable(tmp_path, monkeypatch):
    extra = [{"start": 30.0, "end": 31.0, "speaker": "SPEAKER_00"}]   # 1.0秒の未転写
    lines = [("SPEAKER_00", "最初の話題について説明します。"), ("SPEAKER_01", "なるほど、そうなんですね。")]
    rc, out, _ = _run_with_fake_whisperx(tmp_path, monkeypatch, lines, extra_diar=extra)           # 既定1.5秒 → 出ない
    assert "00:00:30" not in (out / "review_required.md").read_text()
    (tmp_path / "b").mkdir()
    rc, out2, _ = _run_with_fake_whisperx(tmp_path / "b", monkeypatch, lines, extra_diar=extra, extra=["--min-untranscribed-sec", "0.5"])
    assert "00:00:30" in (out2 / "review_required.md").read_text()


def test_normal_dialogue_run_has_no_hallucination_findings(tmp_path, monkeypatch):
    lines = [("SPEAKER_00", "最初はそんなに大きなことをやろうとは思ってなかったんですよね。"), ("SPEAKER_01", "そうだったんですか？"),
             ("SPEAKER_00", "はい。地域で活動しているうちに続けられると思いました。")]
    rc, out, _ = _run_with_fake_whisperx(tmp_path, monkeypatch, lines)
    review = (out / "review_required.md").read_text()
    assert "[HIGH]" not in review and "[MEDIUM]" not in review
    assert all(not d["reject_ops"] for d in json.loads((out / "transcript.json").read_text()))

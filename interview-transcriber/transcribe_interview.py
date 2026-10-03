#!/usr/bin/env python3
"""対談音声 → 逐語録 / 軽い整文 / 雑誌対談原稿 / JSON / 要確認リスト。

WhisperX（文字起こし・alignment・話者分離）を依存ライブラリとして呼び、
その出力をこのプロジェクト側で整形する。各段階の結果は cache/ に個別保存され、
途中で失敗しても再開できる。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import dictionary as dictmod  # noqa: E402
import diarization  # noqa: E402
import editor as editormod  # noqa: E402
import quality_check as qc  # noqa: E402
import transcript_builder as tb  # noqa: E402
import whisperx_runner as wx  # noqa: E402
from whisperx_runner import log  # noqa: E402


def load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(BASE / ".env")
    load_dotenv(Path.cwd() / ".env")


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="対談音声から雑誌向け対談原稿を生成します。")
    p.add_argument("audio", type=Path, help="音声/動画ファイル（mp3 wav m4a mp4 ほか）")
    p.add_argument("--language", default="ja")
    p.add_argument("--model", default="large-v3", help="WhisperXのモデル名（CPUなら small/medium 推奨）")
    p.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    p.add_argument("--compute-type", default="auto", help="auto / float16 / int8 など")
    p.add_argument("--batch-size", type=int, default=8)
    p.add_argument("--speakers", type=Path, default=BASE / "config" / "speakers.yaml")
    p.add_argument("--dictionary", type=Path, default=BASE / "config" / "dictionary.yaml")
    p.add_argument("--output-dir", type=Path, default=BASE / "output")
    p.add_argument("--cache-dir", type=Path, default=BASE / "cache")
    p.add_argument("--temp-dir", type=Path, default=BASE / "temp")
    p.add_argument("--timestamps", action="store_true", help="clean/雑誌版にもタイムコードを表示")
    p.add_argument("--raw-only", action="store_true", help="逐語録とJSONのみ生成")
    p.add_argument("--skip-edit", action="store_true", help="LLM編集（雑誌版）を行わない。raw/cleanのみ")
    p.add_argument("--skip-transcription", action="store_true",
                   help="キャッシュ済みの認識・話者分離結果を再利用し、記事編集だけやり直す")
    p.add_argument("--force", action="store_true", help="キャッシュを無視して最初から実行")
    p.add_argument("--num-speakers", type=int)
    p.add_argument("--min-speakers", type=int)
    p.add_argument("--max-speakers", type=int)
    p.add_argument("--no-diarize", action="store_true", help="話者分離を行わない")
    p.add_argument("--no-normalize", action="store_true", help="音量正規化をしない")
    p.add_argument("--dictionary-prompt", action="store_true",
                   help="辞書をWhisperの初期プロンプトに渡す（既定OFF。実測で認識を悪化させた例があるため明示時のみ。"
                        "指定すると中立プロンプトの代わりにこれだけを渡す）")
    p.add_argument("--no-neutral-prompt", action="store_true",
                   help="中立ASRプロンプト（句読点つきの自然な文の見本。内容・固有名詞に依存しない）を渡さない")
    p.add_argument("--merge-gap", type=float, default=tb.DEFAULT_MERGE_GAP,
                   help="雑誌版で同一話者の発言を結合する最大の時間差（秒、既定 %(default)s）")
    p.add_argument("--fragment-gap", type=float, default=tb.DEFAULT_FRAGMENT_GAP,
                   help="直前が明らかな断片のとき許す最大の時間差（秒、既定 %(default)s）")
    p.add_argument("--editor", default=None, choices=["rule", "local", "claude", "openai"],
                   help="整文方式。標準は rule（外部LLMなし・無料）。local=Ollama等のOpenAI互換API、claude/openai=有料API（明示時のみ）")
    p.add_argument("--diarization-model", default=os.environ.get("DIARIZATION_MODEL"),
                   help=f"既定: {diarization.DEFAULT_DIARIZATION_MODEL}")
    p.add_argument("--editor-model")
    p.add_argument("--chunk-chars", type=int, default=2500, help="LLMに渡す1chunkの目安文字数")
    p.add_argument("--mark-unclear-logprob", type=float, default=None,
                   help="[実験的] 認識の平均対数確率がこの値未満の発言を[聞き取り不明]に置換（例: -1.0）")
    return p.parse_args(argv)


def main(argv=None) -> int:
    load_env()
    a = parse_args(argv)
    notes: list[str] = []
    out_dir: Path = a.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = a.audio.stem
    cdir = a.cache_dir / stem
    cdir.mkdir(parents=True, exist_ok=True)

    # ---------------- STEP1 音声確認
    if a.skip_transcription and not a.audio.exists():
        fp, duration = None, None
        log(f"[音声] {a.audio} が無いためキャッシュのみで再編集します")
    else:
        wx.check_ffmpeg()
        duration = wx.validate_audio(a.audio)
        fp = wx.fingerprint(a.audio)
        log(f"[音声] {a.audio.name}  {duration / 60:.1f}分")

    terms_by_cat = dictmod.load_dictionary(a.dictionary)
    terms = dictmod.all_terms(terms_by_cat)
    # 初期プロンプトの優先順位: 辞書（--dictionary-prompt 明示時のみ）> 中立（既定）> なし（--no-neutral-prompt）。
    # 辞書の語は中立プロンプトには決して混ぜない。辞書は修正候補・品質チェックにも使われる。
    dict_prompt = dictmod.build_initial_prompt(terms) if a.dictionary_prompt else None
    prompt, prompt_kind = wx.resolve_asr_prompt(dict_prompt, use_neutral=not a.no_neutral_prompt)
    log(f"[ASR] 初期プロンプト: {prompt_kind}")
    if prompt_kind == "dictionary":
        log("[ASR] 注意: 辞書プロンプトは、辞書の語が出ない音声では認識が悪化する場合があります")
    cfg = wx.ASRConfig(model=a.model, language=a.language, device=a.device, compute_type=a.compute_type,
                       batch_size=a.batch_size, initial_prompt=prompt, normalize=not a.no_normalize)
    device = wx.resolve_device(a.device)
    sig = {"fingerprint": fp, "model": a.model, "language": a.language, "prompt": prompt}

    f_whisper, f_align = cdir / "whisper_result.json", cdir / "aligned_result.json"
    f_diar = cdir / "diarization_result.json"

    # ---------------- STEP2-4 前処理・文字起こし・alignment
    wav = None
    whisper = wx.cache_load(f_whisper)
    if a.skip_transcription:
        if not whisper:
            raise SystemExit(f"--skip-transcription: キャッシュがありません ({f_whisper})。先に通常実行してください。")
        if fp and whisper.get("_sig", {}).get("fingerprint") not in (None, fp):
            notes.append("キャッシュは別の音声ファイルから作られた可能性があります（指紋不一致）。")
    else:
        if whisper and whisper.get("_sig") == sig and not a.force:
            log("[ASR] キャッシュを使用")
        else:
            log("[前処理] ffmpeg: 16kHz/モノラル" + ("/音量正規化" if cfg.normalize else ""))
            wav = wx.preprocess(a.audio, a.temp_dir, cfg.normalize)
            whisper = wx.transcribe(wav, cfg)
            whisper["_sig"] = sig
            wx.cache_save(f_whisper, whisper)
            f_align.unlink(missing_ok=True)
            f_diar.unlink(missing_ok=True)
    aligned = wx.cache_load(f_align)
    if not aligned:
        try:
            wav = wav or wx.preprocess(a.audio, a.temp_dir, cfg.normalize)
            log("[alignment] 実行中")
            aligned = wx.align(wav, whisper, cfg)
            wx.cache_save(f_align, aligned)
        except Exception as e:  # noqa: BLE001
            notes.append(f"alignment に失敗したため単語タイムスタンプなしで続行しました: {type(e).__name__}: {e}")
            log(f"[警告] {notes[-1]}")
            aligned = wx.mark_unaligned(whisper)
    else:
        log("[alignment] キャッシュを使用")

    # ---------------- STEP5 話者分離
    diar = wx.cache_load(f_diar)
    dmodel = a.diarization_model or diarization.DEFAULT_DIARIZATION_MODEL
    dkey = {"num": a.num_speakers, "min": a.min_speakers, "max": a.max_speakers, "model": dmodel}
    if diar and not a.skip_transcription and diar.get("key") != dkey:
        diar = None
    if diar:
        log("[話者分離] キャッシュを使用")
        diar_segments = diar["segments"]
    elif a.no_diarize or a.skip_transcription:
        diar_segments = None
        if a.no_diarize:
            notes.append("--no-diarize のため話者分離を行っていません。")
        else:
            notes.append("話者分離のキャッシュがありません。話者は不明のままです。")
    else:
        try:
            wav = wav or wx.preprocess(a.audio, a.temp_dir, cfg.normalize)
            log(f"[話者分離] 実行中 ({dmodel})")
            diar_segments = diarization.run_diarization(
                wav, device, os.environ.get("HF_TOKEN"), a.num_speakers, a.min_speakers, a.max_speakers, dmodel)
            wx.cache_save(f_diar, {"key": dkey, "segments": diar_segments})
        except Exception as e:  # noqa: BLE001 - 話者分離が失敗しても文字起こしは残す
            diar_segments = None
            notes.append(f"話者分離に失敗しました（{type(e).__name__}: {str(e)[:200]}）。話者は「{diarization.UNKNOWN_SPEAKER}」として出力しています。"
                         "HF_TOKEN とモデル利用条件への同意を確認し、再実行してください（README参照）。")
            log(f"[警告] {notes[-1]}")
            if os.environ.get("DEBUG"):
                traceback.print_exc()

    # ---------------- STEP6-8 統合・逐語録・話者名
    turns = tb.build_turns(aligned, diar_segments, whisper.get("segments"),
                           mark_unclear_logprob=a.mark_unclear_logprob)
    if not turns:
        notes.append("認識結果が空でした（無音、または言語指定の誤りの可能性）。")
    mapping = diarization.load_speakers(a.speakers)
    labels = tb.apply_speaker_names(turns, mapping)
    title = stem
    if diar_segments:
        shown = set()
        log("[話者] speakers.yaml の対応確認用に、各話者の最初の発言:")
        for t in turns:
            if t["speaker_id"] and t["speaker_id"] not in shown:
                shown.add(t["speaker_id"])
                log(f"   {t['speaker_id']} → {labels[t['speaker_id']]}: {t['raw_text'][:40]}")
        unmapped_cfg = [k for k in mapping if k not in labels]
        if unmapped_cfg:
            notes.append(f"speakers.yaml の {unmapped_cfg} に該当する話者は音声中で検出されませんでした。")
        if mapping:
            notes.append("話者名は speakers.yaml の SPEAKER_xx との対応に基づきます。SPEAKER番号は実行ごとに"
                         "入れ替わり得るため、各話者の最初の発言（上記ログ）と照合して確認してください。")

    (out_dir / "01_raw_transcript.md").write_text(tb.render_raw(turns, title, labels), encoding="utf-8")
    tb.write_json(out_dir / "transcript.json", turns)
    log(f"[出力] 01_raw_transcript.md / transcript.json（{len(turns)}発言）")

    terms_for_check = terms
    issues = qc.check_raw(turns)
    cands = dictmod.find_candidates(turns, terms) if terms else []

    def finish() -> int:
        qc.write_review(out_dir / "review_required.md", issues, notes, cands)
        high = sum(1 for i in issues if i.severity == qc.HIGH)
        log(f"[品質チェック] 重要 {high} / 要確認 {sum(1 for i in issues if i.severity == qc.MEDIUM)} / "
            f"参考 {sum(1 for i in issues if i.severity == qc.LOW)} → review_required.md")
        return 0

    if a.raw_only:
        return finish()

    # ---------------- STEP9 整文
    tb.apply_clean(turns)
    for t in turns:
        t["edited_text"], t["edited_dropped"], t["edit_source"] = None, None, None
    tb.write_json(out_dir / "transcript.json", turns)
    (out_dir / "02_clean_transcript.md").write_text(tb.render_clean(turns, title, a.timestamps), encoding="utf-8")
    log("[出力] 02_clean_transcript.md")
    if a.skip_edit:
        return finish()

    try:
        ed = editormod.get_editor(a.editor, a.editor_model)
    except editormod.EditorError as e:
        notes.append(f"指定されたLLMエディタを初期化できませんでした（{e}）。ルール整文で雑誌版を作成しました。")
        log(f"[警告] {notes[-1]}")
        ed = editormod.RuleEditor()
    result = editormod.run_edit(turns, ed, cdir / "edit_cache.json", target_chars=a.chunk_chars)
    notes += result.notes

    names = [t["speaker_name"] for t in turns]
    rejected_issues: list[qc.Issue] = []
    for i, t in enumerate(turns):
        text, src = result.texts[t["id"]], result.sources[t["id"]]
        if src == "llm":
            lo, hi = max(0, i - 3), min(len(turns), i + 4)
            found = qc.check_turn(t, text, names, terms_for_check, turns[lo:hi])
            highs = [x for x in found if x.severity == qc.HIGH]
            if highs:  # 発言の正確性を優先: 重大な逸脱は不採用にして clean 版へ差し戻す
                t["llm_rejected_text"] = text
                text, src = t["clean_text"], "llm-rejected"
                for x in highs:
                    x.edited, x.extra["rejected"] = text, t["llm_rejected_text"]
                rejected_issues += highs
        t["edited_text"], t["edit_source"] = text, src
        t["edited_dropped"] = not text.strip()

    final = qc.check_all(turns, names, terms_for_check)
    issues += rejected_issues + final
    if any(t["edit_source"] == "llm-rejected" for t in turns):
        n = sum(1 for t in turns if t["edit_source"] == "llm-rejected")
        notes.append(f"{n} 発言でLLMの編集が重大な逸脱（数字・固有名詞・話者・聞き取り不明の変化など）を含んだため不採用とし、clean版の文を使っています。")

    note = ("ルールベース整文（外部LLM不使用）" if isinstance(ed, editormod.RuleEditor)
            else f"編集: {ed.name}/{ed.model}")
    note += "。同一話者の細切れ発言の結合・段落分け・句読点整理のみで、文面の書き換えはしていません。"
    if not diar_segments:
        note += "話者分離が行われていないため、話者は「話者不明」です。"
    note += "掲載前に review_required.md と音声で確認してください。"
    (out_dir / "03_magazine_interview.md").write_text(
        tb.render_magazine(turns, title, a.timestamps, note=note,
                           merge_gap=a.merge_gap, fragment_gap=a.fragment_gap), encoding="utf-8")
    tb.write_json(out_dir / "transcript.json", turns)
    log("[出力] 03_magazine_interview.md / transcript.json 更新")
    return finish()


if __name__ == "__main__":
    sys.exit(main())

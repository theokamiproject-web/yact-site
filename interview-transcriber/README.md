# interview-transcriber

日本語の対談・インタビュー音声から、**逐語録 → 軽い整文 → 雑誌対談原稿** を一括生成する CLI。
音声認識・話者分離は [WhisperX](https://github.com/m-bain/whisperX)（faster-whisper + pyannote）を**依存ライブラリとして**利用し、
話者名の置換・整文・品質チェック・出力はこのプロジェクト側で実装しています（WhisperX本体は改造していません）。

最優先は **発言の正確性** です。音声にない内容の追加・数字や固有名詞の変更・聞き取れない箇所の補完を禁じ、機械的に検査して `review_required.md` に出します。

## 処理の流れ

```
音声 → ffmpeg前処理(16kHz/mono/音量正規化) → WhisperX文字起こし → alignment(文字単位の時刻)
     → 話者分離(pyannote) → 発言(turn)化 → 01 逐語録
     → ルール整文 → 02 軽い整文版
     → LLM整文(chunk分割) → 品質チェック → 03 雑誌版 / transcript.json / review_required.md
```

各段階の結果は `cache/<音声名>/` に個別保存され、途中で止まっても再開できます。

## セットアップ

動作確認環境: **Python 3.11**、whisperx 3.8.6、torch 2.8、Linux（CPUのみ）。

```bash
cd interview-transcriber
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # whisperx が torch 等も入れます（数GB）
cp .env.example .env                     # 必要な値を記入（.env は .gitignore 済み）
```

### ffmpeg
`ffmpeg` と `ffprobe` が PATH に必要です。

```bash
sudo apt install ffmpeg      # Ubuntu / Debian
brew install ffmpeg          # macOS
winget install ffmpeg        # Windows
```

### GPU / CPU
- GPU（CUDA）があれば自動で使用（`float16`）。無ければ CPU（`int8`）に自動フォールバック。
- 既定モデルは `large-v3`。**CPUでは非常に遅い**ため `--model small` か `medium` を推奨します。
- 手動指定: `--device cuda|cpu`、`--compute-type float16|int8|...`

### Hugging Face トークン（話者分離に必須）
pyannote の話者分離モデルは**ゲート付き**です。

1. <https://huggingface.co> でアカウント作成、read 権限のトークンを発行
2. 次のモデルページで利用条件に同意: `pyannote/speaker-diarization-community-1`（および表示される依存モデル）
3. `.env` に `HF_TOKEN=hf_...` を記入

トークンが無い／同意していない場合、話者分離だけが失敗し、文字起こしは**話者「話者不明」で出力されます**（警告は `review_required.md` に記載）。

### LLM（雑誌版の整文）用 APIキー
`.env` に設定します。コードには書きません。**どれも未設定ならLLMを使わず、ルール整文のみ**で雑誌版を作ります。

| 変数 | 内容 |
|---|---|
| `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` | Claude（既定 `claude-sonnet-5-5`） |
| `OPENAI_API_KEY` / `OPENAI_MODEL` / `OPENAI_BASE_URL` | OpenAI |
| `LOCAL_LLM_BASE_URL` / `LOCAL_LLM_MODEL` | Ollama・llama.cpp 等 OpenAI互換のローカルLLM |
| `EDITOR_PROVIDER` | `auto`(既定: claude→openai→local→rule) / `claude` / `openai` / `local` / `rule` |

プロバイダの追加は `editor.py` の `BaseEditor.complete()` を実装するだけです。

## 使い方

```bash
python transcribe_interview.py interview.m4a --model small

python transcribe_interview.py interview.m4a \
  --language ja --model large-v3 \
  --speakers config/speakers.yaml --dictionary config/dictionary.yaml \
  --output-dir output --min-speakers 2 --max-speakers 3 --timestamps
```

| オプション | 説明 |
|---|---|
| `--model` / `--device` / `--compute-type` / `--batch-size` | WhisperXの設定 |
| `--speakers` / `--dictionary` | 設定ファイル（既定 `config/` 配下） |
| `--min-speakers` / `--max-speakers` / `--num-speakers` | 話者数の指定（分かっていれば精度向上） |
| `--timestamps` | clean版・雑誌版の各発言末尾に `[HH:MM:SS]` を付ける |
| `--raw-only` | 逐語録と JSON だけ |
| `--skip-edit` | LLM編集をしない（raw と clean のみ） |
| `--skip-transcription` | キャッシュ済みの認識・話者分離を再利用して**編集だけやり直す** |
| `--force` | キャッシュを無視 |
| `--no-diarize` | 話者分離しない |
| `--editor` / `--editor-model` / `--chunk-chars` | LLM編集の設定 |
| `--mark-unclear-logprob -1.0` | 【実験的】低信頼の発言を `[聞き取り不明 HH:MM:SS]` に置換（原文は JSON の `unclear` に退避） |

対応形式: mp3 / wav / m4a / mp4（ほか ffmpeg が読めるもの）。元ファイルは変更しません。一時ファイルは `temp/`。

### 再実行・再開
- 失敗後の再実行: **同じコマンドをもう一度**。完了済みの段階（文字起こし／alignment／話者分離／LLMのchunk）はキャッシュから再利用されます。
- 編集だけやり直す（speakers.yaml 変更、モデル変更、プロンプト調整後など）:
  `python transcribe_interview.py interview.m4a --skip-transcription`
  LLMのchunk結果は `cache/<名前>/edit_cache.json` に入力ごとに保存され、同じ入力なら再課金されません。
- 話者数を変えて話者分離だけやり直す: `--min-speakers/--max-speakers` を変えて実行（話者分離のキャッシュは設定が変わると無効化）。

## speakers.yaml

```yaml
SPEAKER_00: 真坂
SPEAKER_01: 寺戸
SPEAKER_02: 眞庭
```

- 書かなかった話者は `話者A` `話者B` …、判定が曖昧な発言は `話者不明` になります（人物を推測で確定しません）。
- **SPEAKER番号は音声ごと（実行ごと）に入れ替わり得ます。** 実行ログに出る「各話者の最初の発言」と見比べて対応を確認してください。
- 重なり発話などで話者が割れる発言は `speaker_uncertain: true` となり、`review_required.md` に載ります。

## dictionary.yaml

```yaml
people: [真坂雅, 寺戸隆之]
organizations: [OKAMI企画]
places: [由利本荘市]
projects: [アキタウミヨコお座敷シアター]
```
カテゴリ名は自由、値は文字列のリスト。用途は次の2つだけです。

1. 認識の手がかり（Whisperの初期プロンプトに先頭約120字ぶんを渡す。不要なら `--no-prompt-dictionary`）
2. 似ているが一致しない語（例: 「由利本庄市」）を `review_required.md` に**候補として**表示

辞書を根拠にした**自動置換はしません**。

## 出力ファイル（`--output-dir`、既定 `output/`）

| ファイル | 内容 |
|---|---|
| `01_raw_transcript.md` | 逐語録。フィラー保持、各発言にタイムコード |
| `02_clean_transcript.md` | フィラー・重複・単純な相槌のみ整理（ルールベース） |
| `03_magazine_interview.md` | 雑誌対談向け整文（LLM。無ければルール整文） |
| `transcript.json` | 発言ごとの構造化データ |
| `review_required.md` | 品質チェックの要確認一覧 |

### transcript.json
発言（turn）ごとに `speaker_id` / `speaker_name` / `start` / `end` / `raw_text` / `clean_text` / `edited_text` に加え、
`segment_ids`（WhisperXの元セグメント）、`words`（文字ごとの `[文字, start, end, score]`）、`edit_source`
（`llm` / `rule` / `rule-fallback` / `llm-rejected`）、`llm_rejected_text` などを持ちます。
編集は**発言IDごと**に行うため、雑誌版のどの文も元のタイムコードへ遡れます（空文字＝削除、`*_dropped`＝削除フラグ）。

### 出力例（合成音声で生成。話者分離は擬似区間）
```markdown
# 逐語録（sample_dialogue）
00:00:00

真坂：
えーと、今日はですね、この企画について話していきたいと思います。

00:00:06

寺戸：
はい。
```
```markdown
# 対談（sample_dialogue）
真坂：
今日はですね、この企画について話していきたいと思います。そもそもこれを始めたのは、2024年の10月ごろなんです。

寺戸：
そうだったんですか。

真坂：
はい、参加者は30人くらいでした。
```
```markdown
## 00:32:14　[重要] 年月日の追加
RAW:
> 来年の5月くらい
EDITED:
> 来年の5月くらい
LLMの提案（不採用・clean版へ差し戻し）:
> 来年5月15日
理由：
原文に存在しない年月日「15日」が追加されています。
```

## 編集と品質チェックの方針

- **LLMへの制約**: 追加・要約・発言創作・話者変更・数字/日付変更・固有名詞の推測・聞き取り不明の補完を禁止（`editor.py` の `SYSTEM_PROMPT`）。
- **長時間音声**: 全文を一度に渡さず、話者交替・間・文末を見て約2,500字ごとの chunk に分割し、直前3発言を文脈として重複させます。出力は編集対象の発言IDだけなので、重複出力は構造上起きません。
- **自動チェック**（`quality_check.py`）: 数字・年月日・金額の追加/変更、固有名詞の追加、別話者の文言混入、大量削除、`[聞き取り不明]` の補完、否定の増減・「たぶん」「〜くらい」等の強弱語の増減、内容の乖離。
- **重大な逸脱はLLM案を採用しません**（数字・固有名詞・話者・聞き取り不明の変化など）。clean版の文に差し戻し、LLM案を `review_required.md` に残します。

## 既知の制限（必ず読んでください）

- **自動チェックは機械的なヒューリスティックで、正確性の保証ではありません。** 公開前に `review_required.md` と、重要な発言は音声での確認を。
- **「聞き取り不明」の自動検出は弱いです。** WhisperXの文字スコアは正しい文字でも 0 になることがあり、信頼できません。既定では発言の平均対数確率が低い発言を「参考」として列挙するだけで、本文は置換しません（`--mark-unclear-logprob` は実験的）。Whisperは聞き取れない箇所に**もっともらしい文を出力することがあります**。固有名詞・数字は特に聞き直してください。
- 無音区間で出やすい幻覚定型句（「ご視聴ありがとうございました」等）は検出して参考に出します。
- 話者分離は完全ではありません。短い相槌（約0.6秒/4文字未満）は文中では前後の話者へ吸収されます。重なり発話は `話者不明` になります。
- 既定のルール整文は保守的です（「まあ」「なんか」などは読点を伴うときだけ除去）。雑誌水準の整文はLLMが担います。

## トラブルシューティング

| 症状 | 対処 |
|---|---|
| `ffmpeg が見つかりません` | ffmpeg を導入し PATH を確認 |
| 話者が全員「話者不明」 | `HF_TOKEN` 未設定／モデル利用条件に未同意。`review_required.md` の注意欄にエラー内容 |
| alignment で `punkt_tab not found` | `python -c "import nltk; nltk.download('punkt_tab')"`。ネットワークがプロキシ経由でNLTKに拒否される場合は、<https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/tokenizers/punkt_tab.zip> を `~/nltk_data/tokenizers/` に展開。失敗しても単語時刻なしで続行します |
| CUDA out of memory | `--batch-size 4`、`--compute-type int8`、小さいモデル |
| CPUで終わらない | `--model small`/`medium`。所要時間の目安（未実測）: CPUでは音声長の1倍前後以上 |
| LLMが失敗する | 該当chunkはルール整文で代替され、再実行で続きから。キー・モデル名・残高を確認 |
| 雑誌版が硬い／くだけすぎ | `editor.py` の `SYSTEM_PROMPT` を調整し `--skip-transcription` で再編集（`PROMPT_VERSION` を上げるとキャッシュが無効化されます） |

## テスト

```bash
python -m pytest tests -q          # 25件。WhisperX・音声不要（偽LLMサーバを使用）
python tests/make_sample_audio.py samples/sample_dialogue.m4a   # open_jtalk で合成音声を作る（任意）
```

## ファイル構成

```
transcribe_interview.py   CLI（段階制御・キャッシュ・失敗耐性）
whisperx_runner.py        ffmpeg前処理 / WhisperX文字起こし・alignment
diarization.py            話者分離 / speakers.yaml
transcript_builder.py     発言(turn)化・結合・ルール整文・Markdown/JSON出力
editor.py                 LLM整文（プロバイダ切替・chunk分割・プロンプト）
quality_check.py          raw と edited の比較 → review_required.md
dictionary.py / text_utils.py
config/  speakers.yaml dictionary.yaml     output/  cache/  temp/
```

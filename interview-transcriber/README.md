# interview-transcriber

日本語の対談・インタビュー音声から、**逐語録 → 軽い整文 → 雑誌対談原稿** を一括生成する CLI。
音声認識・話者分離は [WhisperX](https://github.com/m-bain/whisperX)（faster-whisper + pyannote）を**依存ライブラリとして**利用し、
話者名の置換・整文・品質チェック・出力はこのプロジェクト側で実装しています（WhisperX本体は改造していません）。

**標準動作は完全に無料・外部API不要**です（WhisperX + pyannote + ルールベース整文）。`python transcribe_interview.py interview.m4a` だけで最後まで完走します。
目標は「完全な雑誌完成稿の自動生成」ではなく、**誰が・何を・どの順番で話したかを正確に取り出し、人が少し直せば原稿になる状態**にすることです。
最優先は **発言の正確性** です。音声にない内容の追加・数字や固有名詞の変更・聞き取れない箇所の補完をせず、機械的に検査して `review_required.md` に出します。

## 処理の流れ

```
音声 → ffmpeg前処理(16kHz/mono/音量正規化) → WhisperX文字起こし → alignment(文字単位の時刻)
     → 話者分離(pyannote community-1) → 発言(turn)化 → 01 逐語録
     → ルール整文 → 02 軽い整文版
     → 結合・段落分け・句読点整理 → 品質チェック → 03 対談原稿 / transcript.json / review_required.md
     （外部LLMは標準では使わない。任意でローカルLLM等を差し込める）
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

### Hugging Face トークン（話者分離。無料）
話者分離は `pyannote/speaker-diarization-community-1`（`--diarization-model` / `DIARIZATION_MODEL` で変更可）。モデルは**ゲート付き**です。

1. <https://huggingface.co> でアカウント作成、read 権限のトークンを発行
2. `pyannote/speaker-diarization-community-1` のページで利用条件に同意
3. `.env` に `HF_TOKEN=hf_...` を記入

**トークンが無い／同意していなくてもエラー終了しません。** 話者分離だけが失敗し、文字起こしは「話者不明」で全ファイルが出力されます（警告は `review_required.md` に記載）。

### 整文について（APIキー不要）
- 02・03 は**ルールベース**で生成します。有料APIは必要なく、環境に `ANTHROPIC_API_KEY` などがあっても**自動では使いません**。
- 任意機能: 既にあるローカルLLM（Ollama等のOpenAI互換API）を使う場合のみ `.env` に `LOCAL_LLM_BASE_URL` を設定し `--editor local`。新たにOllamaや大きなモデルを入れる必要はありません。
- `--editor claude` / `--editor openai` も残していますが、有料APIであり、使う場合は明示指定が必要です。LLM案は品質チェックで数字・固有名詞などの逸脱が見つかると不採用になります。
- プロバイダの追加は `editor.py` の `BaseEditor.complete()` を実装するだけです。

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
| `--neutral-prompt` | 中立ASRプロンプトを渡す（**標準はOFF**）。句点がほぼ出ない音声で試す |
| `--dictionary-prompt` | 辞書をWhisperの初期プロンプトに渡す（**標準はOFF**）。`--neutral-prompt` とは同時指定不可（エラー） |
| `--merge-gap` / `--fragment-gap` | 雑誌版で同一話者の発言を結合する最大の時間差（秒。既定 2.0 / 明らかな断片の続きは 3.0） |
| `--raw-only` | 逐語録と JSON だけ |
| `--skip-edit` | 雑誌版（03）を作らない（raw と clean のみ） |
| `--skip-transcription` | キャッシュ済みの認識・話者分離を再利用して**編集だけやり直す** |
| `--force` | キャッシュを無視 |
| `--no-diarize` | 話者分離しない |
| `--editor rule\|local\|claude\|openai` | 整文方式。**標準は rule（無料・外部LLMなし）** |
| `--diarization-model` | 話者分離モデル（既定 community-1） |
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
カテゴリ名は自由、値は文字列のリスト。標準での用途は次のとおりです。

1. 似ているが一致しない語（例: 「由利本庄市」）を `review_required.md` に**候補として**表示
2. 品質チェックで「原文にない固有名詞が編集で現れていないか」の判定に使用

**辞書は Whisper の初期プロンプトには、標準では渡しません。** 実音声（3人の雑談150秒）で、辞書をプロンプトに渡すと
認識が約23%減り（414字。プロンプトなしは540字）、一部の発話が欠落したためです。人名・団体名の多い対談で
認識の手がかりとして使いたい場合のみ `--dictionary-prompt` を指定してください（先頭約120字ぶんを渡します。
`--neutral-prompt` とは同時に指定できません。連結はしません）。

### 中立ASRプロンプト（標準OFF・`--neutral-prompt` で使用）
**初期プロンプトは標準では渡しません**（`python transcribe_interview.py interview.m4a` → プロンプトなし）。

Whisper はプロンプトが無いと、音源によっては日本語の句読点をほとんど出さず、文境界が崩れて話者境界が語の途中で
切れやすくなります（実測：Track-78 で句点0・語途中の話者境界20）。そこで、**内容に依存しない句読点つきの自然な文**を
見本として渡すオプションを用意しています。

```
python transcribe_interview.py interview.m4a --neutral-prompt
```
```
はい、そうですね。ええと、それはですね、こういうことなんです。
```

- **中立プロンプトは日本語の句読点・文境界を改善することがある一方、音源によって相槌の増加や speaker 境界の悪化が確認されたため、標準ではOFFです。**
- **Track-78 のように句点がほとんど出ない場合は、`--neutral-prompt` を試してください**（句点 0→39、語途中の話者境界 20→6）。
- 実測の副作用（Track-79）：チャンク末尾に短い「はい。」が別話者の独立した発言として2件増えた（誘発の可能性）／英語せりふ区間で話者境界が悪化した（2→7）。
- 辞書語・人名・地名・団体名・話題・カタカナ語を含みません。指示文にもしません（指示文は欠落と幻覚が増えたため）。
- 初期プロンプトの扱い：**指定なし → プロンプトなし／`--dictionary-prompt` → 辞書プロンプトのみ／`--neutral-prompt` → 中立プロンプトのみ**。辞書と中立は連結せず、**両方を指定するとエラー**になります。
- 欠落量はプロンプトやチャンク境界で大きく揺れるため、**音源ごとに `--neutral-prompt` あり・なしを比較**することを勧めます。
辞書を根拠にした**自動置換はしません**。

## 出力ファイル（`--output-dir`、既定 `output/`）

| ファイル | 内容 |
|---|---|
| `01_raw_transcript.md` | 逐語録。フィラー保持、各発言にタイムコード |
| `02_clean_transcript.md` | 読みやすい逐語録。発言単位のまま、フィラー・語頭の言い直し・重複・単独の相槌のみ整理 |
| `03_magazine_interview.md` | 対談原稿の素材（細切れ発言の結合・段落分け・句読点整理。ルールベース） |
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

| | 01 逐語録 | 02 clean | 03 対談原稿 |
|---|---|---|---|
| フィラー（えー・あのー・そのー等）・語頭の言い直し・同語反復 | 残す | 除去 | 除去 |
| 単独の相槌（はい・うん・そうですね…） | 残す | 除去（※） | 除去（※） |
| 発言の単位 | turn | turn（結合しない） | 同一話者の連続発言を結合、長ければ段落分け |
| 句読点・空白・記号 | そのまま | そのまま | 整理（全角化・重複除去・段落末の句点） |
| 話者名・順序 | 保持 | 保持 | 保持（別話者が挟まれば結合しない） |

※ 質問への返答（直前が「？」）・「？」を含む発言・話者が確定していない発言は残します。

- **文面は書き換えません。** 「そんな」を「そんなに」にする等の補完・言い換え・作文はしません。削る・つなぐ・句読点を整えるだけです。
- 「まあ」「なんか」「あの」「その」は、読点を伴う文節頭のときだけ除去します（「あの人」「その後」を壊さないため）。助詞に直付けの「それはまあ、」のような用法は意味を持つ場合があるので残します。
- 段落分け: 文末で、間が1秒以上あり120字以上たまったとき、または240字を超えたとき。
- **結合の条件（03）**: 同じ話者であっても、発言間の実質的な無音が `--merge-gap`（既定2.0秒）を超えれば結合せず、話者名を再掲します（直前が助詞・接続表現や話者交替で途中切れの発言なら `--fragment-gap` の3.0秒まで）。間に話者不明の発言が挟まる場合も結合しません。
- **句点の付与（03）**: 文として確実に終わっている語尾（〜です／〜ます／〜た／〜ね 等）にだけ付けます。話者交替などで文の途中で切れた発言、助詞・接続表現で終わる発言、判定が不確かなものには付けず、元の文字列を維持します。
- **自動チェック**（`quality_check.py`）: 数字・年月日・金額の追加/変更、固有名詞の追加、別話者の文言混入、大量削除、`[聞き取り不明]` の補完、否定の増減・「たぶん」「〜くらい」等の強弱語の増減、内容の乖離、認識の幻覚疑い、話者判定の不確実。
- LLMを任意で使った場合、重大な逸脱（数字・固有名詞・話者・聞き取り不明の変化など）は不採用にして整文済みの文に差し戻し、LLM案を `review_required.md` に残します。長時間音声は話者交替・間・文末を見て約2,500字ごとに分割し、直前3発言を文脈として重複させます。

## 既知の制限（必ず読んでください）

- **ASRの欠落量はプロンプトやチャンク境界で大きく揺れます**（実音声で、似た趣旨の短いプロンプト間でも未転写率が17.8〜33.8%と変動）。初期プロンプトは標準では渡しません。`--neutral-prompt` は句点がほぼ出ない音声向けのオプションで、音源によっては相槌の増加や話者境界の悪化があります。`output/quality_report.md` の検証を参照。

- **自動チェックは機械的なヒューリスティックで、正確性の保証ではありません。** 公開前に `review_required.md` と、重要な発言は音声での確認を。
- **「聞き取り不明」の自動検出は弱いです。** WhisperXの文字スコアは正しい文字でも 0 になることがあり、信頼できません。既定では発言の平均対数確率が低い発言を「参考」として列挙するだけで、本文は置換しません（`--mark-unclear-logprob` は実験的）。Whisperは聞き取れない箇所に**もっともらしい文を出力することがあります**。固有名詞・数字は特に聞き直してください。
- 無音区間で出やすい幻覚定型句（「ご視聴ありがとうございました」等）は検出して参考に出します。
- 話者分離は完全ではありません。短い相槌（約0.6秒/4文字未満）は文中では前後の話者へ吸収されます。重なり発話は `話者不明` になります。
- ルール整文は保守的です。雑誌の完成稿にはなりません（語尾の統一・言い換え・要約はしません）。人が校正する前提の素材です。

## トラブルシューティング

| 症状 | 対処 |
|---|---|
| `ffmpeg が見つかりません` | ffmpeg を導入し PATH を確認 |
| 話者が全員「話者不明」 | `HF_TOKEN` 未設定／モデル利用条件に未同意。`review_required.md` の注意欄にエラー内容 |
| alignment で `punkt_tab not found` | `python -c "import nltk; nltk.download('punkt_tab')"`。ネットワークがプロキシ経由でNLTKに拒否される場合は、<https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/tokenizers/punkt_tab.zip> を `~/nltk_data/tokenizers/` に展開。失敗しても単語時刻なしで続行します |
| CUDA out of memory | `--batch-size 4`、`--compute-type int8`、小さいモデル |
| CPUで終わらない | `--model small`/`medium`。所要時間の目安（未実測）: CPUでは音声長の1倍前後以上 |
| 任意のLLM(`--editor local`等)が失敗する | 該当chunkはルール整文で代替され、再実行で続きから。URL・モデル名を確認 |
| 整文を変えたい | `text_utils.py` のフィラー規則等を調整し `--skip-transcription` で再編集（認識・話者分離はキャッシュ再利用） |

## テスト

```bash
python -m pytest tests -q          # 70件。WhisperX・音声不要（偽LLMサーバを使用）
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

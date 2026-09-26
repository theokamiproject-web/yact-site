# ポッドキャスト自動編集ツール（podcast-tool）

収録した音声を `input/` に入れて 1 行のコマンドを実行すると、次の処理をして `output/` に配信用の完成音源を作ります。

- ノイズ低減・ローカット・音量の均し
- OP・アイキャッチ・ED の BGM 挿入（声と重なる部分では BGM を自動で下げる）
- 冒頭と末尾の無音を除去
- ラウドネスの調整（初期値 −16 LUFS / True Peak −1 dBTP）

```
podcast episode.wav
```

| 出力ファイル | 用途 |
|---|---|
| `output/episode_master.wav` | 編集用マスター（48kHz / 24bit） |
| `output/episode_publish.mp3` | 配信用（128kbps） |
| `output/episode_report.json` / `.txt` | 処理前後の測定値・挿入位置・警告 |
| `output/episode_process.log` | 実行した FFmpeg コマンドの記録（失敗時の原因調査用） |

元の音源は読むだけで、上書きしません。同じ素材と設定で実行すれば、同じ完成ファイルが作られます。

---

## 1. 準備（最初の 1 回だけ）

### 1-1. FFmpeg を入れる

| OS | 手順 |
|---|---|
| macOS | [Homebrew](https://brew.sh/ja/) を入れて、ターミナルで `brew install ffmpeg` を実行 |
| Windows | PowerShell で `winget install Gyan.FFmpeg` を実行し、PowerShell を開き直す |

`ffmpeg -version` を実行して、バージョンが表示されれば完了です（5.0 以上が必要）。

### 1-2. Python を入れる

Python 3.9 以上が必要です。

- macOS: `brew install python`
- Windows: [python.org](https://www.python.org/downloads/) からインストール（インストール画面で「Add python.exe to PATH」にチェックを入れる）

### 1-3. このツールを入れる

ターミナル（Windows は PowerShell）で `podcast-tool` フォルダに移動して、次を実行します。

```
pip install -e .
```

これで `podcast` コマンドが使えるようになります。
`podcast` コマンドが見つからないと表示された場合は、代わりに `python podcast.py`（macOS は `python3 podcast.py`）を使ってください。動作は同じです。

---

## 2. 使い方

1. `assets/` に BGM を置きます。ファイル名は次の 3 つです。
   - `opening.mp3`（OP）
   - `jingle.mp3`（アイキャッチ）
   - `ending.mp3`（ED）
2. `input/` に収録音声を置きます（WAV / MP3 / M4A / FLAC など）。
3. `podcast-tool` フォルダで実行します。

```
podcast episode.wav
```

- ファイル名にスペースがある場合は `"..."` で囲みます（例 `podcast "第3回 収録.wav"`）。日本語のファイル名も使えます。
- `input/` の音声をまとめて処理する場合は `podcast --all` です。
- 解析だけする（音声を書き出さない）場合は `podcast --analyze episode.wav` です。
- 中間ファイルを残して調べたい場合は `podcast --keep-work episode.wav` です。

### 素材なしで試す

```
python tools/make_test_assets.py
podcast "第1回 テスト 収録.wav"
```

合成した声（英語 2 名・音量差 9dB・ノイズ入り）と合成 BGM で、一連の処理を試せます。

---

## 3. 設定の変え方（`config/podcast.yaml`）

数値はすべてこのファイルに書かれています。変更して再実行すれば作り直せます。よく変える項目は次のとおりです。

| やりたいこと | 項目 | 初期値 |
|---|---|---|
| 完成音源の音量を変える | `loudness.target_lufs` | −16（Apple 推奨値。Spotify 基準は −14） |
| ピークの上限を変える | `loudness.true_peak_max_dbtp` | −1.0 |
| MP3 の音質・容量を変える | `output.publish.bitrate` | `128k` |
| MP3 をモノラルにする（容量半分） | `output.publish.channels` | 2 |
| OP の BGM 単体の長さ | `opening.solo_sec` | 8 秒 |
| 声の下で流れる BGM の音量 | `opening.bed_gain_db` / `ending.bed_gain_db` | −12 dB |
| アイキャッチの位置 | `jingle.positions` | 本編の 50% 地点 |
| ED を本編終了の何秒前から始めるか | `ending.lead_in_sec` | 12 秒 |
| 本編終了後に ED を流す長さ | `ending.tail_sec` | 10 秒 |
| ノイズ低減の強さ | `cleanup.denoise.reduction_db` | 10（6〜12 推奨） |
| BGM を下げる強さ（ダッキング） | `bgm.ducking.threshold_db` / `ratio` | −26 / 3 |
| OP・アイキャッチ・ED を使わない | `opening.enabled` など | `true` |

### アイキャッチを複数入れる

```yaml
jingle:
  positions:
    - minutes: 10      # 本編開始から 10 分後
    - minutes: 20
    - percent: 75      # 本編全体の 75% 地点
```

アイキャッチは、指定した地点の前後 `search_window_sec`（初期値 30 秒）の範囲で、`min_silence_sec`（0.5 秒）以上の無音に挿入します。会話の途中では切りません。
条件に合う無音がなければ挿入せず、レポートに警告を残します。

### OP・ED の音量の流れ

```
OP:  BGM単体（solo_sec）→ 声の直前に下げる（duck_transition_sec）→ 声の下で流す（bed_sec）→ フェードアウト
ED:  本編終了の lead_in_sec 秒前からフェードイン → 声の下で流す → 本編終了後に戻す（rise_sec）→ tail_sec 流す → フェードアウト
```

声と重なる部分では、上記に加えてダッキングで BGM がさらに下がります。声が止まると、`release_ms` の時間をかけて元の音量に戻ります。

---

## 4. 処理の中身（何をしているか）

| 工程 | 内容 | FFmpeg フィルタ |
|---|---|---|
| 解析 | 長さ・サンプルレート・ch 数・ラウドネス・True Peak・LRA・無音区間・ノイズフロア・クリップの疑い | ffprobe, ebur128, silencedetect, astats |
| クリーニング | ローカット（80Hz）、ノイズ低減（実測ノイズフロアを使用、10dB）、区間ごとの音量差の均し、2:1 の軽いコンプ | highpass, afftdn, dynaudnorm, acompressor |
| 無音処理 | 冒頭と末尾の無音を除去（0.3 秒 / 0.6 秒の余白を残す）。本編中の長い無音は削除せず候補として報告 | silencedetect |
| ミックス | 声と BGM をそれぞれ基準の音量に揃えてから配置し、声をトリガーに BGM を下げる | volume, adelay, sidechaincompress, amix |
| マスタリング | ゲイン調整と、4 倍オーバーサンプリングのピークリミッタ。WAV と MP3 を別々に実測し、目標に入るまで補正 | alimiter, aresample, ebur128 |
| 品質チェック | 完成ファイルを再解析して、ラウドネス・True Peak・クリップ・長さ・長すぎる無音を確認 | ebur128, astats, silencedetect |

MP3 は WAV を変換せず、ミックスから直接作ります。検証では、128kbps の MP3 に変換すると音量が約 0.4 LU 下がりました。そのため MP3 も個別に目標値へ合わせています。

---

## 5. 困ったとき

| 表示 | 対処 |
|---|---|
| `ffmpeg が見つかりません` | 1-1 を行い、ターミナルを開き直します。それでも出る場合は `config/podcast.yaml` の `ffmpeg.path` に ffmpeg のフルパスを書きます |
| `BGM ファイルが見つかりません` | `assets/` に表示された名前でファイルを置きます。使わない BGM は `opening.enabled: false` などにします |
| `設定項目 '...' がありません` | 同梱の `config/podcast.yaml` と見比べて、項目を足します |
| `FFmpeg の処理に失敗しました` | 表示されたログファイル（`output/*_process.log`）に、失敗したコマンドと FFmpeg のメッセージが記録されています |
| アイキャッチが入らない | レポートの警告を確認し、`search_window_sec` を広げるか、`min_silence_sec` を短くします |
| 声が金属的・水中のような音になる | `cleanup.denoise.reduction_db` を 6〜8 に下げます |
| BGM が大きい・小さい | `bed_gain_db`（声の下）、`solo_gain_db`（BGM 単体）、`bgm.ducking.threshold_db`（下げる強さ）で調整します |

品質チェックで「注意」と出る「長すぎる無音」は、確認を促すためのものです。本編中の「間」は作品の一部なので、自動では削除しません。

---

## 6. 制約（初期版）

- 話者ごとの個別処理（話者分離）はしません。全体の音量差を穏やかに均すだけです。
- ノイズが非常に大きい録音（声とノイズの差が 15dB 程度以下）では、冒頭・末尾の無音を検出できないことがあります。その場合はトリムせず、警告を出します。
- 録音時の音割れ（クリップ）は後処理では直せません。入力にクリップの疑いがあると警告を出します。
- 処理時間は、検証環境で本編 30 分あたり約 5 分でした（PC の性能によって変わります）。
- 自動処理の結果が良いかどうかは、必ず試聴して判断してください。レポートの数値は測定値であり、音質の良し悪しを示すものではありません。

## 7. テスト

```
pip install pytest
python -m pytest tests
```

`tests/test_timeline.py` は配置計算のテストで、FFmpeg は不要です。
`tests/test_e2e.py` は合成素材で実際に処理を通すテストです。日本語とスペースを含むパス、元音源が変わらないこと、再実行で完全に同じファイルになること、素材がないときのエラー表示を確認します。

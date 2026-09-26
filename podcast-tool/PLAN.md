# 実装計画・設計

## 1. 方針

| 項目 | 決定 | 理由 |
|---|---|---|
| 音声処理 | FFmpeg のフィルタのみ（afftdn / highpass / dynaudnorm / acompressor / sidechaincompress / alimiter / loudnorm / silencedetect） | Win/Mac 共通・再現性・追加ライブラリ不要 |
| 制御 | Python 3.9+（標準ライブラリ + PyYAML のみ） | タイムライン計算・レポート・エラー処理を書きやすい |
| 設定 | `config/podcast.yaml` に全パラメータ | コードに数値を書かない |
| FFmpeg 呼び出し | `subprocess` に引数リストで渡す（シェルを通さない） | 日本語・スペース入りパス対応 |
| 元音源 | 読み取りのみ。出力先が入力と同一なら停止 | 上書き防止 |

## 2. 処理フロー

```
[1] 事前チェック   FFmpeg・必須フィルタ・BGMファイル・設定値
[2] 入力解析       ffprobe(長さ/SR/ch) + loudnorm(I/TP/LRA) + 100ms毎RMS分布(ノイズフロア推定)
                   + silencedetect + astats(クリップ疑い)
[3] 声のクリーニング  mono化 → highpass → afftdn(ノイズフロア実測値を使用) → dynaudnorm(穏やか) → acompressor(2:1)
[4] クリーン後解析   silencedetect → 冒頭/末尾の無音トリム位置・アイキャッチ挿入点・長すぎる無音候補
[5] タイムライン計算  OP / 声セグメント / アイキャッチ / ED の配置秒とBGM音量エンベロープ（Python側で計算）
[6] ミックス        声を目標ラウドネスへ、BGMを基準ラウドネスへ揃えてから dB オフセット適用
                   BGMバス = OP+ED → 声をサイドチェインにしたダッキング → 声・ジングルと合成
[7] マスタリング     ゲイン + 4倍オーバーサンプリングのリミッタ（True Peak 対策）
                   → 測定 → ずれがあれば最大4回補正
[8] 書き出し        WAV（編集用マスター）/ MP3（配信用）
[9] 品質チェック     完成ファイル（WAV・MP3両方）を再測定し、設定値と照合して警告
[10] レポート       JSON + TXT + 実行ログ（FFmpegコマンド全記録）
```

## 3. ファイル構成

```
podcast-tool/
  podcast.py              インストール不要の起動用
  pyproject.toml          pip install で `podcast` コマンドを作る
  config/podcast.yaml     全設定
  assets/                 opening.mp3 / jingle.mp3 / ending.mp3（各自用意）
  input/                  収録音声
  output/                 完成音源・レポート・ログ
  podcast_tool/
    cli.py                コマンドライン引数
    config.py             設定の読込・既定値・検証
    ffmpeg.py             FFmpeg 実行・ログ・エラー整形
    analyze.py            解析（ラウドネス・無音・ノイズフロア・クリップ）
    timeline.py           配置計算（FFmpeg 非依存・単体テスト可能）
    render.py             フィルタグラフ生成と実行
    qc.py                 品質チェック
    report.py             レポート出力
    pipeline.py           全体の手順
  tests/                  単体テスト + 通し試験
  tools/make_test_assets.py  試験用の声・BGMを合成
```

## 4. 依存関係

- FFmpeg 5.0 以上（`amix normalize` オプションが必要。6.x で動作確認）
- Python 3.9 以上
- PyYAML

## 5. 意図的にやらないこと（初期版）

- 会話中の「間」の自動削除（候補の検出・報告のみ）
- 話者分離・話者ごとの個別音量調整（全体を穏やかに均すのみ）
- AI系ノイズ除去（RNNoise等）：モデルファイル配布が必要になるため見送り
- GUI

# デザイン学習用の外部資料（取り込み状況つき）
ライセンスは確認時点（2026-10）。コードを持ち込む場合は、公開リポジトリのため**依存として使い、再配布しない**／必要な表記を付ける。

| 資料 | ライセンス | 取り込み | 使い方 |
|---|---|---|---|
| [anthropics/skills canvas-design](https://github.com/anthropics/skills/tree/main/skills/canvas-design) | Apache-2.0 | 方式を採用（`design-philosophy.md`） | 描く前に視覚の方針を1枚書く |
| [pbakaus/impeccable](https://github.com/pbakaus/impeccable) | Apache-2.0 | 考え方を採用（`scripts/slop_check.py` は独自実装。コードは取り込んでいない） | 決まった規則で「ダサい案」を検出 |
| [w3c/jlreq](https://w3c.github.io/jlreq/?lang=ja) | W3C文書 | 縦組みの要点を整理（`vertical-typesetting.md`）、`lib.mjs` に約物処理を実装 | 縦組みの題字・作者名 |
| [rough-stuff/rough](https://github.com/rough-stuff/rough)（roughjs 4.6.6） | MIT | `scripts/sketchy.mjs`（依存: `npm i roughjs`。同梱しない） | 細い線を手で引いた線にする |
| [abey79/vpype](https://github.com/abey79/vpype)（1.15.0） | MIT | 下の手順のみ（`pip install vpype`。同梱しない） | 線画の整理・最適化 |
| [mattdesl/canvas-sketch](https://github.com/mattdesl/canvas-sketch) | MIT | 参考のみ（別環境） | 図形の構成・生成的な作例を眺めて発想の幅を広げる |
| [PosterReward](https://alexlai2860.github.io/PosterReward/)／[PosterIQ](https://arxiv.org/html/2603.24078v1) | 論文・各リポジトリを確認 | 参考のみ（GPUが必要） | 講評の観点（文字組み・レイアウト・美しさ）の根拠。**人間評価との照合は、Pilot 01 の結果が出てから** |
| [Awesome-Aesthetics-Assessment](https://github.com/sahilg06/Awesome-Aesthetics-Assessment) | 一覧（各論文による） | 参考のみ | 文献の入口 |
| CyberAgent [OpenCOLE](https://arxiv.org/html/2406.08232v1)／[LayoutDM](https://alphaxiv.org/resources/2303.08137v1)／[MarkupDM](https://huggingface.co/cyberagent/markupdm) | 各リポジトリ・モデルカードを確認（MarkupDM は Apache-2.0 と記載） | 参考のみ（学習・GPUが前提） | 「要素をどこに置くか」の研究として読む |
| [Jolg42/awesome-typography](https://github.com/Jolg42/awesome-typography) | 一覧（最終更新2023） | 参考のみ | 文字組みの基礎資料。ウェブ向けが多い |

## vpype で線画を整理する（検証済みのコマンド）
`pip install vpype` →
`vpype read in.svg linemerge --tolerance 0.3mm linesimplify --tolerance 0.05mm reloop linesort write --page-size 60x40mm --center out.svg`
- 出力は折れ線（曲線は近似）で、単位が cm の viewBox になる。K単色PDFに使う前に、`svg2pdf.cjs` の入力（width/height=mm）に合わせて寸法を確認し、線の太さ（stroke-width）を指定し直す。
- 効果: 途切れた線をつなぐ（linemerge）、点を減らす（linesimplify）。細かい線が多い図で、ファイルの軽量化と引っかかりの除去に使う。手の痕跡を足す用途ではない（それは `roughen.py` / `sketchy.mjs`）。

## 取り込まなかったもの・理由
- 画像生成・レイアウト生成の学習系（OpenCOLE 等）: GPU・学習が必要で、この作業環境と手順に合わない。
- Impeccable のコード本体: ウェブ画面向けの規則が中心。K単色の表紙に使えるのは考え方のみ。

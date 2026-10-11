---
name: print-cover-pdf
description: モノクロ（K単色）の印刷物（台本・冊子の表紙、チラシ表面、ポスター等）を、SVGから生成→文字を曲線化→入稿用ベクターPDF（正確な判型・塗り足し・TrimBox・黒ベタ回避）にして納品する。仕様を機械検査で担保する手順と、デザイン案を複数出して好みへ収束させる進め方を含む。「表紙デザイン」「B5/A6の入稿用PDF」「K単色」「文字は曲線化」「ベタ塗り避ける」「3案出して」などの依頼で使う。
---

# print-cover-pdf

## Purpose
仕様が厳しい（判型・余白・K単色・曲線化・黒ベタ不可）モノクロ印刷物のデザイン案を、**機械検査に合格した入稿用PDF**＋プレビュー＋意図説明として納品する。

## When to use / NOT
- 使う: 表紙・チラシ・ポスター等の「文字＋図形」を、SVGからベクターPDFで作る依頼。
- 使わない: 写真入り／カラー・特色／Word・PowerPoint納品／複数ページ本文組版（→ `script-booklet-print` や `pdf` / `docx` 系）／Tシャツ（→ `tshirt-order-handoff`）。

## Inputs（無ければ最初に1回だけ確認。決められるものは既定で進める）
判型(mm)・塗り足し(mm、無ければ0)・安全余白・色(K単色か)・載せてよい文言（**これ以外の文字を作らない**）・素材ファイル・書体条件（商用可）・縮小転用の有無・**印刷会社の最新仕様**。

## 重要原則
- 数値(最小線幅・余白・黒面積・形式)は**案件ごとの入力**で、このSkillの固定値ではない。`references/spec-checklist.md` の値は例。
- **印刷会社の仕様とSkill内の安全基準が違えば、実案件では会社仕様を優先**（会社値を `check_pdf.py` の引数に渡す）。会社仕様が不明なときだけ内部基準を使い、そう明記する。
- **環境が足りなければ失敗として報告**する。ツールが無いのに「検査済み」と言わない（各スクリプトは不足時に exit≠0）。

## Workflow
0. `scripts/env_check.sh <node_modules>` が `ENV OK` になること（node, playwright(-core)+Chromium, python: pikepdf/numpy/pillow, poppler, opentype.js, @fontsource/noto-serif-jp）。`ENV NG` なら不足を依頼者に伝え、インストール（一時ディレクトリ推奨）してから進む。
1. **仕様を表にする**（`references/spec-checklist.md`）。ページ=塗り足し込み寸法。縮小転用は縦横比が同じか確認。
2. **素材の有無を確認**。指定ロゴが無い → 仮置きし、最終報告で「未受領・仮」と明記。ラスター混在ロゴは `references/raster-to-vector.md`。
3. **方向性は「抽象度」で振る**（`references/design-taste.md`）。
4. **SVGを書く**: `scripts/example.mjs` を複製し `scripts/lib.mjs` の `vtext/htext`（曲線化）・`halo`・`embed` を使う。座標はmm。**テキスト要素(`<text>`)・`<image>`・色付き指定は使わない**。
5. **PDF化と検査（1コマンド）**: `scripts/run_pipeline.sh in.svg out.pdf PAGE_W PAGE_H BLEED MIN_MARGIN [MAX_BLACK]` = svg2pdf(Chromium) → gray_pdf(RGB/CMYK→K、上端基準で寸法確定、TrimBox設定) → check_pdf。**全て PASS で初めて次へ**。
6. **プレビューを目で見る**（PNG化して読む）。見切れ・重なり・可読を確認。
7. **納品**: PDF／一覧画像／説明md（意図2〜3行・書体とライセンス・未確認事項・仮置き素材）。
8. スクリプトを変更したら `tests/run-fixture-test.sh`（正常系＋不適合4種の拒否＋環境不足の拒否）。

## check_pdf.py が見る項目（最終検査）
ページ数1 / MediaBox寸法 / TrimBox有無と位置(=塗り足し分内側) / フォント0 / ラスター画像0 / テキスト層0(曲線化) / RGB・CMYK演算子0・sc系/非Gray色空間0 / パス描画あり(ベクター保持) / トリム端からの余白 / 黒面積。NGがあれば exit 1。

## Decision rules
- 余白実測 < 仕様 → 図形を縮める／ずらす。塗り足しなしで端に接する図は作らない。
- 黒面積が大きい（会社が黒ベタ不可なら会社基準、無ければ案件で決めた上限）→ 面を線・網点へ。
- 画像が残る → SVG内の mask/image 参照を除去（ラスターのマスク残りが典型原因）。
- `gray_pdf` が非グレーを報告 → ロゴ等の色味付き黒を `fill` で正規化（輝度グレー、暗い値は#000）。
- 面を斜線/網点で表現 → 縮小転用で潰れる。最小線幅・網点を説明に書く。
- 塗り足しあり → SVGサイズを「仕上がり+両側塗り足し」にし、`gray_pdf`/`check_pdf` に BLEED を渡す。

## Failure modes → Recovery
- 書体に無い文字 → `lib.mjs` が例外。別書体/異体字に。
- Chromiumの用紙寸法の丸め(0.1〜0.7mm) → `gray_pdf` が上端基準で正確に切り直す（検査はこの後のPDFに対して行う）。
- 「ダサい」「具体的すぎ」「数が多い」→ 要素を減らす方向に直す（`references/design-taste.md`）。
- 自動の細線太らせ(ロゴ)で潰れる → 1回試して崩れたら止め、作り直し/用途別方式/現状入稿を提示。
- 環境不足でテスト・検査不能 → 不足を列挙して報告。成功と書かない。

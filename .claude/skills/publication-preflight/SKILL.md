---
name: publication-preflight
description: 入稿前チェック（preflight）の実行と読み方。ページ数・サイズ・塗り足し・欠落素材・本文あふれ・ノンブル・フォント・解像度・色の確認結果（PASS/WARNING/FAIL/MANUAL CHECK）を扱う。HTML→PDF（Chromium/Vivliostyle）で作ったカラー冊子を、CMYK変換・アウトライン化・本文黒のK100化・表紙連結して印刷所へ出す仕上げ（「入稿準備」「CMYKにして」「フォントをアウトライン化」）にも使う。
---
# Publication preflight

`npm run publication:preflight -- <id>`（または `publication:all`）。要 `build`+`render` 済み。結果は `output/<id>/preflight.{md,json}`。FAIL があれば終了コード1。

**これは入稿適合の保証書ではない。** 項目は AUTOMATED CHECK（決定的な測定）/ HEURISTIC（経験則）/ MANUAL CHECK（未確認）に分類され、総合判定に「ready」はない。

## ステータス
- **PASS**: 自動で確認でき、問題なし
- **WARNING**: 問題の可能性。理由を確認して判断（例: Type 3 フォント、RGB画像、本文枠が疎）
- **FAIL**: 修正が必要（欠落素材・本文切れ・ページ数不一致・ノンブル誤り・未解決のBLOCKER/HIGH）
- **MANUAL CHECK**: v0.1 では自動確認できない。**確認済みではない**（CMYK/PDF-X、クロップマーク、批評・校正の未完了）

## 項目
P00 公開境界（非公開の号が公開ツリーにある→FAIL）, P01 flatplan/schema, P02 未配置記事, P03 未知layout, P04 欠落素材, P05 キャプション欠落(FAIL), P06 原稿量, P08 総ページ数, P09 PDFページ数, P10 PDFが最新か, P11 仕上がりサイズ(TrimBox), P12 塗り足し(BleedBox), P13 トンボ, P14 フォント埋め込み, P15 テーマフォント有無, P17 白ページ, P18 画像破損, P19 本文あふれ/はみ出し, P20 ノンブル欠落/重複/誤り, P21 セーフエリア, P22 実効ppi, P23 断ち落とし画像の塗り足し, P24/P25 画像色空間, P26 PDF色/PDF-X, P27 Critic（見た成果物に結び付いたレビューのみ判定。古いレビューは MANUAL CHECK）, P28 Proofreader, P29 孤立行(HEURISTIC), P30 未充填頁(HEURISTIC), P31 目次の欠落, P32-P34 ICC・オーバープリント/トラッピング/インキ総量・印刷会社適合（MANUAL CHECK）

## 対処
- P19 FAIL: 台割のページ配分/variant/原稿量。`rhythm.md` の `fill` 列を根拠に
- P10 FAIL: ソース変更後に再build。P16: 再render
- P22: 画像を高解像度に差し替え（元データは残す）
- P14 Type 3: Chromium出力の仕様。印刷所のpreflight可否を確認
- MANUAL CHECK は号の記録（`notes/decisions.md`）に「誰が・いつ・何を確認したか」を残す

## v0.1 のスコープ外
CMYK自動変換、PDF/X適合保証、印刷会社別プロファイル。これらは MANUAL CHECK として残す。

## カラー冊子の入稿仕上げ（v0.1外の作業を手で行う）
`npm` の preflight を通さずに組んだ冊子（Vivliostyle/Chromium 出力のRGB・フォント埋め込みPDF）を印刷所に出すときの手順。
1. 組版PDFから本文ページだけを抜く（表紙が別データなら `pdfseparate`→`pdfunite`）。
2. `python3 .claude/skills/publication-preflight/scripts/color-print-finish.py 本文.pdf 入稿.pdf --cover 表紙.pdf --bleed 3`
   - gs で CMYK 変換＋アウトライン化（画像はダウンサンプルしない）→ ほぼ黒を K100 に置換 → 表紙を先頭に連結 → 全ページに TrimBox/BleedBox → 検査値を表示。gs が無ければ `apt-get install -y ghostscript`。
3. 表示を確認: ページ数＝注文ページ数、全ページ同寸（仕上がり＋塗り足し）、フォント0、最小ppi≥300（仕上がり寸法で）、インキ総量（最大と99.5%値。上限は印刷会社の値で判断）。
4. 追加の目視・機械確認: 全ページを縮小して並べて見る／仕上がり線から3mm以内に文字が無いか（暗画素を数え、塗り足し写真・背景によるものは意図と判断）／**QRコードは変換後のPDFを300dpiでラスタライズして再デコード**する。
5. 報告: 何をPASSとしたかと、未確認のもの（写真の掲載同意など内容面）を分けて書く。

判断基準と失敗例:
- 濃い色（例 #1F1B18）の文字は RGB→CMYK で4色ベタ（C72 M69 Y63 K83 程度、総量280%超）になる。8pt前後の本文で版ズレするとにじむので K100 にする。置換後に `tiff32nc` でラスタライズし、文字部が (0,0,0,100) になったか数える。
- 表紙をデザイナーから受け取ったら `pdfinfo -box`・`pdffonts`・色演算子（`k` のみで `rg` が無い）を確認してから連結する。受領PDFは TrimBox=MediaBox のことがあるので連結後にまとめて設定し直す。
- 表紙に文字を足すときはフォントを入れず、fontTools でグリフをパス化したSVG→PDFを重ねる（`pypdf` の `merge_transformed_page`）。差し替え版の表紙が届いたら、足した文字は元の差し替え版に既に含まれていないか確認して重複させない。
- 変換で写真の朱・赤系は画面よりくすむ。ユーザーに一言伝える。
- ソースを直したら、このスクリプトからやり直す（古い入稿PDFを送らない）。最終版はファイル名を固定し、「前に送った版ではなくこれを入稿」と明示する。

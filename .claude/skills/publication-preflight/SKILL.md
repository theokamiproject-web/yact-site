---
name: publication-preflight
description: 入稿前チェック（preflight）の実行と読み方。ページ数・サイズ・塗り足し・欠落素材・本文あふれ・ノンブル・フォント・解像度・色の確認結果（PASS/WARNING/FAIL/MANUAL CHECK）を扱う。
---
# Publication preflight

`npm run publication:preflight -- <id>`（または `publication:all`）。要 `build`+`render` 済み。結果は `output/<id>/preflight.{md,json}`。FAIL があれば終了コード1。

## ステータス
- **PASS**: 自動で確認でき、問題なし
- **WARNING**: 問題の可能性。理由を確認して判断（例: Type 3 フォント、RGB画像、本文枠が疎）
- **FAIL**: 修正が必要（欠落素材・本文切れ・ページ数不一致・ノンブル誤り・未解決のBLOCKER/HIGH）
- **MANUAL CHECK**: v0.1 では自動確認できない。**確認済みではない**（CMYK/PDF-X、クロップマーク、批評・校正の未完了）

## 項目
P01 flatplan/schema, P02 未配置記事, P03 未知layout, P04 欠落素材, P05 キャプション欠落(FAIL), P06 原稿量, P08 総ページ数, P09 PDFページ数, P10 PDFが最新か, P11 仕上がりサイズ(TrimBox), P12 塗り足し(BleedBox), P13 トンボ, P14 フォント埋め込み, P15 テーマフォント有無, P17 白ページ, P18 画像破損, P19 本文あふれ/はみ出し, P20 ノンブル欠落/重複/誤り, P21 セーフエリア, P22 実効ppi, P23 断ち落とし画像の塗り足し, P24/P25 画像色空間, P26 PDF色/PDF-X, P27 Critic, P28 Proofreader

## 対処
- P19 FAIL: 台割のページ配分/variant/原稿量。`rhythm.md` の `fill` 列を根拠に
- P10 FAIL: ソース変更後に再build。P16: 再render
- P22: 画像を高解像度に差し替え（元データは残す）
- P14 Type 3: Chromium出力の仕様。印刷所のpreflight可否を確認
- MANUAL CHECK は号の記録（`notes/decisions.md`）に「誰が・いつ・何を確認したか」を残す

## v0.1 のスコープ外
CMYK自動変換、PDF/X適合保証、印刷会社別プロファイル。これらは MANUAL CHECK として残す。

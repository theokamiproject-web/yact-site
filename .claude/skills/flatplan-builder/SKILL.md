---
name: flatplan-builder
description: 台割（flatplan.yaml）を作る・直す。記事のページ配分、見開き構成、強弱とリズムの設計、layout/variantの割り当て、台割の検証をするときに使う。
---
# Flatplan builder

## 構造（`issues/<id>/flatplan.yaml`）
```yaml
pages:
  - { pages: [4, 5], article: harbor-theater, layout: feature-opener, variant: spread-bleed,
      visual_intensity: 5, text_density: 2, image_density: 5, notes: 意図, slots: { image: x.jpg } }
```
- `pages: [n]` 単ページ / `[n, n+1]` 見開き。**見開きは偶数ページ始まり**（中綴じ・無線綴じとも。1ページ目は右ページ単独）
- 全ページ 1..`issue.pages` を**ちょうど1回**。中綴じは総ページ数が4の倍数
- `visual_intensity` `text_density` `image_density`: 1–5。計画値。実測は `render` 後の `rhythm.md` で確認され、乖離が大きいと NOTE が出る
- `intentional_sparse: true` + `notes`（理由必須）: 意図して本文が少ない頁の宣言。quote/divider/写真/cover/colophon は宣言不要
- `slots`: そのページ限りの入力上書き（`image`, `images`, `hero_image`, `pull_quote`, `quote_source`, `facts`）

## リズム設計
1. 固定: 1=表1、最終=表4、2=目次、奥付は後ろ
2. 山（写真見開き・大見出し）を全体の1/4以下、静かなページ（余白の多い本文/引用）を最低1つ
3. 同一layoutを3連続しない（`max_same_layout_run`）。写真主体を3ページ以上連続させない
4. 記事の入口は variant を変える。オープナーは見開きと単ページを混ぜる
5. 文字ページが4連続したら、引用・写真・コラムを挟む

## 検証
`npm run publication:validate -- <id>`。エラー例: `FLATPLAN_GAP`(未割当) `FLATPLAN_OVERLAP`(重複) `SPREAD_PARITY`(見開きが奇数始まり) `SPAN_MISMATCH`(variantのページ数と不一致) `UNKNOWN_LAYOUT` `ARTICLE_NOT_PLACED` `MISSING_INPUT`。
承認フロー: Editor が骨格 → Editor in Chief 承認 → Layout Designer が型を当てる。

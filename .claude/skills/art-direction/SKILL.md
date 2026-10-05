---
name: art-direction
description: 号のvisual conceptとDesign Systemを決める。テーマ（themes/・issue theme.css・theme_overrides）の色・書体・サイズ・余白・グリッドの調整、Fingerprint Control（fingerprint_target）の設定をするときに使う。
---
# Art direction

## Design System の継承
`themes/base`（tokens/typography/page/grid/components.css）→ `themes/<name>/*.css` → `issues/<id>/theme.css` → `issue.yaml: theme_overrides`。ページサイズ・断ち落としは `issue.yaml` が正で、ビルド時に `css/page-setup.css` として最後に注入される。

## 主なトークン（`themes/base/tokens.css`）
3系統: PHYSICAL（実寸固定: 塗り足し・罫線・最小文字 7pt）/ PAGE-RELATIVE（ページ比: 余白・段間・ヒーロー高さ・画像領域）/ TYPOGRAPHY-DERIVED（`--type-scale` で拡縮: 文字サイズ・行送り）。ページ相対の値に mm を書かない。
- 余白/グリッド: `--margin-top/bottom/inner/outer` `--columns` `--gutter` `--baseline`(行送り=縦リズムの単位) `--safe`
- 書体: `--font-body`(明朝) `--font-heading`(ゴシック) `--font-display`
- サイズ: `--fs-caption/small/body/lead/h3/h2/h1/display`、`--lh-*`
- 色: `--color-paper/ink/sub/accent/accent-2/tint`、罫線 `--rule-thin/bold`
- 要素: `--folio-offset` `--runhead-offset`（ノンブル・柱）

## 号のアイデンティティ
- 新しい号は `theme_overrides` で色（accent）から変える。書体変更は印刷用フォントの埋め込み可否を確認してから
- 反復するモチーフを1つ決め（例: 茜色の短い罫線）、全記事で出す。`fingerprint_target.motif` に書く（Criticが目視で確認）
- 数値目標: `max_same_layout_run` `max_consecutive_image_heavy` `min_intensity_range` `max_opener_repeat` `min_quiet_pages`

## 注意
- 本文サイズ・行送りを変えても、容量は組版前の実測枠から決まるので追従する。変更後は `render` の `text_occupancy` と `P19` で必ず検証
- 変更後は全ページを見る（contact sheet）。1ページだけ見て決めない
- baseを直接変えると既存号すべてに影響する。号固有は issue theme へ

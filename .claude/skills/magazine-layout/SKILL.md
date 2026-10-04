---
name: magazine-layout
description: 誌面のlayout componentを選び、組む。component一覧と入力契約、variant、見開き構成、本文あふれ対処、新component追加の作法。flatplan.yamlのlayout/variant/slotsを決めるときに使う。
---
# Magazine layout

**ページをゼロからHTMLで発明しない。** `publishing-studio/layouts/<family>/index.mjs` の component を使う。

## Components（layout 名: variants — 入力契約）
| layout | variants (pages) | 必須入力 | 備考 |
|---|---|---|---|
| cover | full / typo / split / back (1) | full,split: hero_image | `cover_lines`で表紙コピー。back=表4 |
| contents | list / large (1) | toc(自動) | 目次は台割から自動生成 |
| feature-opener | hero-top / title-over (1), spread-bleed (2) | title, deck, hero_image | spread は偶数ページ始まり |
| feature-body | two-col / two-col-image / pullquote (1) | image(two-col-image), pull_quote(pullquote) | 本文は自動配分 |
| interview-opener | portrait-left / big-quote (1) | title, interviewee, portrait(portrait-left) | Q&Aを途中から開始 |
| interview-body | qa / qa-portrait (1) | image(qa-portrait) | `Q:`/`A:` 段落 |
| essay | opener / body / end (1) | title(opener) | endは終わりの印■ |
| photo-essay | grid-3 / sequence-4 / wide-single (2) | images(3/4/1枚以上) | 見開き |
| full-bleed-photo | single (1) / spread (2) | hero_image | 裁ち落とし |
| quote-page | center / color-block / left-rule (1) | pull_quote | |
| divider | ink / paper / accent (1) | title | |
| column | box / plain (1) | title | |
| profile | card / wide (1) | title | `facts: [{label,value}]` slot |
| credits | columns (1) | – | `credits.yaml` |
| colophon | standard / with-credits (1) | – | `credits.yaml` |
入力は記事の front matter（`title` `deck` `intro` `author` `assets` `pull_quotes` …）とflatplanの `slots` から作られる。画像は `assets` の role（hero/portrait/inline/…）で自動解決され、`slots` で上書きできる。

## 組み方
1. 台割の意図（notes・強度）を読み、variant を選ぶ。同じ意味内容でも variant で表情を変える
2. `validate` → error ゼロ。`MISSING_INPUT` は契約違反（必須入力が無い）
3. `all` → `rhythm.md` と contact-spreads.png で見開きの流れを確認
4. 本文あふれ（P19 FAIL）: ページ配分を変える／variantを容量の大きいものに／原稿を削る（Editorの判断）

## 新しい component/variant を足すとき
`layouts/<family>/index.mjs` の `components[name]` に `variants{name:{pages}} defaultVariant required(variant) optional captions text?{capacity(variant,inputs)} render({inputs,variant,text,model})` を定義。render は `pages` 個の `{html, chrome:'full'|'folio'|'none', bg?, dark?}` を返す。全面画像は `.bleed` か 断ち落とし分(`--bleed`)をはみ出させる。CSS は同階層 `style.css` にトークンで書く。
新規 component を足したら `tests/` の component 網羅テストが自動で拾う。

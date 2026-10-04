# Publishing Studio v0.1

雑誌・ZINE・冊子を **企画 → 台割 → Art Direction → 組版 → 全ページレビュー → 修正 → Preflight** の工程ごと Claude Code 上で再現可能にする出版環境です。

> **原則**: AIが毎回デザインを発明するのではなく、**編集構造（Publication Model）・Design System（テーマ）・再利用 component の制約下で**編集・設計する。品質の再現性を生成の自由度より優先する。

誌面HTMLは生成物です。**原稿・台割・テーマを直せば、誌面は作り直されます**（原稿や編集構造は壊れません）。

## セットアップ

```bash
npm install            # リポジトリのルートで
```
必要なもの: Node 20+、Chromium（`/opt/pw-browsers` や Playwright のものを自動検出。別の場所なら `PS_BROWSER=/path/to/chrome`）、poppler（`pdftoppm` `pdffonts`）、日本語フォント（Noto Serif/Sans CJK JP）。
Debian/Ubuntu: `apt install poppler-utils fonts-noto-cjk`。

## 5分で試す（サンプル号）

```bash
npm run publication:all -- test-issue-01
```
`publishing-studio/output/test-issue-01/` に PDF・全ページPNG・contact sheet・レビューpack・preflight が出ます（約10秒）。

## 新しい号の作り方

```bash
npm run publication:new -- issue-01 --title "創刊号"   # issues/_template をコピー
# issues/issue-01/ を編集（下記）
npm run publication:validate -- issue-01               # 構造チェック（何が足りないか日本語で出ます）
npm run publication:all -- issue-01                    # 検証→PDF→全ページ画像→批評pack→preflight
```
`issue-01` のように末尾の数字は号数（`issue_number`）に自動設定されます。

編集する場所は `issues/<id>/` の次の7つだけです。

| ファイル | 書くこと |
|---|---|
| `issue.yaml` | タイトル、判型（`format` `width` `height` mm）、総ページ数、綴じ、塗り足し、言語、テーマ名 |
| `editorial.yaml` | コンセプト、読者、編集の声、空気感、リズム、密度、キーワード |
| `articles/*.md` | 記事（front matter + Markdown本文） |
| `flatplan.yaml` | 台割（どのページに何をどの型で置くか） |
| `images/` `captions/` | 写真とキャプション |
| `credits.yaml` | クレジット・奥付 |
| `notes/` | メモ（ビルド対象外・Blind Reviewには渡らない） |

## 原稿を追加する

1. `articles/<記事id>.md` を作る。ファイル名＝`id`。
```markdown
---
id: harbor-theater
title: 倉庫が劇場になる日
kicker: 特集
deck: タイトルが伝えない「なぜ今・誰の話か」を1〜2文で。
intro: 本文の入口（80字前後・任意）
type: feature            # feature | interview | essay | photo-essay | column | profile | quote | divider | …
priority: 1              # 1=目玉 3=つなぎ
target_pages: 4
author: 汐田 結
assets:
  - { image: harbor-hero.jpg, role: hero }
pull_quotes:
  - 客席は、みんなで運んだ椅子でできている。
---
本文はMarkdown。空行で段落。

## 小見出しはこう書く
```
2. インタビューは、段落を `Q: ` と `A: ` で始めます。
3. **台割に置く**（次節）。置かない記事は `status: spiked`。
4. `npm run publication:validate -- <id>`。本文の分量は警告で分かります。

| 警告/エラー | 意味と対処 |
|---|---|
| `TEXT_PAGE_SPARSE` | 本文枠の充填率が35%未満 → 原稿を足す／ページを減らす |
| `TEXT_MAY_OVERFLOW` | 見込みが枠の105%超 → 原稿を削る／ページを足す／容量の大きい型に |
| `TEXT_PAGE_EMPTY` | 本文ページに文章が回ってこない → ページ配分を見直す |
| `TARGET_PAGES` | 記事の `target_pages` と台割のページ数が違う |

長い記事は台割で **同じ記事を複数ページ** に割り当てます。本文は先頭から、各ページの容量に応じて自動配分されます（段落の途中は句点で切れ、`Q:`は`A:`と離れません）。

## 写真を追加する

1. 画像を `images/` に置く（元データのまま。JPEG/PNG。**仕上がり寸法で200ppi以上**が目安）。
2. 使う記事の `assets` に書く: `- { image: ファイル名, role: hero }`（role: `hero` `portrait` `inline` `transition` `sequence` `decorative`）。または台割の `slots` で指定。
3. `captions/captions.yaml` にキャプション:
```yaml
harbor-hero.jpg: { caption: 夕暮れの潮見港。, credit: 写真＝氏名 }
```
キャプションが無いと `validate` は警告、`preflight` は **FAIL**（`decorative` と表紙は不要）。
4. 任意: `images/images.yaml` に `focal: [x, y]`（0〜1、トリミングで残す中心）・`alt`・`note`。
見開きの写真は中央（ノド）に被写体を置かないこと。

## 台割を変更する

`flatplan.yaml`:
```yaml
pages:
  - { pages: [4, 5], article: harbor-theater, layout: feature-opener, variant: spread-bleed,
      visual_intensity: 5, text_density: 2, image_density: 5, notes: 意図, slots: { image: x.jpg } }
```
- `pages: [n]` 単ページ、`[n, n+1]` 見開き（**偶数ページ始まり**）。1ページ目は右ページ単独。
- 全ページ `1..issue.pages` を**ちょうど1回**。中綴じは総ページ数が **4の倍数**。
- `visual_intensity` / `text_density` / `image_density`（1–5）は計画値。実測値は `rhythm.md` に出て、乖離が大きいと注意されます。
- `layout` / `variant` は下の表から。迷ったら `variant` を省略（既定値）。
- 並べ替えるときは `pages` の数字だけ直す。原稿・写真は動かしません。

### Layout components

| layout | variant（ページ数） | 必須入力 |
|---|---|---|
| `cover` | `full` `typo` `split` `back`（1） | full/split: `hero_image` |
| `contents` | `list` `large`（1） | 自動 |
| `feature-opener` | `hero-top` `title-over`（1）, `spread-bleed`（2） | `title` `deck` `hero_image` |
| `feature-body` | `two-col` `two-col-image` `pullquote`（1） | `image`/`pull_quote`（該当variantのみ） |
| `interview-opener` | `portrait-left` `big-quote`（1） | `title` `interviewee` `portrait`（portrait-left） |
| `interview-body` | `qa` `qa-portrait`（1） | `image`（qa-portrait） |
| `essay` | `opener` `body` `end`（1） | `title`（opener） |
| `photo-essay` | `grid-3` `sequence-4` `wide-single`（2） | `images`（3 / 4 / 1枚以上） |
| `full-bleed-photo` | `single`（1）, `spread`（2） | `hero_image` |
| `quote-page` | `center` `color-block` `left-rule`（1） | `pull_quote` |
| `divider` | `ink` `paper` `accent`（1） | `title` |
| `column` | `box` `plain`（1） | `title` |
| `profile` | `card` `wide`（1） | `title`（`facts` slot 任意） |
| `credits` / `colophon` | `columns` / `standard` `with-credits`（1） | `credits.yaml` |

入力は記事の front matter（`title` `deck` `intro` `author` `assets` `pull_quotes` …）と台割の `slots` から自動で作られます。契約を満たさないと `validate` が `MISSING_INPUT` を返します。

## テーマ（Design System）を変更する

継承: `themes/base` → `themes/<name>` → `issues/<id>/theme.css` → `issue.yaml` の `theme_overrides`。ページサイズ・塗り足しは `issue.yaml` が正で、最後に自動注入されます。

- **この号だけ色を変える**: `issue.yaml`
```yaml
theme_overrides:
  --color-accent: "#2f6f5e"
  --font-body: '"Noto Sans CJK JP", sans-serif'
```
- **もっと変える**: `issues/<id>/theme.css` を作り、CSSカスタムプロパティを上書き。
- **他の号でも使う**: `themes/<名前>/` に `*.css` を置き、`issue.yaml` の `theme: <名前>`。
- `themes/base` は直接変えない（全号に影響）。

主なトークン（`themes/base/tokens.css`）: 余白 `--margin-*`、`--columns` `--gutter` `--baseline`、書体 `--font-*`、サイズ `--fs-*`、色 `--color-*`、罫線 `--rule-*`、ノンブル/柱 `--folio-offset` `--runhead-offset`。
**本文サイズ・余白・行送りを変えると、文字数の容量見積りがずれます**。変更後は `render` の充填率と `preflight P19` で確認してください。

## build / preview

```bash
npm run publication:build   -- <id>            # PDF（output/<id>/<id>.pdf）
npm run publication:build   -- <id> --marks    # トンボ付き
npm run publication:preview -- <id>            # Vivliostyle の実ページ送りプレビュー（http://localhost:13000）
npm run publication:build   -- <id> --web-only # 静的HTMLだけ（output/<id>/web/index.html を直接開ける）
npm run publication:render  -- <id>            # 全ページPNG + contact sheet + 計測
```
`render` の出力（`output/<id>/`）: `pages/page-NN.png`（仕上がり寸法のみ）、`contact/contact-4xN.png` `contact-8xN.png` `contact-spreads.png`（見開き並び）、`metrics.json`。

## critic（批評）

制作と批評は**別のコンテキスト**で行います（`.claude/agents/publication-critic.md`）。

```bash
npm run publication:critic -- <id>           # pack・rhythm・fingerprint・レビュー雛形を生成
npm run publication:critic -- <id> --check   # 完了したレビューを検証して critic-report.json を生成
```
1. `output/<id>/review-pack/blind/`（ページPNG・contact sheet・数値のみ）→ **Blind Review** → `issues/<id>/reviews/critic-blind.md`
2. `review-pack/context/`（編集意図・台割・fingerprint・rhythm・preflight）→ **Context Review** → `critic-context.md`
3. 重大度 `BLOCKER/HIGH/MEDIUM/LOW/NOTE` で優先順位 → 修正 → `publication:all` 再実行
4. **Re-review** → `critic-rereview.md`（全指摘に `fixed/open/regressed/wontfix`）

指摘は **問題 → 根拠 → ページ → 重大度 → 修正案** の形式。雛形は `status: pending`、自動検出（`A-xxx`）が埋め込まれます。`--check` はスコア（10項目）・ID一意・必須項目・ページ範囲・disposition漏れを検証します。
**自動計測（`rhythm.md` `fingerprint.json`）は事実、視覚評価は Critic の仕事**で、混ぜません。`pending` のレビューは preflight で `MANUAL CHECK`（実施済みではない）です。

- `rhythm.md`: ページ別の強度・文字量・画像比・余白・本文充填率。同一layout連続、写真ページ連続、強弱の振れ幅、静かなページの自動検出。
- **Publication Fingerprint**（`fingerprint.json`）: DESIGN（D1–D7）/ EDITORIAL（E1–E6）/ ISSUE（I1–I6）の19軸を `machine` / `hybrid` / `visual` に区別。意図は `editorial.yaml` の `fingerprint_target`（**Fingerprint Control**）、実物から現れた癖は `## Emergent fingerprint` に記録。

## preflight

```bash
npm run publication:preflight -- <id>
```
`PASS` / `WARNING` / `FAIL` / `MANUAL CHECK`（自動確認できない＝**確認済みではない**）。FAIL があると終了コード1。結果は `output/<id>/preflight.md|json`。

検査項目: 総ページ数（期待/実際）、PDFが最新か、仕上がりサイズ（TrimBox）、塗り足し（BleedBox）、トンボ、白ページ、欠落素材、画像破損、キャプション欠落、本文あふれ/はみ出し、ノンブルの欠落・重複・誤り、未配置記事、未知layout、フォント埋め込み/不足、画像の有効ppi、RGB/CMYK、セーフエリア、断ち落とし画像の塗り足し、Critic/Proofreader の完了状況。

## 作業の流れとagent

`.claude/agents/`: `editor-in-chief` `editor` `art-director` `layout-designer` `photo-editor` `proofreader` `publication-critic`（役割は混ぜない。各自が書いてよいファイルが決まっています）。
`.claude/skills/`: `publishing-studio`（全体手順・ゲート）`editorial-planning` `flatplan-builder` `art-direction` `magazine-layout` `photo-editing` `publication-critic` `publication-preflight`。

```
企画 → 原稿・写真 → 台割(EiC承認) → Art Direction → 組版 → 校正 → Critic(blind→context) → 修正 → Re-review → Preflight
```

## ディレクトリ構成

```
.claude/agents/           7 agents
.claude/skills/           8 skills
package.json              publication:* scripts（リポジトリルート）
publishing-studio/
  issues/_template/       新規号の雛形
  issues/<id>/            号ごとのデータ（source of truth）
    reviews/              critic-*.md, proofread.md（Git管理）
  themes/base/            tokens / typography / page / grid / components .css
  layouts/<family>/       index.mjs（契約+描画）+ style.css
  schemas/                issue / editorial / flatplan / article / critic-report の JSON Schema
  scripts/                CLI（new-issue validate build preview render-pages critic-pack preflight all）
  scripts/lib/            load / validate-model / compose / build / metrics / render / analysis / critic / preflight
  tests/                  node:test（npm run publication:test）
  output/<id>/            生成物（Git管理外）
  docs/BUILD_LOG.md       実装ログ
```

テスト: `npm run publication:test`（スキーマ・台割・未配置記事・未知layout・欠落素材・全component・build・PDFページ数・全ページ画像・critic pack・preflight・異常系のFAIL）。

## current limitations（v0.1）

- **色**: PDFはRGB（Chromium出力）。CMYK変換・出力インテント・**PDF/X適合は未対応**（`MANUAL CHECK`）。PDFのフォントは Type 3 で埋め込まれる（印刷所によっては要確認、`WARNING`）。
- **トンボ**: `--marks` で付くが、トンボ自体の内容は検査していない。
- **縦書き・ルビ・禁則の細かな調整は未対応**（横組み・`line-break: strict`）。
- **本文の流し込み**は文字数ベースの見積り（実測で±10%程度）。最終判定はDOM計測（P19）。Vivliostyleの自動ページ送りではなく、台割で固定した1ページ=1枠。ページをまたぐ脚注・図版回り込みは無い。
- 見開きの写真は、ノド（中央）の画像は両ページで連続するが、ノドでの喰い込み補正はしない。
- 画像の自動トリミング・色補正・写真の内容理解は行わない（`focal` は人が指定）。
- 容量見積りは `themes/base` の本文サイズ・余白前提。テーマを大きく変えたら再校正が必要。
- Critic の批評そのものは agent（LLM）が書く。スクリプトは pack 生成・構造検証・機械的な自動検出まで。
- 過去号との類似度分析、自動修正ループ、EPUB、Web版、GUI/CMSは対象外。
- `publishing-studio/` はGitHub Pages（リポジトリ直下の静的サイト）から配信対象に含まれ得ます。公開したくない号は別リポジトリに分けるか、`issues/` を公開対象から外してください。

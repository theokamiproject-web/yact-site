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

Chromium は**サンドボックス有効**で起動します。root で動かす隔離コンテナなどで起動できない場合のみ `PS_NO_SANDBOX=1`（Claude の管理リモートコンテナでは root 時に自動で無効化され、起動時に注意書きが出ます）。原稿の HTML はすべて無害化され、測定用ブラウザはネットワークに出られません。

## 5分で試す（サンプル号）

```bash
npm run publication:all -- test-issue-01
```
`publishing-studio/output/test-issue-01/` に PDF・全ページPNG・contact sheet・レビューpack・preflight が出ます（約10秒）。

## 公開境界: 何を Git に入れてよいか（最初に読む）

このリポジトリのルートは **GitHub Pages で公開される静的サイト**です。Git に入れたものは公開され得ます。そこで、すべてのファイルを次の5分類で扱います（`boundary.json`）。

| 分類 | 対象 | Git |
|---|---|---|
| `PRIVATE_SOURCE` | 実制作号の原稿・写真・captions・notes・editorial・台割・レビュー（`workspace/` と、`issues/` のうち例示号以外） | **入れない**（`.gitignore` + pre-commit + CI が拒否） |
| `BUILD_TEMP` | `output/<id>/{web,pages,contact,review-pack}` | 入れない |
| `GENERATED_PRIVATE` | PDF・metrics・preflight・rhythm 等 | 入れない |
| `PUBLISHABLE` | 例示号（`issues/test-issue-01` `test-issue-02` `_template`）、意図して公開する `publish/<id>/` | 入れてよい |
| `SYSTEM` | scripts・layouts・themes・schemas・tests・docs・フレームワークのレビュー記録 | 入れてよい |

- `npm run publication:new -- <id>` は **`workspace/issues/<id>/`**（Git 管理外）に作ります。実号はここに置いてください（バックアップは別途）。
- `validate` / `build` / `all` / `preflight` は、非公開の号が「Git に追跡されている」または「Git に無視されないまま公開ツリー内にある」場合に **FAIL** します（P00）。意図的に許可するときだけ `--i-understand-private-source-may-be-published`（または環境変数 `PS_ALLOW_PUBLIC_TREE=I_UNDERSTAND_PRIVATE_SOURCE_MAY_BE_PUBLISHED`）。許可した事実は preflight に WARNING で残ります。
- `npm run publication:boundary` で追跡ファイルを検査。`npm install` が `core.hooksPath=.githooks` を設定し、**commit 時に自動検査**します（CI も同じ検査）。
- 公開ツリーの外（別ディレクトリ・非公開リポジトリ）で作業するなら `PS_ISSUES_DIR=/path/to/issues`。
- 例示号を増やすときは `boundary.json` の `examples` と `.gitignore` の許可リストの**両方**に追加（テストが一致を検査）。

## 新しい号の作り方

```bash
npm run publication:new -- issue-01 --title "創刊号"   # issues/_template を workspace/issues/ にコピー
# workspace/issues/issue-01/ を編集（下記）
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

**原稿は信頼できない入力として扱われます**。使えるのは Markdown が生成する `p h3 strong em del code br ul ol li blockquote` だけ。生の HTML（`<script>` `<style>` `<iframe>` `on*=` など）はエスケープされ**文字としてそのまま印刷**され、validate が `MD_RAW_HTML_ESCAPED` で知らせます。Markdown の画像 `![]()` は削除、リンクは文字だけ印刷。画像は必ず `images/` に置いて `assets` に書いてください。
4. `npm run publication:validate -- <id>`。本文の分量は警告で分かります。

| 警告/エラー | 意味と対処 |
|---|---|
| `TEXT_UNDERFILLED` | 本文が、その component の**記事内での位置**（最初/中/最後/単独）に期待される量に満たない（HEURISTIC）→ 原稿を足す／ページを減らす／意図なら下記 `intentional_sparse` |
| `TEXT_MAY_OVERFLOW` | 見込みが枠の105%超 → 原稿を削る／ページを足す／容量の大きい型に |
| `TEXT_PAGE_EMPTY` | 本文ページに文章が回ってこない → ページ配分を見直す（または `intentional_sparse`） |
| `CONTENTS_OVERFLOW` / `LAYOUT_OVERFLOW` | **本文を入れる前から**目次の項目や見出し・キャプションがページに収まらない（エラー）。項目が消えるビルドは作りません |
| `TARGET_PAGES` | 記事の `target_pages` と台割のページ数が違う |
| `INTENT_NEEDS_NOTE` | `intentional_sparse: true` には `notes` に理由が必要 |

長い記事は台割で **同じ記事を複数ページ** に割り当てます。本文は先頭から、各ページの容量に応じて自動配分されます（段落の途中は句点で切れ、`Q:`は`A:`と離れません）。

## 写真を追加する

1. 画像を `images/` に置く（元データのまま。JPEG/PNG。**仕上がり寸法で200ppi以上**が目安）。ファイル名は日本語・空白・`#`・括弧も使えます（標準の URL エンコードで扱います）。パス区切りや `..` は不可。
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
- **意図した「空き」は宣言する**: 本文が少ない頁を意図するときは `intentional_sparse: true` と、`notes` に理由を書く（理由なしはエラー）。quote・divider・写真見開き・cover・colophon などは契約上もともと空きが許されるため宣言不要です。宣言した頁は `rhythm.md` に一覧されます。

### Layout components

| layout | variant（ページ数） | 必須入力 |
|---|---|---|
| `cover` | `full` `typo` `split` `back`（1） | full/split: `hero_image` |
| `contents` | `list` `large`（1） | 自動。**収容数は実測**（超えると `CONTENTS_OVERFLOW` エラー。大きい `large` は少なめ）。`in_contents: false` で項目を外す |
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

各 component には**密度の契約**（`layouts/_contracts.mjs`）があり、本文頁は記事内の位置（最初/中/最後/単独）ごとに期待される本文量と内容の到達度を持ちます。全頁共通の「充填率◯%」のような単一閾値はありません。

入力は記事の front matter（`title` `deck` `intro` `author` `assets` `pull_quotes` …）と台割の `slots` から自動で作られます。契約を満たさないと `validate` が `MISSING_INPUT` を返します。

## テーマ（Design System）を変更する

継承: `themes/base` → `themes/<name>` → `issues/<id>/theme.css` → `issue.yaml` の `theme_overrides`。ページサイズ・塗り足しは `issue.yaml` が正で、最後に自動注入されます（本文サイズなどの文字寸法は判型から `--type-scale` で導出）。

レイアウトは**判型相対**です。`themes/base/tokens.css` のトークンは3系統に分かれます。

| 系統 | 例 | 方針 |
|---|---|---|
| PHYSICAL（物理固定） | 塗り足し、罫線の太さ、最小文字サイズ `--min-text`(7pt)、セーフ `--safe` | どの判型でも同じ実寸 |
| PAGE-RELATIVE（ページ相対） | `--margin-*` `--gutter` `--content-w/h` `--opener-hero-h` `--inline-img-h` … | ページ寸法の比率。**component CSS に mm の直値は書けません**（テストが拒否） |
| TYPOGRAPHY-DERIVED（文字由来） | `--fs-*` `--baseline` `--space-*` | `--type-scale`（A5=1.00, B5≈1.11）で拡縮。1行の字数・段数・本文容量は**実測**から導出（コードに定数を持たない） |

- **この号だけ色を変える**: `issue.yaml`
```yaml
theme_overrides:
  --color-accent: "#2f6f5e"
  --font-body: '"Noto Sans CJK JP", sans-serif'
```
- **もっと変える**: `issues/<id>/theme.css` を作り、CSSカスタムプロパティを上書き。component のルール自体を上書きするには詳細度が必要（`layouts.css` が後から読まれます）。`@import` や外部 `url()` は使えません（validate エラー）。
- **他の号でも使う**: `themes/<名前>/` に `*.css` を置き、`issue.yaml` の `theme: <名前>`。
- `themes/base` は直接変えない（全号に影響）。

本文量は**組版前に実際のブラウザで枠を測って**配分します（余白や本文サイズを変えても自動で追従）。変更後は `render` の `text_occupancy` と `preflight P19` で確認してください。

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
1. `output/<id>/review-pack/blind/`（ページPNG・contact sheet・数値のみ）→ **Blind Review** → `<issue>/reviews/critic-blind.md`
2. `review-pack/context/`（編集意図・台割・fingerprint・rhythm・preflight）→ **Context Review** → `critic-context.md`
3. 重大度 `BLOCKER/HIGH/MEDIUM/LOW/NOTE` で優先順位 → 修正 → `publication:all` 再実行
4. **Re-review** → `critic-rereview.md`（全指摘に `fixed/open/regressed/wontfix`）

指摘は **問題 → 根拠 → ページ → 重大度 → 修正案** の形式。`--check` はスコア（10項目）・ID一意・必須項目・ページ範囲・disposition漏れを検証します。

**レビューは監査記録であり、ビルド成果物ではありません。**
- レビューファイルは**雛形から一度だけ**作られ、パイプラインは二度と書き換えません（生成された数値・時刻は `output/<id>/` 側にだけ出ます）。
- `critic --reset` は、いずれかのレビューに作業（status/指摘/スコア/reviewer）が入っていると**拒否**します。続けるには `--force`。`--force` は上書き前に `reviews/archive/<日時>/` へ**全ファイルを退避**します。
- レビューは見た成果物に**結び付き**ます。`review-pack/PACK.json` の `source_hash` を front matter に写してください。ソースが変わるとそのレビューは **STALE**（以前の版の記録）になり、preflight P27 は `MANUAL CHECK`（再レビュー要）になります（古いレビューの未解決指摘が新しい版を FAIL させることも、新しい版を保証することもありません）。

**自動計測と視覚評価は混ぜません。** `rhythm.md` と `fingerprint.json` は次の3種類に分けて出力されます。
- **MEASUREMENT**: 描画から測った事実（本文占有率 `text_occupancy`、内容の到達度 `content_extent`、孤立行、画像比、余白…）。それ自体を良い/悪いに変換しません。
- **HEURISTIC**: 経験則（under-filled、同型layoutの連続、強弱の振れ幅…）。**外れることがあり**、人が判断します。component ごとの密度契約と、台割の `intentional_sparse` 宣言に基づきます。
- **REVIEW_REQUIRED**: 機械では判断不能（余白の美しさ、意図された沈黙、編集的リズム、視覚的緊張…）。Critic の仕事です。
- **Publication Fingerprint**（19軸）は MEASUREMENT / HEURISTIC / REVIEW_REQUIRED に分類。単独号では意味のない軸（E5, I2）は注記付きです。意図は `editorial.yaml` の `fingerprint_target`（**Fingerprint Control**）、実物から現れた癖は `## Emergent fingerprint` に記録。

## preflight

```bash
npm run publication:preflight -- <id>
```
**これは入稿適合の保証書ではありません。** 各項目は種類が明示されます。

| 種類 | 意味 |
|---|---|
| **AUTOMATED CHECK** | スクリプトが決定的に測った（ページ数・サイズ・塗り足し・欠落・あふれ・ノンブル・画像解像度…） |
| **HEURISTIC** | 経験則。誤検知・見逃しがあり得る（未充填頁、孤立行、原稿量） |
| **MANUAL CHECK** | **確認していない**。「OK」と読まないこと（PDF/X・CMYK・ICC・オーバープリント・トラッピング・インキ総量・Type 3 の受理・印刷会社固有仕様・Critic/Proofreader の未実施） |

結果は `PASS` / `WARNING` / `FAIL` / `MANUAL CHECK`。総合判定は `FAIL` > `WARNING` > `MANUAL CHECK REQUIRED` > `AUTOMATED CHECKS PASSED` で、「印刷可能」「ready」という表現は使いません。FAIL があると終了コード1。結果は `output/<id>/preflight.md|json`。

検査項目: 公開境界（P00）、総ページ数、PDFが最新か、仕上がりサイズ（TrimBox）、塗り足し（BleedBox）、トンボ、白ページ、欠落素材、画像破損、キャプション欠落、本文あふれ/はみ出し、**目次の項目欠落**、ノンブルの欠落・重複・誤り、未配置記事、未知layout、フォント埋め込み/不足、画像の有効ppi、RGB/CMYK、セーフエリア、断ち落とし画像の塗り足し、孤立行・未充填頁（HEURISTIC）、Critic/Proofreader の状況。

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
  boundary.json           公開境界の分類定義（例示号の許可リスト）
  workspace/issues/<id>/  **実制作号（Git管理外）** — publication:new の既定の作成先
  issues/_template/       新規号の雛形
  issues/test-issue-01|02 例示号（A5/16p、B5/24p。commit 可）
    expected-warnings.yaml  残る WARNING とその理由（テストが照合）
  issues/<id>/reviews/    critic-*.md, proofread.md（監査記録。パイプラインは書き換えない）
  themes/base/            tokens / typography / page / grid / components .css
  layouts/<family>/       index.mjs（契約+描画）+ style.css
  layouts/_contracts.mjs  component ごとの密度契約（sparse_allowed / 占有率の期待範囲 / 容量）
  schemas/                issue / editorial / flatplan / article / critic-report の JSON Schema
  scripts/                CLI（new-issue validate build preview render-pages critic-pack preflight all）
  scripts/lib/            load / validate-model / compose / layout-probe / web / build / metrics / render / analysis / density / critic / preflight / boundary / tone
  tests/                  node:test（npm run publication:test）
  output/<id>/            生成物（Git管理外）
  docs/BUILD_LOG.md       実装ログ
```

テスト: `npm run publication:test`（スキーマ・台割・公開境界・画像パス・原稿の無害化・判型相対（A5/B5）・測定値・本文配分・密度契約・各 preflight 検査の故障注入・critic 保護・例示号2冊）。`npm run publication:mutation` は実装を1か所ずつ壊して**テストが落ちるか**を確認します（落ちなければ未テストの挙動）。

## current limitations（RC2 candidate）

- **商用印刷は未保証**: PDFはRGB（Chromium出力）、フォントは Type 3。CMYK変換・ICC/出力インテント・**PDF/X適合・オーバープリント・トラッピング・インキ総量・黒の構成・面付け/クリープは未対応/未検査**で、すべて `MANUAL CHECK` です。全頁の紙色ベタ（`--color-paper`）も印刷では版が乗ります（意図を確認）。校正刷り以上の用途では印刷会社の仕様と必ず突き合わせてください。
- **トンボ**: `--marks` で付くが、トンボ自体の内容は検査していない。
- **縦書き・ルビ・細かな禁則調整は未対応**（横組み。`line-break: strict`、`word-break: auto-phrase`、`text-wrap: pretty` に依存。Chromium 系エンジン前提）。
- **判型**: A5 と B5 で検証済み。他の判型は `--type-scale` と比率トークンで追従する設計だが、A4 等は未検証。コンポーネントの構図は判型を問わず同じ比率（例: ヒーローは頁高の53%）。
- **本文の流し込み**は、組版前の実測（枠の寸法・段数・行送り）に基づく行数モデル（`LINE_EFFICIENCY=0.96` の較正を含む）。最終判定はDOM計測（P19）。Vivliostyleの自動ページ送りではなく、台割で固定した1ページ=1枠。ページをまたぐ脚注・図版回り込みは無い。
- **目次**は自動分割しない。収まらなければ `CONTENTS_OVERFLOW` で止まる（項目を減らす/コンパクトな variant）。
- **品質指標は仮説**: HEURISTIC は外れる。REVIEW_REQUIRED は人が見る。MEASUREMENT も「良い/悪い」を意味しない。
- 見開きの写真は、ノド（中央）の画像は両ページで連続するが、ノドでの喰い込み補正はしない。写真エッセイの変化（構図の同質性）は検査しない。
- 衝突検出（文字と写真・文字同士の接触）は未実装。Critic の目視に依存する。
- 画像の自動トリミング・色補正・写真の内容理解は行わない（`focal` は人が指定）。画像の「色調」は柱・ノンブルの色決定にだけ使う。
- Critic の批評そのものは agent（LLM）が書く。スクリプトは pack 生成・構造検証・機械的な計測まで。**独立性は仕組みでは強制できない**（blind の「見ない」は規律）。
- ツールチェーン（Vivliostyle/Chromium/フォント）のバージョンは固定・記録していない。`scripts/lib` の変更は「PDFが古い」判定の対象外。
- 過去号との類似度分析、自動修正ループ、EPUB、Web版、GUI/CMSは対象外。

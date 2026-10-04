# Publishing Studio v0.1 — RC1 独立レビュー

**判定: REVISE**（実際の雑誌・ZINE制作へ投入するのは、P0/P1 を解消するまで不可）

- 対象: ブランチ `claude/bold-shannon-746w8g` @ `42b7d5b203b40924a659f7dff8c55a6037caf3e0`（PR 未作成）
- 方針: 実装コードは**変更していない**。追加したのは `publishing-studio/reviews/**`（本書・証跡・QAツール）、`issues/test-issue-01/reviews/critic-{blind,context}.md`（実レビュー）、`issues/test-issue-02/**`（サンプルデータ）のみ。破壊的な実験はすべてサンドボックス（`/tmp/.../sbx` に複製）で実施。
- **独立性の限界（重要）**: レビュアーは本システムの実装者と同一モデル・同一セッションで、実装の記憶がある。Blind Review は「見えるものだけを書く」規律による**擬似的な盲検**であり、真の独立レビューではない。出荷判定に使う場合は、別コンテキストの publication-critic で blind/context を再実施すること（P1-9）。
- 証跡: `publishing-studio/reviews/evidence/`（再現ツールは `reviews/tools/`）

---

## Phase A — Freeze

| 項目 | 記録 |
|---|---|
| HEAD | `42b7d5b203b40924a659f7dff8c55a6037caf3e0`（"Fix component count in build log"）。作業ツリーは clean（レビュー開始時）。`origin/main` 比 126 files / +14,977 行（全て追加） |
| Node / npm | v22.22.0 / 10.9.4 |
| 依存 | `package-lock.json` あり（git 管理、`package.json` は `^` 範囲指定）。Vivliostyle CLI 11.3.3 / playwright-core 1.63.0 / sharp 0.35.5。`npm audit --omit=dev`: 0 vulnerabilities。**Chromium は `/opt/pw-browsers/chromium-1194` を自動検出して使用**（Vivliostyle は Chrome 141 / Vivliostyle.js 2.45.1 を使用）→ ツールチェーンのバージョンは lock されない（P2） |
| README / BUILD_LOG | 存在（README は日本語、BUILD_LOG に各 Phase の記録） |
| npm scripts | `publication:new/validate/build/preview/render/critic/preflight/all/test` の9本 |
| 依頼文の `npm run publication`（3行とも同一） | スクリプト名が欠落していたため **`publication:all -- test-issue-01` / `publication:test` / `publication:preflight -- test-issue-01` と解釈**して実行 |
| `publication:all -- test-issue-01` | exit 0。preflight **WARNING**（PASS 18 / WARNING 3 / FAIL 0 / MANUAL CHECK 4）。`evidence/A-run-all.txt` |
| `publication:test` | **25/25 pass**（約25秒）。`evidence/A-run-test.txt` |
| `publication:preflight -- test-issue-01` | exit 0、WARNING（同上）。`evidence/A-run-preflight.txt` |
| RC1 基準成果物 | PDF 1 + ページPNG 16 + contact sheet 3 の sha256 を `evidence/A-rc1-sha256.txt` に記録（PDF `9978a190…c7e`）。実体は `/tmp/.../scratchpad/rc1`（Gitに入れない） |
| **副作用の発見** | `publication:all` を実行すると、**git 管理下の** `issues/test-issue-01/reviews/critic-*.md`（AUTO ブロックのタイムスタンプ）と `auto-findings.snapshot.json` が書き換わり、作業ツリーが dirty になる（P1-7） |

Reproducibility（`evidence/D-stale-repro.json`）: 同一ソースで 2 回 build → **PDF バイナリは不一致（sha 先頭 12桁 `c502fed5…` vs `4451bf8a…`）だが、差は PDF メタデータの `CreationDate`/`ModDate`（Skia/PDF）のみ**。`pdftotext` の全文は同一、全16ページの PNG（sha256）も同一。→ レイアウトは決定的。バイナリ比較で再現性を検証するとき（CI等）はメタデータ除外が必要（P3）。

---

## Phase B — Blind Review（`issues/test-issue-01/reviews/critic-blind.md`）

15 件（BLOCKER 0 / HIGH 2 / MEDIUM 6 / LOW 4 / NOTE 2）。上位:

- **F-001 HIGH**: p2,3,7,9,14,15 の下半分が空いた「未完成に見える」ページが反復（内容下端が頁高の 48%/52%/38% で終了）
- **F-002 HIGH**: p8 人物写真の端に隣接テキストが接触、キャプションも写真角に接触
- F-003 孤立行（p7「る。」p9「す。」「か。」p13「に。」）/ F-004 引用の語中改行（「だ／け」）/ F-005 画像上の柱・ノンブルのコントラスト不足 / F-006 約19字の狭い段の均等割付 / F-007,008 写真エッセイ（同一構図・p10 に宙に浮いた白帯）/ F-009 号固有の視覚語彙が弱い

`critic --check` で構造検証を通過（BLOCKER/HIGH が open と表示される）。

## Phase C — Context Review（`critic-context.md`）

10 件（HIGH 1 / MEDIUM 5 / LOW 2 / NOTE 2）。要点:

- **Editorial Intent**: mood の「木の床・手書きの看板・手仕事」が未表現。density: medium は未達（25〜995字/頁）。audience（30〜60代）に対し 6.5pt の小字が多い
- **Flatplan Fidelity**: 計画強度と実測は概ね整合（ツールの中核機能は有効）。ただし**台割自体**が前後を静かに設計しており尻すぼみ
- **Design System**: 一貫性は保たれているが、本文ページの構造が単調（全幅1枠+上部1要素）
- **Fingerprint 19軸の突合**: 数値が良好でも欠点が残る 3 型 —①未充填ページが「静かなページ」として加点 ②画像上の可読性を測らない ③和文組版欠陥（孤立行・折返し）を測らない。**D1 body_pt は実体と乖離**（max 20pt / mean 8.7pt。実際の本文は 8.5pt 一定）。E5・I2 は 1 号では弁別力なし
- **fit_fill 検証（実画像で別計測: `evidence/C-content-bottom.json`）**

| p | fit_fill | 内容の下端 | 35% 閾値で警告 |
|--:|--:|--:|:-:|
| 3 | null（計測外） | 48% | なし |
| 7 | 0.48 | 68% | なし |
| 9 | 0.47 | 52% | なし |
| 14 | 0.34 | 38% | **あり** |

単一閾値 0.35 は ①p9 を見逃し p14 だけ警告（偶然の僅差）②記事の最終ページ（部分充填が自然）と中間ページを区別できない ③写真・引用ページは `.fit` が無く null で**誤警告はない**（これは良い）が、本文を持つ頁が `.fit` を使わなければ永久に未計測。component 別/記事位置別の期待範囲が**必要**。

---

## Phase D — System QA

### D1. Publication Model / Source of Truth
- `issue.yaml` → `css/page-setup.css`（`@page` と `--page-w/--page-h/--bleed`）は単一ソースで OK（`tokens.css` にも既定値があるが後から上書きされる）。
- **二重管理（確認済み）**: 余白・本文サイズ・行送りが ①`themes/base/tokens.css` ②`layouts/_shared.mjs` の `liveBox`（16/18/17/13mm）と `frameChars`（8.5pt/5.5mm）③`metrics.mjs`（safe 5mm 固定）に分散。テーマで本文を 12pt（adv-14）や余白を大幅変更（adv-15）しても容量見積りは追従せず、`validate` は無警告、post-render の P19 でしか分からない。
- **layouts の固定値**: `layouts/*/style.css` に **mm 直値が 41 か所**（例: ヒーロー 112mm、行 90mm、写真 104mm）。トークン化されていない。
- **スキーマを通る意味的な誤り（確認済み）**: 記事 `type` と `layout` の不整合（essay を interview-body に置いても通る、adv-23）。`status: draft` は読まれておらず draft 記事もビルドに入る（`grep draft` → コード上の参照なし）。`slots` のキー typo は無視される（コード読み）。
- ファイル名: 画像ファイル名は URL エンコードされず `src="images/<raw>"`（adv-21）。

### D2. Components（37 variant）
- `evidence/D-component-stress.txt`: 15 component × 37 variant × 7 シナリオ（必須入力のみ／任意なし・キャプションなし／200字超の文字列／本文60段落／本文なし／目次100件／HTML文字列）= **259 レンダリングで throw・`undefined`・`NaN`・未エスケープなし**。→ 静的な耐性は良好。
- ただしこれは **HTML 生成の静的検査**。見た目の破綻（あふれ・衝突）は DOM 計測側に依存し、そこは下記の欠陥あり。
- **contents**: 項目数の上限・分割・縮小戦略がない（Phase E で実証、8件で切れる）。
- **写真なし/キャプションなし**: `required()` で明確に error、キャプションは validate=warning / preflight=FAIL で一貫。

### D3. CSS / specificity（実験: `evidence/D-css-order.txt`）
`!important` はテーマ/レイアウト CSS に**0件**、ID セレクタ**0件**（良い）。ただし:
- **cascade 順序の逆転（実証）**: `compose.mjs` は `theme.css` → `layouts.css` の順に読み込む。issue の `theme.css` に `.cv-title { font-size: 20pt }` を書くと **component 側 56pt が勝つ**（74.67px のまま）。`!important` を付けないと上書きできない。README の「`issues/<id>/theme.css` で上書き」はカスタムプロパティ以外では実質効かない。
- **属性セレクタの高詳細度（実証）**: ベースの `.page[data-side="right"] .folio {right: …}`（0,3,0）に対し、issue theme の `.folio { right: 40mm }` は**無視された**（13mm のまま）。
- 今回の `.page h1` 事故は `:where()` で修正済みだが、同種の構造（`.page[...] .x`, `.body p:first-child` 等）は他にも残り、**回帰テストは存在**（m5: `:where` を戻すとパイプラインテストが落ちる）ものの、原因はテストが偶然 h1 サイズ依存の出力差を拾うため。CSS 構造の恒久対策（`@layer` 等）は未実施。
- `.fit` クラス: 本文あふれ検出が `.fit` 付与に依存（付け忘れると検出対象外）。

### D4. Overflow の区別
| 種別 | 検出 | 備考 |
|---|---|---|
| DOM overflow（`.fit` の scroll>client） | ○ metrics `overflow` | m1: **無効化してもテストが通る**（`text-outside-trim` が代替検出するため、この経路は個別にテストされていない） |
| text clipping（頁外へはみ出したテキスト矩形） | ○ `text-outside-trim` | 1要素でも矩形ごとに重複メッセージ（スパム、P2） |
| PDF 上の visual clipping | **×** | PDF側の実測なし。DOM は screen メディア、PDF は print メディアで、両者の一致は**ページ数以外で未検証** |
| Vivliostyle fragmentation（想定外の改ページ） | △ | **ページ数不一致（P09）でのみ**検出（adv-22 で 1 page） |
| 意図的トリミング（object-fit: cover） | **×** | 意図/事故の区別がなく、極端アスペクト（adv-06/07）は ppi 低下以外で検出されない |
| テキスト同士・文字と画像の衝突/接触 | **×** | blind F-002（p8）は**どの自動検査も検出しない** |

### D5. Staleness（実験: `evidence/D-stale-repro.json`）
| 変更 | P10 |
|---|---|
| 記事本文 / front matter / キャプション / credits / editorial / issue.yaml（title, bleed） / flatplan（variant） / images.yaml / theme_overrides / 画像バイト / themes/base CSS / layouts の CSS・JS | **FAIL（検出）** |
| flatplan の notes のみ | FAIL（過検出。出力は不変、P3） |
| notes/（想定どおり対象外） | PASS |
| **`scripts/lib/*.mjs`（build・計測ロジック）** | **PASS（未検出）** |
| ツールチェーン（Vivliostyle/Chromium/フォント）のバージョン | 未検出（ハッシュ対象外、コード読み） |
| article 変更→build のみ（render 未実行） | P10 PASS / **P16「render is current」FAIL（検出）** |

→ 「ソースの変更」の検出は良好。「ビルド手段の変更」は未検出（P2）。

### D6. Reproducibility
上記 Phase A のとおり（レイアウトは同一、バイナリ差はメタデータのみ）。

### D7. テストの検出力（ミューテーション, `evidence/D-mutation-*.json`）
14 件のバグ注入（実装を壊す）で**テストが落ちたか**:

| # | 注入したバグ | 結果 |
|---|---|---|
| m1 | `.fit` overflow 検出を無効化 | **SURVIVED** |
| m2 | 見開き偶数始まりチェック削除 | killed |
| m3 | ソースハッシュを定数化（陳腐化検出） | killed |
| m4 | Q&A 孤立防止ロジック削除 | killed |
| m5 | `:where` 修正を戻す | killed |
| m6 | PDF ページ数チェックを常に PASS | **SURVIVED** |
| m7 | rereview disposition 検証削除 | killed |
| m8 | 欠落キャプション FAIL→WARNING | **SURVIVED** |
| m9 | ノンブル欠落/重複を無視 | **SURVIVED** |
| m10 | 白ページ検査を無効化 | **SURVIVED** |
| m11 | セーフエリア検査を無効化 | **SURVIVED** |
| m12 | 画像 ppi 検査を無効化 | **SURVIVED** |
| m13 | 塗り足し(BleedBox)検査を無効化 | **SURVIVED** |
| m14 | blind pack に台割を漏洩 | killed |

→ **14 件中 8 件が生存**。README が「preflight で検出する」と謳う 7 項目（ページ数不一致・キャプション欠落 FAIL・ノンブル・白ページ・セーフエリア・解像度・塗り足し）の**回帰テストがない**。今回の敵対的実験で動作は確認できたが（下記）、テストが保証していない。

### D8. その他の実装リスク
- `critic --reset` は **完了済みレビュー（critic-*.md）を確認なしで雛形に上書き**し、バックアップもない（README 未記載、usage にのみ表示）。
- Markdown 本文の生 HTML が素通し（`marked.parseInline`）。Chromium は `--no-sandbox` で起動（`browser.mjs`）。
- `blind pack` の contact sheet ラベルに layout/variant 名（実装情報）が入る。blind の「見るな」は Read 権限のある agent には強制力がない（ポリシーのみ）。
- 重複メッセージ: 欠落キャプション/画像が同一画像で 3 重に出る（`imageRefs` が hero/image/images を重複列挙）。

---

## Phase E — TEST ISSUE 02（B5 / 24p / 中綴じ / 写真主導）

構成: cover/split・contents/large・column×3(plain/box/plain)・full-bleed-photo（spread, single）・divider（ink, accent）・quote-page×3（center, left-rule, color-block）・photo-essay×3（wide-single, sequence-4, grid-3）・profile×2（card, wide）・interview-opener/big-quote（極短2問答）・colophon/with-credits・cover/back。**新規 layout/component は追加していない**（サンプルデータのみ）。`theme_overrides` で色を変更。生成: `reviews/tools/make-issue02.mjs`。

| 項目 | 結果 |
|---|---|
| validate | ○（初回、私の台割ミス＝奥付の未配置を `ARTICLE_NOT_PLACED` が**正しく検出**→修正） |
| flatplan / 24p / B5 / 見開き偶数始まり | ○ |
| build / PDF 24ページ / TrimBox 182×257 | ○（P09, P11, P12 PASS） |
| render / contact sheet / critic pack / rhythm / fingerprint | ○ 生成 |
| preflight | **FAIL 1**（P19: p2 目次のはみ出し）、WARNING 4、MANUAL CHECK 4 |
| fit_fill | 計測できたのは **24頁中 p20 の 1 頁のみ**（短文頁は `fit-auto`/`.fit` なしで null）。全体で `TEXT_PAGE_SPARSE` が **6 件**（p3,10,14,17,20,22）。短文・写真主導の号では**意図的な短さが全て警告になる**ノイズで、抑制手段がない |
| rhythm | intensity 11〜79、写真連続最大2、同型連続1。メトリクスは問題なく計算される |

**SYSTEM GAP（本当に不足している機能）**
1. **SG-1 レイアウトが判型相対でない**: B5 でも破綻はしないが、A5 前提の mm 固定値（ヒーロー高さ 112mm 等）と本文 8.5pt のままのため、**p3/p8-9/p10/p14/p17/p20/p22 が60〜95%空白**に見える（`pages/` 参照）。写真が本来比率で拡張されず、プロファイルの肖像が小さい。「B5 対応」とは言えない。
2. **SG-2 contents に容量契約・改頁・縮小戦略がない**: 12 項目で 8 件目で切れ、**項目（18, 20 頁）が PDF から消える**（`pdftotext` で確認: 17 まで）。preflight は FAIL にしたが、メッセージは `text-outside-trim` の連呼で原因が分かりにくい。
3. **SG-3 意図の宣言手段がない**: 短文/余白を意図した頁を `intentional_*` 等で宣言して警告を止められない（blank のみ `intentional_blank`）。
4. SG-4（軽微）: photo-essay に 2 枚用の variant がない（1/3/4 枚のみ）。

---

## Phase F — Adversarial Tests（`evidence/F-adversarial-*.json`）

| # | ケース | 期待 | 実際 | 判定 |
|--:|---|---|---|---|
| 1 | 非常に長い見出し | レイアウト保持、または検出 | validate 無警告。preflight **FAIL P19**（p4, p8 で頁外/枠外）、P21 WARNING。メッセージが矩形ごとに重複 | PASS（検出は事後のみ） |
| 2 | 非常に短い本文 | 警告、build可 | `TEXT_PAGE_EMPTY/SPARSE`。p6 充填1%。空頁 p14 を preflight **FAIL P17** | PASS |
| 3 | 非常に長い本文 | あふれ検出 | validate `TEXT_MAY_OVERFLOW`（531%）。preflight **FAIL P19** | PASS |
| 4 | 画像なし | 明確な error | `MISSING_INPUT`（cover/full, feature-opener）。all は停止 | PASS |
| 5 | 存在しない画像 | error | `MISSING_ASSET` ×4 | PASS（重複メッセージ） |
| 6 | 極端な縦長画像 (300×6000) | 検出 | builds。**FAIL P22**（65ppi）。ppi が低いため検出されただけで、**高解像度の極端比率は検出されない**（アスペクト/トリミング率のチェックなし。コード読み） | PARTIAL |
| 7 | 極端な横長画像 (6000×200) | 同上 | **FAIL P22**（36ppi）。同上 | PARTIAL |
| 8 | キャプションなし | validate warn / preflight FAIL | 同じ画像で 3 重の warning。preflight **FAIL P05** | PASS（ノイズ） |
| 9 | 長いキャプション | あふれ検出 | preflight **FAIL P19**（p5, p10） | PASS |
| 10 | 記事の未配置 | error・停止 | `ARTICLE_NOT_PLACED`+`TEXT_NOT_PLACED`+`FLATPLAN_GAP`。all 停止 | PASS |
| 11 | ページの重複 | error | `FLATPLAN_OVERLAP` + `FLATPLAN_GAP` | PASS |
| 12 | 見開き開始位置異常 | error | `SPREAD_PARITY`（+OVERLAP/GAP） | PASS |
| 13 | ページ数不一致 | error | 20p→`FLATPLAN_GAP`、12p→`FLATPLAN_RANGE`。all 停止 | PASS |
| 14 | テーマで本文12pt | 検出 | validate **無警告**（容量見積りが追従しない）。preflight **FAIL P19**（p6）、P21 WARNING | PARTIAL（事後検出のみ） |
| 15 | テーマで余白を極端に（inner30/outer4/top8/bottom8mm） | 検出 | **exit 0、verdict WARNING**。`P21 safe area` が 10頁で WARNING のみ。トリムから4mmの本文でも FAIL にならない。綴じ側 30mm の妥当性チェックなし | PARTIAL |
| 16 | article変更後に build しない | stale 検出 | **FAIL P10** | PASS |
| 17 | image変更後に build しない | 同 | **FAIL P10**（画像バイト変更） | PASS |
| 18 | CSS変更後に build しない | 同 | themes/layouts/issue theme は **FAIL P10**。`scripts/lib` の変更は**未検出** | PARTIAL |
| 19 | flatplan変更後に build しない | 同 | **FAIL P10**（notes のみの変更も FAIL=過検出） | PASS |
| 20 | 空白ページ | blank 検出 | **FAIL P17**（DOM+ピクセル） | PASS |
| 21 | 日本語/空白/`#` を含む画像ファイル名（追加） | 動作 | **画像が壊れる**（`FAIL P18 broken images`）。URL エンコード欠如。validate は無警告 | **DEFECT** |
| 22 | 原稿に生 HTML `<style>`/`<script>`/`<img onerror>`（追加） | 無害化 | `<style>` で**全頁が非表示→PDF 1ページ**（P09 FAIL で発覚）。`<script>` はビルド/render 時にヘッドレス Chromium（`--no-sandbox`）で**実行される**。無害化なし | **DEFECT** |
| 23 | 記事typeとlayoutの不整合（追加） | 検出 | exit 0（検出なし） | GAP |
| 24 | 記事ID重複（追加） | error | `ARTICLE_DUPLICATE` | PASS |

「既存テストが本当に検出するか」は Phase D7 のミューテーション結果のとおり（実装の検出は上表で実証できたが、テストによる保証は不足）。

---

## Phase G — Print Risk Review（分類のみ）

| 要素 | DEVELOPMENT | PROOF（校正刷り・社内/デジタル） | COMMERCIAL PRINT |
|---|---|---|---|
| RGB のみ（CMYK 変換なし） | 低（問題なし） | 低〜中（色が印刷機・色空間で変わる旨を明記） | **高**: 変換は印刷所/後工程任せ。自動 PASS 禁止（現状 WARNING+MANUAL）。**黒の本文が RGB 近似黒（#1d1c1a）の場合、単純変換で4色ベタ化→小さな文字の見当ズレ** |
| Chromium(Skia) PDF | 問題なし | 低 | 中: PDF/X 非対応生成系。出力インテント/ICC なし |
| Type 3 フォント | 問題なし | 低〜中（印刷/表示でヒンティングなし） | **高**: 一部の RIP/preflight（PitStop 等）が Type 3 を拒否・ラスタライズし得る。自動 PASS 禁止（現状 WARNING） |
| CMYK 未対応 | 問題なし | 低 | **高**（RGB と同根） |
| PDF/X 未保証 | 問題なし | 問題なし | **高**: 入稿規格に「PDF/X-1a/X-4」を要求する印刷所では受理されない可能性。自動 PASS 禁止（現状 MANUAL CHECK） |
| 全頁の地色（#fbfaf6 ベタ） | 問題なし | 低 | **中〜高**: 全頁に薄いベタ版が乗り、インキ総量・版ズレ・コスト増。意図しない紙色の印刷。未検査（preflight に項目なし） |
| グラデーション/不透明度（表紙シェード等） | 問題なし | 低 | 中: 透明の統合が必要な規格では問題。未検査 |
| 総インキ量 (TAC)・オーバープリント・トラッピング | 該当なし | 低 | 中: **未検査（項目が存在しない=報告もされない）**。MANUAL CHECK として明示すべき |
| 塗り足し/断ち落とし（BleedBox 幾何） | 問題なし | 問題なし | 低〜中: ボックスは PASS 検査（ただしテストなし: m13 生存）。内容側の塗り足し（画像が3mm越えているか）は P23 が DOM で確認 |
| トンボ | 問題なし | 問題なし | 中: `--marks` で生成、**内容は未検査**（MANUAL CHECK）。印刷所指定のトンボ形式との整合は人が確認 |
| 中綴じのクリープ/面付け | 該当なし | 低 | 中: **未対応・未検査**（ノド側の余白 17mm、24p B5 では中央見開きの内側寄せ量を印刷所が確認） |
| 画像の有効解像度 | 問題なし | 問題なし | 中: P22 は DOM 由来（≥200ppi で PASS）。**極端トリミング後の実効解像度・拡大率は人が確認**。この検査もテストなし（m12 生存） |
| フォントライセンス | 問題なし | 問題なし | 低: Noto は OFL で埋め込み可。他フォント使用時は要確認 |

**COMMERCIAL PRINT で「自動 PASS にしてはいけない」もの**: RGB→CMYK／PDF/X 適合／Type 3 フォント受理／出力インテント・ICC／総インキ量・黒の構成／全頁ベタ地色の意図確認／透明の統合／トンボの内容／クリープ・面付け／画像の実効解像度（極端トリミング時）／**総合判定そのもの**（現状 WARNING でも「入稿してよい」の意味にならないことを UI/README で明示）。未実装・未検査のものは「項目が存在しない」状態で、レポートからは**「確認済み」に見えてしまう**ため、MANUAL CHECK として明示列挙すべき。

---

## Phase H — Security / Publishing Boundary

事実: リポジトリは `.nojekyll` + ルート `index.html` の **GitHub Pages 静的サイト**。main に載ったファイルは**ビルド対象外のものも含め URL で公開され得る**（`publishing-studio/issues/**`、`package.json`、`.claude/**` 含む）。※Pages が実際に有効かはリポジトリ設定で要確認。現行 `.gitignore` は `node_modules/` と `publishing-studio/output/*` のみ。

| 分類 | 対象 | Git へ commit してよいか |
|---|---|---|
| **source** | `scripts/ layouts/ themes/ schemas/ tests/ docs/ README`、`.claude/agents|skills` | ○（フレームワークコード。公開可） |
| **source（号の原稿）** | `issues/<id>/{issue,editorial,flatplan,credits}.yaml`・`articles/`・`captions/`・`images/`・`theme.css` | **△ 公開済み/公開許可済みの号のみ。未公開号は ×** |
| **private** | 未公開の原稿・写真（肖像・個人情報・権利未処理）、`notes/`（編集メモ・連絡先）、`credits.yaml` の連絡先（colophon.contact）、`reviews/`（批評・校正の内部記録） | **× Pages 配信リポジトリには置かない**（別の非公開リポジトリ/サブモジュール/暗号化） |
| **temporary** | `output/<id>/web`, `review-pack/`, `contact/`, `pages/`, `*.tmp` | ×（`.gitignore` 済み ○） |
| **generated** | PDF・PNG・`rhythm.*`・`fingerprint.json`・`preflight.*`・`metrics.json`・`critic-report.json` | ×（`output/*` は ignore 済み ○）。ただし **`reviews/critic-*.md` の AUTO ブロックと `auto-findings.snapshot.json` は生成内容を含む tracked ファイル**（dirty 化の原因） |
| **publishable** | サンプル号（`test-issue-*`、架空・SVG生成画像）、フレームワーク一式、完成・公開許可済みの号の PDF（`output/` から手動で `docs/` 等へ） | ○（意図的に公開するもののみ） |

リスク:
1. **誤公開（最大）**: 実運用の号を `publishing-studio/issues/<id>/` に置いて commit/push/merge すると、Pages 経由で**未公開原稿・画像が公開**され得る。ガードがない（`issues/*` が ignore されていない、README に境界の記述がない）。公開後の削除でもキャッシュ/検索に残る。
2. 原稿由来のコード実行: 生 HTML 素通し + `--no-sandbox`（Phase F #22）。外部寄稿者の原稿を取り込む運用では重大。
3. `reviews/` や `notes/` に連絡先・内部評価が入りやすい。
4. 運用方針の修正案（**このセッションでは未変更**）: ①`.gitignore` に `publishing-studio/issues/*` を追加し `!publishing-studio/issues/_template`, `!publishing-studio/issues/test-issue-*` で例外化 ②実号は別の非公開リポジトリ（またはサブモジュール/`PS_ISSUES_DIR` を repo 外へ）③README に「何を commit してよいか」の表を追記 ④pre-commit/CI で `issues/` 内の非サンプルを検出して失敗 ⑤Pages の公開対象を `docs/` など専用ディレクトリに限定。

---

## Phase I — 判定

### 判定: **REVISE**

パイプライン（validate→build→PDF→全頁画像→批評pack→preflight）は決定的で、異常系の大半を正しく検出し、不明点を MANUAL CHECK として正直に残す設計は良い。一方、**実運用の判型・日本語ファイル名・原稿由来の入力・公開境界・品質ゲートの信頼性**に、そのまま実号を投入できない欠陥がある。構造自体（Publication Model、component 契約、レビュー書式）は修正可能で、作り直し（REJECT）は不要。

### 評価軸

| # | 軸 | 判定 | 根拠 |
|--:|---|:-:|---|
| 1 | Architecture | **CONDITIONAL** | 責務分離・契約・決定性は良い。cascade 順序の逆転、容量式/余白/本文サイズの二重管理、mm 直値 41 か所 |
| 2 | Reliability | **CONDITIONAL** | 24 敵対ケースのうち 18 が期待どおり、検出は概ね堅牢。日本語ファイル名・生HTMLが欠陥、極端比率/余白/テーマ変更は事後検出のみ |
| 3 | Generalization | **FAIL** | B5/24p は build できるが、A5 固定レイアウトで 60〜95% 空白の頁が多発。contents が容量超過で項目欠落 |
| 4 | Editorial usability | **CONDITIONAL** | validate の日本語メッセージ・新規号テンプレートは良好。日本語ファイル名不可、重複警告、警告抑制手段なし |
| 5 | Visual system | **FAIL** | 現サンプルが自身の Critic で HIGH 2 件。孤立行・引用の語中改行・写真/文字の接触・画像上のノンブル不可読・未充填頁・個性の弱さ |
| 6 | Critic validity | **CONDITIONAL** | 書式と構造検証は有効。盲検は強制不能、Fingerprint/rhythm 指標が未充填を肯定、body_pt 誤計測、blind pack にコンポーネント名が混入。本レビュー自体も疑似盲検 |
| 7 | Preflight reliability | **CONDITIONAL** | 動作は実証できたが、14 注入バグ中 8 件でテストが落ちない。衝突/トリミング/クリープ/インキ量など未検査項目が項目として存在しない |
| 8 | Documentation | **CONDITIONAL** | README は実用的。B5 非対応・`--reset` の破壊性・公開境界・ファイル名制約の記載なし。テストで保証されていない挙動を断定 |
| 9 | Production safety | **FAIL** | 公開境界のガードなし、生 HTML 実行、商用印刷の自動判定不能（MANUAL CHECK が正しく残るのは良い） |

### 修正項目

**P0（誤公開・データ損失・build 不能）** — 1件
- **P0-1 公開境界のガード不在**: 実号の原稿・画像が Pages 配信リポジトリに commit され得る（`issues/*` 未 ignore、運用ルール未記載）。→ `.gitignore`/運用（別リポジトリ・`PS_ISSUES_DIR`）/pre-commit(CI) 検査/README 追記

**P1（v0.1 リリース前に直す）** — 9件
- **P1-1** 画像ファイル名（日本語・空白・`#`）の URL エンコード（または検証での明確な拒否）
- **P1-2** 原稿の生 HTML の無害化（`marked` で html を escape/拒否）。Chromium の `--no-sandbox` を既定から外す/理由を文書化
- **P1-3** レイアウトの判型相対化（mm 直値→ページ寸法/トークン比率）、`liveBox`/`frameChars` を実トークン/実測から導出。B5 で 60% 超の空白頁を出さない
- **P1-4** contents の容量契約・自動縮小/改頁、項目欠落を `validate` 段階で検出
- **P1-5** 品質指標の妥当性: fit_fill を「頁の内容下端」＋ component/記事位置別の期待範囲に、`quiet` を宣言頁に限定、`body_pt` 誤計測の修正、fit-auto 枠も計測
- **P1-6** テスト補強: m1,m6,m8–m13 を殺すテスト（ページ数不一致・欠落キャプション FAIL・ノンブル・白ページ・セーフエリア・ppi・BleedBox）、`@layer`/specificity の回帰、Japanese filename、生HTML、contents 容量
- **P1-7** `critic --reset` の保護（確認/バックアップ）、生成物（AUTO ブロック・snapshot）を tracked review ファイルから分離（`publication:all` で dirty にしない）
- **P1-8** サンプルの組版欠陥: 孤立行（1〜2字+句読点）の検出/調整、見出し・引用の文節折返し、写真と文字のガター、画像上の柱・ノンブルの自動明色化、p10 の白帯
- **P1-9** 独立レビューの再実施: 別コンテキストの publication-critic による blind→context（本レビューは同一モデル・擬似盲検）

**P2（v0.2）**
- `@layer`（base/theme/layout/issue）で cascade を整理、issue theme が component を上書きできるように
- staleness にツールチェーン（Vivliostyle/Chromium/フォント）と `scripts/lib` のハッシュ、notes のみの変更は無視
- 警告の抑制/意図宣言（`intentional_sparse` 等）、重複メッセージ/`text-outside-trim` のスパム解消
- 意味検証の追加: article.type と layout の整合、`status: draft` の扱い（ビルド除外/出荷ゲート）、`slots` キー検証
- テキスト/写真の衝突検出、極端なトリミング率・縦横比の警告、セーフエリア/綴じ余白の FAIL 化とクリープ警告
- DOM（screen）と PDF（print）の整合検査（`pdftotext` の語数と DOM 文字数比較で欠落検出）
- blind pack からコンポーネント名の除去、盲検を強制する仕組み（pack のみの読み取り権限）、reviewer の独立性検証
- 印刷リスク項目（TAC・黒の構成・全頁地色・透明・クリープ）を MANUAL CHECK として preflight に列挙、総合判定の文言整理
- Chromium/Vivliostyle のバージョン固定と記録、`pdffonts` 非存在時の挙動

**P3（将来）**
- RGB→CMYK 変換と PDF/X 出力、面付け/クリープ、縦書き・ルビ・禁則の拡張
- 複数号比較（Fingerprint の E5/I2 を有意に）、過去号との類似度
- 画像の自動トリミング支援、PDF メタデータを除いたバイナリ再現性検証（CI）、flatplan notes のみの変更を stale にしない

### 証跡の索引（`publishing-studio/reviews/evidence/`）
`A-freeze.txt` `A-run-*.txt` `A-rc1-sha256.txt` / `B-critic-blind.snapshot.md` / `C-critic-context.snapshot.md` `C-content-bottom.json` / `D-component-stress.txt` `D-css-order.txt` `D-stale-repro.json` `D-mutation-*.json` / `E-issue02-all.txt` / `F-adversarial-*.json`。ツール: `reviews/tools/{adversarial,stale-repro,mutation,component-stress,css-order,content-bottom,make-issue02}.mjs`（サンドボックス実行用）。

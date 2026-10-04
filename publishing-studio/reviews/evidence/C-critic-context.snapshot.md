---
stage: context
status: complete
reviewer: rc1-qa-reviewer
round: 1
---
# Publication Critic — context review (TEST ISSUE 01, RC1 baseline)

> blind review（`critic-blind.md`, sha256 `0ec75491…62ca`）を保存した**後で**、editorial.yaml / flatplan.yaml / rhythm.md / fingerprint.json を読んで書いた。blind の指摘（F-001〜F-015）は書き換えず、ID を引用して補強する。

## Scores (1–5)

| category | score | note |
|---|:-:|---|
| readability | 3 | 対象読者(30〜60代)に対し 6.5pt の小字が多い |
| hierarchy | 4 | 計画（強度）と実物の階層は概ね一致 |
| visual-rhythm | 3 | 強度の波は計画どおりだが、自動指標が見落とす欠点が残る |
| consistency | 3 | 書体2種・色2色の規律は守られている。モチーフの反復は不完全 |
| originality | 2 | mood の「木の床・手書きの看板・手仕事」が誌面に出ていない |
| editorial-rhythm | 3 | 台割の意図（前後を静かに）は実現。ただし台割自体が尻すぼみ |
| page-balance | 2 | 「読み始めの呼吸」「余韻」の意図が、未完成な空白に見える |
| typography | 2 | blind の指摘（孤立行・引用の折返し）が意図と無関係に残る |
| image-usage | 3 | 見開きオープナーは意図どおり。素材が同質 |
| issue-identity | 2 | fingerprint_target.motif を満たす箇所が散発的 |

## Auto findings (scripts / mechanical — do not edit between markers)

<!-- AUTO:BEGIN -->
(context 段階では rhythm.md と fingerprint.json を一次資料として参照し、その妥当性を下の指摘で検証した)
<!-- AUTO:END -->

## Context checks（指摘ではない記録）

### 1. Editorial Intent Fidelity（editorial.yaml との照合）
| 項目 | 記述 | 誌面での実現 | 判定 |
|---|---|---|---|
| mood | 夕暮れ、潮の匂い、木の床、手書きの看板 | 夕暮れは表紙・p4-5・p10-11 で明確。「木の床」「手書きの看板」「手仕事」は誌面に現れない（素材がイラストで、書体・罫は工業的に整っている） | 部分的 |
| pacing: varied | 強弱の起伏 | 強度 86→14→10→72→60→2→27→35→3→61→56→37→12→4→10→26。中盤は起伏があるが p2-3 / p13-15 が連続して静か | 概ね実現 |
| density: medium | 中程度で均質 | chars/page = 25〜995（stdev 259）。p6 は文字の壁、p3/p9/p14 は空白が目立つ。「中程度」ではなく両極 | 未達 |
| audience: 30〜60代 | 読みやすさ | 本文 8.5pt は許容。キャプション・ノンブル・柱・Q ラベル 6.5pt+灰色は 50〜60代には小さい | 要改善 |
| editorial_voice: 静かで具体的 | 誇張せず | 見出し・色面は控えめで一致。表紙のオレンジの点は装飾的 | 概ね実現 |

### 2. Flatplan Fidelity
- 計画の visual_intensity（1–5）と実測（0–100）の対応: p1(5→86) p4-5(5→72/60) p6(2→2) p9(2→3) p10-11(5→61/56) p13(2→12) p14(1→4) p15(1→10) は整合。**p12(4→37)** と p16(3→26) は乖離（朱の全面色は「強い」と計画されたが、測定上は画像比0・見出しスケール小のため低く出る = 測定側の限界、F-019）。
- 台割の意図（notes）: p3「読み始めの呼吸」、p12「一息つくページ」、p10-11「ページ間の静かな山場」。p12 は計画どおり成立。**p3 は意図が読めない空白に見える**（F-001）。p10-11 は山場として成立するが「静か」ではなく単調（F-007/F-008）。
- 台割自体の弱点: 前半 2,2 / 終盤 2,1,1,3 と**計画段階で**前後が静かに設計されている。実装は計画に忠実で、尻すぼみ（blind F-013）の原因は実装ではなく台割。

### 3. Design System Fidelity
- 一貫性側: 書体2種（Noto Serif/Sans CJK JP）、アクセント1色+濃紺1色、6列グリッド・余白トークン、`safe_violations=0`、ノンブル不一致0。
- 単調さ側: 本文ページ（p6, p7, p9, p13, p14）は同じ「全幅の本文枠+上部に1要素」の構造で、variant 間の差が小さい。記事の入口は variant で表情が変わるが、本文ページの変化が乏しく、反復が「規律」より「単調」に寄る。
- コンポーネント内に固定値（mm）が多く、テーマトークンで追従できない（System QA 参照）。

### 4. Fingerprint 19軸: 機械値と視覚印象の突合
| 軸 | mode | 機械値 | 視覚印象との一致 |
|---|---|---|---|
| D1 Typography | hybrid | fonts 2種、headline 10–56pt、**body_pt min 6.5 / max 20 / mean 8.7** | **不一致**: 本文は実際 8.5pt 一定。body_pt の計測が「最初の `<p>`」を拾い、デッキ/キャプション/表紙小見出しが混入（F-018） |
| D2 Grid | hybrid | 6列/4mm/5.5mm、safe 違反0 | 一致（ただし p8 の写真-文字接触はグリッド違反を検出できていない: F-002） |
| D3 White space | machine | mean 0.40, min 0, max 0.84 | 数値は正しいが、意図的余白と未充填を区別できない（F-017） |
| D4 Image treatment | hybrid | 画像8点、縁接/インセット 5/3、min 202ppi | 一致。ただし「処理の一貫性」は測れていない（p10 の白帯 F-008 は数値に出ない） |
| D5 Hierarchy | hybrid | 見出し/本文比 1.2–5.3 | 概ね一致。`pages_without_heading` に p10（見開きの片側）が入るのは誤警告気味 |
| D6 Motif | visual | null | 計測なし（正しい）。目視ではモチーフは散発（F-020） |
| D7 Navigation | machine | folio 14、柱 11、目次 5 | 数値は正しいが、**画像上で判読不能**な柱・ノンブルを検出できない（F-005） |
| E1 Article rhythm | machine | 記事ごとのページ数列 | 事実の列挙のみ。評価ではない |
| E2 Opening pattern | machine | openers 3 種/3 | 一致 |
| E3 Narrative pace | hybrid | 強度列 | 一致（波は読める）。ただし位置的な偏り（前後が静か）の評価規則がない（F-019） |
| E4 Information density | machine | min 25 / max 995 / mean 258.6 | 数値は正しいが `editorial.density: medium` との対応付けがなく合否が出ない（F-022） |
| E5 Recurring sections | machine | 全タイプ 1 件 | 1号だけでは「反復」を測れず無意味（F-025） |
| E6 Editorial voice | visual | 文字列のみ | 計測なし（正しい） |
| I1 Issue identity | visual | accent色・全面色ページ | 色の事実のみ。個性の有無は測れない（F-009/F-020） |
| I2 Spread variation | machine | 7/7 | 16頁では構造上ほぼ必ず 7/7 になり弁別力がない（F-025） |
| I3 Image rhythm | machine | max 連続 2 | 一致。ただし**素材の同質性**は測れない（F-007） |
| I4 Page density | machine | ink 0.2–1.0 | 概ね一致 |
| I5 Repetition | machine | layout 連続 最大2、variant 最大1 | 一致 |
| I6 Consistency | hybrid | fonts 2, folio 不一致0, overflow 0 | 数値は良いが、blind が見た「孤立行・引用の折返し・接触」は測れない（F-003/F-004） |

**総括**: 数値が「良好」でも誌面に欠点が残る典型が3つある — ①未充填ページが「静かなページ」として加点される、②画像上の可読性（コントラスト）を測っていない、③和文組版の欠陥（孤立行・禁則・折返し）を測っていない。これらは誌面側ではなく **Fingerprint/指標設計側の問題**として記録する。

### 5. fit_fill の検証（`output/test-issue-01/metrics.json` vs 実画像）
実画像から「内容の最下端が頁高の何%か」を別計測した（`reviews/tools/content-bottom.mjs`, 結果 `reviews/evidence/C-content-bottom.json`）。

| p | layout/variant | fit_fill | 実際の内容下端 | 目視 | 35%閾値で警告 |
|--:|---|--:|--:|---|:-:|
| 3 | column/box | **null**（fit-auto で計測外） | 48% | 下半分が空白 | なし |
| 7 | feature-body/two-col-image | 0.48 | 68% | 下1/3が空白 | なし |
| 9 | interview-body/qa | 0.47 | 52% | 下半分が空白 | なし |
| 14 | essay/end | 0.34 | 38% | 下60%が空白 | あり |
| 6 | feature-body/two-col | 0.91 | 88% | 充満 | なし |
| 13 | essay/opener | 0.93 | 84% | 充満 | なし |
- 実際の見た目との一致: p14 は警告されるが、p9（下端52%）・p7（68%）は 0.47/0.48 で警告されず、p3 は計測対象外。**同程度に空いたページが閾値の僅差で警告/非警告に分かれる**。
- 35% の意味: fit_fill は「本文枠」に対する比率で、枠自体が頁の一部（画像の下、箱の内側）だと**頁としての空き具合**を表さない。p7 は枠が頁下部のみのため 0.48 でも頁の1/3が空く。
- 誤警告: 写真主体ページ（p10-11）・引用（p12）・表紙・奥付は `.fit` を持たないため null で**誤警告はない**（良い）。一方、本文を持つ quote/essay 型が `.fit` を使わなければ永久に未計測になる設計。
- component 別の期待範囲: **必要**。記事最終ページ（essay/end, feature 最終）は 100% 未満が自然、オープナーは Q&A/本文が少なくて良い、column/box は箱が内容に合わせて伸びる（現在は null）。単一閾値 0.35 は「最終ページ」と「途中ページ」を区別できず、途中ページの 0.47 は見逃し、最終ページの 0.34 は過警告になる。
- 推奨指標: ①頁の内容下端（%）②記事の「最終ページ」フラグ③component ごとの期待範囲（中間ページ ≥0.8、最終ページ ≥0.3、など）。

## Findings

### F-016 [HIGH] page-balance — fit_fill（35%閾値）が「半分空いたページ」を検出できていない
- Pages: 3, 7, 9, 14
- Problem: Observation: 視覚上は p3/p7/p9/p14 がいずれも頁の1/3〜1/2以上空いているが、警告が出るのは p14（fit_fill 0.34）のみ。p9（0.47）・p7（0.48）は閾値超過で警告なし、p3 は fit-auto のため計測対象外。 Why it matters: 空白の多寡という誌面の最大の欠点（blind F-001）を、準備された検査が見逃す。検査が通ることを根拠に「完成度が高い」と誤判断する危険がある。
- Evidence: 上表（content-bottom 実測 vs fit_fill）。`rhythm.md` の auto finding は A-001 の1件（p14）のみで、F-001 が示す6ページのうち5ページが未検出。
- Fix: 方向性: 本文枠比ではなく「頁の内容下端」（または枠が頁に占める割合を掛けた実効充填率）で評価し、component/記事位置（最終ページか）ごとに期待範囲を持たせる。fit-auto の枠も計測対象にする。

### F-017 [MEDIUM] visual-rhythm — 「静かなページ」判定が未充填ページを肯定的に数えている
- Pages: 3, 9, 14
- Problem: Observation: `quiet`（whitespace≥0.6 かつ画像なし）に p3・p9・p14 が該当し、`min_quiet_pages: 1` を満たす根拠になっている。blind では同じ3頁が「未完成に見える」欠点（F-001）。 Why it matters: 意図的な静けさ（引用・余白ページ）と単なる未充填を区別しないため、悪い状態が「リズムの良さ」として加点される。
- Evidence: `rhythm.md` の「静かなページ: 3, 9, 14」と、blind F-001。
- Fix: 方向性: 静けさは「台割で宣言された（notes/intent）」ページのみに限る、または未充填（最終ページ以外の fit_fill 低下）を別カテゴリにする。

### F-018 [MEDIUM] consistency — Fingerprint D1 の body_pt が実体と乖離（max 20pt, mean 8.7pt）
- Pages: 1, 4, 5
- Problem: Observation: D1 の body_pt が min 6.5 / max 20 / mean 8.7 となっているが、実際の本文は一貫して 8.5pt。計測が「各頁の最初の `p`」を取り、デッキ・キャプション・表紙小見出しを拾っている。 Why it matters: 書体の規律を測る基幹指標が誤っており、テーマ変更時の検知に使えない。
- Evidence: `fingerprint.json` D1、metrics の `body_pt`（頁により 6.5〜20）。
- Fix: 方向性: 本文として明示されたクラス（`.body`）のみを対象にし、無ければ null とする。

### F-019 [MEDIUM] editorial-rhythm — 強度の乖離検知が緩く、位置的なリズム欠陥（前後の尻すぼみ）を検出する規則がない
- Pages: 2, 3, 13, 14, 15, 12
- Problem: Observation: 乖離閾値は |宣言×20−実測| > 45 で、p12（宣言4→実測37、差43）は検知されない。また「冊子の前半/終盤が連続して低強度」という blind F-013 型の欠陥に対応する規則が存在しない（強度の range だけ見ている）。 Why it matters: 強度の range（72）が目標（40）を満たしても、起伏が中盤に偏ることを見逃す。
- Evidence: `rhythm.json` の intensity 列 [86,14,10,72,60,2,27,35,3,61,56,37,12,4,10,26] と auto finding なし。
- Fix: 方向性: 先頭3頁・末尾3頁など区間ごとの平均強度/低強度の連続長を規則に加える。乖離は閾値を下げ、測定側で全面色を強度に反映する。

### F-020 [MEDIUM] issue-identity — fingerprint_target.motif（茜色の短い罫線と小さな四角）が散発的にしか現れない
- Pages: 1, 8, 14, 2, 13, 15
- Problem: Observation: 茜色の短い罫線は表紙の予告リスト、p8 の見出し上罫、p14 の終わりの印にだけ現れる。p2・p13・p15 の主罫は黒の太罫で、モチーフが記事間で反復していない。 Why it matters: 号の個性として宣言したモチーフが、読者に認識される反復になっていない。かつ、その検証は目視のみで、機械的な裏取り（例: アクセント色の罫要素の出現ページ数）がない。
- Evidence: p1/p8/p14 と p2/p13/p15 の比較（PNG）。fingerprint.json D6 は null。
- Fix: 方向性: モチーフ要素の出現を data 属性等で明示し、「全記事の入口に1回以上」のような検査可能な目標を fingerprint_target に持てるようにする。

### F-021 [MEDIUM] readability — 対象読者(30〜60代)に対して 6.5pt の小字（キャプション・ノンブル・柱・Q）が多い
- Pages: 5, 7, 9, 10, 11
- Problem: Observation: キャプション・ノンブル・柱・Q ラベルは 6.5pt の灰色ゴシック。editorial.yaml の audience に対し小さい。blind F-011 の LOW を audience 文脈で MEDIUM に引き上げる。 Why it matters: 老眼世代は 6.5pt の薄灰を印刷物で読みにくい。
- Evidence: `metrics.json` min_font_pt 6.5 が全頁。`rhythm` の LOW 規則（<6pt）では検出されない。
- Fix: 方向性: 対象読者から最小サイズ基準を導く（audience → min pt/contrast）。preflight の最小文字サイズ検査（現状は LOW のみ）を厳格化する。

### F-022 [LOW] editorial-rhythm — density: medium が検査されず、頁ごとの文字量が両極
- Pages: 6, 3, 14
- Problem: Observation: chars/page は 25〜995（stdev 259）。editorial.density=medium との対応付けがない。 Why it matters: 編集方針の数値化がなく、Context Review で毎回主観になる。
- Evidence: `fingerprint.json` E4。
- Fix: 方向性: density の low/medium/high を chars/page の期待範囲・分散上限に対応づける。

### F-023 [LOW] originality — mood の「木の床・手書きの看板・手仕事」が誌面表現に翻訳されていない
- Pages: 1, 4, 5, 8
- Problem: Observation: 書体・罫・色面は工業的に整っており、mood のうち手の気配が出る要素（手書き文字・紙の質感・不揃い）がない。 Why it matters: concept を視覚に翻訳する Art Direction の役割が、テーマ既定値の域を出ていない。
- Evidence: 全体の contact sheet。
- Fix: 方向性: mood の語を1〜2個具体的な視覚規則（書体の1要素、罫の質、色の使い方）に落とし、fingerprint_target に書く。

### F-024 [NOTE] editorial-rhythm — 台割の計画強度と実測は概ね整合している（良い点）
- Pages: 1, 4, 5, 6, 10, 11, 13, 14
- Problem: Observation: 計画 5 の頁は実測 56〜86、計画 1〜2 の頁は 2〜12 と整合し、台割が実装に反映されている。 Why it matters: 台割→誌面の忠実性という中核機能が機能している証拠。
- Evidence: 上記 Flatplan Fidelity の対応表。
- Fix: 方向性: 維持。ただし p12 のように測定の限界で乖離する例外は測定側を直す（F-019）。

### F-025 [NOTE] consistency — E5（Recurring Sections）・I2（Spread Variation）は 1号では弁別力がない
- Pages: 1
- Problem: global。Observation: E5 は全タイプ1件で反復が測れず、I2 は 16頁では構造上ほぼ常に 7/7 になる。 Why it matters: 指標が「通る」ことに意味がなく、合格の根拠として誤用される恐れ。
- Evidence: `fingerprint.json` E5, I2。
- Fix: 方向性: 過去号/複数号比較を前提とする指標は、単独号では「N/A」と明示する。

## Emergent fingerprint

- 「下半分の空白」が、意図（呼吸・余韻）と無関係に記事末・短い記事で発生する癖として固定化している
- 計測指標が未充填を「静かなページ」として肯定する構造（ツール側の癖）
- 本文ページの構造が全幅1枠+上部1要素に収斂している
- 朱色の罫は入口で散発、黒の太罫が主導（宣言モチーフとの差）

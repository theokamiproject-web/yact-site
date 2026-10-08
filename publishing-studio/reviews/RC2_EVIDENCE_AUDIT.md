# RC2 Evidence Integrity Audit

審査者: RC2 独立レビュー（再実行主体）。対象 HEAD `2a6a8e1` / branch `claude/bold-shannon-746w8g`。根拠の優先順位は 実コード > 実行結果 > 生成物 > evidence > git > RC1 文書 > RC2_CANDIDATE。

## 1. ケース総数をコードから確定
- `reviews/tools/adversarial.mjs` の `cases` オブジェクトのキーは **21 件**（`01…15`, `13a/13b`, `20…24`）。
- RC1_REVIEW Phase F の**番号付きケースは 1〜24（24 件）**。番号 13 が `13a/13b` の 2 実行単位に分かれるため、実行単位は 25。
- **16〜19（stale 系 4 件）は adversarial.mjs に存在せず**、別ツール `reviews/tools/stale-repro.mjs`（RC1 証跡 `evidence/D-stale-repro.json`）で扱われる。

| 区分 | 番号付きケース | 実行単位 |
|---|--:|--:|
| 全体 | **24** | **25** |
| adversarial.mjs（RC2 で修正者が再実行） | 20（1–15, 20–24） | 21 |
| stale-repro（RC2 証跡に再実行なし） | 4（16–19） | 4 |

→ 「21 + 4 = 25」は 13 の二重計上による算術（番号は 24）。報告・過去の説明にあった「24 のうち 16–19 を除く＝21」は**誤り**（正しくは 20 番号／21 単位）。RC2_CANDIDATE は「24 ケース」と書くだけで内訳を示さず、16–19 を再実行していないことを明記していなかった（**文書の不備**）。

## 2. Case inventory
区分: VERIFIED_RC2 = RC2 証跡あり、**かつ本レビューが HEAD で再実行して一致**。CARRIED_FROM_RC1 = RC2 証跡なし（本レビューが再実行して VERIFIED_BY_REVIEW）。

| # | key | ケース | RC1 証跡 | RC2 証跡 | 本レビュー再実行 | 区分 | 結果 |
|--:|---|---|---|---|---|---|---|
| 1 | 01-long-title | 長い見出し | F-adversarial-01_…06 | evidence-rc2/F-adversarial.json | 一致 | VERIFIED_RC2 | FIXED（validate `LAYOUT_OVERFLOW`） |
| 2 | 02-short-body | 短い本文 | 同 | 同 | 一致 | VERIFIED_RC2 | OK |
| 3 | 03-long-body | 長い本文 | 同 | 同 | 一致 | VERIFIED_RC2 | OK（validate は警告、preflight P19 FAIL） |
| 4 | 04-no-image | 画像なし | 同 | 同 | 一致 | VERIFIED_RC2 | OK |
| 5 | 05-missing-image | 欠落画像 | 同 | 同 | 一致 | VERIFIED_RC2 | OK |
| 6 | 06-extreme-portrait | 極端な縦長 | 同 | 同 | 一致 | VERIFIED_RC2 | PARTIAL（低 ppi でのみ FAIL） |
| 7 | 07-extreme-landscape | 極端な横長 | F-…07_…13 | 同 | 一致 | VERIFIED_RC2 | PARTIAL（同上） |
| 8 | 08-no-caption | キャプションなし | 同 | 同 | 一致 | VERIFIED_RC2 | OK |
| 9 | 09-long-caption | 長いキャプション | 同 | 同 | 一致 | VERIFIED_RC2 | FIXED（validate `LAYOUT_OVERFLOW`） |
| 10 | 10-unplaced-article | 記事未配置 | 同 | 同 | 一致 | VERIFIED_RC2 | OK |
| 11 | 11-duplicate-page | ページ重複 | 同 | 同 | 一致 | VERIFIED_RC2 | OK |
| 12 | 12-spread-parity | 見開き偶奇 | 同 | 同 | 一致 | VERIFIED_RC2 | OK |
| 13 | 13a-pages-20 / 13b-pages-12 | ページ数不一致（2 単位） | 同 | 同 | 一致 | VERIFIED_RC2 ×2 | OK |
| 14 | 14-theme-font-12pt | テーマで本文 12pt | F-…14_…24 | 同 | 一致 | VERIFIED_RC2 | PARTIAL（validate 警告＋preflight FAIL） |
| 15 | 15-theme-margins | 極端な余白 | 同 | 同 | 一致 | VERIFIED_RC2 | FIXED（FAIL P19） |
| 16 | （stale-repro）本文変更 | D-stale-repro.json | **なし** | 再実行 | CARRIED_FROM_RC1 → 本レビューで確認 | P10 FAIL ✓ |
| 17 | （stale-repro）画像変更 | 同 | なし | 再実行 | 同上 | P10 FAIL ✓ |
| 18 | （stale-repro）CSS/コード変更 | 同 | なし | 再実行 | 同上 | **PARTIAL**: themes/layouts は FAIL、**`scripts/lib/compose.mjs`・`metrics.mjs` の変更は P10 PASS（未検出）** |
| 19 | （stale-repro）台割変更 | 同 | なし | 再実行 | 同上 | P10 FAIL ✓ |
| 20 | 20-blank-page | 白ページ | 〃 | 〃 | 一致 | VERIFIED_RC2 | OK |
| 21 | 21-special-filename | 特殊ファイル名 | 〃 | 〃 | 一致 | VERIFIED_RC2 | FIXED |
| 22 | 22-raw-html | 生 HTML | 〃 | 〃 | 一致 | VERIFIED_RC2 | FIXED |
| 23 | 23-article-type-mismatch | 記事type不一致 | 〃 | 〃 | 一致 | VERIFIED_RC2 | **NOT FIXED**（検出なし） |
| 24 | 24-duplicate-article-id | ID 重複 | 〃 | 〃 | 一致 | VERIFIED_RC2 | OK |

再実行方法: 現 HEAD の `scripts/layouts/themes/schemas/issues` を scratch にコピーし、同一ハーネスを実行（証跡 `reviews/evidence-rc2-review/F-adversarial.rerun.json`, `stale-repro.rerun.log`）。21 単位すべて、修正者の RC2 証跡と validate 終了コード・all 終了コード・preflight 判定・指摘コード集合が**完全一致（差分 0）**。

## 3. 集計（Phase 17）
- TOTAL CASES: 24 番号 / 25 単位
- EXECUTED ON RC2 by the repairing session: 21 単位（20 番号）
- CARRIED FROM RC1（修正者は再実行せず）: 4 単位（16–19）→ **本レビューが再実行**
- MISSING: 0 / DUPLICATE: 0（13 の二重計上は算術上の注意）
- 番号ケースの最終判定（24 = 19 + 4 + 1）:
  - PASSED AS EXPECTED 19: 1, 2, 3, 4, 5, 8, 9, 10, 11, 12, 13, 15, 16, 17, 19, 20, 21, 22, 24
  - PARTIAL 4: 6, 7（低 ppi 以外の極端比率は未検出）, 14（事後検出のみ）, 18（`scripts/lib` 変更が未検出）
  - FAILED UNEXPECTEDLY 1: 23（記事 type とレイアウトの不一致を検出しない）

## 4. その他の証跡の整合
- 修正者のミューテーション証跡は**2 ファイルに分割**（M28 が両方に出現）。「28/28」は単一実行ではなく合成。**本レビューの単一実行は 28/28 KILLED**（`mutation-full.log`、NOT APPLICABLE 0）。
- `reviews/RC1_REVIEW.md` は RC1 コミット `3f474c9` から**未変更**（`git diff` 空）。
- `reviews/evidence/D-stale-repro.json`（RC1 証跡）は `stale-repro.mjs` が相対パスへ書く仕様で、本レビューの再実行が一時的に上書きしたが `git checkout` で復元済み。→ **ハーネスが RC1 証跡を上書きし得る**（P3: `EVIDENCE_DIR` 未対応）。
- RC2_CANDIDATE の「98/98」「PASS 23 / WARNING 2 / FAIL 0 / MANUAL 7」は本レビューで再現（`publication-test.log`: tests 98, pass 98）。

## 5. 判定
証跡に**重大な不整合はない**（算術・文書の不備は上記のとおり解消可能で、結果は再現した）。ただし「16–19 を RC2 で再実行していない」事実の未記載と、`scripts/lib` 変更が未検出のまま RC2 で「FIXED/OK」と読める記述は是正が必要。

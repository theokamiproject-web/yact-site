# RC2 Candidate — Independent Re-review

HEAD `2a6a8e1`（branch `claude/bold-shannon-746w8g`）。コード修正なし・PR なし。実行した証跡は `reviews/evidence-rc2-review/`。

**独立性の限界（先に開示）**: この再レビューを実施したのは、RC1 レビューと RC1 Repair を行ったセッションと**同じ会話系統**で、「別人」ではない。補強として、Blind Review は**別コンテキストの publication-critic エージェント**に画像のみで実施させ（`rc2-independent-blind.md`）、ミューテーション・敵対的ケース・境界・セキュリティは**自分で再実行**した。それでも、完全に独立した第三者レビューではない。

## Verdict: **REVISE**

P0 = 0 / リリースを止める P1 = **2**。v0.1 を freeze しない。修正は小規模（下記）。

| 評価軸 | 判定 | 根拠 |
|---|---|---|
| Architecture | PASS | 境界・トークン・2 パス計測・契約表の分離は妥当 |
| Security | PASS | 注入試験で外部通信 0、ライブタグ/属性 0、CSP 有効、非 root で sandbox-on の完全ビルド成功（下記） |
| Publishing Boundary | CONDITIONAL | 既定動線は閉じた。commit 側ガードは path 許可リスト方式で穴あり（P2）、hook は opt-in、CI は push 後 |
| Reliability | **FAIL** | 鮮度（P10）が `scripts/lib` 変更を検出しない（P1-B） |
| Generalization | CONDITIONAL | A5/B5・左綴じ・横組みのみ。縦組み/右綴じ/無線綴じ/混在カラーは未対応（v0.1 スコープ外だが、実号試行で B-1〜B-3 が顕在化） |
| Editorial Usability | CONDITIONAL | 実号向けの識別性/検証用サンプルが弱い |
| Visual System | CONDITIONAL | テンプレートとしては整う。独自の視覚言語は弱い（F-009）。見出し泣き別れ |
| Critic Validity | CONDITIONAL | 構造化レビューは保護。自由記述のみのレビューは `--reset` で無バックアップ消失 |
| Preflight Reliability | **FAIL** | P30 が `column`/`profile` 等の未宣言スパースを一律免除（P1-A） |
| Test Quality | CONDITIONAL | 28/28 KILLED（単一実行で再現）。ただし独立ミュータント X1 が生存 |
| Documentation | CONDITIONAL | RC2_CANDIDATE が 16–19 の未再実行と 24/25 の内訳を書いていない |
| Production Safety | PASS | 「入稿可」表現なし。P32–34 は MANUAL。P00 で境界 FAIL |

## Evidence Integrity
`RC2_EVIDENCE_AUDIT.md` 参照。ケース = 番号 24 / 実行単位 25（13 が 2 分割）。adversarial.mjs 21 単位を修正者が RC2 で再実行、16–19（stale 4 件）は**再実行されていなかった**。本レビューが全件を現 HEAD で再実行し、21 単位は RC2 証跡と**差分 0**、16–19 も実測した。重大な不整合なし（文書の不備のみ）。

## RC1 P0/P1 Closure（RC1_REVIEW.md の元の failure condition 基準）
| 項目 | 判定 | 独立確認 |
|---|---|---|
| P0-1 公開境界 | **FIXED（条件付き）** | `publication:new` は git-ignored の `workspace/issues/` に作成。`git add -f` で追跡させると pre-commit が exit 1、`validate`/`all`/`build`/`preflight` が `BOUNDARY_TRACKED`（P00 FAIL）で停止。リポジトリ内の非 ignore ディレクトリに置くと `BOUNDARY_NOT_IGNORED` で 4 コマンドとも停止。**残**: 同ディレクトリを `git add` しても pre-commit は `boundary ok`（path 許可リスト方式、P2） |
| P1-1 画像ファイル名 | FIXED | 「舞台 写真 01.jpg」「舞台#01.jpg」「日本海・秋田.jpg」「photo (1).jpg」で all 成功、P18 PASS、PDF に画像 9 点 |
| P1-2 生 HTML / sandbox | FIXED | script/iframe/object/embed/onerror/onclick/javascript:/外部 img・CSS・font を原稿・見出し・キャプションへ注入。ローカル HTTP サーバのヒット **0**、ライブ要素 0、PDF 16p、`<link>` はビルドの自前 CSS 3 本のみ、CSP meta あり。テーマ側の外部参照は `THEME_EXTERNAL_RESOURCE`。**sandbox**: 実装は無条件 `--no-sandbox` ではない（`PS_NO_SANDBOX=1` か remote+root のみ）。**非 root（uid 65534）・`CLAUDE_CODE_REMOTE` 未設定で `all test-issue-01` を実行 → sandbox-on の Chromium + Vivliostyle `--sandbox` で PASS 23/WARN 2/FAIL 0。この環境では VERIFIED**（user namespace が使える環境のみの確認） |
| P1-3 判型相対化 | FIXED | tokens は比率/`--type-scale`。mm/pt 直値は物理トークンと `calc(Npt*--type-scale)` のみ。B5 は A5 の中央浮きではない（余白・opener・画像比が比率で追従） |
| P1-4 contents 容量 | FIXED | TEST ISSUE 02 の目次に 10 項目すべて（p18・p20 を含む）、欠けなし。M15/M16（検出除去）は KILLED |
| P1-5 指標の妥当性 | **PARTIALLY FIXED** | MEASUREMENT/HEURISTIC/REVIEW_REQUIRED に分離、`fit_fill` 廃止、`body_pt` 修正は確認。**だが** `column`/`profile`/`colophon` 等は `sparse_allowed: true` で一律免除。02 の p3（占有 6.5%・extent 0.24）、p22（3.2%・0.21）、p10/p17 は未宣言なのに P30 PASS（P1-A） |
| P1-6 テスト補強 | PARTIALLY FIXED | 単一実行で 28/28 KILLED。独立ミュータント: 画像バイトをハッシュから外す（X2）・captions を外す（X3）は KILLED、**themes/layouts をハッシュ対象から外す（X1）は SURVIVED**（全 98 テストのうち落ちた 3 件は boundary 系で、サンドボックス複製に .git/.githooks が無いための失敗とみられる（ベースライン未取得）。鮮度検出系テストは通る） |
| P1-7 critic 保護 | PARTIALLY FIXED | 構造化レビューは `--reset` 拒否・`--force` で `archive/<ts>/` 退避・`source_hash` 束縛・ソース変更後は STALE を確認。**自由記述のみ（status: pending）のレビューは `--reset` で無警告・無バックアップで消失**（P2） |
| P1-8 サンプル組版 | PARTIALLY FIXED | 孤立行 0、ガター/柱の明暗は改善。**p6 の小見出しが欄末で本文と泣き別れ**（検出なし）、行長ばらつき、02 の未宣言スパース |
| P1-9 独立再レビュー | 本書 | 上記「独立性の限界」参照 |

## TEST ISSUE 01 / 02
- `publication:test` 98/98。`validate` 両号 exit 0。`all` 両号 exit 0、preflight **WARNING（PASS 23 / WARNING 2 [P14, P25] / FAIL 0 / MANUAL 7）**。数値は再現。
- 01 の critic レビュー（RC1 時代の tracked 2 本）は `source_hash` なしのため **STALE と判定され gate しない**（正しい）。
- **「成功」の質**: 数値は通るが、目視では 02 に未宣言の実質空白ページ（p3, p22, p10, p17）、01 に p6 の見出し泣き別れ。P30 の免除が PASS 23 を支えている。

## Independent Blind Review
`rc2-independent-blind.md`（別コンテキスト・画像のみ）。P0=0。最大の問題: ① 02 の内容量不足 ② 01 の本文組み（行長・見出し泣き別れ）③ 後半の空白頁。**自分で目視検証**し、①②③は実在、ただし「p6 だけゴシック」は誤観察（`pdffonts` で明朝）として Context で撤回。Blind 自身の件数は表と集計が一致しない（集計 P1=8、表の P1 は 6）。

## Mutation / Adversarial
- Mutation: 本レビューの単一実行で **28/28 KILLED**（NOT APPLICABLE 0）。M17 などはテスト名絞り込み付き。独立ミュータント X1 生存。
- Adversarial: `RC2_EVIDENCE_AUDIT.md`。FIXED: 1, 9, 15, 21, 22。PARTIAL: 6, 7, 14, 18。NOT FIXED: 23。

## Preflight
- 「ready」表現なし。P32–P34 MANUAL。P00 は境界違反を FAIL。P10 は**ソースの変更は検出するが、組版コード・ツールチェーンの変更は検出しない**。P30 は契約免除の穴。

## P2 Severity Reassessment
| RC2 の P2 | 再評価 | 理由 |
|---|---|---|
| 極端アスペクト/高解像度クロップ | P2 維持 | 低 ppi 時のみ FAIL。実害は目視で見える |
| 記事 type とレイアウト不一致 | P2 維持 | 06 と同様。人が気づく |
| 大フォントの欠け | P2 維持 | P19 が事後検出 |
| **ビルドコードのハッシュ範囲** | **P1 に格上げ（P1-B）** | 実証: `scripts/lib/compose.mjs`・`metrics.mjs` を変更しても P10 PASS。さらに、themes/layouts を hash から外す変異も全テストで生存。**組版ロジックを直した後に古い PDF が「最新」と判定され、入稿へ進める経路**がある。実号制作中にシステムを触る運用（現に別号でその状況）では重大 |
| 文字と写真の衝突 | P2 維持 | |
| （新規）sparse 契約の一律免除 | **P1-A** | 上記 |
| （新規）見出し keep-with-next（ページ跨ぎ） | P2 | 目視で確認、検出なし |
| （新規）自由記述レビューの消失 | P2 | データ消失型だが対象が狭い |
| （新規）commit ガードが path 許可リスト | P2 | 既定動線外の誤配置のみ |

## Remaining Conditions（修正後の再審査用）
1. **P1-A**: `column`/`profile`/`colophon`/`quote-page` 等の `sparse_allowed` を見直し、未宣言の低占有・低 extent ページは WARNING 以上にする。サンプルは意図を `intentional_sparse`＋理由で宣言するか内容を直す。見出し keep-with-next 違反を計測に加える。
2. **P1-B**: `sourceHash` に `scripts/lib`（ビルド・計測・compose）と `package.json` の依存バージョン、Vivliostyle/Chromium の版を含める。themes/layouts を hash から外す変異を殺すテストを追加。
3. RC2_CANDIDATE に 16–19 の扱い・ケース内訳・ミューテーション単一実行の数を反映。
4. （環境）印刷所確認（ICC/TAC/PDF-X/背幅）、**sandbox-on は非 root・userns 有効環境でのみ確認**。
5. critic `--reset` の自由記述保護、commit ガードに `issue.yaml`/`flatplan.yaml` 等のシグネチャ検査を追加（推奨）。

## Release Recommendation
**freeze しない（REVISE）**。P1 2 件はいずれも小規模・局所的で、修正後に P30 と P10 の再試験、サンプル 2 号の再生成、`RC2_CANDIDATE` の訂正を行えば ACCEPT WITH CONDITIONS に到達し得る。

---
P0: 0
P1: 2（P1-A sparse 契約の免除穴 / P1-B 鮮度ハッシュ範囲）
P2: 10
P3: 5

---
name: publication-critic
description: 完成した誌面をBlind→Context→Rereviewで批評する手順とPublication Fingerprint。critic pack生成、レビューの書式、検証、再レビューの進め方。誌面のレビューや品質チェックを頼まれたときに使う。
---
# Publication critic

制作者と批評者を分ける。批評は **publication-critic agent を別コンテキストで** 呼ぶ（制作に関わった会話で自分でレビューしない）。

## 手順
1. `npm run publication:all -- <id>` → `output/<id>/review-pack/{blind,context}/` と `issues/<id>/reviews/critic-*.md`（status: pending）が生成される
2. **Blind**: critic は `review-pack/blind/` のみ見て `critic-blind.md` を書く（editorial/flatplan/notes は見ない）
3. **Context**: `review-pack/context/`（editorial.yaml・flatplan・fingerprint.json・rhythm.md・preflight.md）を見て `critic-context.md`
4. `npm run publication:critic -- <id> --check` で構造検証（スコア・ID一意・必須項目・ページ範囲）。通ると `output/<id>/critic-report.json` が生成される
5. Editor in Chief が優先順位を決め、各担当が修正 → `publication:all` を再実行
6. **Rereview**: 新しいpackで `critic-rereview.md`。blind/contextの全指摘（MEDIUM以上必須）に disposition（fixed/open/regressed/wontfix）。AUTOブロックの `RESOLVED/NEW/STILL` は初回packとの機械的差分

## レビューの保護と結び付け
- レビューファイルは監査記録。パイプラインは書き換えない。`critic --reset` は作業済みを拒否、`--force` は `reviews/archive/<日時>/` に退避してから上書き。
- `review-pack/PACK.json` の `source_hash` を front matter に写す。ソースが変わると STALE（preflight P27 は MANUAL CHECK）。
- 自動出力は MEASUREMENT（事実）/ HEURISTIC（経験則）/ REVIEW_REQUIRED（機械判断不能）に分類される。

## 重大度
BLOCKER(出荷不可) / HIGH / MEDIUM / LOW / NOTE。指摘は 問題→根拠→該当ページ→重大度→修正案。感想は書かない。

## 評価項目（各1–5）
readability, hierarchy, visual-rhythm, consistency, originality, editorial-rhythm, page-balance, typography, image-usage, issue-identity

## Publication Fingerprint（`output/<id>/fingerprint.json`）
| 群 | 軸 | 判定 |
|---|---|---|
| DESIGN | D1 Typography(hybrid) D2 Grid(hybrid) D3 White Space(machine) D4 Image Treatment(hybrid) D5 Hierarchy(hybrid) D6 Motif(visual) D7 Navigation(machine) | |
| EDITORIAL | E1 Article Rhythm(m) E2 Opening Pattern(m) E3 Narrative Pace(hybrid) E4 Information Density(m) E5 Recurring Sections(m) E6 Editorial Voice(visual) | |
| ISSUE | I1 Issue Identity(visual) I2 Spread Variation(m) I3 Image Rhythm(m) I4 Page Density(m) I5 Repetition(m) I6 Consistency(hybrid) | |
machine=スクリプトが測る / hybrid=スクリプトが測りCriticが解釈 / visual=目視のみ。
- **Fingerprint Control**: `editorial.yaml: fingerprint_target` が意図（数値は自動検査、motif/typography は目視）
- **Emergent Fingerprint**: 意図に書かれていないが実物に反復して現れた特徴を `## Emergent fingerprint` に記録し、次号で維持/排除を決める

## Magazine Rhythm
`output/<id>/rhythm.md`: ページ別の強度・文字量・画像比・余白・充填率と、同型layout連続・写真連続・強弱の振れ幅・静かなページの自動検出。ページ単体ではなくcontact sheetで全体を見る。

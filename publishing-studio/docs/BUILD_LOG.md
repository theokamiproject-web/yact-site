# Build log — Publishing Studio v0.1

## Phase 1 — 既存環境調査
- リポジトリは GitHub Pages の静的サイト（`index.html` / `img/` / `.nojekyll`）+ `.claude/hooks/session-start.sh`（LibreOffice/Noto CJK のセットアップ）のみ。`package.json` なし。
- **`.claude/skills` `.claude/agents` flyer-designer design-critic Design Fingerprint blind/context/rereview 実装は、全ブランチ・履歴を通じて存在しなかった。** 再利用/破壊の対象はなし。design-critic の思想（制作者と批評者の分離、Blind/Context/Re-review、Fingerprint Control/Emergent、severity、自動検査と目視評価の分離）は仕様に従い Publishing Studio 側で新規に実装した。将来、既存実装が追加された場合に共有できるよう、critic のレビュー書式・severity・fingerprint は `scripts/lib/critic.mjs` `analysis.mjs` に集約している。
- 利用可能: Node 22、Chromium(`/opt/pw-browsers`)、poppler、Noto CJK、npm（Vivliostyle CLI 11.3.3 が導入可）。
- 既存ファイルは一切変更していない（ルートに `package.json` `.gitignore` `.claude/agents` `.claude/skills` `publishing-studio/` を追加）。

## Phase 2 — Architecture 決定（仕様からの変更）
- ルートが静的サイトなので **`publishing-studio/` に隔離**（`.claude/` と `package.json` のみルート）。
- `layouts/` は仕様の family ディレクトリ（cover/toc/feature/interview/essay/photo-essay/column/quote/divider/colophon）+ `index.mjs`（契約と描画）+ `style.css`。1 family に複数 component。
- レビュー: 生成物（pack, rhythm, fingerprint）は `output/<id>/`（再生成可・Git管理外）、批評者が書く `critic-*.md` は `issues/<id>/reviews/`（Git管理）。**md を正とし、`--check` で検証して `critic-report.json` を生成**（agent が JSON を手で書かない）。
- 本文は固定サイズの1ページ=1枠にし、文字数見積りで台割どおりに配分。Vivliostyle の自動ページ送りに任せない（台割どおりのページ数を保証するため）。

## Phase 3 — Publication Model / schema
- `issue / editorial / flatplan / article(front matter) / critic-report` の JSON Schema（ajv）+ 意味検証（台割の網羅・重複・見開きの偶数始まり・span・未配置記事・必須入力・欠落素材・キャプション・原稿量）。
- テスト: `model.test.mjs`（19項目）。

## Phase 4 — Vivliostyle 最小build
- bleed 3mm・`marks: crop`・日本語フォント埋め込みを煙テストで確認後、`build.mjs` に統合。`@page` は `issue.yaml` から生成。`build.json` にソースハッシュを記録（PDFの陳腐化を preflight が検出）。

## Phase 5/6 — Layout components / TEST ISSUE 01
- 15 component（全variant 計33）。A5 16p 中綴じのサンプルを作成（画像はSVGから生成、本文は架空の日本語ダミー）。
- **発見した問題と修正**: ①テーマの `.page h1` が component の見出しサイズ指定に勝っていた → ベース規則を `:where(.page)` に。②文字数容量式が実測と乖離 → 行数ベースの式に作り直し、`fit_fill`（DOM実測）で校正（見積りと実測の差 ≲10%）。③Q&A の Q が頁末に孤立 → Q は A と一緒に送る。④YAMLの未クォート `: ` を template で踏み、validate が検出。

## Phase 7 — render / contact sheet
- PDF の TrimBox だけを `pdftoppm` で切り出し（トンボ・塗り足しを除く）。DOM計測（文字量・画像比・余白推定・見出しスケール・本文充填率・はみ出し・実効ppi・塗り足し不足）を `metrics.json` に。contact sheet: 4×N / 8×N / 見開き。

## Phase 8 — Critic
- review pack（blind は意図情報なし）、rhythm、fingerprint（19軸を machine/hybrid/visual 区別）、レビュー雛形（AUTOブロック・初回packとの差分）、構造検証。

## Phase 9 — Preflight
- 28項目、PASS/WARNING/FAIL/MANUAL CHECK。確認できない項目（PDF/X、CMYK、トンボ内容、批評・校正の未実施）は MANUAL CHECK のまま。

## Phase 10 — tests / README
- `npm run publication:test`: 25テスト（約25秒）。異常系（本文あふれ、PDF陳腐化、欠落画像、レビュー不備）が FAIL/exit 1 になることを含む。

## 未解決・申し送り
- TEST ISSUE 01 の p14（essay/end）は本文充填率35%で `WARNING`（意図的に残した例）。
- Publication Critic による実際の blind/context/rereview はサンプル号では**未実施**（雛形は `status: pending`、preflight は MANUAL CHECK）。
- フォントは Type 3 埋め込み（Chromium）。印刷所の preflight 可否は要確認。

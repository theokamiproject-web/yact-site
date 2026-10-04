---
name: publishing-studio
description: 雑誌・ZINE・冊子を1冊、企画から入稿前チェックまで作る工程の全体手順。「号を作る」「冊子を作る」「ZINEを作りたい」「台割から組版してPDFにしたい」ときに最初に読む。各工程は専用agent/skillに委ね、ここは順序・ゲート・コマンドを定める。
---
# Publishing Studio — 号の制作工程

原則: **AIが毎回デザインを発明するのではなく、編集構造・Design System・再利用componentの制約下で編集・設計する。** 品質の再現性を生成の自由度より優先する。

Source of truth は `publishing-studio/issues/<id>/` の YAML + Markdown（Publication Model）。誌面HTMLは生成物で、直接編集しない。詳細は `publishing-studio/README.md`。

## 工程とagent
| # | 工程 | agent | 成果物 | ゲート |
|--|--|--|--|--|
| 0 | 新規号 | – | `npm run publication:new -- <id>` | – |
| 1 | 企画 | editor, editor-in-chief | `editorial.yaml` | EiC承認 |
| 2 | 原稿・写真 | editor, photo-editor | `articles/`, `captions/`, `images/` | validate error=0 |
| 3 | 台割 | editor → editor-in-chief | `flatplan.yaml` (`pages`/`article`) | EiC承認 |
| 4 | Art Direction | art-director | theme / `fingerprint_target` | – |
| 5 | 組版 | layout-designer | `flatplan.yaml` (`layout`/`variant`/`slots`) | `publication:all` が通る |
| 6 | 校正 | proofreader | `reviews/proofread.md` | status: complete |
| 7 | 批評 | publication-critic | `reviews/critic-blind.md` → `critic-context.md` | `--check` が通る |
| 8 | 修正 | EiCが優先順位 → 各担当 | 修正コミット | BLOCKER/HIGH=0 |
| 9 | 再批評 | publication-critic | `critic-rereview.md` | 全指摘にdisposition |
| 10 | Preflight | – | `output/<id>/preflight.md` | FAIL=0、MANUAL CHECK確認 |

## コマンド（リポジトリルートで）
```
npm run publication:new -- <id> [--title "…"]
npm run publication:validate -- <id>
npm run publication:all -- <id> [--marks]        # validate→build→render→critic pack→preflight
npm run publication:build|render|critic|preflight|preview -- <id>
npm run publication:critic -- <id> --check       # 完了したレビューの構造検証→critic-report.json
```

## 守ること
1. **制作者と批評者を分ける。** 組版したagentに批評させない。Criticは別コンテキスト（別のagent呼び出し）で、blind→contextの順に。
2. **自動検査と目視評価を混ぜない。** preflight/rhythm の数値は事実、visual判断はCriticの仕事。確認できていない項目を「確認済み」と書かない（`MANUAL CHECK` のまま残す）。
3. **台割承認前に組版しない。** 組版後の原稿変更は台割に影響するので、Editorへ戻す。
4. **レビューは1ラウンドで終わらせない。** 修正したら必ず再build/再render後に rereview。
5. **既存の flyer-designer / design-critic など他の仕組みには触れない。**

## 完了条件（号を「出せる」状態）
`publication:preflight` に FAIL がなく、`critic --check` で open BLOCKER/HIGH が0、`proofread.md` が complete、MANUAL CHECK（RGB/CMYK・PDF/X・クロップマーク）を印刷所に確認する旨を記録した。

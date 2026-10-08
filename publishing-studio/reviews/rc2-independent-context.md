# RC2 独立 Context Review（Blind 保存後に作成。Blind を上書きしない）

読んだもの: issue.yaml, editorial.yaml, flatplan.yaml（TEST ISSUE 02）, expected-warnings.yaml, rhythm.md, fingerprint.json, `layouts/_contracts.mjs`。Blind（`rc2-independent-blind.md`）は変更していない。

## 制作意図で説明できること / できないこと
| Blind の所見 | Context で分かったこと | 判断 |
|---|---|---|
| 02: p7/p11/p21（引用）が「ほぼ空」 | editorial: 「写真主導のZINE。長い文章は置かない」pacing fast / density low / min_quiet_pages 2。引用頁は rhythm で `quiet(declared/composed)` | **意図で説明可**。Blind の P2 は取り下げ可（ただし 11 が前頁 p10 と連続して空白が続く見開きは、意図があっても単調） |
| 02: p20 インタビュー問答 2 つのみ | flatplan `intentional_sparse: true`＋理由あり | 意図あり（宣言済み） |
| 02: p3「はじめに」・p22「あとがき」が本文 1 行・頁の 8 割が空 | **宣言なし**。`column` は `_contracts.mjs` で `sparse_allowed: true`、占有率 6.5% / 3.2%、content_extent 0.24 / 0.21 だが P30 は PASS | **意図では説明できない。Blind の指摘は維持**。意図が editorial にあるとしても flatplan に宣言が無く、契約が検査を免除しているだけ（メトリクス穴） |
| 02: p10, p17（profile）本文 1 行 | `profile` も `sparse_allowed: true` | 同上（宣言なし・免除） |
| 01: p6 本文が「ゴシック」→ p7 が「明朝」 | **事実と異なる**。`pdffonts` p6 は Noto Serif 76 / Sans 15（見出し）— 本文は明朝。低解像度 PNG での見間違い | **Blind の当該所見は誤観察として撤回**（Blind ファイルは保持、本書で訂正） |
| 01: p6/p7/p9 の短行（強制改行風） | 高解像度で確認: `.narrow`（ragged-right）＋文節折り返しで行長は 12〜19 字にばらつく。主因は欄幅 ≈ 20 字と文節禁則 | **実在**。可読性は保たれるが不揃い（P2）。意図では説明できない |
| 01: p6 最下行の小見出し「町が貸すもの、借りるもの」が欄末、本文は p7 | 実在（高解像度 PNG 確認）。見出しの keep-with-next がページ跨ぎで効かず、metrics の `orphan_lines` は検出しない | **システム欠陥（P2）** |
| 02: 表紙サブタイトル「朝と夜のあいだ」重複 | 表紙 variant `split` に副題＋箇条書き行が同文 | データ側の重複（サンプル欠陥, P2） |
| 両号: 写真がイラスト（ビル群/港）で説得力がない | サンプルは生成 SVG/イラスト（`credits`: サンプル画像）。意図通り | テスト素材の限界。**視覚の独自性は評価不能**側に回る |
| 01 p14/p15 の空白 | essay/end・colophon は `last` ロールで占有率の下限が低い契約（0.3）。p14 占有 0.60 | 契約内。見え方は単調（P3） |

## Visual identity（F-009）の位置づけ
- 「テンプレートとして整っている」: 色・罫・柱・ノンブル・見出し造形が号内で一貫（Blind と一致）。
- 「雑誌として独自の視覚言語がある」: 弱い。01 と 02 は部品の配色替えに見え、誌名ロゴ・見出し造形・写真の扱いの癖が共有されない。
- 判断: **v0.1 基盤としては neutral sample で許容（Release 条件にしない, P2）**。ただし Publication Critic の「issue-identity」「originality」軸は、この 2 サンプルでは評価不能になり、critic の**検証用サンプルとしては弱い**。critic の妥当性検証には、識別性のある 3 つ目のサンプルか実号が要る。

## Blind と Context の関係
Context により正当化された Blind の P2 は引用頁の空白のみ。**P1 相当（p3/p22/p10/p17 の未宣言スパース、p6 の見出し泣き別れ）は Context でも覆らない**。覆らないどころか、`sparse_allowed` の一律免除が「PASS 23」を生んでいる点は、RC1 P1-5（`quiet` を宣言頁に限定）の未完了を示す。

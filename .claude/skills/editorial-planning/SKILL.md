---
name: editorial-planning
description: 号の編集企画を立てる。editorial.yaml（concept/audience/voice/mood/pacing/density/keywords）の作成、記事の構成、タイトル・デッキ・リード・キャプション・原稿量の調整をするときに使う。
---
# Editorial planning

## editorial.yaml の書き方
- `concept`: 1〜2文。「誰に・何を・どう感じてほしいか」。形容詞だけにしない
- `audience`: 年齢層・関心・前提知識を具体的に
- `editorial_voice`: 文体を検証可能にする（例: 「です・ます調。体言止めは見出しのみ。比喩は1記事1つまで」）
- `pacing`: `slow|steady|fast|varied` / `density`: `low|medium|high`
- `keywords`: 3〜6語。Art Director がテーマ、Critic が「意図が出ているか」を見る基準になる

## 記事（`articles/<id>.md`）
- front matter 必須: `id` `title` `type` `priority` `target_pages`。任意: `kicker` `deck` `intro` `author` `section` `assets` `pull_quotes` `interviewee`
- 本文はMarkdown。`## 小見出し`。インタビューは段落を `Q: ` / `A: ` で始める
- タイトル: 読者が得るものを1行で。デッキ: タイトルが伝えない「なぜ今・誰の話か」を1〜2文。リード（`intro`）: 本文の入口、80字前後
- プルクォートは本文からの抜粋ではなく、そのページで最も強い一文

## 原稿量
容量は組版前に**実測した枠**から決まる（判型・テーマで変わる）ので、固定の字数表は使わない。
`npm run publication:validate -- <id>` の `TEXT_UNDERFILLED`（記事内の位置別の期待量に満たない: HEURISTIC）`TEXT_PAGE_EMPTY` `TEXT_MAY_OVERFLOW`(>105%) `TARGET_PAGES` で過不足を数字で確認する。意図して短い頁は台割で `intentional_sparse: true` + `notes` に理由。

## 判断基準
「読む体験として成立するか」: 入口（タイトル+デッキ+リード）で読む理由が分かる／各ページに「次を読ませる」要素がある／1ページに主張が1つ／終わりに余韻。美しさは評価しない。

---
name: photo-editing
description: 写真の分類・hero/ポートレート候補の選定・シーケンス・トリミング適性（focal）・解像度の判断。images/images.yaml と記事のassetsを整えるときに使う。
---
# Photo editing

## 置き場と記述
- 画像は `issues/<id>/images/`。メタデータは `images/images.yaml`、記事との紐付けは記事 front matter の `assets`、キャプションは `captions/*.yaml`（キー=ファイル名）
```yaml
# images.yaml
harbor.jpg: { role: hero, orientation: landscape, focal: [0.62, 0.5], alt: 夕暮れの港, note: 見開き用。中央に被写体なし }
# captions/captions.yaml
harbor.jpg: { caption: 夕暮れの潮見港。…, credit: 写真＝氏名 }
```
role: `hero` `portrait` `inline` `transition` `sequence` `decorative`（decorativeはキャプション不要）

## 判断基準
- **hero**: 一枚で主題が伝わる／タイトルの載る余白／見開きなら横長で中央（ノド）に被写体を置かない
- **portrait**: 視線がページ内側へ向く／頭上の余白／トリミングで顔を切らない（focal を顔に）
- **transition**: 記事間の呼吸になる。情報量が少なく、色調がつなぎになる
- **sequence**: 引き/寄り、明/暗、縦/横を交互に。同構図3連続は避ける
- 写真主体ページを3連続させない

## 解像度
仕上がり寸法での有効ppi ≥ 200 が目安（`preflight` P22 が DOM から算出: <100 FAIL / <200 WARNING）。全面裁ち落としはトンボ外3mmの塗り足しを含めて見積もる。
色: 入稿はCMYK変換が前提。v0.1 は変換しない（P25 WARNING / P26 MANUAL CHECK）。

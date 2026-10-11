# Artificial fixture: a tiny made-up script (no real work). usage: python3 make-fixture.py out_dir
import sys, os
d = sys.argv[1]; os.makedirs(d, exist_ok=True)
lines = ["試験劇　台本", "テスト太郎", "キャスト",
 "　山田花子　主人公　　出演者A",
 "　長谷川アンナ　遠くから来た旅人。名前が長い役　　出演者B",
 "　佐藤　通行人　　出演者C",
 "　各役の設定は物語のスタートのもの。", "風景", "　架空の町。", "　一・二階とも部屋がある。", "プロローグ", "　架空の町の広場。"]
for i in range(1, 25):
    lines += ["", f"山田　3人で12時に集まろう。Let's party！ 第{i}場面の台詞です。これは改ページと段組みを確認するための長めの台詞で、同じ文を繰り返します。同じ文を繰り返します。",
              f"長谷川アンナ（遠くから、小さな声で）　そうだね。{i}回目の返事です。続きの行も付けます。", "それがこの継続行です。",
              f"佐藤　（{i}番目のト書き）ええ。", f"　{i}番目の地の文のト書きです。"]
    if i == 12: lines += ["", "＊＊＊＊"]
lines += ["", "終"]
open(os.path.join(d, "source.txt"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
open(os.path.join(d, "corr.tsv"), "w", encoding="utf-8").write("繰り返します。同じ文を繰り返します。\t繰り返します。\n")

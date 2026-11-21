"""クリックポスト「まとめ申込」用CSVを作る（Shift-JIS・CRLF・40件ごとに分割・文字数チェック）

usage: python3 clickpost_csv.py 宛先.csv 出力ファイル名の頭 [内容品]
  宛先.csv（UTF-8, 1行目は見出し）: 郵便番号,氏名,住所1,住所2[,内容品]
    住所1 = 都道府県〜番地、住所2 = 建物名・部屋番号（なければ空）
  出力: <頭>_1.csv, <頭>_2.csv ...（41件以上なら分割）
制限を超える行があると、ファイルを作らずに一覧を出して終了する（exit 1）。
見出し行は手引きのテンプレートと1文字も違わないこと。テンプレートが変わったら HEADER を直す。
"""
import csv, io, sys

HEADER = ["お届け先郵便番号", "お届け先氏名", "お届け先敬称", "お届け先住所1行目",
          "お届け先住所2行目", "お届け先住所3行目", "お届け先住所4行目", "内容品"]
# バイト数上限（Shift-JIS換算：全角2・半角1）。氏名・住所各行=全角20字、内容品=全角15字
LIMIT = {1: 40, 3: 40, 4: 40, 5: 40, 6: 40, 7: 30}
MAX_ROWS = 40


def sjis_len(s):
    return len(s.encode("cp932"))


def main():
    src, head = sys.argv[1], sys.argv[2]
    default_item = sys.argv[3] if len(sys.argv) > 3 else "舞台写真"
    rows, errors = [], []
    with open(src, encoding="utf-8-sig", newline="") as f:
        r = csv.reader(f)
        next(r)
        for n, rec in enumerate(r, start=2):
            if not any(x.strip() for x in rec):
                continue
            rec = [x.strip() for x in rec] + [""] * 5
            zipc, name, a1, a2, item = rec[:5]
            item = item or default_item
            zipc = zipc.replace("ー", "-").replace("－", "-")
            if len(zipc) == 7 and zipc.isdigit():
                zipc = zipc[:3] + "-" + zipc[3:]
            row = [zipc, name, "様", a1, a2, "", "", item]
            for i, lim in LIMIT.items():
                try:
                    if sjis_len(row[i]) > lim:
                        errors.append(f"{n}行目 {HEADER[i]} が長すぎます（{sjis_len(row[i])}/{lim}バイト）: {row[i]}")
                except UnicodeEncodeError as e:
                    errors.append(f"{n}行目 {HEADER[i]} にShift-JISにない文字があります（別の字に置き換えるか、手で入力する）: {e.object[e.start:e.end]}")
            if not (len(zipc) == 8 and zipc[3] == "-"):
                errors.append(f"{n}行目 郵便番号の形式が違います: {zipc}")
            if not name or not a1:
                errors.append(f"{n}行目 氏名か住所1が空です")
            rows.append(row)
    if errors:
        print("\n".join(errors))
        sys.exit(1)
    for k in range(0, len(rows), MAX_ROWS):
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\r\n")
        w.writerow(HEADER)
        w.writerows(rows[k:k + MAX_ROWS])
        out = f"{head}_{k // MAX_ROWS + 1}.csv"
        open(out, "wb").write(buf.getvalue().encode("cp932"))
        print(f"{out}: {len(rows[k:k + MAX_ROWS])}件")


if __name__ == "__main__":
    main()

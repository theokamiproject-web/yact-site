#!/usr/bin/env python3
"""提案書本体と別紙の突合チェック。

使い方:
  python3 crosscheck.py 本体.md [別紙.md ...] [--web web.html] [--print print.html ...]

検出するもの:
  1. 未完成の印（←、TODO、○○、XX、（仮）以外の「要検討」等）
  2. 金額表記（円・万円）— 本体にない金額が別紙に出ていないか
  3. 「第N章」「N-M」参照 — 参照先の見出しが本体／自文書に存在し、内容語が一致するか
  4. 外部URL（Googleドキュメント等）— PDF送付時に残っていないか
  5. 本体Markdownと各HTML版の本文ずれ（段落単位、HTML版にない段落を列挙）
"""
import re
import sys
from pathlib import Path

PLACEHOLDER = re.compile(r"(←|TODO|ＴＯＤＯ|○○|ＸＸ|XX|要検討|うまい理由|未定稿|\?\?\?)")
MONEY = re.compile(r"[0-9０-９,，.]+\s*(?:万|億|千)?円")
CHAPTER_REF = re.compile(r"第([0-9０-９]+)章(?:に記載した|で述べた|の)?([^\s、。（）]{0,8})")
HEADING = re.compile(r"^#{1,4}\s*([0-9]+)(?:-([0-9]+))?\.?\s*(.+)$", re.M)
URL = re.compile(r"https?://\S+")


def strip_html(text):
    text = re.sub(r"<(script|style)[\s\S]*?</\1>", "", text)
    text = re.sub(r"<[^>]+>", "\n", text)
    return re.sub(r"[ \t]+", " ", text)


def paragraphs_md(text):
    out = []
    for block in re.split(r"\n\s*\n", text):
        b = block.strip()
        if not b or b.startswith(("#", "|", "-", "---", "<!--")):
            continue
        b = re.sub(r"\*\*|\*", "", b)
        if len(b) >= 30:
            out.append(re.sub(r"\s+", "", b))
    return out


def main(argv):
    web, prints, docs = [], [], []
    mode = None
    for a in argv:
        if a in ("--web", "--print"):
            mode = a
            continue
        (web if mode == "--web" else prints if mode == "--print" else docs).append(Path(a))
        mode = None
    if not docs:
        print(__doc__)
        return 2

    main_doc, appendices = docs[0], docs[1:]
    texts = {p: p.read_text(encoding="utf-8") for p in docs}
    issues = 0

    print("=" * 50)
    print("提案書 突合チェック")
    print("=" * 50)

    # 1. placeholders
    for p, t in texts.items():
        for n, line in enumerate(t.splitlines(), 1):
            if PLACEHOLDER.search(line):
                print(f"❌ 未完成の印 {p.name}:{n}: {line.strip()[:60]}")
                issues += 1

    # 2. money
    main_money = set(MONEY.findall(texts[main_doc]))
    print(f"\n[金額] 本体の金額表記: {sorted(main_money) or 'なし'}")
    for p in appendices:
        for n, line in enumerate(texts[p].splitlines(), 1):
            for m in MONEY.findall(line):
                if m not in main_money:
                    print(f"⚠️  本体にない金額 {p.name}:{n}: 「{m}」… {line.strip()[:50]}")
                    issues += 1

    # 3. chapter references
    main_heads = {int(h[0]): h[2].strip() for h in HEADING.findall(texts[main_doc]) if not h[1]}
    for p, t in texts.items():
        for n, line in enumerate(t.splitlines(), 1):
            for num, word in CHAPTER_REF.findall(line):
                k = int(num.translate(str.maketrans("０１２３４５６７８９", "0123456789")))
                head = main_heads.get(k)
                if head is None:
                    print(f"❌ 参照先の章が本体にない {p.name}:{n}: 第{k}章")
                    issues += 1
                    continue
                body = section_body(texts[main_doc], k)
                word = re.match(r"[一-鿿゠-ヿA-Za-z0-9]*", word).group(0)
                if word and word not in body:
                    print(f"⚠️  第{k}章「{head}」に「{word}」の記述がない {p.name}:{n}: {line.strip()[:50]}")
                    issues += 1

    # 4. URLs
    for p, t in texts.items():
        for n, line in enumerate(t.splitlines(), 1):
            for u in URL.findall(line):
                print(f"ℹ️  URLあり {p.name}:{n}: {u[:60]}（PDF送付なら不要か確認）")

    # 5. md vs html drift
    md_paras = paragraphs_md(texts[main_doc])
    for h in web + prints:
        if not h.exists():
            print(f"ℹ️  {h} が見つからないため差分確認をスキップ")
            continue
        flat = re.sub(r"\s+", "", strip_html(h.read_text(encoding="utf-8")))
        missing = [para for para in md_paras if para[:40] not in flat]
        for para in missing:
            print(f"⚠️  {h.name} に本体Markdownの段落がない: {para[:40]}…")
            issues += 1

    print("\n" + "=" * 50)
    print("✅ 問題なし" if issues == 0 else f"⚠️  要確認 {issues} 件（金額・章参照はユーザー判断が要る場合あり）")
    print("=" * 50)
    return 0 if issues == 0 else 1


def section_body(text, k):
    m = re.search(rf"^#{{1,3}}\s*{k}\.\s.*$", text, re.M)
    if not m:
        return ""
    nxt = re.search(rf"^#{{1,3}}\s*{k + 1}\.\s.*$", text[m.end():], re.M)
    return text[m.end(): m.end() + nxt.start()] if nxt else text[m.end():]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

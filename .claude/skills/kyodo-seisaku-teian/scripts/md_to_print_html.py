#!/usr/bin/env python3
"""提案書Markdown → 印刷用HTML（weasyprint用）。Markdownを唯一の原本にするための変換器。

使い方: python3 md_to_print_html.py input.md output.html [--css templates/print.css]

Markdownの書き方（この規約に合わせる）:
  先頭〜最初の `---` まで = 表紙ブロック
    # 共同企画のご提案　○○ 御中      → 朱枠タグ
    ## 舞台『作品名（仮題）』          → タイトル
    ### ～サブタイトル～               → サブタイトル
    ラベル：値                        → クレジット表の1行（企画・作演出・出演・時期・提出日など）
  本文
    ## 1. 見出し / ### 1-1. 小見出し
    **小見出し**（単独行）＋次行から本文 → h4＋段落
    | 表 |、1. 番号リスト、- 箇条書き
  最後の `---` 以降 = 問い合わせ欄（各行を改行で表示）
"""
import html
import re
import sys
from pathlib import Path

CJK = r"[　-〿぀-ヿ一-鿿＀-￯]"


def inline(s):
    s = html.escape(s, quote=False)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)


def join_lines(lines):
    out = ""
    for ln in (l.strip() for l in lines):
        if out and not (re.search(CJK + "$", out) or re.match(CJK, ln)):
            out += " "
        out += ln
    return out


def table(rows):
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    head, body = cells[0], [r for r in cells[1:] if not all(re.fullmatch(r":?-+:?", c) for c in r)]
    h = "".join(f"<th>{inline(c)}</th>" for c in head)
    b = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in body)
    return f'<table class="data"><tr>{h}</tr>{b}</table>'


def body_html(lines):
    out, i = [], 0
    while i < len(lines):
        ln = lines[i].rstrip()
        s = ln.strip()
        if not s or s.startswith("<!--"):
            i += 1
            continue
        if s == "---":
            out.append("<hr>")
            i += 1
        elif s.startswith("### "):
            out.append(f"<h3>{inline(s[4:])}</h3>")
            i += 1
        elif s.startswith("## "):
            out.append(f"<h2>{inline(s[3:])}</h2>")
            i += 1
        elif s.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(lines[i])
                i += 1
            out.append(table(rows))
        elif re.match(r"\d+\.\s", s) or s.startswith("- "):
            tag = "ol" if re.match(r"\d+\.\s", s) else "ul"
            items = []
            while i < len(lines) and (re.match(r"\s*(\d+\.|-)\s", lines[i])):
                items.append(re.sub(r"^\s*(\d+\.|-)\s+", "", lines[i]).strip())
                i += 1
            out.append(f"<{tag}>" + "".join(f"<li>{inline(x)}</li>" for x in items) + f"</{tag}>")
        elif re.fullmatch(r"\*\*[^*]+\*\*", s):
            out.append(f"<h4>{inline(s[2:-2])}</h4>")
            i += 1
        else:
            para = []
            while i < len(lines) and lines[i].strip() and not re.match(r"\s*(#|\||---|\d+\.\s|-\s|\*\*[^*]+\*\*$)", lines[i]):
                para.append(lines[i])
                i += 1
            out.append(f"<p>{inline(join_lines(para))}</p>")
    return "\n".join(out)


def convert(md, css):
    lines = md.splitlines()
    seps = [n for n, l in enumerate(lines) if l.strip() == "---"]
    front = lines[: seps[0]] if seps else []
    rest = lines[seps[0] + 1:] if seps else lines
    contact = []
    if len(seps) >= 2:
        last = seps[-1] - (seps[0] + 1)
        rest, contact = rest[:last], rest[last + 1:]

    cover, credits, title = [], [], ""
    for l in front:
        s = l.strip()
        if s.startswith("# "):
            cover.append(f'<span class="tag">{inline(s[2:])}</span>')
        elif s.startswith("## "):
            title = s[3:]
            cover.append(f'<h1 class="title">{inline(title)}</h1>')
        elif s.startswith("### "):
            cover.append(f'<div class="subtitle">{inline(s[4:])}</div>')
        elif "：" in s:
            k, v = s.split("：", 1)
            credits.append(f'<tr><td class="k">{inline(k)}</td><td>{inline(v)}</td></tr>')
        elif s:
            cover.append(f'<div class="subtitle">{inline(s)}</div>')
    if credits:
        cover.append('<table class="credit">' + "".join(credits) + "</table>")
    contact_html = ""
    if any(l.strip() for l in contact):
        contact_html = '<div class="contact">' + "<br>".join(inline(l.strip()) for l in contact if l.strip()) + "</div>"

    return (f'<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8"><title>{html.escape(title or "提案書")}</title>'
            f"<style>{css}</style></head><body>\n" + "\n".join(cover) + "\n" + body_html(rest) + "\n" + contact_html + "\n</body></html>\n")


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    css_path = Path(argv[argv.index("--css") + 1]) if "--css" in argv else Path(__file__).parent.parent / "templates" / "print.css"
    Path(argv[1]).write_text(convert(Path(argv[0]).read_text(encoding="utf-8"), css_path.read_text(encoding="utf-8")), encoding="utf-8")
    print(f"wrote {argv[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

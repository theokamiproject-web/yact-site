#!/usr/bin/env python3
"""既存スキルの一覧（名前・置き場所・同期元・説明の冒頭）を出す。重複確認用。

使い方: python3 list_skills.py [キーワード ...]
  キーワードを渡すと、名前か説明に含むものだけ出す。
"""
import json
import re
import sys
from pathlib import Path

ROOTS = [Path.home() / ".claude" / "skills", Path.cwd() / ".claude" / "skills"]


def frontmatter(md):
    m = re.match(r"---\n(.*?)\n---", md, re.S)
    if not m:
        return {}
    fm, out, key = m.group(1), {}, None
    for line in fm.splitlines():
        k = re.match(r"([A-Za-z_-]+):\s*(.*)$", line)
        if k:
            key, val = k.group(1), k.group(2).strip()
            out[key] = "" if val in ("|", ">") else val
        elif key:
            out[key] = (out[key] + " " + line.strip()).strip()
    return out


def main(words):
    sources = {}
    for root in ROOTS:
        for manifest in root.glob("synced/*/manifest.json"):
            for s in json.loads(manifest.read_text()).get("skills", []):
                sources[s["name"]] = s.get("source", "?")
    seen = set()
    for root in ROOTS:
        for md in sorted(root.glob("**/SKILL.md")):
            fm = frontmatter(md.read_text(encoding="utf-8"))
            name = fm.get("name", md.parent.name)
            desc = fm.get("description", "")
            if words and not any(w in name or w in desc for w in words):
                continue
            key = (name, str(md.parent))
            if key in seen:
                continue
            seen.add(key)
            where = "synced(" + sources.get(name, "?") + ")" if "/synced/" in str(md) else str(md.parent)
            print(f"- {name} [{where}]\n    {desc[:110]}")


if __name__ == "__main__":
    main(sys.argv[1:])

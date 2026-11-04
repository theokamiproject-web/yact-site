#!/usr/bin/env bash
# スキルを検証して .skill に固める。skill-creator 同梱のスクリプトを使う。
# 使い方: bash package.sh <スキルのディレクトリ> <出力ディレクトリ>
set -euo pipefail
SKILL="$(cd "$1" && pwd)"; OUT="$2"
mkdir -p "$OUT"; OUT="$(cd "$OUT" && pwd)"
SC=$(ls -d ~/.claude/skills/synced/*/skill-creator ~/.claude/skills/skill-creator 2>/dev/null | head -1 || true)
if [ -z "$SC" ]; then
  echo "⚠️ skill-creator が無い。zip で代替: $OUT/$(basename "$SKILL").skill"
  (cd "$(dirname "$SKILL")" && python3 -m zipfile -c "$OUT/$(basename "$SKILL").skill" "$(basename "$SKILL")")
  exit 0
fi
(cd "$SC" && python3 scripts/quick_validate.py "$SKILL")
(cd "$SC" && python3 -m scripts.package_skill "$SKILL" "$OUT" | tail -1)

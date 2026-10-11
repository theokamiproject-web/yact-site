#!/bin/bash
# 環境検査。足りないものがあれば一覧して exit 1（黙って成功扱いにしない）。
# 使い方: env_check.sh [NODE_MODULES_DIR]   (NODE_MODULES_DIR に opentype.js と @fontsource/noto-serif-jp、PLAYWRIGHT_DIR に playwright(-core))
ND=${1:-${NODE_MODULES:-}}; miss=()
need() { command -v "$1" >/dev/null 2>&1 || miss+=("コマンド: $1"); }
for c in node python3 pdfinfo pdffonts pdfimages pdftoppm pdftotext; do need $c; done
for m in pikepdf numpy PIL; do python3 -c "import $m" 2>/dev/null || miss+=("python: $m"); done
if [ -z "$ND" ] || [ ! -d "$ND/opentype.js" ]; then miss+=("node: opentype.js (NODE_MODULES を指定: $ND)"); fi
if [ -z "$ND" ] || [ ! -d "$ND/@fontsource/noto-serif-jp/files" ]; then miss+=("node: @fontsource/noto-serif-jp"); fi
PW=${PLAYWRIGHT_DIR:-playwright}
node -e "require('$PW')" 2>/dev/null || miss+=("node: playwright / playwright-core (PLAYWRIGHT_DIR=$PW)")
if [ ${#miss[@]} -gt 0 ]; then echo "ENV NG: 不足 ${#miss[@]} 件"; printf ' - %s\n' "${miss[@]}"; exit 1; fi
echo "ENV OK"

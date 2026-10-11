#!/bin/bash
# BODY ONLY (cover pages are NOT included here).
# Usage: make-print-pdf.sh <body.html> <out_dir> <expected_BODY_pages|any>
# HTML (vivliostyle, @page bleed:3mm) -> out_dir/body_raw.pdf (fonts still present, used for text checks)
#   -> out_dir/body.pdf (Gray + outlined) -> body page-count check. Exits 1 on mismatch.
# The total page count (cover + body) is verified separately by assemble-final.sh.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
HTML=$1; OUT=$2; EXP=$3; V=${VIVLIO:-vivliostyle}
command -v "$V" >/dev/null 2>&1 || V=/home/user/yact-site/node_modules/.bin/vivliostyle
mkdir -p "$OUT"
"$V" build "$HTML" -o "$OUT/body_raw.pdf" >"$OUT/vivliostyle.log" 2>&1 || { echo "ERROR: vivliostyle failed, see $OUT/vivliostyle.log"; exit 1; }
"$HERE/to-gray.sh" "$OUT/body_raw.pdf" "$OUT/body.pdf"
N=$(pdfinfo "$OUT/body.pdf" | awk '/^Pages:/{print $2}')
if [ "$EXP" != "any" ] && [ "$N" != "$EXP" ]; then echo "ERROR body pages=$N expected=$EXP"; exit 1; fi
echo "ok body pages=$N (cover excluded)"

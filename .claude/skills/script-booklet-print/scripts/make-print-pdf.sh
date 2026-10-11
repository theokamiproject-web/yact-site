#!/bin/bash
# Usage: make-print-pdf.sh <body.html> <out_dir> <expected_body_pages>
# HTML (vivliostyle, @page bleed:3mm) -> K-only outlined PDF -> page-count check -> one file per page.
# Run from the directory holding the builder. Needs: vivliostyle (node_modules/.bin), gs, poppler.
set -e
HTML=$1; OUT=$2; EXP=$3; V=${VIVLIO:-/home/user/yact-site/node_modules/.bin/vivliostyle}
mkdir -p "$OUT/work" "$OUT/in"
$V build "$HTML" -o "$OUT/body_raw.pdf" >/dev/null 2>&1
# Gray = K-only (mono print). NoOutputFonts = outlines, so no font embedding problems at the printer.
gs -q -dBATCH -dNOPAUSE -sDEVICE=pdfwrite -dCompatibilityLevel=1.4 -dNoOutputFonts -dEmbedAllFonts=true \
   -sColorConversionStrategy=Gray -dProcessColorModel=/DeviceGray -sOutputFile="$OUT/body.pdf" "$OUT/body_raw.pdf"
N=$(pdfinfo "$OUT/body.pdf" | awk '/^Pages:/{print $2}')
[ "$N" = "$EXP" ] || { echo "ERROR pages=$N expected=$EXP (a build step that exits 0 may still have failed: check the builder's stderr)"; exit 1; }
rm -f "$OUT"/work/b*.pdf; pdfseparate "$OUT/body.pdf" "$OUT/work/b%03d.pdf"
echo "ok body pages=$N"

#!/bin/bash
# Usage: assemble-final.sh <out_dir> <body.pdf> <front.pdf>[,<front2.pdf>...] <back.pdf>[,<back2.pdf>...] [expected_TOTAL]
#   front = cover pages placed before the body (表1,表2), back = after (表3,表4). Each may be a multi-page PDF.
# Verifies: TOTAL = front pages + body pages + back pages (and = expected_TOTAL if given),
#           all pages the same size, then sets TrimBox (3mm bleed inset), writes out_dir/all.pdf and out_dir/single/NN.pdf.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=$1; BODY=$2; FRONT=$3; BACK=$4; EXPT=$5
IFS=, read -ra F <<<"$FRONT"; IFS=, read -ra B <<<"$BACK"
pc() { pdfinfo "$1" | awk '/^Pages:/{print $2}'; }
NF=0; for f in "${F[@]}"; do NF=$((NF+$(pc "$f"))); done
NB=0; for f in "${B[@]}"; do NB=$((NB+$(pc "$f"))); done
NBODY=$(pc "$BODY"); WANT=$((NF+NBODY+NB))
mkdir -p "$OUT/single"; rm -f "$OUT"/single/*.pdf
pdfunite "${F[@]}" "$BODY" "${B[@]}" "$OUT/all_raw.pdf"
TOTAL=$(pc "$OUT/all_raw.pdf")
[ "$TOTAL" = "$WANT" ] || { echo "ERROR total=$TOTAL but front($NF)+body($NBODY)+back($NB)=$WANT"; exit 1; }
if [ -n "$EXPT" ] && [ "$TOTAL" != "$EXPT" ]; then echo "ERROR total=$TOTAL expected=$EXPT"; exit 1; fi
SIZES=$(pdfinfo -f 1 -l "$TOTAL" "$OUT/all_raw.pdf" | awk '/^Page +[0-9]+ size:/{print $4"x"$6}' | sort -u | wc -l)
[ "$SIZES" = 1 ] || { echo "ERROR pages differ in size"; pdfinfo -f 1 -l "$TOTAL" "$OUT/all_raw.pdf" | grep size: | sort | uniq -c; exit 1; }
node "$HERE/set-trimbox.mjs" "$OUT/all_raw.pdf" "$OUT/all.pdf"
pdfseparate "$OUT/all.pdf" "$OUT/single/%02d.pdf"
for f in "$OUT"/single/*.pdf; do node "$HERE/set-trimbox.mjs" "$f" "$f.tmp" && mv "$f.tmp" "$f"; done  # pdfseparate drops TrimBox
NS=$(ls "$OUT/single" | wc -l); [ "$NS" = "$TOTAL" ] || { echo "ERROR singles=$NS total=$TOTAL"; exit 1; }
echo "ok total pages=$TOTAL = front $NF + body $NBODY + back $NB; single files=$NS"

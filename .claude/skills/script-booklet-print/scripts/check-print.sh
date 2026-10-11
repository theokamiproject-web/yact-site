#!/bin/bash
# Usage: check-print.sh <final.pdf>   -> page size/boxes, fonts, colour pages, blank pages
f=$1
pdfinfo -box "$f" | grep -E "Pages|Page size|TrimBox|BleedBox|Encrypted"
echo "--- fonts (expect none when outlined)"; pdffonts "$f" | tail -n +3 | head
echo "--- ink coverage per page: C M Y K"; gs -q -o - -sDEVICE=inkcov "$f" | awk '{n++; if($1+$2+$3>0.00001){print "COLOUR page",n} if($4==0){print "BLANK(white) page",n}}'

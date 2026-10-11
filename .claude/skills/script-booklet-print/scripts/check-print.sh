#!/bin/bash
# Usage: check-print.sh <final.pdf> [expected_total|-] [mono|colour]
# Exit 1 on: wrong page count, mixed page sizes, missing/incorrect TrimBox, fonts present, colour ink in mono mode.
f=$1; EXP=${2:--}; MODE=${3:-mono}; bad=0
N=$(pdfinfo "$f" | awk '/^Pages:/{print $2}')
[ "$EXP" = "-" ] || [ "$N" = "$EXP" ] || { echo "FAIL pages=$N expected=$EXP"; bad=1; }
[ "$(pdfinfo -f 1 -l "$N" "$f" | awk '/^Page +[0-9]+ size:/{print $4"x"$6}' | sort -u | wc -l)" = 1 ] || { echo "FAIL mixed page sizes"; bad=1; }
python3 - "$f" <<'PY' || bad=1
import re,subprocess,sys
o=subprocess.run(['pdfinfo','-box',sys.argv[1]],capture_output=True,text=True).stdout
g=lambda k:[float(x) for x in re.search(k+r':\s+([\d. ]+)',o).group(1).split()]
m,t=g('MediaBox'),g('TrimBox'); mm=3*72/25.4
ok=abs(t[0]-mm)<.3 and abs(t[1]-mm)<.3 and abs((m[2]-t[2])-mm)<.3 and abs((m[3]-t[3])-mm)<.3
print('TrimBox', t, 'OK (3mm inset)' if ok else 'FAIL (expected 3mm bleed inset)'); sys.exit(0 if ok else 1)
PY
NF=$(pdffonts "$f" | tail -n +3 | wc -l); [ "$NF" = 0 ] && echo "fonts: none (outlined)" || { echo "FAIL fonts embedded: $NF"; bad=1; }
INK=$(gs -q -o - -sDEVICE=inkcov "$f")
echo "$INK" | awk -v mode=$MODE '{n++; if(mode=="mono" && ($1+$2+$3)>0.00001){print "FAIL colour ink on page",n; b=1} if($4==0 && $1+$2+$3==0) w=w" "n} END{print "white pages:" w; exit b}' || bad=1
[ $bad = 0 ] && echo "PASS" || { echo "CHECK FAILED"; exit 1; }

#!/bin/bash
# Minimal reproduction test: artificial fixture -> build -> body PDF -> total PDF -> checks. Exit 0 = all pass.
# Run from anywhere:  bash .claude/skills/script-booklet-print/tests/run-fixture-test.sh
set -u
T=$(cd "$(dirname "$0")" && pwd); S=$(dirname "$T"); W=${TMPDIR:-/tmp}/sbp-fixture; rm -rf "$W"; mkdir -p "$W"
pass=0; fail=0
ok()  { echo "PASS  $1"; pass=$((pass+1)); }
ng()  { echo "FAIL  $1"; fail=$((fail+1)); }
chk() { if eval "$2"; then ok "$1"; else ng "$1"; fi; }
python3 "$T/make-fixture.py" "$W" || exit 1
node "$T/make-covers.mjs" "$W" || exit 1
# 1 build (small, real layout settings) -----------------------------------------------------------
export SRC="$W/source.txt" CORR_FILE="$W/corr.tsv" SIZE="182mm 257mm" FS=9.1 LH=1.76 FIELD=3.4 MT=17 MB=19 MO=13 MI=21 COLS=2 SPEAKERS="山田,長谷川アンナ,佐藤" \
       NODOOR=1 ENDBLANK=1 LASTON=1 NOTICE="お問い合わせは下記まで。" MAIL="test@example.com"
python3 "$S/templates/build-script-booklet.py" "$W/body.html" >"$W/build.log" 2>&1; chk "builder runs" "[ -s $W/body.html ]"
chk "CORR applied (approved fix only)" "! grep -q '繰り返します。同じ文を繰り返します。' $W/body.html"
chk "apostrophe is not an HTML entity in the page text (tcy skips entities)" "grep -q 'Let&#x27;s' $W/body.html && ! grep -q '&#x<span' $W/body.html"
chk "long role label is shrunk (class long)" "grep -q 'nn long' $W/body.html"
chk "digits become tcy" "grep -q 'class=\"tcy\">12' $W/body.html"
# 2 body PDF + body page-count check ---------------------------------------------------------------
bash "$S/scripts/make-print-pdf.sh" "$W/body.html" "$W/out" any >"$W/mk.log" 2>&1; chk "make-print-pdf (any) succeeds" "[ -f $W/out/body.pdf ]"
NB=$(pdfinfo "$W/out/body.pdf" | awk '/^Pages:/{print $2}')
chk "fixture body is 5..8 pages (got $NB)" "[ $NB -ge 5 ] && [ $NB -le 8 ]"
bash "$S/scripts/make-print-pdf.sh" "$W/body.html" "$W/out2" $((NB+1)) >"$W/neg1.log" 2>&1; chk "wrong expected BODY page count is rejected (for that reason)" "[ $? -ne 0 ] && grep -q 'expected=$((NB+1))' $W/neg1.log"
bash "$S/scripts/make-print-pdf.sh" "$W/body.html" "$W/out3" $NB >/dev/null 2>&1; chk "correct expected BODY page count accepted" "[ $? -eq 0 ]"
# 3 text checks on the pre-outline PDF (outlined PDFs cannot be read by pdftotext) ------------------
chk "last body page carries the notice + mail" "pdftotext -f $NB -l $NB $W/out/body_raw.pdf - | tr -d '\n ' | grep -q 'お問い合わせは下記まで。test@example.com'"
chk "notice appears ONLY on the last page" "[ \$(pdftotext -f 1 -l $((NB-1)) $W/out/body_raw.pdf - | grep -c 'お問い合わせ') -eq 0 ]"
chk "終 is on the page before the last" "pdftotext -f $((NB-1)) -l $((NB-1)) $W/out/body_raw.pdf - | grep -q 終"
chk "no literal '&#x27;' in text" "! pdftotext $W/out/body_raw.pdf - | grep -q '&#x27;'"
chk "raw PDF has fonts (so the outline check can discriminate)" "[ \$(pdffonts $W/out/body_raw.pdf | tail -n +3 | wc -l) -gt 0 ]"
# 4 gray conversion on a colour cover, then assemble total --------------------------------------------
chk "cover fixture is colour before conversion" "gs -q -o - -sDEVICE=inkcov $W/c1.pdf | awk '{if(\$1+\$2+\$3>0.001)f=1} END{exit !f}'"
bash "$S/scripts/to-gray.sh" "$W/c1.pdf" "$W/g1.pdf"
for i in 2 3 4; do bash "$S/scripts/to-gray.sh" "$W/c$i.pdf" "$W/g$i.pdf"; done
bash "$S/scripts/assemble-final.sh" "$W/final" "$W/out/body.pdf" "$W/g1.pdf,$W/g2.pdf" "$W/g3.pdf,$W/g4.pdf" $((NB+4)) >"$W/as.log" 2>&1; chk "assemble: total = body + 4 covers" "grep -q 'total pages=$((NB+4))' $W/as.log"
bash "$S/scripts/assemble-final.sh" "$W/final_bad" "$W/out/body.pdf" "$W/g1.pdf,$W/g2.pdf" "$W/g3.pdf,$W/g4.pdf" $NB >"$W/neg2.log" 2>&1; chk "assemble rejects an expected total that forgets the covers (for that reason)" "[ $? -ne 0 ] && grep -q 'expected=$NB' $W/neg2.log"
chk "single files = total" "[ \$(ls $W/final/single | wc -l) -eq $((NB+4)) ]"
bash "$S/scripts/check-print.sh" "$W/final/all.pdf" $((NB+4)) mono >"$W/ck.log" 2>&1; chk "check-print passes on final (TrimBox, mono, no fonts, size)" "grep -q PASS $W/ck.log"
chk "TrimBox 182x257mm on a single-page file" "[ -f $W/final/single/03.pdf ] && pdfinfo -box $W/final/single/03.pdf | grep TrimBox | awk '{w=\$4-\$2; h=\$5-\$3; exit !(w>515.5 && w<516.3 && h>728 && h<729)}'"
chk "colour cover became K-only" "gs -q -o - -sDEVICE=inkcov $W/final/single/01.pdf | awk '{if(\$1+\$2+\$3>0.00001)f=1; if(\$4<=0)z=1} END{exit f||z}'"
chk "covers 2,3,4 stay white" "bash $S/scripts/check-print.sh $W/final/all.pdf - mono | grep -q 'white pages: 2 $((NB+3)) $((NB+4))'"
# negative: raw (fonts + colour) PDF must FAIL the checker
cp "$W/out/body_raw.pdf" "$W/raw_final.pdf"; node "$S/scripts/set-trimbox.mjs" "$W/raw_final.pdf" "$W/raw_final2.pdf"
bash "$S/scripts/check-print.sh" "$W/raw_final2.pdf" - mono >"$W/neg3.log" 2>&1; chk "checker rejects PDF with embedded fonts (for that reason)" "[ $? -ne 0 ] && grep -q 'FAIL fonts embedded' $W/neg3.log"
echo "---- $pass passed, $fail failed"; [ $fail -eq 0 ]

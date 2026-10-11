#!/bin/bash
# 最小再現テスト: SVG → PDF → Gray/K → TrimBox → ラスター/フォント/RGB残存検査。正常系1 + 不適合4(拒否されること)。
# 前提: NODE_MODULES (opentype.js, @fontsource/noto-serif-jp), PLAYWRIGHT_DIR (playwright|playwright-core), 任意 CHROMIUM_PATH,
#       python: pikepdf numpy pillow, poppler。足りなければ exit 3（スキップ扱いで緑にしない）。
set -u; T=$(cd "$(dirname "$0")" && pwd); S=$(dirname "$T")/scripts; W=${TMPDIR:-/tmp}/pcp-fixture; rm -rf "$W"; mkdir -p "$W"
pass=0; fail=0; ok() { echo "PASS  $1"; pass=$((pass+1)); }; ng() { echo "FAIL  $1"; fail=$((fail+1)); }
bash "$S/env_check.sh" "${NODE_MODULES:-}" || { echo "環境不足のためテスト不能 (exit 3)"; exit 3; }
node "$T/make-fixture.mjs" "$NODE_MODULES" "$W" >/dev/null || { echo "fixture 生成失敗"; exit 1; }
PW=${PLAYWRIGHT_DIR:-}; Wd=188; Hd=263; BL=3
# 正常系
bash "$S/run_pipeline.sh" "$W/pass.svg" "$W/pass.pdf" $Wd $Hd $BL 8 20 >"$W/pass.log" 2>&1 && ok "正常系: 全パイプラインPASS" || { ng "正常系 (log: $W/pass.log)"; tail -15 "$W/pass.log"; }
grep -q "^PASS" "$W/pass.log" && ok "check_pdf が PASS を出力" || ng "check_pdf PASS 出力なし"
pdfinfo -box "$W/pass.pdf" | awk '/TrimBox/{w=$4-$2; h=$5-$3; exit !(w>515.5 && w<516.3 && h>728 && h<729)}' && ok "TrimBox = 182x257mm (ページ-3mm)" || ng "TrimBox"
[ "$(pdfimages -list "$W/pass.pdf" | tail -n +3 | wc -l)" = 0 ] && [ "$(pdffonts "$W/pass.pdf" | tail -n +3 | wc -l)" = 0 ] && ok "画像0・フォント0" || ng "画像/フォント残存"
python3 - "$W/pass.pdf" <<'PY' && ok "ベクター保持(パス演算子あり)・RGB演算子0" || ng "ベクター/RGB"
import sys, re, pikepdf
pdf = pikepdf.open(sys.argv[1]); p = pdf.pages[0]; d = b'\n'.join(s.read_bytes() for s in ([p.Contents] if not isinstance(p.Contents, pikepdf.Array) else p.Contents))
sys.exit(0 if re.search(rb'(?:^|\s)(?:f\*?|S|B)(?:\s|$)', d) and not re.search(rb'(?:-?[\d.]+ ){3}(?:rg|RG)\b', d) else 1)
PY
# 不適合: どれも「拒否される」ことを、拒否理由まで確認
neg() { # name svg expected-message-regex
  node "$S/svg2pdf.cjs" "$W/$2" "$W/$1.raw.pdf" "$PW" >/dev/null 2>&1 || { ng "$1: svg2pdf 自体が失敗"; return; }
  python3 "$S/gray_pdf.py" "$W/$1.raw.pdf" "$W/$1.pdf" $Wd $Hd $BL >"$W/$1.log" 2>&1; python3 "$S/check_pdf.py" "$W/$1.pdf" --size $Wd $Hd --bleed $BL --min-margin 8 >>"$W/$1.log" 2>&1; rc=$?
  if grep -qE "$3" "$W/$1.log" && { [ $rc -ne 0 ] || grep -q "^NG" "$W/$1.log"; }; then ok "不適合を拒否: $1 ($3)"; else ng "不適合を拒否できない: $1"; tail -8 "$W/$1.log"; fi; }
neg color neg-color.svg "K単色違反|非グレー|NG  RGB"
neg raster neg-raster.svg "NG  ラスター画像"
neg text neg-text.svg "NG  (フォント|テキスト層)"
python3 "$S/check_pdf.py" "$W/pass.pdf" --size 182 257 --bleed 3 >"$W/size.log" 2>&1; grep -q "NG  MediaBox" "$W/size.log" && ok "不適合を拒否: 寸法違い(MediaBox)" || ng "寸法違いを拒否できない"
# 環境不足は黙って成功しない
node "$S/svg2pdf.cjs" "$W/pass.svg" "$W/x.pdf" /nonexistent-dir >/dev/null 2>&1; [ $? -ne 0 ] && ok "playwright 不在なら svg2pdf は失敗(exit≠0)" || ng "playwright 不在でも成功扱い"
NODE_MODULES=/nonexistent bash "$S/env_check.sh" >/dev/null 2>&1; [ $? -ne 0 ] && ok "env_check は依存不足で exit≠0" || ng "env_check が不足を見逃す"
python3 "$S/public_audit.py" "$(dirname "$T")" >"$W/aud.log" 2>&1 && ok "公開監査: このSkillに個人情報/金額/絶対パス/鍵なし" || { ng "公開監査"; cat "$W/aud.log"; }
echo "---- $pass passed, $fail failed"; [ $fail -eq 0 ]

#!/usr/bin/env python3
# 回帰テスト（合成図形・仮の文言のみ）。使い方: NODE_MODULES=<opentype.js・@fontsource/*・playwright（任意で roughjs）を含む node_modules> python3 tests/run_tests.py
import os, sys, subprocess, tempfile, glob
H = os.path.dirname(os.path.abspath(__file__)); S = os.path.join(H, '..', 'scripts'); TS = os.path.join(H, '..', '..', 'tshirt-order-handoff', 'scripts')
NM = os.environ['NODE_MODULES']; os.environ.setdefault('PLAYWRIGHT_DIR', os.path.join(NM, 'playwright')); T = tempfile.mkdtemp(); fails = []
def run(*c): r = subprocess.run(c, capture_output=True, text=True); return r.returncode, r.stdout + r.stderr
def check(n, ok, out=''): print('PASS' if ok else 'FAIL', n); ok or fails.append(n) or print('   ', out.strip()[:800])
c, o = run('node', f'{S}/example.mjs', NM, f'{T}/ex.svg'); check('example.mjs（lib の既定書体・後方互換）', c == 0, o)
c, o = run('node', f'{S}/skeletons.mjs', NM, f'{T}/sk', '182', '257'); svgs = sorted(glob.glob(f'{T}/sk/*.svg')); check('skeletons.mjs で骨格3案', c == 0 and len(svgs) == 3, o)
pngs = []
for f in svgs: p = f[:-4] + '.png'; run('node', f'{TS}/svg2png.cjs', f, p, '4'); pngs.append(p)
c, o = run('python3', f'{S}/review_sheet.py', f'{T}/sheet.png', *pngs); check('骨格の違う3案 → 講評ゲート通過(0)', c == 0 and os.path.exists(f'{T}/sheet.png'), o)
c, o = run('python3', f'{S}/review_sheet.py', f'{T}/s2.png', pngs[0], pngs[0]); check('同じ骨格の2案 → 似すぎ(1)', c == 1 and '似すぎ' in o, o)
open(f'{T}/shape.svg', 'w').write('<svg xmlns="http://www.w3.org/2000/svg" width="60mm" height="40mm" viewBox="0 0 60 40"><circle cx="20" cy="20" r="12" fill="none" stroke="#000" stroke-width="1.5"/><path d="M34 34L56 6" stroke="#000" stroke-width="2"/></svg>')
run('node', f'{TS}/svg2png.cjs', f'{T}/shape.svg', f'{T}/shape.png', '12')
c, o = run('python3', f'{S}/roughen.py', f'{T}/shape.png', '12', f'{T}/rough.svg', '--dry', '0.1'); check('roughen.py → パスSVG', c == 0 and '<image' not in open(f'{T}/rough.svg').read(), o)
run('node', f'{TS}/svg2png.cjs', f'{T}/rough.svg', f'{T}/rough.png', '12')
from PIL import Image; import numpy as np
a = np.asarray(Image.open(f'{T}/shape.png').convert('L')) < 128; b = np.asarray(Image.open(f'{T}/rough.png').convert('L')) < 128
check('roughen の白黒が反転していない（重なり率 > 60%）', (a & b).sum() / a.sum() > .6, f'{(a & b).sum() / a.sum():.2f}')
sk = svgs[0]; c1, o1 = run('node', f'{S}/svg2pdf.cjs', sk, f'{T}/raw.pdf'); c2, o2 = run('python3', f'{S}/gray_pdf.py', f'{T}/raw.pdf', f'{T}/a.pdf', '182', '257')
c3, o3 = run('python3', f'{S}/check_pdf.py', f'{T}/a.pdf', '5', '182', '257'); check('骨格案 → 入稿PDF（フォント0・画像0・寸法・余白）', c1 == c2 == 0 and 'NG' not in o3, o1 + o2 + o3)

# --- slop_check / 縦組み約物 / sketchy ---
bad = f'{T}/bad.svg'; open(bad, 'w').write('<svg xmlns="http://www.w3.org/2000/svg" width="182mm" height="257mm" viewBox="0 0 182 257"><rect width="182" height="257" fill="#fff"/><g fill="none" stroke="#000" stroke-width="1"><rect x="55" y="80" width="30" height="30"/><rect x="95" y="80" width="30" height="30"/><circle cx="91" cy="115" r="12"/><circle cx="91" cy="115" r="28"/></g></svg>')
run('node', f'{TS}/svg2png.cjs', bad, f'{T}/bad.png', '4')
c, o = run('python3', f'{S}/slop_check.py', f'{T}/bad.png'); check('slop_check: 縮こまり・線幅均一を検出(1)', c == 1 and 'R1' in o and 'R6' in o, o)
c, o = run('python3', f'{S}/slop_check.py', *pngs); check('slop_check: 骨格3案は指摘なし(0)', c == 0, o)
open(f'{T}/vt.mjs', 'w').write(f"import fs from 'node:fs'; import {{ makeLib }} from '{S}/lib.mjs'; const L = makeLib({{ nodeModules: '{NM}', pageMM: [40, 60] }}); const a = L.vtext('花、ざ」ー', 8, 20, 5, 700), b = L.vtext('花ざ', 8, 20, 5, 700); fs.writeFileSync('{T}/vt.json', JSON.stringify([a.d, b.d]));")
c, o = run('node', f'{T}/vt.mjs'); import json; da, db = json.load(open(f'{T}/vt.json')) if c == 0 else ('', '')
check('lib.vtext: 約物を含む文言で曲線化できる・通常字は影響なし', c == 0 and da != db and len(da) > len(db), o)
c, o = run('node', f'{S}/sketchy.mjs', NM, f'{T}/shape.svg', f'{T}/sk.svg'); has = os.path.exists(f'{NM}/roughjs')
check('sketchy.mjs（roughjs があれば）→ パスのみのSVG', (c == 0 and '<path' in open(f'{T}/sk.svg').read() and '<image' not in open(f'{T}/sk.svg').read()) if has else True, o)
print(f'\n{"全PASS" if not fails else f"FAIL {len(fails)}件"}  (作業: {T})'); sys.exit(1 if fails else 0)

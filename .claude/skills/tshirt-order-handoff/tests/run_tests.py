#!/usr/bin/env python3
# 回帰テスト（合成図形のみ。実案件のロゴ・氏名は入れない）。使い方: PLAYWRIGHT_DIR=... python3 tests/run_tests.py
import os, sys, subprocess, tempfile
from PIL import Image
import numpy as np
H = os.path.dirname(os.path.abspath(__file__)); S = os.path.join(H, '..', 'scripts'); PC = os.path.join(H, '..', '..', 'print-cover-pdf', 'scripts')
T = tempfile.mkdtemp(); fails = []
def svg(name, body, w=40, h=30, pre=''):
    p = os.path.join(T, name); open(p, 'w').write(f'{pre}<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}mm" height="{h}mm">{body}</svg>'); return p
def run(*c): r = subprocess.run(c, capture_output=True, text=True); return r.returncode, r.stdout + r.stderr
def check(name, cond, out=''):
    print('PASS' if cond else 'FAIL', name); cond or fails.append(name) or print('   ', out.strip().replace('\n', '\n    '))
def plate_png(src, *opt):
    pl, png = src.replace('.svg', '-plate.svg'), src.replace('.svg', '.png')
    c, o = run('python3', f'{S}/make_plate.py', src, pl, *(opt or ('--all',)))
    if c: return c, o, None
    c2, o2 = run('node', f'{S}/svg2png.cjs', pl, png, '12'); return c2, o + o2, png
def fc(png, *x): return run('python3', f'{S}/feature_check.py', png, '12', '1', '2', *x)

# 1) 太い線・広い隙間 → 0
c, o, png = plate_png(svg('ok.svg', ''.join(f'<rect x="{5+i*8}" y="5" width="3" height="20"/>' for i in range(4))))
check('太線3mm/隙間5mm → 終了0', png and fc(png)[0] == 0, o + (fc(png)[1] if png else ''))
# 2) 0.5mm の細線 → 1、overlay が出る
c, o, png = plate_png(svg('thin.svg', ''.join(f'<rect x="{5+i*4}" y="5" width="0.5" height="20"/>' for i in range(6))))
ov = os.path.join(T, 'ov.png'); c2, o2 = fc(png, '--overlay', ov) if png else (None, o)
check('細線0.5mm → 終了1', c2 == 1, o2); check('overlay に赤(消える線)がある', os.path.exists(ov) and bool(((np.asarray(Image.open(ov).convert('RGB')) == (220, 30, 30)).all(-1)).any()), o2)
# 3) 空の版 → 2（make_plate も feature_check も）
c, o = run('python3', f'{S}/make_plate.py', svg('k.svg', '<rect x="5" y="5" width="10" height="10"/>'), os.path.join(T, 'e.svg'), '--ink', '#ff0000')
check('該当色なし → make_plate 終了2', c == 2, o)
blank = os.path.join(T, 'blank.png'); Image.new('L', (100, 100), 255).save(blank); c, o = fc(blank); check('白紙PNG → feature_check 終了2（nanで不適合にしない）', c == 2 and 'nan' not in o, o)
# 4) <?xml?> 宣言 + transform + evenodd の穴が保たれる
ring = '<g transform="translate(20 15)"><path fill-rule="evenodd" d="M-10-10H10V10H-10Z M-5-5H5V5H-5Z"/></g>'
c, o, png = plate_png(svg('ring.svg', ring, pre='<?xml version="1.0" encoding="UTF-8"?>\n'))
im = Image.open(png).convert('L') if png else None
check('xml宣言・transform 対応、evenodd の穴が白のまま', im and im.getpixel((20 * 12, 15 * 12)) > 200 and im.getpixel((20 * 12 - 90, 15 * 12)) < 60, o)
# 5) 未アウトライン文字・ラスター → 2
c, o = run('python3', f'{S}/make_plate.py', svg('t.svg', '<text x="5" y="20">A</text>'), os.path.join(T, 't2.svg'), '--all'); check('<text> → 停止 終了2', c == 2 and '未アウトライン' in o, o)
c, o = run('python3', f'{S}/make_plate.py', svg('i.svg', '<image href="x.png" width="5" height="5"/>'), os.path.join(T, 'i2.svg'), '--all'); check('<image> → 停止 終了2', c == 2 and 'ラスター' in o, o)
# 6) 2色の色分解（style属性の色・継承・線も拾う）
two = '<g style="fill:#E9E3D3"><rect x="2" y="2" width="10" height="10"/></g><rect x="20" y="2" width="10" height="10" fill="#D8325A"/><line x1="2" y1="25" x2="30" y2="25" stroke="#e9e3d3" stroke-width="2"/>'
src = svg('two.svg', two); out = os.path.join(T, 'bone.svg'); c, o = run('python3', f'{S}/make_plate.py', src, out, '--ink', '#E9E3D3')
check('色分解: 生成り版は2要素（塗り1+線1）', c == 0 and '(2 要素' in o, o)
# 7) preflight: テキスト検査と了承文言
good = os.path.join(T, 'README.txt'); open(good, 'w').write('【共通】下地（白）が必要。位置は着用者から見て左胸。')
loss = os.path.join(T, 'mail.md'); open(loss, 'w').write('下地は白インク。着用者から見て左。細部が再現されなくても構いません。電話【　】')
c, o = run('python3', f'{S}/preflight.py', '--text', good); check('preflight 文言OK（下地（白）表記・見出しの【】は欄扱いしない）→ 0', c == 0 and 'WARN' not in o, o)
c, o = run('python3', f'{S}/preflight.py', '--text', loss); check('了承なしで「再現なし」文言 → 1', c == 1, o)
c, o = run('python3', f'{S}/preflight.py', '--text', loss, '--accept-loss'); check('--accept-loss + 文言あり → 0、【】は警告', c == 0 and 'WARN' in o, o)
# 8) preflight: ベクターPDF（print-cover-pdf の svg2pdf.cjs で生成）
pdf = os.path.join(T, 'ok.pdf'); c, o = run('node', f'{PC}/svg2pdf.cjs', os.path.join(T, 'ok-plate.svg'), pdf)
c2, o2 = run('python3', f'{S}/preflight.py', '--pdf', f'{pdf}:40:30', '--zip', os.path.join(T, 'p.zip'), T) if c == 0 else (None, o)
check('preflight PDF（フォント0・画像0・寸法）→ 0 と zip', c2 == 0 and os.path.exists(os.path.join(T, 'p.zip')), o2)
print(f'\n{"全PASS" if not fails else f"FAIL {len(fails)}件"}  (作業: {T})'); sys.exit(1 if fails else 0)

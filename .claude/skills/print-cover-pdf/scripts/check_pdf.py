#!/usr/bin/env python3
# 入稿前チェック。使い方: check_pdf.py file.pdf MIN_MARGIN_MM [W_mm H_mm]
# 確認: ページ寸法 / フォント埋め込み0（曲線化済み）/ 画像0 / 端からの余白(mm)実測 / 黒面積% / 淡グレー率
import sys, subprocess, numpy as np
from PIL import Image
f, mm_min = sys.argv[1], float(sys.argv[2]); size = (float(sys.argv[3]), float(sys.argv[4])) if len(sys.argv) > 4 else None
info = subprocess.run(['pdfinfo', f], capture_output=True, text=True).stdout; ps = [l for l in info.splitlines() if 'Page size' in l][0]
w_pt, h_pt = [float(x) for x in ps.split(':')[1].replace('pts', '').split('x')]; W, H = w_pt / 72 * 25.4, h_pt / 72 * 25.4
nf = len(subprocess.run(['pdffonts', f], capture_output=True, text=True).stdout.strip().splitlines()) - 2
ni = len(subprocess.run(['pdfimages', '-list', f], capture_output=True, text=True).stdout.strip().splitlines()) - 2
subprocess.run(['pdftoppm', '-r', '150', '-png', '-singlefile', f, '/tmp/_chk'], check=True)
im = np.asarray(Image.open('/tmp/_chk.png').convert('L')); ys, xs = np.where(im < 250); d = 150 / 25.4
m = dict(L=xs.min() / d, R=(im.shape[1] - xs.max()) / d, T=ys.min() / d, B=(im.shape[0] - ys.max()) / d)
ok = lambda c: 'OK ' if c else 'NG '
print(f'寸法 {W:.1f}x{H:.1f}mm', ok(size is None or (abs(W - size[0]) < 0.3 and abs(H - size[1]) < 0.3)), f'| フォント埋め込み {nf}', ok(nf == 0), f'| 画像 {ni}', ok(ni == 0))
print('余白mm ' + ' '.join(f'{k}{v:.1f}' for k, v in m.items()), ok(min(m.values()) >= mm_min), f'(基準 {mm_min}mm)')
print(f'黒面積 {100*(im < 128).mean():.1f}% / 淡グレー(60-240) {100*((im >= 60) & (im < 240)).mean():.1f}%  ※大きな黒面は避ける。10〜15%超なら面を線・網点に')

#!/usr/bin/env python3
# 「コードで描いた完璧な線」に手の痕跡（揺らぎ・かすれ・太さムラ）を足し、ベクター（パスのみ）で返す。
# SVGフィルタ(feTurbulence)はPDFでラスター化され check_pdf の画像>0 になるので使わない → ラスタで崩して potrace で戻す。
# 使い方: roughen.py in.png PX_PER_MM out.svg [--wobble 0.4] [--scale 6] [--grain 0.1] [--dry 0] [--seed 1]
#   in.png: 黒=インク（svg2png 等で 12px/mm 以上に書き出した図）。文字は対象外にして、図形レイヤーだけを通すのが基本。
#   --wobble mm: 線の揺らぎ量／--scale mm: 揺らぎの波長（大きいほどゆったり）／--grain mm: 縁のざらつき
#   --dry 0〜0.3: かすれ（インクの抜け）の割合。0.1 前後から試す。上げすぎると汚く見える。
# 出力: width/height=mm の SVG（<path> 1本, fill=#000）。lib.mjs の embed や <g transform> でそのまま重ねられる。
import sys, argparse, numpy as np, potrace
from PIL import Image
from scipy import ndimage as ndi

ap = argparse.ArgumentParser(); ap.add_argument('png'); ap.add_argument('ppm', type=float); ap.add_argument('out')
ap.add_argument('--wobble', type=float, default=.4); ap.add_argument('--scale', type=float, default=6)
ap.add_argument('--grain', type=float, default=.1); ap.add_argument('--dry', type=float, default=0); ap.add_argument('--seed', type=int, default=1)
a = ap.parse_args(); rng = np.random.default_rng(a.seed); p = a.ppm
m = np.asarray(Image.open(a.png).convert('L')) < 128
if not m.any(): print('停止: インクがない'); sys.exit(2)
pad = int(np.ceil((a.wobble + a.grain) * p * 3)) + 2; m = np.pad(m, pad); h, w = m.shape
def field(sig_mm):  # 平均0・標準偏差1のなめらかなノイズ
    f = ndi.gaussian_filter(rng.standard_normal((h, w)), max(.5, sig_mm * p)); return (f - f.mean()) / (f.std() + 1e-9)
yy, xx = np.mgrid[0:h, 0:w].astype(float)
dx, dy = field(a.scale) * a.wobble * p, field(a.scale) * a.wobble * p          # 大きな揺らぎ（線がまっすぐでなくなる）
dx += field(a.grain * 2) * a.grain * p; dy += field(a.grain * 2) * a.grain * p  # 細かいざらつき（縁）
r = ndi.map_coordinates(m.astype(float), [yy + dy, xx + dx], order=1) > .5
if a.dry > 0:  # かすれ: 小さな抜けの粒（方向を固定すると機械的に見えたので等方）
    g = ndi.gaussian_filter(rng.standard_normal((h, w)), max(.5, .35 * p))
    r &= g < np.quantile(g[r], 1 - a.dry) if r.any() else r
lab, n = ndi.label(r); sizes = ndi.sum(r, lab, range(1, n + 1))
r = np.isin(lab, 1 + np.flatnonzero(sizes >= (0.3 * p) ** 2))  # 0.3mm角未満の粒は消す（印刷で飛ぶ）
paths = potrace.Bitmap(~r).trace(turdsize=2, alphamax=1.0, opttolerance=.2)  # potracer は白黒を逆に解釈する（raster-to-vector.md の落とし穴）
k = 1 / p; f = lambda q: f'{(q.x - pad) * k:.3f} {(q.y - pad) * k:.3f}'; d = ''
for c in paths:
    d += 'M' + f(c.start_point)
    for s in c.segments: d += ('L' + f(s.c) + 'L' + f(s.end_point)) if s.is_corner else ('C' + f(s.c1) + ' ' + f(s.c2) + ' ' + f(s.end_point))
    d += 'Z'
W, H = (w - 2 * pad) * k, (h - 2 * pad) * k
open(a.out, 'w').write(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.2f}mm" height="{H:.2f}mm" viewBox="0 0 {W:.2f} {H:.2f}"><path fill="#000" fill-rule="evenodd" d="{d}"/></svg>')
print('roughen:', a.out, f'{W:.1f}x{H:.1f}mm', f'インク面積 元比 {100 * r.sum() / m.sum():.0f}%')

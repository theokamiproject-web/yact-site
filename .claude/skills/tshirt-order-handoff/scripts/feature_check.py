#!/usr/bin/env python3
# 版（インク面）が、印刷所の最小線幅/最小隙間を満たすかを数値化する。 使い方: feature_check.py plate.png PX_PER_MM MIN_LINE_MM MIN_GAP_MM
# plate.png: 黒=インク・白=抜き（svg2png.cjs の出力）。 例: シルク 線1mm/隙間2mm
import sys, numpy as np
from PIL import Image
from scipy import ndimage as ndi
f, ppm, ml, mg = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4])
m = np.asarray(Image.open(f).convert('L')) < 128; tot = m.sum()
def disk(r): y, x = np.ogrid[-r:r + 1, -r:r + 1]; return x * x + y * y <= r * r
op = ndi.binary_opening(m, disk(max(1, int(round(ml / 2 * ppm))))); cl = ndi.binary_closing(m, disk(max(1, int(round(mg / 2 * ppm)))))
lost = 100 * (1 - op.sum() / tot); filled = 100 * (cl.sum() - tot) / tot
print(f'{ml}mm未満の線として消えるインク {lost:.1f}% / {mg}mm未満の隙間で埋まる量(インク面積比) {filled:.1f}%')
print('判定:', '問題小(<3%)' if max(lost, filled) < 3 else '要確認(3〜10%)' if max(lost, filled) < 10 else '不適合の可能性大(>=10%) → 作り直し/方式変更/現状で入稿(再現性なしを了承)を選ばせる')

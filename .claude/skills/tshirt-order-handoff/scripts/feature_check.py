#!/usr/bin/env python3
# 版（インク面）が、印刷会社の最小線幅/最小隙間を満たすかを数値化する。
# 使い方: feature_check.py plate.png --ppm PX_PER_MM --min-line MM --min-gap MM [--warn PCT --reject PCT]
#   plate.png: 【黒=インク・白=抜き】（svg2png.cjs の出力）。--min-line/--min-gap は【印刷会社の最新仕様の値】を渡す（Skillの固定値ではない）。
#   --warn/--reject は判定の目安(既定 3/10 %: 社内ヒューリスティック。会社が許容基準を示していればそちらを優先)。
# exit: 0=問題小 / 1=不適合の可能性大(reject以上) / 2=要手動確認(要確認帯・二値でない・反転の疑い) / 3=環境不足
import sys, argparse
try: import numpy as np; from PIL import Image; from scipy import ndimage as ndi
except ImportError as e: print(f'ENV NG: python モジュール不足 ({e})'); sys.exit(3)
ap = argparse.ArgumentParser(); ap.add_argument('png'); ap.add_argument('--ppm', type=float, required=True); ap.add_argument('--min-line', type=float, required=True)
ap.add_argument('--min-gap', type=float, required=True); ap.add_argument('--warn', type=float, default=3.0); ap.add_argument('--reject', type=float, default=10.0); a = ap.parse_args()
g = np.asarray(Image.open(a.png).convert('L')); m = g < 128; tot = int(m.sum())
if tot == 0: print('NG: インク面が空（黒=インクの版になっていない可能性）'); sys.exit(2)
mid = 100 * ((g >= 40) & (g <= 215)).mean(); ink = 100 * m.mean(); notes = []
if mid > 5: notes.append(f'中間調 {mid:.1f}%（アンチエイリアス以外のグレーがある。二値の版か確認）')
if ink > 60: notes.append(f'インク面積 {ink:.0f}%（反転=黒地ベタ/白黒逆の疑い。黒=インクの定義を確認）')
disk = lambda r: (lambda y, x: x * x + y * y <= r * r)(*np.ogrid[-r:r + 1, -r:r + 1])
op = ndi.binary_opening(m, disk(max(1, int(round(a.min_line / 2 * a.ppm))))); cl = ndi.binary_closing(m, disk(max(1, int(round(a.min_gap / 2 * a.ppm)))))
lost = 100 * (1 - op.sum() / tot); filled = 100 * (cl.sum() - tot) / tot; worst = max(lost, filled)
print(f'{a.min_line}mm未満の線として消えるインク {lost:.1f}% / {a.min_gap}mm未満の隙間で埋まる量(インク面積比) {filled:.1f}%')
for n in notes: print('注意:', n)
verdict = 'reject' if worst >= a.reject else 'warn' if worst >= a.warn else 'ok'
print('判定:', {'ok': f'問題小(<{a.warn}%)', 'warn': f'要確認({a.warn}〜{a.reject}%)', 'reject': f'不適合の可能性大(>={a.reject}%) → 作り直し/方式変更/現状で入稿(再現性なしの了承)から選ばせる。自動で太らせ続けない'}[verdict])
sys.exit(1 if verdict == 'reject' else 2 if (verdict == 'warn' or notes) else 0)

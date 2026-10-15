#!/usr/bin/env python3
# 版（インク面）が、印刷会社の最小線幅/最小隙間を満たすかを数値化する。合否は会社の値だけで出す（社内の暫定基準は使わない）。
# 使い方: feature_check.py plate.png PX_PER_MM MIN_LINE_MM MIN_GAP_MM [--overlay out.png]
#   plate.png: 黒=インク・白=抜き（svg2png.cjs の出力, 12px/mm 以上推奨）。例: シルク 線1mm/隙間2mm
#   --overlay: 消える線=赤、埋まる隙間=青、残るインク=灰 の確認画像（依頼主への説明・了承用）
# 終了コード: 0=問題小 / 1=要確認・不適合 / 2=対象外（版が空・入力エラー）
# 判定の閾値 3%/10% は1案件からの暫定値。納品物と照らして校正する。縁の誤差は約±1px（12px/mm で ±0.08mm）。
import sys, argparse, numpy as np
from PIL import Image
from scipy import ndimage as ndi

def disk(r): y, x = np.ogrid[-r:r + 1, -r:r + 1]; return x * x + y * y <= r * r
def opening(m, mm, ppm): return ndi.binary_opening(m, disk(max(1, int(round(mm / 2 * ppm)))))
def closing(m, mm, ppm):
    r = max(1, int(round(mm / 2 * ppm))); p = np.pad(m, r)  # 端での誤検出を防ぐ
    return ndi.binary_closing(p, disk(r))[r:-r, r:-r]

def thinnest(m, ppm, f, tot, limit, step=0.1, ratio=1.0):
    # インクの ratio% 以上が変化し始める幅(mm)。limit まで変化しなければ None（=基準を十分に満たす）
    w = step
    while w <= limit + 1e-9:
        d = abs(f(m, w, ppm).sum() - tot) / tot * 100
        if d >= ratio: return w
        w = round(w + step, 3)
    return None

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('png'); ap.add_argument('ppm', type=float)
    ap.add_argument('min_line', type=float); ap.add_argument('min_gap', type=float); ap.add_argument('--overlay')
    a = ap.parse_args()
    m = np.asarray(Image.open(a.png).convert('L')) < 128; tot = int(m.sum())
    if tot == 0: print('判定: 対象外（版が空。インクがない）'); sys.exit(2)
    op, cl = opening(m, a.min_line, a.ppm), closing(m, a.min_gap, a.ppm)
    lost = 100 * (1 - op.sum() / tot); filled = 100 * (cl.sum() - tot) / tot
    tl = thinnest(m, a.ppm, opening, tot, a.min_line); tg = thinnest(m, a.ppm, closing, tot, a.min_gap)
    print(f'{a.min_line}mm未満の線として消えるインク {lost:.1f}% / {a.min_gap}mm未満の隙間で埋まる量(インク面積比) {filled:.1f}%')
    print('最細の線 ≈', f'{tl:.1f}mm（ここでインクの1%以上が消え始める）' if tl else f'{a.min_line}mm以上',
          '/ 最小の隙間 ≈', f'{tg:.1f}mm（ここで1%以上埋まり始める）' if tg else f'{a.min_gap}mm以上')
    if a.overlay:
        img = np.full(m.shape + (3,), 255, np.uint8); img[m] = (190, 190, 190)
        img[m & ~op] = (220, 30, 30); img[cl & ~m] = (30, 90, 220)
        Image.fromarray(img).save(a.overlay); print('overlay:', a.overlay, '（赤=消える線 / 青=埋まる隙間 / 灰=残るインク）')
    worst = max(lost, filled)
    if worst < 3: print('判定: 問題小(<3%)'); sys.exit(0)
    print('判定:', '要確認(3〜10%)' if worst < 10 else '不適合の可能性大(>=10%) → 作り直し/方式変更(DTF)/現状で入稿(再現性なしを了承)を選ばせる'); sys.exit(1)

if __name__ == '__main__':
    try: main()
    except (OSError, ValueError) as ex: print('判定: 対象外（入力エラー）', ex); sys.exit(2)

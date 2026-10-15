#!/usr/bin/env python3
# 提出前の自己講評ゲート。候補PNG（同じ判型）を並べ、縮小・ぼかし・反転の見え方と数値を1枚にまとめる。
# 使い方: review_sheet.py out.png A.png B.png C.png [--names 文字だけ,図が主役,題字を崩す] [--thumb-mm 30]
# 見るもの（数値は判断材料。最後は画像を自分の目で読む）:
#   縮小(幅30mm相当)で主役と脇役の差が分かるか／ぼかしで塊の配置（骨格）が読めるか／反転で余白の形が良いか
#   黒面積%・要素数・最大要素の占有（主役の強さ）・使っている範囲（スケール）・重心のずれ（動き）
#   骨格の類似度: 候補どうしの塊の配置が似ていたら「骨格が同じ＝モチーフ違いの3案」になっている → 出し直す
# 終了コード: 0=通過 / 1=骨格が似た組がある（類似度 >= --max-sim, 既定 0.85）
import sys, argparse, numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps, ImageFont
from scipy import ndimage as ndi

ap = argparse.ArgumentParser(); ap.add_argument('out'); ap.add_argument('pngs', nargs='+')
ap.add_argument('--names'); ap.add_argument('--thumb-mm', type=float, default=30); ap.add_argument('--max-sim', type=float, default=.85)
a = ap.parse_args(); names = a.names.split(',') if a.names else [chr(65 + i) for i in range(len(a.pngs))]
CELL = 300; TH = int(a.thumb_mm / 25.4 * 96)  # 画面上で幅30mm相当（96dpi）
try: font = ImageFont.truetype('NotoSansCJK-Regular.ttc', 15)
except OSError: font = ImageFont.load_default()

def metrics(im):
    g = np.asarray(im.convert('L')); m = g < 128; tot = m.sum() or 1
    lab, n = ndi.label(ndi.binary_closing(m, iterations=2)); sizes = ndi.sum(m, lab, range(1, n + 1)) if n else np.array([0])
    big = sizes[sizes >= tot * .005]  # 0.5%未満の粒は要素として数えない
    ys, xs = np.nonzero(m); h, w = m.shape
    span = ((xs.max() - xs.min()) * (ys.max() - ys.min())) / (w * h) * 100 if len(xs) else 0
    cy, cx = ndi.center_of_mass(m) if m.any() else (h / 2, w / 2)
    off = np.hypot((cx - w / 2) / w, (cy - h / 2) / h) * 100
    blob = np.asarray(Image.fromarray((~m * 255).astype(np.uint8)).resize((12, 16), Image.BOX), float); blob = 255 - blob
    return dict(黒面積=100 * m.mean(), 要素数=len(big), 主役占有=100 * big.max() / tot if len(big) else 0, 使用範囲=span, 重心ずれ=off), blob

rows = []; blobs = []
for p in a.pngs:
    im = Image.open(p).convert('RGB'); s = CELL / max(im.size); base = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
    t = im.resize((TH, int(im.height * TH / im.width)), Image.LANCZOS)
    blur = base.filter(ImageFilter.GaussianBlur(6)); inv = ImageOps.invert(base)
    mt, bl = metrics(im); rows.append((base, t, blur, inv, mt)); blobs.append(bl.ravel())
sim = {}
for i in range(len(blobs)):
    for j in range(i + 1, len(blobs)):
        u, v = blobs[i] - blobs[i].mean(), blobs[j] - blobs[j].mean(); sim[(i, j)] = float(u @ v / (np.linalg.norm(u) * np.linalg.norm(v) + 1e-9))
W = 4 * (CELL + 10) + 260; H = len(rows) * (CELL + 40) + 60 + 22 * max(1, len(sim))
sheet = Image.new('RGB', (W, H), 'white'); d = ImageDraw.Draw(sheet)
for k, lab in enumerate(['原寸比', f'縮小 {a.thumb_mm:g}mm幅', 'ぼかし（骨格）', '反転（余白の形）']): d.text((k * (CELL + 10) + 4, 4), lab, fill='black', font=font)
for r, (base, t, blur, inv, mt) in enumerate(rows):
    y = 30 + r * (CELL + 40)
    for k, im in enumerate([base, t, blur, inv]): sheet.paste(im, (k * (CELL + 10), y))
    d.text((4 * (CELL + 10), y), names[r], fill='black', font=font)
    for i, (k, v) in enumerate(mt.items()): d.text((4 * (CELL + 10), y + 24 + i * 20), f'{k} {v:.0f}{"" if k == "要素数" else "%"}', fill='black', font=font)
y = 30 + len(rows) * (CELL + 40); bad = []
for (i, j), v in sim.items():
    flag = v >= a.max_sim; bad += [(i, j)] if flag else []
    d.text((4, y), f'骨格の類似度 {names[i]}–{names[j]}: {v:.2f}' + ('  ← 似すぎ。骨格を変えて出し直す' if flag else ''), fill='red' if flag else 'black', font=font); y += 22
sheet.save(a.out)
for r, (*_, mt) in enumerate(rows): print(names[r], ' '.join(f'{k}{v:.0f}' for k, v in mt.items()))
for (i, j), v in sim.items(): print(f'骨格の類似度 {names[i]}-{names[j]} {v:.2f}', '似すぎ' if v >= a.max_sim else '')
print('sheet:', a.out); sys.exit(1 if bad else 0)

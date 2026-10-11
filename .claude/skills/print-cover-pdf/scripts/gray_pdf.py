#!/usr/bin/env python3
# 色をK(グレー)へ変換し、判型を正確に（上端基準）切り直す。 使い方: gray_pdf.py in.pdf out.pdf W_mm H_mm
# Chromium PDF は黒を "0 0 0 rg"(RGB) で出す → "0 g"(DeviceGray) に直す。r≠g≠b の色が残れば警告（K単色の違反）
import sys, re, pikepdf
src, dst, W, H = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4]); pt = 72 / 25.4
pdf = pikepdf.open(src); cnt = [0, 0]
def conv(data):
    def r(m):
        a, b, c = (float(x) for x in m.groups()[:3]); cnt[0] += 1
        if abs(a - b) > 0.02 or abs(b - c) > 0.02: cnt[1] += 1
        return (f'{0.299*a+0.587*b+0.114*c:.4f} ' + ('g' if m.group(4) == b'rg' else 'G')).encode()
    return re.sub(rb'(-?[\d.]+) (-?[\d.]+) (-?[\d.]+) (rg|RG)\b', r, data)
for page in pdf.pages:
    arr = page.Contents if isinstance(page.Contents, pikepdf.Array) else [page.Contents]
    for st in arr: st.write(conv(st.read_bytes()))
    for _, xo in (page.Resources.get('/XObject') or {}).items():
        if xo.get('/Subtype') == '/Form': xo.write(conv(xo.read_bytes()))
    top = float(page.MediaBox[3]); box = pikepdf.Array([0, round(top - H * pt, 3), round(W * pt, 3), round(top, 3)])
    page.MediaBox = box; page.CropBox = box; page.TrimBox = box; page.BleedBox = box
pdf.save(dst); print(f'色演算子 {cnt[0]} 個を変換 / 非グレー {cnt[1]} 個' + ('  ← K単色違反の可能性' if cnt[1] else ''))

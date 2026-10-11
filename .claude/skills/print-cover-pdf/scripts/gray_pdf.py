#!/usr/bin/env python3
# 色をK(グレー)へ変換し、判型を上端基準で正確に切り直し、TrimBox を設定する。
# 使い方: gray_pdf.py in.pdf out.pdf PAGE_W_mm PAGE_H_mm [BLEED_mm]
#   PAGE = 塗り足しを含む入稿ページ全体。BLEED>0 なら TrimBox = PAGE を BLEED だけ内側へ。
# Chromium PDF は黒を "0 0 0 rg"(RGB) で出す → "0 g"(DeviceGray) に直す。CMYK(k/K)もグレー化。
# 変換できない色指定(sc/scn/SC/SCN で3・4成分)・非グレーRGBが残れば exit 1（K単色違反）。
import sys, re, pikepdf
if len(sys.argv) < 5: sys.exit('usage: gray_pdf.py in.pdf out.pdf PAGE_W_mm PAGE_H_mm [BLEED_mm]')
src, dst, W, H = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4]); bleed = float(sys.argv[5]) if len(sys.argv) > 5 else 0.0
pt = 72 / 25.4; pdf = pikepdf.open(src); cnt = {'converted': 0, 'nongray': 0, 'unconverted': 0}
NUM = rb'(-?[\d.]+)'
def conv(data):
    def rgb(m):
        a, b, c = (float(x) for x in m.groups()[:3]); cnt['converted'] += 1
        if abs(a - b) > 0.02 or abs(b - c) > 0.02: cnt['nongray'] += 1
        return (f'{0.299*a+0.587*b+0.114*c:.4f} ' + ('g' if m.group(4) == b'rg' else 'G')).encode()
    def cmyk(m):
        c, mm, y, k = (float(x) for x in m.groups()[:4]); cnt['converted'] += 1
        if max(c, mm, y) > 0.02: cnt['nongray'] += 1
        return (f'{max(0.0, 1 - min(1.0, 0.3*c + 0.59*mm + 0.11*y + k)):.4f} ' + ('g' if m.group(5) == b'k' else 'G')).encode()
    data = re.sub(NUM + rb' ' + NUM + rb' ' + NUM + rb' (rg|RG)\b', rgb, data)
    data = re.sub(NUM + rb' ' + NUM + rb' ' + NUM + rb' ' + NUM + rb' (k|K)\b', cmyk, data)
    cnt['unconverted'] += len(re.findall(NUM + rb' ' + NUM + rb' ' + NUM + rb'(?: ' + NUM + rb')? (?:sc|scn|SC|SCN)\b', data))
    return data
for page in pdf.pages:
    arr = page.Contents if isinstance(page.Contents, pikepdf.Array) else [page.Contents]
    for st in arr: st.write(conv(st.read_bytes()))
    for _, xo in (page.Resources.get('/XObject') or {}).items():
        if xo.get('/Subtype') == '/Form': xo.write(conv(xo.read_bytes()))
    top = float(page.MediaBox[3]); box = pikepdf.Array([0, round(top - H * pt, 3), round(W * pt, 3), round(top, 3)])
    page.MediaBox = box; page.CropBox = box; page.BleedBox = box
    b = bleed * pt; page.TrimBox = pikepdf.Array([round(b, 3), round(top - H * pt + b, 3), round(W * pt - b, 3), round(top - b, 3)])
pdf.save(dst)
print(f"色演算子 {cnt['converted']} 個を変換 / 非グレー {cnt['nongray']} / 変換不能(sc系) {cnt['unconverted']}")
if cnt['nongray'] or cnt['unconverted']: print('NG: K単色違反の可能性（色付きの塗り・線が残る）'); sys.exit(1)

#!/usr/bin/env python3
"""カラー冊子の入稿仕上げ（HTML→PDF の出力を印刷所向けにする）。
使い方: color-print-finish.py IN.pdf OUT.pdf [--cover COVER.pdf] [--bleed 3] [--no-k100]
  1. Ghostscript で CMYK 変換 + 文字のアウトライン化（画像はダウンサンプルしない, JPEG Q95）
  2. ほぼ黒（C,M,Y>=0.5 かつ K>=0.7）の塗り/線を K100 に置換（小さい文字の版ズレ対策）
  3. --cover があれば先頭に連結（表紙は別データ。既に CMYK・アウトライン済みであること）
  4. 全ページに TrimBox=MediaBox-塗り足し、BleedBox=CropBox=MediaBox を設定
  5. 検査を表示: ページ数 / ページ寸法 / フォント数 / 最小実効ppi / ページ別インキ総量(最大と99.5%値)
必要: gs, pikepdf, numpy, pillow, poppler-utils。不足すれば exit 2。検査値の合否は印刷会社の仕様で判断する。
"""
import sys, os, re, shutil, subprocess, tempfile, argparse
ap = argparse.ArgumentParser(); ap.add_argument('inp'); ap.add_argument('out')
ap.add_argument('--cover'); ap.add_argument('--bleed', type=float, default=3.0); ap.add_argument('--no-k100', action='store_true')
a = ap.parse_args()
for t in ('gs', 'pdffonts', 'pdfimages'):
    if not shutil.which(t): print(f'ENV NG: {t} がありません (apt-get install -y ghostscript poppler-utils)'); sys.exit(2)
try:
    import pikepdf, numpy as np
    from PIL import Image
except ImportError as e: print('ENV NG:', e); sys.exit(2)
tmp = tempfile.mkdtemp(); cm = os.path.join(tmp, 'cmyk.pdf')
subprocess.run(['gs', '-q', '-o', cm, '-sDEVICE=pdfwrite', '-dNoOutputFonts', '-sColorConversionStrategy=CMYK',
    '-dProcessColorModel=/DeviceCMYK', '-dDownsampleColorImages=false', '-dDownsampleGrayImages=false',
    '-dAutoFilterColorImages=false', '-dColorImageFilter=/DCTEncode', '-dJPEGQ=95', '-dCompatibilityLevel=1.6', a.inp], check=True)
p = pikepdf.open(cm); n = 0
num = rb'(\d*\.?\d+)'
pat = re.compile(rb'(?<![\d.])' + rb'\s+'.join([num] * 4) + rb'\s+([kK])\b')
def k100(m):
    c, mg, y, k = (float(m.group(i)) for i in range(1, 5))
    if min(c, mg, y) >= 0.5 and k >= 0.7: return b'0 0 0 1 ' + m.group(5)
    return m.group(0)
if not a.no_k100:
    for obj in p.objects:
        if isinstance(obj, pikepdf.Stream) and obj.get('/Subtype') != '/Image' and obj.get('/Type') != '/XRef':
            try: d = obj.read_bytes()
            except Exception: continue
            d2 = pat.sub(k100, d)
            if d2 != d: n += sum(1 for x, y in zip(pat.findall(d), pat.findall(d2)) if x != y); obj.write(d2)
out = pikepdf.new()
if a.cover: out.pages.extend(pikepdf.open(a.cover).pages)
out.pages.extend(p.pages)
b = a.bleed * 72 / 25.4
for pg in out.pages:
    x0, y0, x1, y1 = [float(v) for v in pg.MediaBox]
    pg.TrimBox = [x0 + b, y0 + b, x1 - b, y1 - b]; pg.BleedBox = pg.MediaBox; pg.CropBox = pg.MediaBox
    if '/ArtBox' in pg.obj: del pg.obj['/ArtBox']
out.save(a.out)
print(f'K100置換: {n} 箇所')
print('ページ数:', len(out.pages))
for i, pg in enumerate(out.pages, 1):
    x0, y0, x1, y1 = [float(v) for v in pg.MediaBox]; print(f'  p{i}: {(x1-x0)/72*25.4:.1f}x{(y1-y0)/72*25.4:.1f}mm (仕上がり {(x1-x0-2*b)/72*25.4:.1f}x{(y1-y0-2*b)/72*25.4:.1f}mm)')
fonts = subprocess.run(['pdffonts', a.out], capture_output=True, text=True).stdout.splitlines()[2:]
print('フォント数:', len(fonts), '(0 = アウトライン済み)')
ppi = [int(l.split()[12]) for l in subprocess.run(['pdfimages', '-list', a.out], capture_output=True, text=True).stdout.splitlines()[2:] if len(l.split()) > 13]
print('最小実効ppi:', min(ppi) if ppi else '画像なし')
subprocess.run(['gs', '-q', '-o', os.path.join(tmp, 't-%03d.tif'), '-sDEVICE=tiff32nc', '-r40', a.out], check=True)
for f in sorted(x for x in os.listdir(tmp) if x.startswith('t-')):
    s = np.asarray(Image.open(os.path.join(tmp, f))).astype(int).sum(2) / 255 * 100
    print(f'  インキ総量 p{int(f[2:5])}: 最大 {s.max():.0f}% / 99.5%値 {np.percentile(s, 99.5):.0f}%')
shutil.rmtree(tmp)

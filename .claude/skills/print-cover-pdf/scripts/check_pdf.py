#!/usr/bin/env python3
# 入稿前チェック（最終検査）。全項目 OK のときだけ exit 0。NG は exit 1、環境不足は exit 3（黙って成功にしない）。
# 使い方: check_pdf.py file.pdf --size W H [--bleed MM] [--min-margin MM] [--max-black PCT] [--mono]
#   --size: 入稿ページ全体(塗り足し込み)mm / --bleed: 塗り足し(TrimBox を内側に期待) / --min-margin: トリム端からの余白下限
#   --mono(既定ON): RGB/CMYK 演算子・非グレー色空間・画像・フォント・テキスト層が残っていれば NG
# 判定の閾値(--min-margin, --max-black)は呼び出し側が案件の仕様から渡す。会社仕様があればそちらが優先。
import sys, re, shutil, subprocess, argparse, tempfile, os
for t in ('pdfinfo', 'pdffonts', 'pdfimages', 'pdftoppm', 'pdftotext'):
    if not shutil.which(t): print(f'ENV NG: {t} が無い'); sys.exit(3)
try: import numpy as np, pikepdf; from PIL import Image
except ImportError as e: print(f'ENV NG: python モジュール不足 ({e})'); sys.exit(3)
ap = argparse.ArgumentParser(); ap.add_argument('pdf'); ap.add_argument('--size', nargs=2, type=float, required=True)
ap.add_argument('--bleed', type=float, default=0.0); ap.add_argument('--min-margin', type=float, default=None); ap.add_argument('--max-black', type=float, default=None)
a = ap.parse_args(); mm = 72 / 25.4; bad = []
def ok(name, cond, detail=''):
    print(('OK  ' if cond else 'NG  ') + name + (f'  {detail}' if detail else ''))
    if not cond: bad.append(name)
pdf = pikepdf.open(a.pdf); ok('ページ数 1', len(pdf.pages) == 1, f'({len(pdf.pages)})'); pg = pdf.pages[0]
mb = [float(x) for x in pg.MediaBox]; W, H = (mb[2] - mb[0]) / mm, (mb[3] - mb[1]) / mm
ok('MediaBox 寸法', abs(W - a.size[0]) < 0.3 and abs(H - a.size[1]) < 0.3, f'{W:.2f}x{H:.2f}mm (期待 {a.size[0]}x{a.size[1]})')
tb = [float(x) for x in pg.get('/TrimBox', pikepdf.Array(mb))]; has_trim = '/TrimBox' in pg
exp = [mb[0] + a.bleed * mm, mb[1] + a.bleed * mm, mb[2] - a.bleed * mm, mb[3] - a.bleed * mm]
ok('TrimBox 設定と位置', has_trim and all(abs(x - y) < 0.5 for x, y in zip(tb, exp)), f'trim={[round(x, 1) for x in tb]} 期待={[round(x, 1) for x in exp]}')
nf = len(subprocess.run(['pdffonts', a.pdf], capture_output=True, text=True).stdout.strip().splitlines()) - 2
ok('フォント埋め込み 0（曲線化）', max(nf, 0) == 0, f'({max(nf, 0)})')
ni = len(subprocess.run(['pdfimages', '-list', a.pdf], capture_output=True, text=True).stdout.strip().splitlines()) - 2
ok('ラスター画像 0（ベクター保持）', max(ni, 0) == 0, f'({max(ni, 0)})')
tx = re.sub(r'\s', '', subprocess.run(['pdftotext', a.pdf, '-'], capture_output=True, text=True).stdout)
ok('テキスト層 0（文字が曲線化済み）', len(tx) == 0, f'({len(tx)}字)')
# 色: コンテンツストリーム中の RGB/CMYK 演算子と非グレー色空間
streams = [pg.Contents] if not isinstance(pg.Contents, pikepdf.Array) else list(pg.Contents)
res = pg.get('/Resources', {}); xo = res.get('/XObject', {}) if res else {}
streams += [x for _, x in xo.items() if x.get('/Subtype') == '/Form']
data = b'\n'.join(s.read_bytes() for s in streams)
rgbops = len(re.findall(rb'(?:-?[\d.]+ ){3}(?:rg|RG)\b', data)); cmykops = len(re.findall(rb'(?:-?[\d.]+ ){4}(?:k|K)\b', data)); scops = len(re.findall(rb'\b(?:sc|scn|SC|SCN)\b', data))
nongray = 0
for pat in re.finditer(rb'(-?[\d.]+) (-?[\d.]+) (-?[\d.]+) (?:rg|RG)\b', data):
    r, g, b = (float(x) for x in pat.groups()); nongray += (abs(r - g) > 0.02 or abs(g - b) > 0.02)
cs = res.get('/ColorSpace', {}) if res else {}; cs_bad = [k for k, v in cs.items() if str(v) != '/DeviceGray' and 'Gray' not in str(v)]
ok('RGB 演算子 0', rgbops == 0, f'(rg/RG={rgbops}, うち非グレー={nongray})'); ok('CMYK 演算子 0', cmykops == 0, f'({cmykops})')
ok('色空間指定(sc系/非Gray ColorSpace) 0', scops == 0 and not cs_bad, f'(sc系={scops}, ColorSpace={cs_bad})')
ok('描画(ベクターのパス)がある', bool(re.search(rb'(?:^|\s)(?:f\*?|S|B\*?|b\*?)(?:\s|$)', data)))
# 実測: トリム端からの余白と黒面積（150dpi）
d = tempfile.mkdtemp(); subprocess.run(['pdftoppm', '-r', '150', '-png', '-singlefile', a.pdf, os.path.join(d, 'p')], check=True)
im = np.asarray(Image.open(os.path.join(d, 'p.png')).convert('L')); k = 150 / 25.4; b0 = int(round(a.bleed * k))
trim = im[b0:im.shape[0] - b0, b0:im.shape[1] - b0] if b0 else im; ys, xs = np.where(trim < 250)
ok('紙面に描画がある', len(xs) > 0)
if len(xs):
    m = dict(L=xs.min() / k, R=(trim.shape[1] - xs.max()) / k, T=ys.min() / k, B=(trim.shape[0] - ys.max()) / k)
    print('    余白mm(トリム端から) ' + ' '.join(f'{x}{v:.1f}' for x, v in m.items()))
    if a.min_margin is not None: ok(f'余白 >= {a.min_margin}mm', min(m.values()) >= a.min_margin)
blk = 100 * (trim < 128).mean(); print(f'    黒面積 {blk:.1f}%')
if a.max_black is not None: ok(f'黒面積 <= {a.max_black}%', blk <= a.max_black)
print('PASS' if not bad else 'FAIL: ' + ', '.join(bad)); sys.exit(0 if not bad else 1)

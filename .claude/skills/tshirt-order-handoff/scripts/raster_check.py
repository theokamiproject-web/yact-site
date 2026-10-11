#!/usr/bin/env python3
# ラスター混在の検出。使い方: raster_check.py file.svg|file.pdf [...]   exit 0=なし / 2=あり(=既存の細線チェッカーのPASSを信用してはならない)
import sys, re, subprocess, shutil
hit = []
for f in sys.argv[1:]:
    if f.lower().endswith('.pdf'):
        if not shutil.which('pdfimages'): print('ENV NG: pdfimages が無い'); sys.exit(3)
        n = len(subprocess.run(['pdfimages', '-list', f], capture_output=True, text=True).stdout.strip().splitlines()) - 2
        if n > 0: hit.append(f'{f}: PDF内に画像 {n} 個')
    else:
        s = open(f, encoding='utf-8', errors='ignore').read()
        for pat, name in ((r'<image\b', '<image>'), (r'data:image', 'data:image'), (r'<feImage\b', '<feImage>'), (r'<pattern\b[^>]*>(?:(?!</pattern>).)*<image', 'pattern内画像')):
            if re.search(pat, s, re.S): hit.append(f'{f}: {name}')
if hit: print('RASTER あり → 自動の細線チェッカー(社内/他Skill含む)のPASSは無効。完成画像を会社基準で実測すること\n  ' + '\n  '.join(hit)); sys.exit(2)
print('ラスターなし'); 

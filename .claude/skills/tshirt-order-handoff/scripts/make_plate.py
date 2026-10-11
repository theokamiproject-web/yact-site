#!/usr/bin/env python3
# 単一パスのアートワークSVGから、フィルム用の版SVG（【黒=インクが乗る／白=抜き】）を作る。
# 使い方: make_plate.py artwork.svg plate.svg
# 拒否(exit 2): <image>(ラスター) / <text>(未アウトライン) / stroke指定(外形化されていない線) / 複数インク指定(data-plate)。人手で整えてから再実行。
# 注意: 版の「黒」は"インクが乗る場所"の表記。生地が黒でも、下地(白インク)の版は同形で別に指示する(黒生地の色ではない)。
import sys, re
s = open(sys.argv[1], encoding='utf-8').read(); why = []
if re.search(r'<image\b|data:image|<feImage\b', s): why.append('ラスター画像(<image>等)が含まれる')
if re.search(r'<text\b', s): why.append('<text> が未アウトライン')
if re.search(r'\bstroke="(?!none)', s) or re.search(r'stroke:(?!none)', s): why.append('stroke 指定の線がある(外形化してから)')
if 'data-plate' in s: why.append('複数インクの指定(data-plate)。版ごとに手で分ける')
if why: print('make_plate NG: ' + ' / '.join(why)); sys.exit(2)
hdr = re.match(r'<svg[^>]*>', s).group(0); ds = re.findall(r' d="([^"]+)"', s)
if not ds: print('make_plate NG: パスが無い'); sys.exit(2)
open(sys.argv[2], 'w', encoding='utf-8').write(f'{hdr}<rect width="100%" height="100%" fill="#FFFFFF"/><g fill="#000000">' + ''.join(f'<path fill-rule="nonzero" d="{d}"/>' for d in ds) + '</g></svg>')
print('plate:', sys.argv[2], f'({len(ds)} paths)  黒=インク / 白=抜き')

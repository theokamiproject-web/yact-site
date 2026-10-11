#!/usr/bin/env python3
# 単一パスのアートワークSVGから、フィルム用の版SVG（黒=インク、白=抜き）を作る。 使い方: make_plate.py artwork.svg plate.svg
# 複数インクのSVG（<g data-plate=..>）は手で分ける。下地版は同形（縮小=チョークは印刷所の指示に従う）
import sys, re
s = open(sys.argv[1]).read(); hdr = re.match(r'<svg[^>]*>', s).group(0); ds = re.findall(r' d="([^"]+)"', s)
open(sys.argv[2], 'w').write(f'{hdr}<rect width="100%" height="100%" fill="#FFFFFF"/><g fill="#000000">' + ''.join(f'<path fill-rule="nonzero" d="{d}"/>' for d in ds) + '</g></svg>')
print('plate:', sys.argv[2], f'({len(ds)} paths)')

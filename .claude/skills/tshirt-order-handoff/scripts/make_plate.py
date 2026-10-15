#!/usr/bin/env python3
# アートワークSVGから、フィルム用の版SVG（黒=インク、白=抜き）を作る。
# 使い方: make_plate.py artwork.svg plate.svg [--ink "#E9E3D3" | --all] [--tol 40]
#   --ink: その色（RGB距離 tol 以内）の塗り/線だけを版にする（多色の色分解）。
#   --all: 塗り/線のある要素すべてを1版にする（1色デザイン、または下地=白インク版）。
# 元の構造（transform・fill-rule・rect/circle 等）はそのまま残し、色だけ黒に置き換える。
# 停止(終了コード2): <text>（未アウトライン）／<image>（ラスター）／use・clip・mask・filter・グラデーション（平坦化してから渡す）／版が空。
import sys, re, argparse, xml.etree.ElementTree as ET

SVG = 'http://www.w3.org/2000/svg'; ET.register_namespace('', SVG); ET.register_namespace('xlink', 'http://www.w3.org/1999/xlink')
SHAPES = {'path', 'rect', 'circle', 'ellipse', 'polygon', 'polyline', 'line'}
STOP = {'text': '文字が未アウトライン', 'image': 'ラスター画像が埋め込まれている', 'use': '<use> 参照', 'clipPath': 'クリップ',
        'mask': 'マスク', 'filter': 'フィルタ', 'linearGradient': 'グラデーション', 'radialGradient': 'グラデーション', 'pattern': 'パターン'}
NAMED = {'black': '#000000', 'white': '#ffffff', 'red': '#ff0000', 'none': 'none'}

def tag(e): return e.tag.split('}')[-1]
def style(e):
    d = {k: v for k, v in e.attrib.items()}
    for kv in e.get('style', '').split(';'):
        if ':' in kv: k, v = kv.split(':', 1); d[k.strip()] = v.strip()
    return d
def rgb(c):
    c = NAMED.get(c.lower(), c.lower()) if c else c
    if not c or c == 'none' or c.startswith('url('): return c
    m = re.fullmatch(r'#([0-9a-f]{3}|[0-9a-f]{6})', c)
    if m: h = m.group(1); h = ''.join(x * 2 for x in h) if len(h) == 3 else h; return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    m = re.fullmatch(r'rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)', c)
    if m: return tuple(int(x) for x in m.groups())
    raise ValueError(f'色を解釈できない: {c}')

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('src'); ap.add_argument('out')
    g = ap.add_mutually_exclusive_group(required=True); g.add_argument('--ink'); g.add_argument('--all', action='store_true')
    ap.add_argument('--tol', type=float, default=40); a = ap.parse_args()
    target = rgb(a.ink) if a.ink else None
    root = ET.parse(a.src).getroot()  # <?xml?> 宣言・コメントがあっても可
    errs = [f'<{tag(e)}> {STOP[tag(e)]}' for e in root.iter() if tag(e) in STOP]
    if errs: print('停止:', ' / '.join(sorted(set(errs))), '→ 平坦化・アウトライン化してから再実行'); sys.exit(2)
    hit = 0
    def match(c):
        if c is None or c == 'none': return False
        if isinstance(c, str): raise ValueError(f'未対応の塗り: {c}')
        return True if target is None else sum((x - y) ** 2 for x, y in zip(c, target)) ** .5 <= a.tol
    def walk(e, inh):
        nonlocal hit
        s = style(e); cur = dict(inh)
        for k in ('fill', 'stroke'):
            if k in s and s[k] != 'inherit': cur[k] = rgb(s[k])
        for k in ('fill', 'stroke', 'style', 'opacity', 'fill-opacity', 'stroke-opacity'): e.attrib.pop(k, None)
        for ch in list(e):
            if tag(ch) in ('defs', 'title', 'desc', 'metadata'): e.remove(ch); continue
            if walk(ch, cur) is False: e.remove(ch)
        if tag(e) in SHAPES:
            f, st = match(cur['fill']), match(cur['stroke'])
            if not (f or st): return False
            e.set('fill', '#000000' if f else 'none'); e.set('stroke', '#000000' if st else 'none'); hit += 1
            if st and 'stroke-width' in s: e.set('stroke-width', s['stroke-width'])
            if 'fill-rule' in s: e.set('fill-rule', s['fill-rule'])  # evenodd の穴を保持
        return None
    walk(root, {'fill': (0, 0, 0), 'stroke': 'none'})  # SVG既定: fill=黒, stroke=なし
    if hit == 0: print('停止: 版が空（該当色の要素なし）。--ink の色・--tol を確認'); sys.exit(2)
    vb = root.get('viewBox'); x, y, w, h = (vb.replace(',', ' ').split() if vb else ('0', '0', '100%', '100%'))
    bg = ET.Element(f'{{{SVG}}}rect', {'x': x, 'y': y, 'width': w, 'height': h, 'fill': '#FFFFFF'}); root.insert(0, bg)
    ET.ElementTree(root).write(a.out, encoding='unicode')
    print('plate:', a.out, f'({hit} 要素, {"全塗り" if target is None else a.ink})')

if __name__ == '__main__':
    try: main()
    except ValueError as ex: print('停止:', ex); sys.exit(2)

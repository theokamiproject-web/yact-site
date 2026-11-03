#!/usr/bin/env python3
"""こりっち「予約一覧表」PDF → 来場リスト（Excel、A4縦1枚、LibreOfficeでPDF化）

使い方:
  python3 corich_raiba.py 予約一覧表.pdf --title "31日(土)12時" \
      --price 一般=3500 --price U25=3000 --price 招待=0 \
      [--cancel 1-41 --cancel 2-86] [--no-mado 1-23] [--walkin 5 --walkin-price 4500] \
      [--outdir out] [--pdf]

- 列: 公演日時|名前|フリガナ|取扱窓口|支払方法|料金種別|単価|枚数|合計金額|備考（団体の既存の来場リストの形）
- 並び: 取扱窓口ありを窓口ごと（PDFの出現順）→窓口なし→窓口なしの招待
- --cancel の予約No.は行ごと削除。--no-mado は取扱窓口を空にする（招待の並びへ移す等）
- 列境界は見出し語の位置から自動で決める（列の幅が変わっても動く）
"""
import argparse, html, json, os, re, subprocess, sys

HEAD = {'date': '公演日時', 'no': '予約', 'name': '名前', 'kana': '名前（カナ）', 'kind': 'チケット名',
        'n': '枚数', 'seat': '席番号', 'pay': '支払方法', 'mado': '取扱窓口', 'memo': '備考'}
LABEL = {'一般': '前売り', 'U25': 'U25割', '招待': '招待', '当日': '当日'}

def words(pdf):
    out = subprocess.run(['pdftotext', '-bbox', pdf, '-'], capture_output=True, text=True).stdout
    pages = []
    for pg in re.findall(r'<page.*?</page>', out, re.S):
        m = re.search(r'<page width="[\d.]+" height="([\d.]+)"', pg)
        ph = float(m.group(1)) if m else 595.0
        ws = [(float(a), float(b), html.unescape(w)) for a, b, w in
              re.findall(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="[\d.]+" yMax="[\d.]+">(.*?)</word>', pg)]
        pages.append((ph, ws))
    return pages

def cols_from_header(ws):
    hy = min(y for x, y, w in ws if w == '公演日時')
    hx = {}
    for x, y, w in ws:
        if abs(y - hy) < 4:
            for k, lab in HEAD.items():
                if w.startswith(lab) and k not in hx:
                    if k == 'name' and w.startswith('名前（'):
                        continue
                    hx[k] = x
    order = sorted(hx.items(), key=lambda kv: kv[1])
    bounds = []
    for i, (k, x) in enumerate(order):
        nxt = order[i + 1][1] if i + 1 < len(order) else 1e9
        bounds.append((k, x - 3, nxt - 3))
    return hy, bounds

def col(x, bounds):
    for k, a, b in bounds:
        if a <= x < b:
            return k
    return None

def lines(tokens, tol=3.0):
    """y が近い語を1行にまとめ、行ごとに x 順で連結"""
    tokens = sorted(tokens)
    rows = []
    for y, x, w in tokens:
        if rows and abs(rows[-1][0] - y) <= tol:
            rows[-1][1].append((x, w))
        else:
            rows.append([y, [(x, w)]])
    return [''.join(w for x, w in sorted(r[1])) if False else ' '.join(w for x, w in sorted(r[1])) for r in rows]

def parse(pdf):
    recs = []
    for ph, ws in words(pdf):
        if not any(w == '公演日時' for _, _, w in ws):
            continue
        hy, bounds = cols_from_header(ws)
        body = [w for w in ws if hy + 8 < w[1] < ph - 35 and not re.fullmatch(r'\d+/\d+', w[2])]
        anchors = sorted(y for x, y, w in body if re.match(r'20\d\d/\d\d/\d\d\(', w))
        for i, y0 in enumerate(anchors):
            y1 = anchors[i + 1] if i + 1 < len(anchors) else 1e9
            cells = {}
            for x, y, w in body:
                if y0 - 3 <= y < y1 - 3:
                    k = col(x, bounds)
                    if k:
                        cells.setdefault(k, []).append((y, x, w))
            r = {k: lines(v) for k, v in cells.items()}
            r['date'] = ' '.join(r.get('date', [])).replace('( ', '(').replace(' )', ')')
            recs.append(r)
    return recs

def norm(r):
    name = ''.join(r.get('name', [])) if len(r.get('name', [])) > 1 else ' '.join(r.get('name', []))
    name = re.sub(r'\s*様$', '', name.replace(' 様', '')).strip()
    kana = ''.join(r.get('kana', []))
    kind_txt = ''.join(t.replace(' ', '') for t in r.get('kind', []))
    kinds = re.findall(r'\(([^)]*)\)', kind_txt) or ([kind_txt] if kind_txt else [])
    n = int(re.sub(r'\D', '', ''.join(r.get('n', ['0']))) or 0)
    if len(kinds) == 1 and n > 1:
        kinds = kinds * n
    return dict(date=r.get('date', ''), no=''.join(r.get('no', [])), name=name, kana=kana,
                mado=''.join(r.get('mado', [])).replace(' ', ''), pay=''.join(r.get('pay', [])),
                kinds=kinds, n=n, memo=''.join(r.get('memo', [])))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pdf'); ap.add_argument('--title', required=True)
    ap.add_argument('--price', action='append', default=[], help='種別=単価 例 一般=3500')
    ap.add_argument('--cancel', action='append', default=[]); ap.add_argument('--no-mado', action='append', default=[])
    ap.add_argument('--walkin', type=int, default=5); ap.add_argument('--walkin-price', type=int, default=None)
    ap.add_argument('--outdir', default='.'); ap.add_argument('--pdf-out', dest='pdf_out', action='store_true')
    a = ap.parse_args()
    price = dict(p.split('=') for p in a.price); price = {k: int(v) for k, v in price.items()}
    recs = [norm(r) for r in parse(a.pdf)]
    recs = [r for r in recs if r['no'] not in a.cancel]
    for r in recs:
        if r['no'] in a.no_mado:
            r['mado'] = ''
        miss = sorted({k for k in r['kinds'] if k not in price})
        if miss:
            sys.exit(f"単価が未指定の料金種別: {miss}（--price {miss[0]}=金額 を足す）")
        r['amount'] = sum(price[k] for k in r['kinds'])
        cnt = {k: r['kinds'].count(k) for k in dict.fromkeys(r['kinds'])}
        r['label'] = '・'.join(LABEL.get(k, k) + (f'×{c}' if len(cnt) > 1 else '') for k, c in cnt.items())
    with_m = [r for r in recs if r['mado']]
    no_m = [r for r in recs if not r['mado']]
    rows = with_m + [r for r in no_m if r['pay'] != '招待'] + [r for r in no_m if r['pay'] == '招待']
    build_xlsx(rows, a)
    print(f"{a.title}: {len(rows)}件 {sum(r['n'] for r in rows)}枚 金額{sum(r['amount'] for r in rows)}円")
    print(json.dumps([[r['no'], r['name'], r['mado'], r['label'], r['n']] for r in rows], ensure_ascii=False))

def build_xlsx(rows, a):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
    F = 'Noto Sans CJK JP'; thin = Side(style='thin', color='000000'); B = Border(left=thin, right=thin, top=thin, bottom=thin)
    YEL = PatternFill('solid', fgColor='FFFF00')
    wb = Workbook(); ws = wb.active; ws.title = a.title[:31]
    hdr = ['公演日時', '名前', 'フリガナ', '取扱窓口', '支払方法', '料金種別', '単価', '枚数', '合計金額', '備考']
    widths = [10, 13.5, 14.5, 9.5, 9, 10, 8, 5.5, 9, 25.5]
    for i, (h, w) in enumerate(zip(hdr, widths), 1):
        c = ws.cell(1, i, h); c.font = Font(name=F, size=11, bold=True); c.border = B
        c.alignment = Alignment(horizontal='center', vertical='center'); ws.column_dimensions[c.column_letter].width = w
    r = 2
    for x in rows:
        vals = [x['date'], x['name'], x['kana'], x['mado'], x['pay'], x['label'], x['amount'], x['n'], x['amount'], x['memo']]
        for i, v in enumerate(vals, 1):
            c = ws.cell(r, i, v); c.border = B
            c.alignment = Alignment(vertical='center', shrink_to_fit=True, horizontal='right' if i in (7, 9) else ('center' if i == 8 else 'left'))
            c.font = Font(name=F, size={1: 5, 2: 13, 3: 9, 4: 9}.get(i, 10 if i in (5, 6, 10) else 11))
        ws.cell(r, 2).fill = YEL
        if x['pay'] == '招待':
            for i in (5, 6): ws.cell(r, i).font = Font(name=F, size=10, color='FF0000')
        long = len(x['memo']) > 18
        if long:
            ws.cell(r, 10).alignment = Alignment(vertical='center', wrap_text=True); ws.cell(r, 10).font = Font(name=F, size=7)
        ws.row_dimensions[r].height = 28 if long else 19
        r += 1
    for _ in range(a.walkin):  # 当日券の書き込み用
        for i in range(1, 11):
            c = ws.cell(r, i); c.border = B; c.font = Font(name=F, size=11)
        ws.cell(r, 2).fill = YEL; ws.cell(r, 5, '当日精算'); ws.cell(r, 6, '当日')
        if a.walkin_price: ws.cell(r, 7, a.walkin_price)
        ws.row_dimensions[r].height = 19; r += 1
    c = ws.cell(r, 8, sum(x['n'] for x in rows)); c.font = Font(name=F, size=12, bold=True); c.alignment = Alignment(horizontal='center')
    ws.page_setup.paperSize = ws.PAPERSIZE_A4; ws.page_setup.orientation = 'portrait'
    ws.page_setup.fitToWidth = 1; ws.page_setup.fitToHeight = 1; ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = '1:1'; ws.page_margins.left = ws.page_margins.right = 0.3
    os.makedirs(a.outdir, exist_ok=True); path = os.path.join(a.outdir, f'{a.title}.xlsx'); wb.save(path)
    if a.pdf_out:
        subprocess.run(['soffice', '--headless', '--convert-to', 'pdf', '--outdir', a.outdir, path], capture_output=True)

if __name__ == '__main__':
    main()

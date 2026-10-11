# TEMPLATE (adapt per project): source file names, CORR list, cast-table format and env vars (FS LH FIELD MT MB MO MI SIZE COLS NODOOR ENDBLANK LASTON NOTICE) are from the first use.
# CORR = approved (old,new) text fixes only. Run from the builder directory; see SKILL.md.
# 『ノア版 桜の花ざかり』台本冊子 (A6, 縦組み, 右綴じ) builder.  usage: python3 build-sakura.py out.html
import re, sys, html, os
OUT = sys.argv[1]
FS = float(os.environ.get('FS', '8.6')); LH = float(os.environ.get('LH', '1.75')); RUNIN = os.environ.get('RUNIN','0')=='1'
FIELD = float(os.environ.get('FIELD', '3.2'))
MT, MB, MO, MI = [float(os.environ.get(k, d)) for k, d in (('MT','12'),('MB','14'),('MO','9'),('MI','13'))]
T = open('source-sakura.txt', encoding='utf-8').read().lstrip('﻿')
# user-approved corrections (2026-10-10); source-sakura.txt / .docx stay untouched
CORR = [('水を刺されて', '水を差されて'), ('包帯撒いて', '包帯巻いて'), ('ポッド', 'ポット'), ('来て始めて', '来て初めて'), ('三苫', '三笘'), ('那珂川荘', '那賀川荘'), ('頭がｌ痛く', '頭が痛く'), ('見たいなってい言う', '見たいなって言う'), ('取調調書を勝手にコピーしたもの', '調書を勝手に持ち出したもの'),('血が着いた','血が付いた'),('差出す','差し出す'),('ほって置けない','ほっておけない'),('話しを','話を'),('えーッと','えーっと'),('注文を悩んで','注文に悩んで'),('大久保に詰める','大久保に詰め寄る'),("Let's party",'Let’s party'),('出来','でき'),('苗字','名字'),('コップ','カップ'),('あの、あぶらかたぶら','あの、あっぶらかたぶら'),('(田辺に)','（田辺に）'),('(山田に)','（山田に）'),('ほっと胸をなでおろす３人','ほっと胸をなでおろす三人')]
for a, b in CORR: T = T.replace(a, b)
L = [l.rstrip() for l in T.split('\n')]
SP = set("富久迫 桜井 大沢 水野 大久保 山田 中野 門奈 川上 高橋 田辺 杢代 店員 内藤 おば アキ 三人 二人 全員 男 田辺アキ".split())
def spk(l):
    m = re.match(r'^([^\s　（）「」『』。、！？…]{1,16}?)([（(][^）)]*[）)])?(?: |　)+(.*)$', l)
    if not m: return None
    nm = m.group(1)
    parts = re.split(r'[・]', nm)
    ok = all(p in SP or p.endswith('店員') or p.endswith('おばちゃん') or p == 'ラーメン屋のおばちゃん' for p in parts)
    return (nm + (m.group(2) or ''), m.group(3)) if ok else None
# ---- locate sections
i_cast = L.index('キャスト'); i_view = L.index('風景'); i_pro = L.index('プロローグ')
cast_lines = [l.strip() for l in L[i_cast+1:i_view] if l.strip()]
view_lines = [l.strip() for l in L[i_view+1:i_pro] if l.strip()]
TITLE = L[0].strip(); AUTHOR = L[1].strip()
# ---- body
body = []; mode = None; cur = None
HEAD = re.compile(r'^[１-４]$|^エピローグ$|^プロローグ$')
for i in range(i_pro, len(L)):
    l = L[i]
    if not l.strip(): mode = 'b'; cur = None; continue
    s = l.strip()
    if HEAD.match(s): body.append(('h', s)); mode = 'h'; cur = None; continue
    if s == '＊＊＊＊': body.append(('sep', s)); mode = 'h'; cur = None; continue
    if s == '終': body.append(('end', s)); mode = 'h'; cur = None; continue
    if l.startswith('　') and not spk(l): body.append(('s', s)); mode = 's'; cur = None; continue
    sp = spk(l)
    if sp: cur = ['u', sp[0], [sp[1]]]; body.append(cur); mode = 'u'; continue
    if mode == 'u' and cur is not None: cur[2].append(s); continue
    body.append(('s', s)); mode = 's'; cur = None
def esc(x): return html.escape(x)
def tcy(h):
    parts = re.split(r'(<[^>]*>|&#?\w+;)', h); out = []
    for p in parts:
        if p.startswith('<') or p.startswith('&'): out.append(p); continue
        p = re.sub(r'(?<![0-9０-９])([0-9０-９]{1,2})(?![0-9０-９])', r'<span class="tcy">\1</span>', p)
        out.append(p)
    return ''.join(out)
H = []
# ---- front matter
NODOOR = os.environ.get('NODOOR') == '1'
if not NODOOR: H.append(f'<section class="door"><h1>{esc(TITLE)}</h1><p class="au">{esc(AUTHOR)}</p></section>')
if not NODOOR: H.append('<section class="doorback">&#8203;</section>')
LCN = lambda x: ' l' if len(x) > 4 else ''
cast = ['<section class="front"><h2 class="cap">キャスト</h2>']
for l in cast_lines:
    if l.startswith('•') or l.startswith('・') or 'の設定は' in l: cast.append(f'<p class="note">{esc(l.lstrip("•・ "))}</p>'); continue
    parts = [p for p in re.split(r'　+', l) if p]
    if len(parts) >= 3: cast.append(f'<p class="cast"><span class="cn{LCN(parts[0])}">{esc(parts[0])}</span><span class="cr">{esc("　".join(parts[1:-1]))}</span><span class="ca">{esc(parts[-1])}</span></p>')
    elif len(parts) == 2 and len(parts[0]) > 8: cast.append(f'<p class="cast nm"><span class="cr">{esc(parts[0])}</span><span class="ca">{esc(parts[1])}</span></p>')
    elif len(parts) == 2: cast.append(f'<p class="cast"><span class="cn{LCN(parts[0])}">{esc(parts[0])}</span><span class="cr">{esc(parts[1])}</span></p>')
    else: cast.append(f'<p class="cast">{esc(l)}</p>')
cast.append('<h2 class="cap sc">風景</h2>')
for l in view_lines: cast.append(f'<p class="view">{esc(l)}</p>')
cast.append('</section>'); H.append(''.join(cast))
# ---- play
P = ['<main class="play">']
for b in body:
    k = b[0]
    if RUNIN and k != 'u' and P[-1].startswith('<p class="run"') and not P[-1].endswith('</p>'): P[-1] += '</p>'
    if k == 'h': P.append(f'<h2 class="{"scene" if re.fullmatch("[１-４]", b[1]) else "part"}">{esc(b[1])}</h2>')
    elif k == 'sep': P.append('<p class="sep">＊＊＊＊</p>')
    elif k == 'end': P.append('<p class="fin">終</p>')
    elif k == 'u':
        # long labels: keep only the name in the label field; a trailing （…） moves to the start of the speech (same characters, same as lines like 桜井　（読んで）「…」)
        _m = re.match(r'^([^（(]+)([（(].*[）)])$', b[1])
        if _m: b = ('u', _m.group(1), ['%s%s' % (_m.group(2), b[2][0])] + b[2][1:])
        if RUNIN:
            if not P[-1].startswith('<p class="run"') or P[-1].endswith('</p>'): P.append('<p class="run">')
            P[-1] += f'<span class="ru"><span class="rn">{esc(b[1])}</span>{" ".join(esc(x) for x in b[2])}</span> '
        else: P.append(f'<p class="u"><span class="n"><span class="nn{" long" if len(b[1]) > 4 else ""}">{esc(b[1])}</span></span>{"<br>".join(esc(x) for x in b[2])}</p>')
    else: P.append(f'<p class="s">{esc(b[1])}</p>')

if RUNIN and P[-1].startswith('<p class="run"') and not P[-1].endswith('</p>'): P[-1] += '</p>'
P.append('</main>'); H.append(''.join(P))
# ---- colophon / last page
NOTICE = os.environ.get('NOTICE', '上演を希望される場合は、下記までご連絡ください。')
LASTON = os.environ.get('LASTON')
if os.environ.get('ENDBLANK') == '1': H.append('<section class="blank">&#8203;</section>')
if not LASTON: H.append('<section class="blank">&#8203;</section>')
if not LASTON: H.append(f'<section class="colo"><div class="notice"><p>{esc(NOTICE)}</p><p class="mail">aoirobin@yahoo.co.jp</p></div></section>')
NOTE_CSS = ''
if LASTON:
    NOTE_CSS = '@page endp { @bottom-right { content: none; } @bottom-left { content: "%s\\A aoirobin@yahoo.co.jp"; white-space: pre; writing-mode: horizontal-tb; text-align: left; vertical-align: bottom; padding-bottom: %smm; margin-left: -%smm; width: 90mm; font: 7.5pt/1.7 "Noto Serif CJK JP"; } }' % (NOTICE, os.environ.get('NB','6'), os.environ.get('NL','11'))
css = f'''
@page {{ size: {os.environ.get('SIZE','105mm 148mm')}; bleed: 3mm; }}
@page :left  {{ margin: {MT}mm {MI}mm {MB}mm {MO}mm; @bottom-left  {{ content: counter(page); font: 6.5pt "Noto Serif CJK JP"; writing-mode: horizontal-tb; vertical-align: top; padding-top: 2.5mm; margin-left: {MO}mm; }} }}
@page :right {{ margin: {MT}mm {MO}mm {MB}mm {MI}mm; @bottom-right {{ content: counter(page); font: 6.5pt "Noto Serif CJK JP"; writing-mode: horizontal-tb; vertical-align: top; padding-top: 2.5mm; margin-right: {MO}mm; }} }}
@page door {{ @bottom-left {{ content: none; }} @bottom-right {{ content: none; }} }}
{NOTE_CSS}
:root {{ writing-mode: vertical-rl; }}
html {{ font-family: "Noto Serif CJK JP", serif; font-size: {FS}pt; line-height: {LH}; }}
body {{ margin: 0; line-break: strict; word-break: normal; orphans: 2; widows: 2; text-combine-upright: digits 2; }}
.door {{ page: door; break-after: page; height: 100vh; position: relative; }}
.door h1 {{ position: absolute; right: 22mm; top: 18mm; margin: 0; font-size: 17pt; font-weight: 700; letter-spacing: .3em; }}
.door .au {{ position: absolute; right: 8mm; top: 44mm; margin: 0; font-size: 10pt; letter-spacing: .3em; }}
.doorback {{ page: door; break-after: page; height: 100vh; }}
.front {{ break-after: page; }}
.cap {{ font-size: 1.15em; font-weight: 700; margin: 0 0 0 1.4em; letter-spacing: .3em; }} .cap.sc {{ margin-block-start: 3em; }}
.cast {{ margin: 0; padding-inline-start: 6em; text-indent: -6em; font-size: .86em; }} .cn {{ display: inline-block; inline-size: 6em; text-indent: 0; font-weight: 700; font-family: "Noto Sans CJK JP"; }} .cast:not(.nm) .cr {{ text-indent: 0; display: inline-block; inline-size: 29.5em; }} .ca {{ font-family: "Noto Sans CJK JP"; margin-inline-start: 0; font-size: .92em; }}
.cast.nm {{ white-space: nowrap; padding-inline-start: 0; text-indent: 0; }} .cast.nm .cr {{ font-family: 'Noto Sans CJK JP'; font-weight: 700; display: inline-block; inline-size: 35.5em; }}
.note {{ margin: 0; margin-block-start: 2.2em; font-size: .8em; }} .view {{ margin: 0; font-size: .88em; }}
main {{ break-before: page; {('columns: %s; column-gap: 7mm; column-fill: auto; height: 100vh;' % os.environ['COLS']) if os.environ.get('COLS') else ''} }}
.u {{ margin: 0; padding-inline-start: {FIELD}em; text-indent: -{FIELD}em; orphans: 3; widows: 3; }}
.n {{ display: inline-block; inline-size: {FIELD}em; text-indent: 0; font-weight: 400; color: #222; }} .n .nn {{ font-size: .86em; }} .n .nn.long {{ font-size: .6em; line-height: 1; display: inline-block; vertical-align: top; inline-size: calc({FIELD}em / .6); }}
.s {{ margin: 0; padding-inline-start: {FIELD}em; font-size: .9em; color: #444; orphans: 2; widows: 2; }}
.u + .s, .s + .u {{ margin-block-start: {FS*LH*0.5:.2f}pt; }}
h2.scene {{ font-weight: 400; font-size: 1.5em; margin: 0 1.2em 0 1em; break-after: avoid; }} h2.part {{ font-weight: 400; font-size: 1.15em; letter-spacing: .3em; margin: 0 1.2em 0 1em; break-after: avoid; }}
.sep {{ margin: 0 .6em; text-align: center; letter-spacing: .1em; font-size: .8em; color: #555; }}
.fin {{ margin: 0; margin-block-start: 1.4em; text-align: end; font-size: 1.1em; }}
.blank {{ page: {"endp" if LASTON else "door"}; break-before: page; height: 100vh; }}
.colo {{ break-before: page; height: 100vh; position: relative; }}
.cb {{ position: absolute; right: 12mm; top: 20mm; }} .cb p {{ margin: 0 0 0 1.4em; font-size: .9em; }} .ct {{ font-weight: 700; }}
.notice {{ position: absolute; left: 0; right: 0; bottom: 0; writing-mode: horizontal-tb; font-size: .86em; line-height: 1.8; }} .notice p {{ margin: 0; }} .mail {{ font-family: "Noto Sans CJK JP"; font-size: .95em; margin-top: 1mm !important; }}
.run {{ margin: 0; text-indent: 0; }} .rn {{ font-size: .8em; font-weight: 700; font-family: 'Noto Sans CJK JP'; margin-block-end: .35em; margin-block-start: .35em; display: inline-block; }} .ru {{ }}
.tcy {{ text-combine-upright: all; }}
'''
open(OUT, 'w', encoding='utf-8').write(f'<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>{esc(TITLE)}</title><style>{css}</style></head><body>{tcy("".join(H))}</body></html>')
print('blocks', len(body), 'speech', sum(1 for b in body if b[0] == "u"))

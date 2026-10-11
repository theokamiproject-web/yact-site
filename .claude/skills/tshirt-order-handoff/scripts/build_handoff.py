#!/usr/bin/env python3
# 入稿一式を生成する。検査が通らなければ一式を作らずに止まる（成功扱いにしない）。
# 使い方: build_handoff.py --plate plate.svg --out DIR --order order.json --min-line MM --min-gap MM [--artwork art.svg ...]
#         [--ppm 12] [--vendor-label 名称] [--raster-reviewed] [--accept-risk "ユーザーの了承文言"]
#   order.json: {"title","garment","position","width_mm","height_mm","qty":{"M":3,...}}  (会社名・住所・電話は入れない)
#   終了: 0=生成 / 1=不適合で生成せず(選択肢を表示) / 2=ラスター混在で生成せず / 3=環境不足
#   --accept-risk: ユーザーが「細部の再現なし」を明示的に了承した場合のみ。README/報告に原文を記録し、再調整しない。
import sys, os, json, shutil, subprocess, argparse
H = os.path.dirname(os.path.abspath(__file__)); T = os.path.join(os.path.dirname(H), 'templates')
ap = argparse.ArgumentParser(); ap.add_argument('--plate', required=True); ap.add_argument('--out', required=True); ap.add_argument('--order', required=True)
ap.add_argument('--min-line', type=float, required=True); ap.add_argument('--min-gap', type=float, required=True); ap.add_argument('--artwork', nargs='*', default=[])
ap.add_argument('--ppm', type=float, default=12); ap.add_argument('--vendor-label', default='印刷会社'); ap.add_argument('--raster-reviewed', action='store_true'); ap.add_argument('--accept-risk', default='')
a = ap.parse_args(); order = json.load(open(a.order, encoding='utf-8')); os.makedirs(a.out, exist_ok=True)
def run(cmd): r = subprocess.run(cmd, capture_output=True, text=True); return r.returncode, (r.stdout + r.stderr).strip()
# 1 ラスター混在
rc, rtxt = run([sys.executable, os.path.join(H, 'raster_check.py'), a.plate, *a.artwork])
if rc == 3: print(rtxt); sys.exit(3)
if rc == 2 and not a.raster_reviewed: print(rtxt + '\n→ 完成画像を会社基準で実測し、確認したら --raster-reviewed を付けて再実行。一式は作りません。'); sys.exit(2)
# 2 版 → PNG
png = os.path.join(a.out, 'plate.png'); rc2, t2 = run(['node', os.path.join(H, 'svg2png.cjs'), a.plate, png, str(a.ppm), os.environ.get('PLAYWRIGHT_DIR', '')])
if rc2: print('環境/変換 NG:', t2); sys.exit(3)
# 3 最小線幅/隙間
rc3, ftxt = run([sys.executable, os.path.join(H, 'feature_check.py'), png, '--ppm', str(a.ppm), '--min-line', str(a.min_line), '--min-gap', str(a.min_gap)])
print(ftxt)
if rc3 == 3: sys.exit(3)
if rc3 == 1 and not a.accept_risk:
    print('\n不適合の可能性大。自動補正は1回まで。選択肢: ①細部だけ別方式(DTF等) ②簡略化の作り直し ③先に会社のデータチェックを受ける ④ユーザーが了承すれば現状で入稿(--accept-risk に了承文言)。一式は作りません。'); sys.exit(1)
# 4 一式
shutil.copy(a.plate, os.path.join(a.out, 'plate.svg'))
accept = f'- **再現性についてユーザー了承あり**: 「{a.accept_risk}」（細部が再現されなくても構わない旨。再調整しない）\n' if a.accept_risk else ''
qty = order.get('qty', {}); qty_block = '- ' + ' / '.join(f'{k}={v}' for k, v in qty.items()) + f'  → 合計 {sum(qty.values())} 枚' if qty else '- 【枚数未確定】'
fill = dict(title=order.get('title', ''), garment=order.get('garment', ''), position=order.get('position', ''), width_mm=order.get('width_mm', ''), height_mm=order.get('height_mm', ''),
            min_line=a.min_line, min_gap=a.min_gap, vendor_label=a.vendor_label, feature_summary=ftxt.splitlines()[0] + f'（終了コード {rc3}: 0=問題小 1=不適合 2=要確認）',
            raster_summary='なし' if rc == 0 else '**あり**（完成画像を別途実測済みと申告 --raster-reviewed）', accept_block=accept, qty_block=qty_block,
            qty_line=' / '.join(f'{k}={v}' for k, v in qty.items()) or '【】')
for src, dst in (('README-handoff.md.tmpl', 'README.md'), ('mail-inquiry.md.tmpl', 'mail-draft.md')):
    s = open(os.path.join(T, src), encoding='utf-8').read()
    for k, v in fill.items(): s = s.replace('{{' + k + '}}', str(v))
    open(os.path.join(a.out, dst), 'w', encoding='utf-8').write(s)
json.dump(dict(feature_exit=rc3, feature=ftxt, raster_exit=rc, raster=rtxt, accepted_risk=a.accept_risk, min_line=a.min_line, min_gap=a.min_gap, ppm=a.ppm), open(os.path.join(a.out, 'report.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('handoff OK ->', a.out, os.listdir(a.out))

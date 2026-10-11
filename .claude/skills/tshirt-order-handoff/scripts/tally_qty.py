#!/usr/bin/env python3
# サイズ別枚数の集計。使い方: tally_qty.py rows.csv [--base N --relation add|include] [--strict]
#   rows.csv: name,size,qty[,confidence]   confidence = ok | uncertain（OCR・手書き・読みが不確か）。空は ok 扱い。
#   --base: すでに別の合計(元の注文枚数など)がある場合。--relation を必ず併記: add=元に【追加】する / include=元の【内数】(すでに含まれる)
#   uncertain 行は集計に含めつつ「推定」と明記し、確認が必要な行として列挙する（--strict なら exit 2）。
import sys, csv, argparse, collections
ap = argparse.ArgumentParser(); ap.add_argument('csv'); ap.add_argument('--base', type=int); ap.add_argument('--relation', choices=['add', 'include']); ap.add_argument('--strict', action='store_true'); a = ap.parse_args()
if a.base is not None and not a.relation: sys.exit('tally NG: --base には --relation add|include が必要（追加か内包かを確認してから）')
rows = list(csv.DictReader(open(a.csv, encoding='utf-8'))); by = collections.OrderedDict(); unc = []
for r in rows:
    q = int(r['qty']); by[r['size']] = by.get(r['size'], 0) + q
    if (r.get('confidence') or 'ok').strip() != 'ok': unc.append(r)
tot = sum(by.values()); print('サイズ別: ' + ' / '.join(f'{k}={v}' for k, v in by.items()) + f'  → 合計 {tot} 枚')
if a.base is not None:
    if a.relation == 'add': print(f'元 {a.base} 枚に【追加】 → 総計 {a.base + tot} 枚')
    else: print(f'元 {a.base} 枚の【内数】 → 総計 {a.base} 枚' + ('  ✓一致' if tot == a.base else f'  ✗ 内訳合計 {tot} ≠ {a.base}（差 {tot - a.base:+d}）'))
if unc:
    print('推定を含む(読みが不確か。確認してから確定):'); [print(f"  - {r['name']} {r['size']} {r['qty']}枚（推定）") for r in unc]
sys.exit(2 if (unc and a.strict) or (a.relation == 'include' and tot != a.base) else 0)

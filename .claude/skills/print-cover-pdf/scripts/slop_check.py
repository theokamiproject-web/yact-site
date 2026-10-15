#!/usr/bin/env python3
# 「ダサい案」の決まった規則による検出（LLMなし・毎回同じ結果）。方式は impeccable（Apache-2.0, https://github.com/pbakaus/impeccable）の
# 「AIっぽさを決定的な規則で検出する」考え方を借りたもの。規則そのものは、この案件群の失敗（台本表紙18案）から作った独自のもの。
# 使い方: slop_check.py A.png [B.png ...]   （PNG=黒インク/白地。表紙全体）
# 終了コード: 0=指摘なし / 1=指摘あり（直してから出す）。数値は判断材料。最後は画像を自分の目で読む。
import sys, numpy as np
from PIL import Image
from scipy import ndimage as ndi

def analyze(p):
    g = np.asarray(Image.open(p).convert('L')); m = g < 128; h, w = m.shape; tot = int(m.sum()); out = []
    if tot == 0: return ['空白（インクがない）']
    ys, xs = np.nonzero(m); x0, x1, y0, y1 = xs.min() / w, xs.max() / w, ys.min() / h, ys.max() / h
    span = (x1 - x0) * (y1 - y0) * 100; black = 100 * tot / (w * h)
    lab, n = ndi.label(ndi.binary_closing(m, iterations=2)); sizes = ndi.sum(m, lab, range(1, n + 1)); big = sizes[sizes >= tot * .005]
    lead = 100 * big.max() / tot
    margins = (x0, 1 - x1, y0, 1 - y1)
    # 1 縮こまり: 使用範囲が小さく、四辺とも余白が大きい（前例: 図が紙面中央の約50%に収まっていた）
    if span < 45 and min(margins) > .08: out.append(f'R1 縮こまり: 使用範囲 {span:.0f}% / 最小余白 {min(margins)*100:.0f}%。端まで使う（安全余白は守る）か、極端に小さく置いて対比を作る')
    # 2 主役が弱い: 最大の塊がインクの20%未満（均等な小要素の寄せ集め）
    if lead < 20 and len(big) > 4: out.append(f'R2 主役が弱い: 最大要素 {lead:.0f}% / 要素 {len(big)}。1つを桁違いに大きく（または他を極小に）')
    # 3 要素過多（前例: 図形が多すぎる）
    if len(big) > 12: out.append(f'R3 要素過多: {len(big)} 個。2〜3種に減らす')
    # 4 黒ベタ（K単色の回避ルール）
    if black > 15: out.append(f'R4 黒面積 {black:.0f}%。10〜15%を超える面は線・網点へ')
    # 5 左右対称の静的構図（前例: 左に図・右に題字、が全案で同じ骨格だった。対称は動きがない）
    mir = m[:, ::-1]; sym = 100 * (m & mir).sum() / max(1, (m | mir).sum())
    if sym > 70: out.append(f'R5 左右対称 {sym:.0f}%。静的。非対称にずらす')
    # 6 線幅が均一すぎる（コードで描いた完璧な幾何。前例: 採用案は線の太さがばらついていた）。線画が主体のときだけ
    if black < 8:
        dt = ndi.distance_transform_edt(m); ridge = (dt >= ndi.maximum_filter(dt, 3)) & (dt > 1.2); t = 2 * dt[ridge]
        if t.size > 300 and t.std() / t.mean() < .12: out.append(f'R6 線幅が均一: 変動 {t.std()/t.mean():.2f}。roughen.py / sketchy.mjs で手の痕跡を（文字は除く）')
    # 7 重心が中央に張り付く
    cy, cx = ndi.center_of_mass(m); off = np.hypot(cx / w - .5, cy / h - .5) * 100
    if off < 4 and span < 70: out.append(f'R7 重心が中央 (ずれ {off:.0f}%)。動きがない。重心を寄せるか、余白を偏らせる')
    return out

bad = 0
for p in sys.argv[1:]:
    r = analyze(p); bad += bool(r); print(('NG  ' if r else 'OK  ') + p)
    for x in r: print('    ' + x)
sys.exit(1 if bad else 0)

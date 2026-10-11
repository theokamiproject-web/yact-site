#!/bin/bash
# 最小再現テスト: 版データ → PNG → 最小線幅/隙間検査 → ラスター混在検査 → 入稿一式生成。正常系＋不適合(拒否されること)。
# 前提: node + PLAYWRIGHT_DIR (playwright|playwright-core) + 任意 CHROMIUM_PATH、python: numpy pillow scipy。足りなければ exit 3。
set -u; T=$(cd "$(dirname "$0")" && pwd); S=$(dirname "$T")/scripts; W=${TMPDIR:-/tmp}/tho-fixture; rm -rf "$W"; mkdir -p "$W"
pass=0; fail=0; ok() { echo "PASS  $1"; pass=$((pass+1)); }; ng() { echo "FAIL  $1"; fail=$((fail+1)); }
python3 -c "import numpy, PIL, scipy" 2>/dev/null || { echo "ENV NG: python numpy/pillow/scipy (exit 3)"; exit 3; }
node -e "require('${PLAYWRIGHT_DIR:-playwright}')" 2>/dev/null || { echo "ENV NG: playwright (PLAYWRIGHT_DIR) (exit 3)"; exit 3; }
python3 - "$W" <<'PY'
import sys; w = sys.argv[1]
def svg(body, extra=''): return f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="80mm" height="60mm" viewBox="0 0 80 60"><rect width="80" height="60" fill="#fff"/>{body}{extra}</svg>'
bars = lambda wd, gap, n: ''.join(f'<path d="M{10 + i * (wd + gap)} 10h{wd}v40h-{wd}z" fill="#000"/>' for i in range(n))
open(f'{w}/art-ok.svg', 'w').write(svg(bars(3, 4, 8)))                      # 太い線(3mm)・広い隙間(4mm)
open(f'{w}/art-thin.svg', 'w').write(svg(bars(0.3, 0.4, 60)))                # 極細(0.3mm)・狭い隙間(0.4mm)
open(f'{w}/art-raster.svg', 'w').write(svg(bars(3, 4, 8), '<image x="5" y="5" width="4" height="4" xlink:href="data:image/png;base64,AAAA"/>'))
open(f'{w}/art-text.svg', 'w').write(svg('<text x="5" y="20" font-size="8">raw</text>'))
open(f'{w}/art-stroke.svg', 'w').write(svg('<path d="M10 10h60" stroke="#000" stroke-width="2" fill="none"/>'))
import json; json.dump(dict(title='試験版', garment='濃色', position='左胸', width_mm=80, height_mm=60, qty={'M': 3, 'L': 2}), open(f'{w}/order.json', 'w'), ensure_ascii=False)
from PIL import Image, ImageDraw
im = Image.new('L', (960, 720), 0); d = ImageDraw.Draw(im); [d.rectangle([100 + i * 80, 100, 140 + i * 80, 600], fill=255) for i in range(8)]; im.save(f'{w}/inverted.png')  # 黒地に白図形=反転
open(f'{w}/rows.csv', 'w').write('name,size,qty,confidence\nA,M,2,ok\nB,L,1,ok\nC,L,1,uncertain\n')
PY
PW=${PLAYWRIGHT_DIR:-}
# 版作成 -------------------------------------------------------------------------------------------
python3 "$S/make_plate.py" "$W/art-ok.svg" "$W/plate-ok.svg" >/dev/null && ok "make_plate: 正常な単一パス版を作成" || ng "make_plate 正常系"
python3 "$S/make_plate.py" "$W/art-thin.svg" "$W/plate-thin.svg" >/dev/null; python3 "$S/make_plate.py" "$W/art-raster.svg" "$W/plate-raster.svg" >/dev/null 2>&1; [ $? -eq 2 ] && ok "make_plate: ラスター入りを拒否(exit 2)" || ng "make_plate ラスター拒否"
python3 "$S/make_plate.py" "$W/art-text.svg" "$W/x.svg" >/dev/null 2>&1; [ $? -eq 2 ] && ok "make_plate: <text>(未アウトライン)を拒否" || ng "make_plate text"
python3 "$S/make_plate.py" "$W/art-stroke.svg" "$W/x.svg" >/dev/null 2>&1; [ $? -eq 2 ] && ok "make_plate: stroke線(外形化前)を拒否" || ng "make_plate stroke"
grep -q 'fill="#000000"' "$W/plate-ok.svg" && grep -q 'fill="#FFFFFF"' "$W/plate-ok.svg" && ok "版は 黒=インク / 白=抜き" || ng "版の色定義"
# raster_check -------------------------------------------------------------------------------------
python3 "$S/raster_check.py" "$W/art-ok.svg" >/dev/null && ok "raster_check: ラスターなし=0" || ng "raster_check 正常"
python3 "$S/raster_check.py" "$W/art-raster.svg" >"$W/r.log" 2>&1; [ $? -eq 2 ] && grep -q "PASSは無効" "$W/r.log" && ok "raster_check: ラスター検出(exit 2)＋PASS無効の警告" || ng "raster_check 検出"
# 入稿一式: 正常 -----------------------------------------------------------------------------------
PLAYWRIGHT_DIR=$PW python3 "$S/build_handoff.py" --plate "$W/plate-ok.svg" --artwork "$W/art-ok.svg" --out "$W/h-ok" --order "$W/order.json" --min-line 1 --min-gap 2 >"$W/h-ok.log" 2>&1; rc=$?
[ $rc -eq 0 ] && [ -f "$W/h-ok/README.md" ] && [ -f "$W/h-ok/plate.png" ] && [ -f "$W/h-ok/mail-draft.md" ] && [ -f "$W/h-ok/report.json" ] && ok "build_handoff: 正常データで一式生成(README/PNG/mail/report)" || { ng "build_handoff 正常 (rc=$rc)"; tail -8 "$W/h-ok.log"; }
grep -q "黒＝インクが乗る場所" "$W/h-ok/README.md" && grep -q "白インク" "$W/h-ok/README.md" && ok "READMEに 黒=インク・下地=白インク の定義" || ng "README定義"
grep -q "合計 5 枚" "$W/h-ok/README.md" && ok "READMEの枚数合計が内訳と一致" || ng "枚数"
! grep -qE "[A-Za-z0-9._-]+@[A-Za-z0-9.-]+|0[0-9]{1,4}-[0-9]{1,4}-[0-9]{3,4}" "$W/h-ok/mail-draft.md" && grep -q "【" "$W/h-ok/mail-draft.md" && ok "メール雛形に実在の宛先なし(【】プレースホルダ)" || ng "メール雛形"
# 不適合 -------------------------------------------------------------------------------------------
PLAYWRIGHT_DIR=$PW python3 "$S/build_handoff.py" --plate "$W/plate-thin.svg" --out "$W/h-thin" --order "$W/order.json" --min-line 1 --min-gap 2 >"$W/h-thin.log" 2>&1; rc=$?
[ $rc -eq 1 ] && [ ! -f "$W/h-thin/README.md" ] && grep -q "一式は作りません" "$W/h-thin.log" && ok "細すぎる版: 一式を作らず exit 1（選択肢を表示）" || { ng "thin 拒否 (rc=$rc)"; tail -5 "$W/h-thin.log"; }
PLAYWRIGHT_DIR=$PW python3 "$S/build_handoff.py" --plate "$W/plate-thin.svg" --out "$W/h-thin2" --order "$W/order.json" --min-line 1 --min-gap 2 --accept-risk "細部の再現なしで構いません" >/dev/null 2>&1; rc=$?
[ $rc -eq 0 ] && grep -q "細部の再現なしで構いません" "$W/h-thin2/README.md" && ok "ユーザー了承(--accept-risk)があれば生成し、了承をREADMEに記録" || ng "accept-risk (rc=$rc)"
PLAYWRIGHT_DIR=$PW python3 "$S/build_handoff.py" --plate "$W/plate-ok.svg" --artwork "$W/art-raster.svg" --out "$W/h-ras" --order "$W/order.json" --min-line 1 --min-gap 2 >"$W/h-ras.log" 2>&1; rc=$?
[ $rc -eq 2 ] && [ ! -f "$W/h-ras/README.md" ] && ok "ラスター混在: 一式を作らず exit 2（--raster-reviewed 要）" || ng "ラスター混在の停止 (rc=$rc)"
PLAYWRIGHT_DIR=$PW python3 "$S/build_handoff.py" --plate "$W/plate-ok.svg" --artwork "$W/art-raster.svg" --out "$W/h-ras2" --order "$W/order.json" --min-line 1 --min-gap 2 --raster-reviewed >/dev/null 2>&1 && grep -q "あり" "$W/h-ras2/README.md" && ok "--raster-reviewed なら生成し、READMEにラスターありと明記" || ng "raster-reviewed"
python3 "$S/feature_check.py" "$W/inverted.png" --ppm 12 --min-line 1 --min-gap 2 >"$W/inv.log" 2>&1; rc=$?; [ $rc -eq 2 ] && grep -q "反転" "$W/inv.log" && ok "feature_check: 反転(黒地)版は exit 2 で止める" || ng "反転検出 (rc=$rc)"
# 環境不足は成功扱いにしない
PLAYWRIGHT_DIR=/nonexistent python3 "$S/build_handoff.py" --plate "$W/plate-ok.svg" --out "$W/h-env" --order "$W/order.json" --min-line 1 --min-gap 2 >"$W/h-env.log" 2>&1; rc=$?
[ $rc -ne 0 ] && [ ! -f "$W/h-env/README.md" ] && ! grep -q "handoff OK" "$W/h-env.log" && ok "playwright不在: 失敗(exit≠0)・一式なし" || ng "環境不足が成功扱い (rc=$rc)"
# 枚数集計 -----------------------------------------------------------------------------------------
python3 "$S/tally_qty.py" "$W/rows.csv" --base 4 >/dev/null 2>&1; [ $? -ne 0 ] && ok "tally: --base だけ(追加/内包 未指定)はエラー" || ng "tally relation 必須"
python3 "$S/tally_qty.py" "$W/rows.csv" --base 10 --relation add >"$W/t1.log"; grep -q "総計 14 枚" "$W/t1.log" && ok "tally: 追加 → 10+4=14" || ng "tally add"
python3 "$S/tally_qty.py" "$W/rows.csv" --base 10 --relation include >"$W/t2.log"; rc=$?; [ $rc -eq 2 ] && grep -q "✗" "$W/t2.log" && ok "tally: 内包で内訳合計≠元 → 不一致を検出(exit 2)" || ng "tally include (rc=$rc)"
grep -q "（推定）" "$W/t1.log" && ok "tally: 読みが不確かな行を『推定』と明記" || ng "tally 推定"
python3 "$S/tally_qty.py" "$W/rows.csv" --strict >/dev/null; [ $? -eq 2 ] && ok "tally --strict: 推定を含むと exit 2" || ng "tally strict"
# 公開監査 -----------------------------------------------------------------------------------------
python3 "$S/public_audit.py" "$(dirname "$T")" >"$W/aud.log" 2>&1 && ok "公開監査: このSkillに個人情報/金額/絶対パス/鍵なし" || { ng "公開監査"; cat "$W/aud.log"; }
# 検出パターンがこのファイル自体に載らないよう、文字列は分割して組み立てる
mkdir -p "$W/seed"; printf '%s\n' "contact: someone""@""private-mail.jp 03""-1234-""5678 ""¥""12,000 /ho""me/user/x" > "$W/seed/a.md"; python3 "$S/public_audit.py" "$W/seed" >/dev/null 2>&1; [ $? -ne 0 ] && ok "公開監査: 混入(メール/電話/金額/パス)を検出して失敗" || ng "公開監査が混入を見逃す"
echo "---- $pass passed, $fail failed"; [ $fail -eq 0 ]

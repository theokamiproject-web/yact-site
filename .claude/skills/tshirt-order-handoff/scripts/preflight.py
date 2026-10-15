#!/usr/bin/env python3
# 入稿前チェック（送る前に1回）。PDF・README・メール本文を機械的に確認し、任意で zip を作る。
# 使い方: preflight.py --pdf front.pdf:92:67 --pdf back.pdf:300:300 --text README.txt --text mail.md [--accept-loss] [--zip out.zip DIR]
#   --pdf FILE:W_mm:H_mm  フォント0（曲線化）／画像0（ベクター）／1ページ／寸法が ±0.5mm で一致
#   --text FILE           「白インク（または下地（白））」「着用者から見て」が入っているか。【】の残りは警告（依頼主が埋める欄）
#   --accept-loss         依頼主が「細部の再現なし」を了承したときだけ付ける → 了承文言が必須になる。付けないのに文言があれば NG
# 終了コード: 0=全OK / 1=NGあり（zip は作らない） / 2=入力エラー
# PDF生成は print-cover-pdf の scripts/svg2pdf.cjs を使う（gray_pdf.py はK単色用なのでカラーのTシャツ版には使わない。寸法の丸めは ±0.5mm 判定で確認）。
import sys, os, re, argparse, subprocess, zipfile

LOSS = re.compile(r'再現(され)?(な|性な)')
NEED = {r'白インク|下地[（(]白': '下地=白インクの明記', '着用者から見て': '位置の左右（着用者から見て）'}
# 未記入欄: 【】【　】【N】【M/D】【〜場合のみ】。見出し（【共通】等）は対象外
HOLE = re.compile(r'【(\s*|[\x20-\x7e]+|[^】]*場合のみ)】')

def run(*c): return subprocess.run(c, capture_output=True, text=True, check=True).stdout

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--pdf', action='append', default=[]); ap.add_argument('--text', action='append', default=[])
    ap.add_argument('--accept-loss', action='store_true'); ap.add_argument('--zip', nargs=2, metavar=('OUT', 'DIR')); a = ap.parse_args()
    if not a.pdf and not a.text: ap.error('--pdf か --text を1つ以上')
    ng = 0
    def rep(ok, msg, warn=False):
        nonlocal ng; ng += (not ok and not warn); print('OK  ' if ok else ('WARN' if warn else 'NG  '), msg)
    for spec in a.pdf:
        try: f, w, h = spec.rsplit(':', 2); w, h = float(w), float(h)
        except ValueError: print('入力エラー: --pdf は FILE:W_mm:H_mm', spec); sys.exit(2)
        if not os.path.exists(f): print('入力エラー: ファイルが無い', f); sys.exit(2)
        info = run('pdfinfo', f); pages = int(re.search(r'Pages:\s+(\d+)', info).group(1))
        pw, ph = [float(x) / 72 * 25.4 for x in re.search(r'Page size:\s+([\d.]+) x ([\d.]+)', info).groups()]
        nf = len(run('pdffonts', f).strip().splitlines()) - 2; ni = len(run('pdfimages', '-list', f).strip().splitlines()) - 2
        n = os.path.basename(f)
        rep(nf == 0, f'{n}: フォント埋め込み {nf}（0=曲線化済み）'); rep(ni == 0, f'{n}: 画像 {ni}（0=ベクターのみ）')
        rep(pages == 1, f'{n}: ページ数 {pages}')
        rep(abs(pw - w) <= .5 and abs(ph - h) <= .5, f'{n}: 寸法 {pw:.1f}x{ph:.1f}mm（指定 {w:g}x{h:g}mm, 許容±0.5）')
    for f in a.text:
        if not os.path.exists(f): print('入力エラー: ファイルが無い', f); sys.exit(2)
        s = open(f, encoding='utf-8').read(); n = os.path.basename(f)
        for k, why in NEED.items(): rep(bool(re.search(k, s)), f'{n}: {why}')
        has = bool(LOSS.search(s))
        if a.accept_loss: rep(has, f'{n}: 「細部の再現なし了承」の文言（--accept-loss 指定あり）')
        else: rep(not has, f'{n}: 了承していないのに「再現なし」の文言が入っていない')
        left = len(HOLE.findall(s)); rep(left == 0, f'{n}: 未記入の【】 {left} 箇所（送信前に依頼主が埋める）', warn=True)
    if ng: print(f'\n結果: NG {ng} 件 → 修正してから再実行（zip は作らない）'); sys.exit(1)
    if a.zip:
        out, d = a.zip
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
            for r, _, fs in os.walk(d):
                for x in sorted(fs):
                    if not x.startswith('.'): p = os.path.join(r, x); z.write(p, os.path.relpath(p, os.path.dirname(os.path.abspath(d))))
        print('zip:', out, f'{os.path.getsize(out)/1e6:.1f}MB')
    print('\n結果: 全OK'); sys.exit(0)

if __name__ == '__main__': main()

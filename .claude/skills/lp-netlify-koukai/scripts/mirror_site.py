"""公開中のLPを、参照しているファイルごと丸ごと手元に復元する。
Netlify へのデプロイはディレクトリ全体の差し替えなので、手元に無いファイルは本番から消える。
手元のソースが無いとき（コンテナが替わった等）は、編集の前にこれで復元する。

usage: python3 mirror_site.py https://example.netlify.app/ 出力ディレクトリ
- index.html を取得し、src/href/srcset/url()/"assets/..." から相対パスのファイルを拾って取得する
- 取得できなかったもの（本番でも404など）は NG として一覧に出し、ファイルは作らない
"""
import re, sys, os, urllib.parse, urllib.request

base = sys.argv[1].rstrip('/') + '/'
out = sys.argv[2]
os.makedirs(out, exist_ok=True)


def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'site-mirror'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


html = get(base).decode('utf-8')
open(os.path.join(out, 'index.html'), 'w', encoding='utf-8').write(html)

cands = set()
for m in re.finditer(r'(?:src|href|content|poster|data-src|data-full|data-img)\s*=\s*"([^"]+)"', html):
    cands.add(m.group(1))
for m in re.finditer(r'srcset\s*=\s*"([^"]+)"', html):
    for part in m.group(1).split(','):
        cands.add(part.strip().split(' ')[0])
for m in re.finditer(r'url\(([^)]+)\)', html):
    cands.add(m.group(1).strip('\'" '))
for m in re.finditer(r'["\'](assets/[^"\']+)["\']', html):
    cands.add(m.group(1))
for extra in ('favicon.ico', 'favicon.png', 'robots.txt', 'apple-touch-icon.png'):
    cands.add(extra)

paths = set()
for c in cands:
    if c.startswith(base):
        c = c[len(base):]
    if not c or c.startswith(('http', '//', '#', 'mailto:', 'tel:', 'data:', 'javascript:')) or '${' in c:
        continue
    c = c.split('#')[0].split('?')[0].lstrip('/')
    if c and '.' in c.split('/')[-1] and ' ' not in c:
        paths.add(c)

ok, ng = 0, []
for p in sorted(paths):
    try:
        data = get(base + urllib.parse.quote(p))
    except Exception as e:
        ng.append(f'{p} ({getattr(e, "code", e)})')
        continue
    dst = os.path.join(out, p)
    os.makedirs(os.path.dirname(dst) or out, exist_ok=True)
    open(dst, 'wb').write(data)
    ok += 1
print(f'index.html + {ok} files -> {out}')
if ng:
    print('NG（本番でも取得できない。favicon等の候補は無くて正常なこともある）:')
    print('\n'.join('  ' + x for x in ng))

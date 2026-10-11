#!/usr/bin/env python3
# 公開前監査（公開リポジトリ用）。使い方: public_audit.py DIR [DIR...]   検出があれば exit 1。
# 検出: メールアドレス(example.* 除く)・電話番号・注文/発注番号らしき文字列・金額・ローカル絶対パス・長い英数ID(Drive等)・鍵/トークン
import sys, re, os
PAT = [('メール', r'[\w.+-]+@(?!example\.)[\w-]+\.[\w.-]+'), ('電話', r'\b0\d{1,4}-\d{1,4}-\d{3,4}\b'), ('注文番号', r'\b[A-Z]{2,}-\d{6,}[-\d]*\b'),
       ('金額', r'(?:¥\s?\d[\d,]*|\d[\d,]{2,}\s?円)'), ('絶対パス', r'(?:/home/|/Users/|/root/|/tmp/claude|[A-Z]:\\\\)\S+'), ('長いID', r'\b[A-Za-z0-9_-]{28,}\b'),
       ('鍵/トークン', r'(?i)(?:sk-[A-Za-z0-9]{10,}|ghp_[A-Za-z0-9]{10,}|AKIA[0-9A-Z]{12,}|api[_-]?key\s*[:=]|bearer\s+[A-Za-z0-9._-]{10,}|password\s*[:=])')]
bad = 0
for d in sys.argv[1:]:
    for root, _, fs in os.walk(d):
        for f in fs:
            p = os.path.join(root, f)
            if '/node_modules/' in p or p.endswith(('.png', '.pdf', '.woff', '.jpg')): continue
            try: s = open(p, encoding='utf-8').read()
            except Exception: continue
            for name, pat in PAT:
                for m in re.finditer(pat, s):
                    if os.path.basename(p) == 'public_audit.py': continue
                    print(f'{name}: {p}: {m.group(0)[:70]}'); bad += 1
print('AUDIT ' + ('NG %d 件' % bad if bad else 'OK (検出なし)')); sys.exit(1 if bad else 0)

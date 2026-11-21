#!/usr/bin/env bash
# デプロイ後に、本番のLPが新しい版になったかを確かめる。
# usage: verify_live.sh <URL> "<新しく入れた文言>" ["<消えたはずの文言>"] [確認するファイルのパス...]
# 例: verify_live.sh https://example.netlify.app "受付中のお知らせ" "販売は<b>終演後" assets/main-visual.jpg
set -u
URL="${1%/}"; NEW="$2"; OLD="${3:-}"; shift 2; [ $# -gt 0 ] && shift
TMP="$(mktemp)"
curl -s "$URL/?v=$(date +%s)" -o "$TMP"   # キャッシュを避ける
fail=0
if grep -F -- "$NEW" "$TMP" >/dev/null; then echo "OK  新しい文言あり: $NEW"; else echo "NG  新しい文言がない: $NEW"; fail=1; fi
if [ -n "$OLD" ]; then
  if grep -F -- "$OLD" "$TMP" >/dev/null; then echo "NG  古い文言が残っている: $OLD"; fail=1; else echo "OK  古い文言は消えた: $OLD"; fi
fi
for p in "$@"; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "$URL/$p")
  if [ "$code" = "200" ]; then echo "OK  $code $p"; else echo "NG  $code $p"; fail=1; fi
done
rm -f "$TMP"
exit $fail

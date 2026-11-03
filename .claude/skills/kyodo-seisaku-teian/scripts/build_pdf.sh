#!/usr/bin/env bash
# 提案書Markdown → 印刷HTML → PDF → 組版チェック → ページ数 → 確認用PNG
# 使い方: bash build_pdf.sh input.md output.pdf [workdir]
#   workdir（省略時は output と同じ場所）に print HTML と page_N.png を出す。PNGは確認後に消す。
set -euo pipefail
IN="$1"; OUT="$2"; WORK="${3:-$(dirname "$OUT")}"
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$WORK"
HTML="$WORK/$(basename "${OUT%.pdf}")-print.html"

# 1) 環境: wkhtmltopdf は無いことが多い → weasyprint。日本語フォントが無ければ入れる
# pip ではなく python3 -m pip（pip が別の Python を指していることがある）
# システムの Pillow（/usr/lib/python3/dist-packages）が壊れていて weasyprint が落ちることがある → --ignore-installed で入れ直す
python3 -c "import weasyprint, pypdf, pymupdf" 2>/dev/null || python3 -m pip install -q --ignore-installed pillow weasyprint pypdf pymupdf --break-system-packages 2>&1 | grep -v WARNING || true
# 新しいコンテナでは apt-get update しないとパッケージが見つからない。入れた後は fc-cache で認識させる
fc-list | grep "Noto Serif CJK JP" >/dev/null || { { apt-get update -q >/dev/null 2>&1; apt-get install -y -q fonts-noto-cjk fonts-ipafont >/dev/null 2>&1; fc-cache -f >/dev/null 2>&1; } || echo "⚠️ フォント導入失敗（ネットワーク不可？）: IPAフォント等で代替される"; }
fc-list | grep "Noto Serif CJK JP" >/dev/null || echo "⚠️ Noto CJK 無し: 明朝が中国語字形やゴシックに化ける恐れ。PNGで字形を必ず確認"

# 2) 変換
python3 "$HERE/md_to_print_html.py" "$IN" "$HTML"
python3 -m weasyprint "$HTML" "$OUT"

# 3) 組版チェック（pdf-eigyo-maker の検査スクリプトがあれば使う）
CHECK=$(ls /root/.claude/skills/*/*/pdf-eigyo-maker/scripts/verify_japanese_pdf.py ~/.claude/skills/pdf-eigyo-maker/scripts/verify_japanese_pdf.py 2>/dev/null | head -1 || true)
if [ -n "$CHECK" ]; then python3 "$CHECK" "$HTML" "$OUT" || echo "⚠️ 組版チェックで指摘あり（全角スペースを<p>内で区切りに使うと誤検知する→「・」に替える）"; fi

# 4) ページ数と確認用PNG（見るのは1回だけ）
python3 - "$OUT" "$WORK" <<'PY'
import sys, pymupdf
doc = pymupdf.open(sys.argv[1])
print(f"📄 {len(doc)}ページ")
for i, p in enumerate(doc, 1):
    p.get_pixmap(dpi=100).save(f"{sys.argv[2]}/page_{i}.png")
PY
echo "確認用: $WORK/page_*.png（確認後に削除）"

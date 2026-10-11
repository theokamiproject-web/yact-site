#!/bin/bash
# SVG → ベクターPDF → K単色(グレー)・TrimBox → 最終検査。どれかが失敗したら exit 1（成功扱いにしない）。
# 使い方: run_pipeline.sh in.svg out.pdf PAGE_W PAGE_H BLEED MIN_MARGIN [MAX_BLACK]
#   PAGE_W/H = 塗り足し込みの入稿ページ(mm)。SVG のサイズと一致させる。環境変数: NODE_MODULES PLAYWRIGHT_DIR CHROMIUM_PATH
set -e; H=$(cd "$(dirname "$0")" && pwd)
SVG=$1; OUT=$2; W=$3; HH=$4; BL=$5; MM=$6; MB=${7:-}
bash "$H/env_check.sh" "${NODE_MODULES:-}"
RAW=$(mktemp --suffix=.pdf)
node "$H/svg2pdf.cjs" "$SVG" "$RAW" "${PLAYWRIGHT_DIR:-}"
python3 "$H/gray_pdf.py" "$RAW" "$OUT" "$W" "$HH" "$BL"
python3 "$H/check_pdf.py" "$OUT" --size "$W" "$HH" --bleed "$BL" --min-margin "$MM" ${MB:+--max-black "$MB"}
rm -f "$RAW"

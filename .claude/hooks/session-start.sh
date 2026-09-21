#!/bin/bash
# Claude Code on the web 用のセットアップ。
# 台本・申請書などの .docx / .xlsx を PDF にするために LibreOffice Writer と
# 日本語フォントを入れ、Word の日本語フォント指定を Noto CJK JP に寄せる。
# これが無いと soffice が "source file could not be loaded" で落ち、
# 入っても漢字が中国語フォント（WenQuanYi）に化けて潰れる。
set -euo pipefail

# ローカル環境は各自の設定を壊さないよう触らない
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

export DEBIAN_FRONTEND=noninteractive

# 1) Writer 本体と日本語フォント（既に入っていれば apt が何もしない）
if [ ! -f /usr/lib/libreoffice/program/libswlo.so ] || ! fc-list :lang=ja 2>/dev/null | grep -q "Noto Serif CJK JP"; then
  apt-get update -qq
  apt-get install -y -qq libreoffice-writer fonts-noto-cjk
fi

# 2) Word の日本語フォント指定の受け皿。游明朝→Noto Serif、游ゴシック→Noto Sans。
#    これが無いと中国語フォントに落ちて漢字が黒く潰れる。
FC=/etc/fonts/conf.d/99-ja-prefer-noto.conf
if [ ! -f "$FC" ]; then
  cat > "$FC" <<'XML'
<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
  <alias binding="same"><family>游明朝</family><accept><family>Noto Serif CJK JP</family></accept></alias>
  <alias binding="same"><family>Yu Mincho</family><accept><family>Noto Serif CJK JP</family></accept></alias>
  <alias binding="same"><family>MS Mincho</family><accept><family>Noto Serif CJK JP</family></accept></alias>
  <alias binding="same"><family>ＭＳ 明朝</family><accept><family>Noto Serif CJK JP</family></accept></alias>
  <alias binding="same"><family>游ゴシック</family><accept><family>Noto Sans CJK JP</family></accept></alias>
  <alias binding="same"><family>Yu Gothic</family><accept><family>Noto Sans CJK JP</family></accept></alias>
  <alias binding="same"><family>MS Gothic</family><accept><family>Noto Sans CJK JP</family></accept></alias>
  <alias binding="same"><family>ＭＳ ゴシック</family><accept><family>Noto Sans CJK JP</family></accept></alias>

  <match target="pattern">
    <test name="lang" compare="contains"><string>ja</string></test>
    <test name="family"><string>WenQuanYi Zen Hei</string></test>
    <edit name="family" mode="prepend" binding="strong"><string>Noto Sans CJK JP</string></edit>
  </match>
  <selectfont><rejectfont>
    <pattern><patelt name="family"><string>WenQuanYi Zen Hei Sharp</string></patelt></pattern>
  </rejectfont></selectfont>
</fontconfig>
XML
  fc-cache -f >/dev/null 2>&1 || true
fi

# 3) 実際に変換できるところまで確認する（ここで落ちるなら気づけたほうがいい）
SMOKE=$(mktemp -d)
printf '\u3042\u3044\u3046\u3048\u304a\n' > "$SMOKE/smoke.txt"
if soffice --headless --norestore --convert-to pdf --outdir "$SMOKE" "$SMOKE/smoke.txt" >/dev/null 2>&1 \
   && [ -s "$SMOKE/smoke.pdf" ]; then
  echo "setup: docx/txt -> PDF 変換が使えます（LibreOffice Writer + Noto CJK JP）"
else
  echo "setup: 警告 — LibreOffice の変換が動いていません。手動で確認してください" >&2
fi
rm -rf "$SMOKE"

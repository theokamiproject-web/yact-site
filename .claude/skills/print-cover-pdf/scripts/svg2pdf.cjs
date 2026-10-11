// SVG(mm指定) → ベクターPDF（Chromium）。使い方: node svg2pdf.cjs in.svg out-raw.pdf [PLAYWRIGHT_DIR]
// 環境変数: PLAYWRIGHT_DIR（playwright / playwright-core の場所）, CHROMIUM_PATH（実行ファイル。未指定なら playwright 既定）
// 注意: Chromium は用紙高さを丸めて 0.1〜0.7mm 大きく出す → gray_pdf.py で正確な判型に直す
// 失敗（依存なし・起動失敗・PDF無し）は必ず exit 1。
const fs = require('fs'); const [inp, out, pw] = process.argv.slice(2);
const die = (msg) => { console.error('svg2pdf NG: ' + msg); process.exit(1); };
if (!inp || !out) die('usage: svg2pdf.cjs in.svg out.pdf [PLAYWRIGHT_DIR]');
let chromium; try { ({ chromium } = require(pw || process.env.PLAYWRIGHT_DIR || 'playwright')); } catch (e) { die('playwright が読み込めない: ' + e.message.split('\n')[0]); }
(async () => {
  const s = fs.readFileSync(inp, 'utf8'); const m = s.match(/width="([\d.]+)mm" height="([\d.]+)mm"/); if (!m) die('svg に width="..mm" height="..mm" が必要');
  const opt = process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {};
  const b = await chromium.launch(opt); const p = await b.newPage();
  await p.setContent(`<style>@page{size:${m[1]}mm ${m[2]}mm;margin:0}html,body{margin:0;background:#fff}svg{display:block}</style>${s}`);
  await p.pdf({ path: out, width: m[1] + 'mm', height: m[2] + 'mm', printBackground: true, pageRanges: '1' }); await b.close();
  if (!fs.existsSync(out) || fs.statSync(out).size < 200) die('PDF が生成されていない');
  console.log('ok', out);
})().catch((e) => die(e.message.split('\n')[0]));

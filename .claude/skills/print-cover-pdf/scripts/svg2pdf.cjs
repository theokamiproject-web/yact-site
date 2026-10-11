// SVG(mm指定) → ベクターPDF（Chromium）。使い方: node svg2pdf.cjs in.svg out-raw.pdf [PLAYWRIGHT_DIR]
// 注意: Chromium は用紙高さを丸めて 0.1〜0.7mm 大きく出す → gray_pdf.py で正確な判型に直す
const fs = require('fs'); const [inp, out, pw] = process.argv.slice(2);
const { chromium } = require(pw || process.env.PLAYWRIGHT_DIR || 'playwright');
(async () => { const s = fs.readFileSync(inp, 'utf8'); const m = s.match(/width="([\d.]+)mm" height="([\d.]+)mm"/); if (!m) throw new Error('svg に width="..mm" height="..mm" が必要');
  const b = await chromium.launch(); const p = await b.newPage();
  await p.setContent(`<style>@page{size:${m[1]}mm ${m[2]}mm;margin:0}html,body{margin:0;background:#fff}svg{display:block}</style>${s}`);
  await p.pdf({ path: out, width: m[1] + 'mm', height: m[2] + 'mm', printBackground: true, pageRanges: '1' }); await b.close(); })();

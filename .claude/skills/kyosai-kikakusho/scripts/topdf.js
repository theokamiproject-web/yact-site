// 使い方: node topdf.js input.html output.pdf
// A4・余白0（余白はHTML側の .page の padding で取る）。画像・背景色も印刷する。
const { chromium } = require('playwright');
const path = require('path');
(async () => {
  const [inp, out] = process.argv.slice(2);
  if (!inp || !out) { console.error('usage: node topdf.js input.html output.pdf'); process.exit(1); }
  const b = await chromium.launch(); const p = await b.newPage();
  await p.goto('file://' + path.resolve(inp), { waitUntil: 'load' });
  await p.pdf({ path: out, format: 'A4', printBackground: true, margin: { top: 0, bottom: 0, left: 0, right: 0 } });
  await b.close();
})();

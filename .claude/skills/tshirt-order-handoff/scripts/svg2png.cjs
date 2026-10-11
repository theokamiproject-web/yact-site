// SVG(mm指定) → PNG（px/mm 指定）。 使い方: node svg2png.cjs in.svg out.png PX_PER_MM [PLAYWRIGHT_DIR]
// 環境変数: PLAYWRIGHT_DIR, CHROMIUM_PATH。失敗は必ず exit 1（黙って成功にしない）。
const fs = require('fs'); const [inp, out, ppm, pw] = process.argv.slice(2);
const die = (m) => { console.error('svg2png NG: ' + m); process.exit(1); };
if (!inp || !out || !ppm) die('usage: svg2png.cjs in.svg out.png PX_PER_MM [PLAYWRIGHT_DIR]');
let chromium; try { ({ chromium } = require(pw || process.env.PLAYWRIGHT_DIR || 'playwright')); } catch (e) { die('playwright が読み込めない: ' + e.message.split('\n')[0]); }
(async () => {
  const s = fs.readFileSync(inp, 'utf8'); const m = s.match(/width="([\d.]+)mm" height="([\d.]+)mm"/); if (!m) die('svg の width/height に mm が必要');
  const W = Math.round(m[1] * ppm), H = Math.round(m[2] * ppm); const opt = process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {};
  const b = await chromium.launch(opt); const p = await b.newPage({ viewport: { width: W, height: H } });
  await p.setContent(`<body style="margin:0;background:#fff">${s.replace(/width="[\d.]+mm" height="[\d.]+mm"/, `width="${W}" height="${H}"`)}</body>`);
  await p.screenshot({ path: out, clip: { x: 0, y: 0, width: W, height: H } }); await b.close();
  if (!fs.existsSync(out)) die('PNG が生成されていない'); console.log('ok', out, `${W}x${H}px`);
})().catch((e) => die(e.message.split('\n')[0]));

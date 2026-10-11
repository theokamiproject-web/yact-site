// SVG(mm指定) → PNG（px/mm 指定）。 使い方: node svg2png.cjs in.svg out.png PX_PER_MM [PLAYWRIGHT_DIR]
const fs = require('fs'); const [inp, out, ppm, pw] = process.argv.slice(2); const { chromium } = require(pw || process.env.PLAYWRIGHT_DIR || 'playwright');
(async () => { const s = fs.readFileSync(inp, 'utf8'); const m = s.match(/width="([\d.]+)mm" height="([\d.]+)mm"/); if (!m) throw new Error('width/height に mm が必要');
  const W = Math.round(m[1] * ppm), H = Math.round(m[2] * ppm); const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: W, height: H } });
  await p.setContent(`<body style="margin:0;background:#fff">${s.replace(/width="[\d.]+mm" height="[\d.]+mm"/, `width="${W}" height="${H}"`)}</body>`); await p.screenshot({ path: out, clip: { x: 0, y: 0, width: W, height: H } }); await b.close(); })();

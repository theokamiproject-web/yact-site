// SVG(mm指定) → PNG（px/mm 指定）。 使い方: node svg2png.cjs in.svg out.png PX_PER_MM [PLAYWRIGHT_DIR]
// width/height は mm 必須（属性の順序は問わない）。viewBox が無い場合は mm 値をそのまま viewBox にする。<?xml?> 宣言は除去。
const fs = require('fs'); const [inp, out, ppm, pw] = process.argv.slice(2); const { chromium } = require(pw || process.env.PLAYWRIGHT_DIR || 'playwright');
(async () => { let s = fs.readFileSync(inp, 'utf8').replace(/<\?xml[^>]*\?>/, '').replace(/<!DOCTYPE[^>]*>/i, '');
  const tagm = s.match(/<svg\b[^>]*>/); if (!tagm) throw new Error('<svg> が無い'); let t = tagm[0];
  const w = t.match(/\swidth="([\d.]+)mm"/), h = t.match(/\sheight="([\d.]+)mm"/); if (!w || !h) throw new Error('width/height に mm が必要');
  const W = Math.round(w[1] * ppm), H = Math.round(h[1] * ppm);
  if (!/\sviewBox=/.test(t)) t = t.replace('<svg', `<svg viewBox="0 0 ${w[1]} ${h[1]}"`);
  t = t.replace(/\swidth="[\d.]+mm"/, ` width="${W}"`).replace(/\sheight="[\d.]+mm"/, ` height="${H}"`); s = s.replace(tagm[0], t);
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: W, height: H } });
  await p.setContent(`<body style="margin:0;background:#fff">${s}</body>`); await p.screenshot({ path: out, clip: { x: 0, y: 0, width: W, height: H } }); await b.close(); })()
  .catch(e => { console.error('svg2png:', e.message); process.exit(2); });

// usage: node pngdiff.mjs <dirA> <dirB> — mean abs pixel difference per page (0-255) and % of pixels differing by >24.
import fs from 'node:fs';
import path from 'node:path';
import sharp from 'sharp';
const [A, B] = process.argv.slice(2);
for (const f of fs.readdirSync(A).filter((x) => x.endsWith('.png')).sort()) {
  if (!fs.existsSync(path.join(B, f))) { console.log(f, 'missing'); continue; }
  const [a, b] = await Promise.all([A, B].map((d) => sharp(path.join(d, f)).removeAlpha().raw().toBuffer({ resolveWithObject: true })));
  if (a.info.width !== b.info.width || a.info.height !== b.info.height) { console.log(f, `size ${a.info.width}x${a.info.height} vs ${b.info.width}x${b.info.height}`); continue; }
  let sum = 0, big = 0;
  for (let i = 0; i < a.data.length; i++) { const d = Math.abs(a.data[i] - b.data[i]); sum += d; if (d > 24) big++; }
  console.log(f, 'mean', (sum / a.data.length).toFixed(2), 'diff%', ((big / a.data.length) * 100).toFixed(2));
}

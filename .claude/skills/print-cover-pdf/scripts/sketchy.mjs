// rough.js（MIT, https://github.com/rough-stuff/rough）で、SVGの線・四角・円・パスを「手描き風の線（ベクター）」にする。
// 使い方: node sketchy.mjs <node_modules> in.svg out.svg [roughness=1.2] [seed=1] [stroke=1.2]
//   node_modules に roughjs が必要（npm i roughjs）。入力は width/height=mm の SVG。対応: line / rect / circle / ellipse / path（transform なし）。
//   出力は <path stroke> のみ（塗りなし・画像なし）。K単色でもそのままPDF化できる。面は線の重ね描きで表現されるので、黒ベタには使わない。
// 使い分け: roughen.py=太い面や既存の図形を「崩す」／sketchy.mjs=細い線を「手で引いた線」にする（軽い・線のまま残る）。
// 注意: rough.js の「手描き風」は型が決まっていて見慣れた印象になりやすい。roughness 1.0〜2.0、題字には使わない。
import fs from 'node:fs'; import path from 'node:path'; import { createRequire } from 'node:module';
const [nm, inp, out, rough = 1.2, seed = 1, sw = 1.2] = process.argv.slice(2);
const require = createRequire(path.join(nm, '..', 'package.json')); const R = require('roughjs/bundled/rough.cjs.js');
const gen = R.generator({ options: { seed: +seed, roughness: +rough, bowing: 1, strokeWidth: +sw } });
const s = fs.readFileSync(inp, 'utf8'); const head = s.match(/<svg\b[^>]*>/)[0];
const attr = (el, k) => { const m = el.match(new RegExp(`\\s${k}="([^"]*)"`)); return m ? m[1] : null; };
const num = (el, k, d = 0) => { const v = attr(el, k); return v === null ? d : parseFloat(v); };
let body = '', n = 0, skip = 0;
if (/transform=/.test(s)) { console.error('停止: transform を含む。先に座標へ展開すること'); process.exit(2); }
for (const el of s.match(/<(line|rect|circle|ellipse|path)\b[^>]*\/?>/g) || []) {
  const t = el.match(/^<(\w+)/)[1]; let d;
  if (t === 'line') d = gen.line(num(el, 'x1'), num(el, 'y1'), num(el, 'x2'), num(el, 'y2'));
  else if (t === 'rect') d = gen.rectangle(num(el, 'x'), num(el, 'y'), num(el, 'width'), num(el, 'height'));
  else if (t === 'circle') d = gen.circle(num(el, 'cx'), num(el, 'cy'), 2 * num(el, 'r'));
  else if (t === 'ellipse') d = gen.ellipse(num(el, 'cx'), num(el, 'cy'), 2 * num(el, 'rx'), 2 * num(el, 'ry'));
  else { const p = attr(el, 'd'); if (!p) { skip++; continue; } d = gen.path(p); }
  const w = attr(el, 'stroke-width') || sw;
  for (const p of gen.toPaths(d)) { if (p.stroke === 'none') continue; body += `<path d="${p.d}" fill="none" stroke="#000" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round"/>`; }
  n++;
}
if (!n) { console.error('停止: 対象の要素がない'); process.exit(2); }
fs.writeFileSync(out, `${head}${body}</svg>`); console.log(`sketchy: ${out} (${n} 要素${skip ? `, 対象外 ${skip}` : ''})`);

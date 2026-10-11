// SVG 生成の共通部品：文字の曲線化（縦組み/横組み）・白フチ・SVG枠。依存: opentype.js, @fontsource/noto-serif-jp
// 使い方: import { makeLib } from './lib.mjs'; const L = makeLib({ nodeModules: '/path/to/node_modules', pageMM: [182, 257] });
import fs from 'node:fs'; import path from 'node:path'; import { createRequire } from 'node:module';
export function makeLib({ nodeModules, pageMM, weights = [500, 700, 900], chars }) {
  const require = createRequire(path.join(nodeModules, '..', 'package.json')); const opentype = require('opentype.js');
  const FD = path.join(nodeModules, '@fontsource/noto-serif-jp/files'); const n = (v) => Math.round(v * 100) / 100; const cache = {}; const map = {};
  const files = (w) => fs.readdirSync(FD).filter((f) => f.endsWith(`-${w}-normal.woff`));
  const load = (f) => cache[f] || (cache[f] = (() => { const b = fs.readFileSync(path.join(FD, f)); return opentype.parse(b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength)); })());
  // フォントは文字ごとに分割ファイルになっている。必要な文字がどの分割にあるかを探して引く（なければ例外）
  const fontFor = (w, ch) => { map[w] = map[w] || {}; if (!map[w][ch]) { for (const f of files(w)) { const g = load(f).charToGlyph(ch); if (g && g.index !== 0) { map[w][ch] = f; break; } } } if (!map[w][ch]) throw new Error(`書体に無い文字: ${ch} (w${w})`); return load(map[w][ch]); };
  // 縦組み: cx=列の中心(mm), y0=上端(mm)。空白は 0.3em 空ける。戻り値 {d, bottom}
  function vtext(str, em, cx, y0, w = 700) { let d = '', y = y0; for (const ch of str) { if (ch === '　' || ch === ' ') { y += em * 0.3; continue; } const f = fontFor(w, ch), g = f.charToGlyph(ch); const a = g.advanceWidth / f.unitsPerEm * em; d += g.getPath(cx - a / 2, y + em * 0.86, em).toPathData(2); y += em; } return { d, bottom: y }; }
  // 横組み: x0=左端, base=ベースライン(mm)
  function htext(str, em, x0, base, w = 700) { let d = '', x = x0; for (const ch of str) { const f = fontFor(w, ch), g = f.charToGlyph(ch); d += g.getPath(x, base, em).toPathData(2); x += g.advanceWidth / f.unitsPerEm * em; } return { d, right: x }; }
  const halo = (d, sw = 2.6) => `<path d="${d}" fill="#fff" stroke="#fff" stroke-width="${sw}" stroke-linejoin="round"/><path d="${d}" fill="#000"/>`;
  const frame = (body) => `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="${pageMM[0]}mm" height="${pageMM[1]}mm" viewBox="0 0 ${pageMM[0]} ${pageMM[1]}"><rect width="${pageMM[0]}" height="${pageMM[1]}" fill="#fff"/>${body}</svg>`;
  // 外部SVG（ロゴ）をそのまま埋め込む。viewBox="x y w h" の中身を (x,y) 幅 w mm に置く
  const embed = (svgText, vb, x, y, w) => { const inner = svgText.replace(/^[\s\S]*?<svg[^>]*>/, '').replace(/<\/svg>\s*$/, ''); const s = w / vb[2]; return `<g transform="translate(${x} ${y}) scale(${n(s * 1000) / 1000}) translate(${-vb[0]} ${-vb[1]})">${inner}</g>`; };
  return { vtext, htext, halo, frame, embed, n };
}

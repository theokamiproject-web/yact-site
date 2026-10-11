// 最小の使用例（これを複製して案を作る）。 node example.mjs <node_modules> <out.svg> [W H]
// 例: node example.mjs /path/to/node_modules /tmp/cover.svg 148 210
import fs from 'node:fs'; import { makeLib } from './lib.mjs';
const [nm, out, W = 182, H = 257] = process.argv.slice(2); const L = makeLib({ nodeModules: nm, pageMM: [+W, +H] });
const m = Math.max(10, +W * 0.06);                         // 安全余白（仕様の最小値より大きく取る）
const title = L.vtext('題字のサンプル', +W * 0.11, +W - m - +W * 0.07, m + 4, 700);   // 縦組み題字（右寄り）
const author = L.vtext('作者名　作', +W * 0.034, +W - m - +W * 0.07, title.bottom + 4, 500);
const band = `<rect x="${m}" y="${m}" width="${+W * 0.45}" height="${+H * 0.45}" fill="none" stroke="#000" stroke-width="1.6"/>`;   // 図形は線で
fs.writeFileSync(out, L.frame(`${band}${L.halo(title.d, 3)}${L.halo(author.d, 1.5)}`)); console.log('ok', out);

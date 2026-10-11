// 人工fixture(実案件と無関係)。node make-fixture.mjs <node_modules> <outdir>
// pass.svg: 縦組み題字(曲線化)＋線の枠。 neg-*.svg: 意図的な不適合（色/ラスター/生テキスト）。ページ=B5+塗り足し3mm=188x263mm
import fs from 'node:fs'; import { makeLib } from '../scripts/lib.mjs';
const [nm, out] = process.argv.slice(2); const L = makeLib({ nodeModules: nm, pageMM: [188, 263] });
const t = L.vtext('試験表紙', 20, 120, 40, 700);
const frame = '<rect x="30" y="30" width="60" height="90" fill="none" stroke="#000" stroke-width="1.6"/>';
const wrap = (body) => L.frame(body);
fs.writeFileSync(`${out}/pass.svg`, wrap(`${frame}${L.halo(t.d, 2)}`));
fs.writeFileSync(`${out}/neg-color.svg`, wrap(`${frame}<rect x="100" y="150" width="40" height="40" fill="#ff0000"/>${L.halo(t.d, 2)}`));
// 1x1 PNG をその場で生成（長いリテラルを置かない）
import zlib from 'node:zlib';
const crc = (b) => { let c, t = []; for (let n = 0; n < 256; n++) { c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; } let r = 0xffffffff; for (const x of b) r = t[(r ^ x) & 255] ^ (r >>> 8); return (r ^ 0xffffffff) >>> 0; };
const chunk = (ty, d) => { const b = Buffer.concat([Buffer.from(ty), d]); const l = Buffer.alloc(4); l.writeUInt32BE(d.length); const c = Buffer.alloc(4); c.writeUInt32BE(crc(b)); return Buffer.concat([l, b, c]); };
const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(1, 0); ihdr.writeUInt32BE(1, 4); ihdr[8] = 8; ihdr[9] = 0;
const png = Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk('IHDR', ihdr), chunk('IDAT', zlib.deflateSync(Buffer.from([0, 0]))), chunk('IEND', Buffer.alloc(0))]).toString('base64');
fs.writeFileSync(`${out}/neg-raster.svg`, wrap(`${frame}<image x="100" y="150" width="30" height="30" xlink:href="data:image/png;base64,${png}"/>${L.halo(t.d, 2)}`));
fs.writeFileSync(`${out}/neg-text.svg`, wrap(`${frame}<text x="100" y="60" font-size="12" fill="#000">raw text</text>`));
console.log('fixture ok');

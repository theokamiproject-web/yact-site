// 4 fixture cover pages at 188x263mm (B5 + 3mm bleed): 表1 has colour (RGB red) + black, 表2-4 white.
import {PDFDocument, rgb} from 'pdf-lib';
import fs from 'fs';
const mm = 72 / 25.4, W = 188 * mm, H = 263 * mm, dir = process.argv[2];
for (const [name, paint] of [['c1', true], ['c2', false], ['c3', false], ['c4', false]]) {
  const d = await PDFDocument.create(); const p = d.addPage([W, H]);
  if (paint) { p.drawRectangle({x: 40, y: 400, width: 200, height: 120, color: rgb(1, 0, 0)}); p.drawRectangle({x: 40, y: 200, width: 200, height: 60, color: rgb(0, 0, 0)}); }
  fs.writeFileSync(`${dir}/${name}.pdf`, await d.save());
}

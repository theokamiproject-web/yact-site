// 初回3案の雛形：モチーフではなく「骨格」を振る。node skeletons.mjs <node_modules> <outdir> [W H] [題字] [作者]
// A 文字だけ（題字が紙面の6割以上）／B 図が主役（題字は極小）／C 題字を図として崩す（字を分割・ずらし・はみ出し寸前）
// どれも K単色・線/文字のみ・安全余白内。書体は案ごとに変える（明朝の太字固定にしない）。図は roughen.py で手の痕跡を足せる。
import fs from 'node:fs'; import path from 'node:path'; import { makeLib } from './lib.mjs';
const [nm, outdir, W = 182, H = 257, title = '題字のサンプル', author = '作者名　作'] = process.argv.slice(2);
const w = +W, h = +H, m = Math.max(10, w * 0.06), L = makeLib({ nodeModules: nm, pageMM: [w, h] }); fs.mkdirSync(outdir, { recursive: true });
const n = [...title].filter((c) => c.trim()).length;
const save = (k, body) => { const f = path.join(outdir, `${k}.svg`); fs.writeFileSync(f, L.frame(body)); console.log('ok', f); };

// A: 文字だけ。題字を縦に紙面いっぱい（高さの約8割）、極端に大きく。作者は極小で対比。
{ const em = Math.min((h - 2 * m) * 0.84 / n, (w - 2 * m) * 0.62);
  const t = L.vtext(title, em, w / 2 + em * 0.12, m + 2, 800, { family: 'shippori-mincho-b1', track: -0.06 });
  const a = L.htext(author, w * 0.026, m, h - m, 500, { family: 'noto-sans-jp', track: 0.4 });
  save('A-文字だけ', `<path d="${t.d}"/><path d="${a.d}"/>`); }

// B: 図が主役。大きな円弧1本＋水平線1本で紙面を割る。題字は小さく端に寄せ、図との大小差を最大に。
{ const r = w * 0.9, cx = w * 0.95, cy = h * 0.62;
  const arc = `<path d="M${m} ${cy} A${r} ${r} 0 0 1 ${w - m} ${cy - r * 0.55}" fill="none" stroke="#000" stroke-width="2.2"/>`;
  const line = `<path d="M${m} ${h * 0.72} H${w - m}" stroke="#000" stroke-width="0.8"/>`;
  const t = L.vtext(title, w * 0.045, m + w * 0.03, m + 4, 600, { family: 'zen-old-mincho' });
  const a = L.vtext(author, w * 0.022, m + w * 0.08, m + 4, 500, { family: 'zen-old-mincho' });
  save('B-図が主役', `${arc}${line}${L.halo(t.d, 2)}${L.halo(a.d, 1.2)}`); }

// C: 題字を崩す。1字ずつ大きさと位置を変え、2列に割って段差をつける（読み順は保つ）。
{ const chars = [...title].filter((c) => c.trim()); const half = Math.ceil(chars.length / 2); let body = '';
  const em1 = (h - 2 * m) * 0.9 / half, em2 = em1 * 0.62;
  let y = m; chars.slice(0, half).forEach((c, i) => { const e = i % 2 ? em1 * 0.78 : em1; const g = L.vtext(c, e, w - m - em1 * 0.55, y, 400, { family: 'dela-gothic-one' }); body += `<path d="${g.d}"/>`; y = g.bottom - e * 0.04; });
  y = m + em1 * 1.4; chars.slice(half).forEach((c) => { const g = L.vtext(c, em2, w - m - em1 * 1.15 - em2 * 0.55, y, 400, { family: 'dela-gothic-one' }); body += `<path d="${g.d}"/>`; y = g.bottom; });
  const a = L.htext(author, w * 0.03, m, h - m, 400, { family: 'klee-one' });
  save('C-題字を崩す', `${body}<path d="${a.d}"/>`); }

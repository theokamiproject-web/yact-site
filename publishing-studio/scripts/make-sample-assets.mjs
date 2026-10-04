#!/usr/bin/env node
// Generates abstract placeholder "photographs" (SVG -> JPEG) for the sample issue. Deterministic; no external assets.
import fs from 'node:fs';
import path from 'node:path';
import sharp from 'sharp';
import { ISSUES_DIR } from './lib/paths.mjs';

const dir = path.join(ISSUES_DIR, 'test-issue-01/images');
fs.mkdirSync(dir, { recursive: true });

function rng(seed) { let s = seed; return () => ((s = (s * 1664525 + 1013904223) % 4294967296) / 4294967296); }

function scene({ w, h, sky, sea, sun, hills, seed, horizon = 0.58, person = false, lanterns = false }) {
  const r = rng(seed);
  const hy = Math.round(h * horizon);
  const hillPath = (base, amp, color) => {
    let d = `M0 ${h}`; const n = 7;
    for (let i = 0; i <= n; i++) d += ` L${Math.round((w / n) * i)} ${Math.round(base - r() * amp)}`;
    return `<path d="${d} L${w} ${h} Z" fill="${color}"/>`;
  };
  const boats = Array.from({ length: 4 }, (_, i) => {
    const x = w * (0.12 + 0.22 * i + r() * 0.05), y = hy + h * (0.04 + r() * 0.1), s = w * (0.035 + r() * 0.02);
    return `<path d="M${x} ${y} h${s * 2} l${-s * 0.4} ${s * 0.5} h${-s * 1.2} Z" fill="#14202a"/><rect x="${x + s}" y="${y - s * 1.4}" width="${s * 0.06}" height="${s * 1.4}" fill="#14202a"/>`;
  }).join('');
  const lamps = lanterns ? Array.from({ length: 9 }, (_, i) => `<circle cx="${w * (0.08 + i * 0.105)}" cy="${h * (0.2 + 0.03 * Math.sin(i))}" r="${w * 0.018}" fill="#ffb347" opacity="0.9"/>`).join('') : '';
  const ppl = person ? `<g fill="#1a1a1c"><circle cx="${w * 0.5}" cy="${h * 0.42}" r="${w * 0.13}"/><path d="M${w * 0.12} ${h} Q${w * 0.15} ${h * 0.64} ${w * 0.5} ${h * 0.62} Q${w * 0.85} ${h * 0.64} ${w * 0.88} ${h} Z"/></g>` : '';
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
<defs><linearGradient id="s" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${sky[0]}"/><stop offset="1" stop-color="${sky[1]}"/></linearGradient>
<linearGradient id="m" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${sea[0]}"/><stop offset="1" stop-color="${sea[1]}"/></linearGradient>
<radialGradient id="g"><stop offset="0" stop-color="${sun}" stop-opacity="0.9"/><stop offset="1" stop-color="${sun}" stop-opacity="0"/></radialGradient></defs>
<rect width="${w}" height="${h}" fill="url(#s)"/>
<circle cx="${w * 0.62}" cy="${hy - h * 0.06}" r="${w * 0.3}" fill="url(#g)"/><circle cx="${w * 0.62}" cy="${hy - h * 0.06}" r="${w * 0.075}" fill="${sun}"/>
${hillPath(hy + 4, h * 0.14, hills[0])}
<rect y="${hy}" width="${w}" height="${h - hy}" fill="url(#m)"/>
${Array.from({ length: 14 }, (_, i) => `<rect x="${w * (0.45 + r() * 0.3)}" y="${hy + h * 0.012 * (i + 1) * 1.6}" width="${w * (0.06 + r() * 0.1)}" height="${Math.max(2, h * 0.003)}" fill="${sun}" opacity="${0.5 - i * 0.03}"/>`).join('')}
${boats}${lamps}${ppl}
${hillPath(h + 1, 0, 'none')}
</svg>`;
  return Buffer.from(svg);
}

const specs = {
  'cover-harbor.jpg': { w: 1300, h: 1850, sky: ['#1b2a49', '#e8825a'], sea: ['#2d4a63', '#0f1d2b'], sun: '#ffd9a0', hills: ['#15202e'], seed: 3, horizon: 0.62, lanterns: true },
  'harbor-hero.jpg': { w: 2400, h: 1120, sky: ['#274060', '#f0a36b'], sea: ['#36586f', '#13222f'], sun: '#ffe0b0', hills: ['#1a2735'], seed: 8, horizon: 0.6 },
  'stage-inline.jpg': { w: 1400, h: 900, sky: ['#5b4a3f', '#d99b6c'], sea: ['#3b3430', '#1c1815'], sun: '#ffe9c4', hills: ['#2a211c'], seed: 12, horizon: 0.55, lanterns: true },
  'portrait-hamabe.jpg': { w: 1000, h: 1400, sky: ['#2c3e50', '#a7b9c4'], sea: ['#31424f', '#1a2630'], sun: '#e8eef2', hills: ['#223040'], seed: 21, horizon: 0.8, person: true },
  'tide-1.jpg': { w: 1300, h: 1850, sky: ['#20303a', '#7fb0a8'], sea: ['#1d4a52', '#0b2227'], sun: '#e9fff6', hills: ['#13262b'], seed: 31, horizon: 0.5 },
  'tide-2.jpg': { w: 1400, h: 900, sky: ['#3a2b4d', '#e58f8f'], sea: ['#4a3a63', '#1b1428'], sun: '#ffd0d0', hills: ['#231a33'], seed: 41, horizon: 0.6 },
  'tide-3.jpg': { w: 1400, h: 900, sky: ['#14313a', '#f3d9a4'], sea: ['#2a5560', '#0e252b'], sun: '#fff2d1', hills: ['#0f2329'], seed: 51, horizon: 0.64 },
};
for (const [name, s] of Object.entries(specs)) {
  await sharp(scene(s)).blur(0.6).jpeg({ quality: 78, mozjpeg: true }).withMetadata({ density: 300 }).toFile(path.join(dir, name));
  console.log('wrote', name, fs.statSync(path.join(dir, name)).size, 'bytes');
}

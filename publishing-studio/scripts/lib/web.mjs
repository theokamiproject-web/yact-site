// Write a composed book (HTML + resolved CSS + images) to a directory.
import fs from 'node:fs';
import path from 'node:path';
import { loadRegistry } from './registry.mjs';
import { resolveTheme, pageSetupCss } from './theme.mjs';

export async function writeWeb(model, composed, dir, { marks = false } = {}) {
  const reg = await loadRegistry();
  fs.rmSync(dir, { recursive: true, force: true });
  fs.mkdirSync(path.join(dir, 'css'), { recursive: true });
  fs.mkdirSync(path.join(dir, 'images'), { recursive: true });
  const theme = resolveTheme(model);
  fs.writeFileSync(path.join(dir, 'css/theme.css'), theme.map((t) => `/* ==== ${t.source} ==== */\n${t.css}`).join('\n\n'));
  fs.writeFileSync(path.join(dir, 'css/layouts.css'), reg.styles.map((s) => `/* ==== layouts/${s.family} ==== */\n${s.css}`).join('\n\n'));
  fs.writeFileSync(path.join(dir, 'css/page-setup.css'), pageSetupCss(model.issue, { marks }));
  for (const [f, src] of Object.entries(model.images)) fs.copyFileSync(src, path.join(dir, 'images', f));
  fs.writeFileSync(path.join(dir, 'index.html'), composed.html);
  fs.writeFileSync(path.join(dir, 'pages.json'), JSON.stringify({ issue: model.issue, pages: composed.pages, toc: composed.toc }, null, 2));
}

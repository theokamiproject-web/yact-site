// PDF -> per-page PNG (trim box only) + contact sheets + metrics.json
import fs from 'node:fs';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { pathToFileURL } from 'node:url';
import sharp from 'sharp';
import { PDFDocument } from 'pdf-lib';
import { outDir } from './paths.mjs';
import { loadIssue } from './load.mjs';
import { launch } from './browser.mjs';
import { collectMetrics, measuredIntensity } from './metrics.mjs';
import { sourceHash } from './build.mjs';

const exec = promisify(execFile);
const pad = (n) => String(n).padStart(2, '0');

export async function renderPages(id, { dpi = 110, log = console.log } = {}) {
  const out = outDir(id);
  const pdfPath = path.join(out, `${id}.pdf`);
  if (!fs.existsSync(pdfPath)) throw new Error(`no PDF at ${pdfPath}. Run: npm run publication:build -- ${id}`);
  const model = loadIssue(id);
  const pagesDir = path.join(out, 'pages');
  fs.rmSync(pagesDir, { recursive: true, force: true });
  fs.mkdirSync(pagesDir, { recursive: true });

  const pdf = await PDFDocument.load(fs.readFileSync(pdfPath));
  const total = pdf.getPageCount();
  const files = [];
  for (let i = 0; i < total; i++) {
    const p = pdf.getPage(i);
    const mb = p.getMediaBox();
    const tb = p.getTrimBox();
    const s = dpi / 72;
    const x = Math.round((tb.x - mb.x) * s), y = Math.round((mb.y + mb.height - (tb.y + tb.height)) * s);
    const w = Math.round(tb.width * s), h = Math.round(tb.height * s);
    const base = path.join(pagesDir, `page-${pad(i + 1)}`);
    await exec('pdftoppm', ['-f', String(i + 1), '-l', String(i + 1), '-r', String(dpi), '-x', String(x), '-y', String(y), '-W', String(w), '-H', String(h), '-png', '-singlefile', pdfPath, base]);
    files.push(`${base}.png`);
  }
  log(`  rendered ${files.length} page PNG(s) @${dpi}dpi -> ${path.relative(process.cwd(), pagesDir)}`);

  const browser = await launch();
  try {
    const { pages: metrics, tokens } = await collectMetrics(browser, path.join(out, 'web'), model.issue);
    for (const m of metrics) {
      const f = files[m.n - 1];
      if (f) {
        const st = await sharp(f).stats();
        m.pixel_stddev = +(st.channels.slice(0, 3).reduce((a, c) => a + c.stdev, 0) / 3).toFixed(2);
        m.pixel_mean = +(st.channels.slice(0, 3).reduce((a, c) => a + c.mean, 0) / 3).toFixed(1);
      }
      m.measured_intensity = measuredIntensity(m);
    }
    fs.writeFileSync(path.join(out, 'metrics.json'), JSON.stringify({ issue: id, generated_at: new Date().toISOString(), source_hash: sourceHash(model), page_count_png: files.length, tokens, pages: metrics }, null, 2));

    const sheets = await contactSheets(browser, out, model.issue, files, metrics);
    log(`  contact sheets: ${sheets.map((s) => path.basename(s)).join(', ')}`);
    return { files, metrics, sheets };
  } finally {
    await browser.close();
  }
}

async function contactSheets(browser, out, issue, files, metrics) {
  const dir = path.join(out, 'contact');
  fs.rmSync(dir, { recursive: true, force: true });
  fs.mkdirSync(dir, { recursive: true });
  const url = (f) => pathToFileURL(f).href;
  const label = (n) => { const m = metrics.find((x) => x.n === n); return `<span>${n}</span> ${m ? `${m.layout}${m.variant ? `/${m.variant}` : ''}` : ''}`; };
  const css = `body{margin:0;padding:14px;background:#2a2a2a;font:11px/1.3 sans-serif;color:#ddd;display:inline-block}
.grid{display:grid;gap:10px}.cell{position:relative}.cell img{display:block;width:100%;box-shadow:0 0 0 1px #555;background:#fff}
.lab{margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.lab span{font-weight:700;color:#fff}
.sp{display:flex}.sp img{width:50%;display:block}.sp .ph{width:50%;aspect-ratio:${issue.width}/${issue.height}}`;
  const gridSheet = async (cols, thumbW, name) => {
    const cells = files.map((f, i) => `<div class="cell"><img src="${url(f)}"><div class="lab">${label(i + 1)}</div></div>`).join('');
    return render(name, `<style>${css}.grid{grid-template-columns:repeat(${cols},${thumbW}px)}</style><div class="grid">${cells}</div>`);
  };
  const spreadSheet = async (perRow, spreadW, name) => {
    const items = [];
    const n = files.length;
    const lone = (f, side, lab) => `<div class="cell" style="width:${spreadW}px"><div class="sp">${side === 'right' ? '<div class="ph"></div>' : ''}<img src="${url(f)}">${side === 'left' ? '<div class="ph"></div>' : ''}</div><div class="lab">${lab}</div></div>`;
    items.push(lone(files[0], 'right', label(1)));
    for (let p = 2; p < n; p += 2) {
      const r = files[p];
      items.push(`<div class="cell" style="width:${spreadW}px"><div class="sp"><img src="${url(files[p - 1])}">${r ? `<img src="${url(r)}">` : '<div class="ph"></div>'}</div><div class="lab">${label(p)}${r ? ` | ${label(p + 1)}` : ''}</div></div>`);
    }
    if (n % 2 === 0) items.push(lone(files[n - 1], 'left', label(n)));
    return render(name, `<style>${css}.grid{grid-template-columns:repeat(${perRow},${spreadW}px)}</style><div class="grid">${items.join('')}</div>`);
  };
  const render = async (name, html) => {
    const page = await browser.newPage({ viewport: { width: 1200, height: 800 }, deviceScaleFactor: 1 });
    const htmlFile = path.join(dir, name.replace(/\.png$/, '.html'));
    fs.writeFileSync(htmlFile, `<!doctype html><meta charset="utf-8">${html}`);
    await page.goto(url(htmlFile), { waitUntil: 'load' });
    await page.evaluate(() => Promise.all([...document.images].map((i) => (i.complete ? 1 : new Promise((r) => (i.onload = i.onerror = r))))));
    const file = path.join(dir, name);
    await page.screenshot({ path: file, fullPage: true });
    await page.close();
    fs.rmSync(htmlFile);
    return file;
  };
  return [await gridSheet(4, 280, 'contact-4xN.png'), await gridSheet(8, 150, 'contact-8xN.png'), await spreadSheet(3, 440, 'contact-spreads.png')];
}

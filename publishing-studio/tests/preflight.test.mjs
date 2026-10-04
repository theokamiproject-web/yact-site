// Every preflight check must FAIL when its failure is injected (RC1: 8 of 14 injected bugs were not caught by any test).
// Strategy: one real build, then tamper with a single artifact/source at a time and run preflight (fast), restoring after.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { PDFDocument } from 'pdf-lib';
import * as yaml from 'js-yaml';
import { workspace } from './helpers.mjs';
import { sourceHash } from '../scripts/lib/build.mjs';

const ws = workspace();
const ID = 'test-issue-01';
const out = path.join(ws.output, ID);
const src = path.join(ws.issues, ID);
test.after(() => ws.cleanup());

const preflight = () => {
  const r = ws.run('preflight.mjs', ID);
  const j = JSON.parse(fs.readFileSync(path.join(out, 'preflight.json'), 'utf8'));
  return { r, by: Object.fromEntries(j.items.map((i) => [i.code, i])), j };
};
async function tamper(file, mutate, fn) {
  const orig = fs.readFileSync(file);
  try {
    const next = await mutate(orig);
    fs.writeFileSync(file, next);
    return await fn();
  } finally { fs.writeFileSync(file, orig); }
}
const metricsFile = () => path.join(out, 'metrics.json');
const withMetrics = (mut, fn) => tamper(metricsFile(), (b) => { const m = JSON.parse(b); mut(m); return JSON.stringify(m); }, fn);
const withText = (file, mut, fn) => tamper(file, (b) => mut(b.toString('utf8')), fn);
const pdfFile = () => path.join(out, `${ID}.pdf`);

test('baseline: build once; the automated checks pass; verdict is never a bare PASS and never "ready"', { timeout: 200000 }, () => {
  const a = ws.run('all.mjs', ID);
  assert.ok(a.status === 0, a.stdout + a.stderr);
  const { by, j } = preflight();
  for (const c of ['P00', 'P01', 'P02', 'P03', 'P04', 'P05', 'P08', 'P09', 'P10', 'P11', 'P12', 'P17', 'P18', 'P19', 'P20', 'P22', 'P23', 'P31']) assert.equal(by[c].status, 'PASS', `${c}: ${by[c].detail}`);
  assert.ok(!/^PASS$/.test(j.verdict) && !/ready/i.test(j.verdict), j.verdict);
  assert.match(j.disclaimer, /Not a print-readiness certificate/);
  for (const c of ['P26', 'P32', 'P33', 'P34']) { assert.equal(by[c].status, 'MANUAL CHECK'); assert.equal(by[c].kind, 'MANUAL CHECK'); }
  assert.equal(by.P29.kind, 'HEURISTIC');
  assert.equal(by.P01.kind, 'AUTOMATED CHECK');
  const md = fs.readFileSync(path.join(out, 'preflight.md'), 'utf8');
  assert.match(md, /AUTOMATED CHECK/); assert.match(md, /HEURISTIC/); assert.match(md, /MANUAL CHECK/);
});

test('page count mismatch (PDF has fewer pages than the issue) -> P09 FAIL', async () => {
  await tamper(pdfFile(), async (b) => { const d = await PDFDocument.load(b); d.removePage(5); return Buffer.from(await d.save()); }, () => {
    const { by, r } = preflight();
    assert.equal(by.P09.status, 'FAIL'); assert.match(by.P09.detail, /15 page/); assert.equal(r.status, 1);
  });
});

test('wrong trim size -> P11 FAIL; invalid bleed (BleedBox == TrimBox) -> P12 FAIL', async () => {
  await tamper(pdfFile(), async (b) => { const d = await PDFDocument.load(b); const p = d.getPage(0); const t = p.getTrimBox(); p.setTrimBox(t.x, t.y, t.width - 20, t.height); return Buffer.from(await d.save()); }, () => assert.equal(preflight().by.P11.status, 'FAIL'));
  await tamper(pdfFile(), async (b) => { const d = await PDFDocument.load(b); for (const p of d.getPages()) { const t = p.getTrimBox(); p.setBleedBox(t.x, t.y, t.width, t.height); } return Buffer.from(await d.save()); }, () => assert.equal(preflight().by.P12.status, 'FAIL'));
});

test('low image resolution: <100ppi FAIL, <200ppi WARNING', async () => {
  await withMetrics((m) => { m.pages.find((p) => p.images.length).images[0].ppi = 60; }, () => assert.equal(preflight().by.P22.status, 'FAIL'));
  await withMetrics((m) => { m.pages.find((p) => p.images.length).images[0].ppi = 150; }, () => assert.equal(preflight().by.P22.status, 'WARNING'));
});

test('overflow / clipped text -> P19 FAIL (both .fit clipping and text outside the trim)', async () => {
  await withMetrics((m) => { m.pages[5].overflow = [{ el: 'fb-text fit', kind: 'content-clipped', scroll: [1, 2], client: [1, 1] }]; }, () => assert.equal(preflight().by.P19.status, 'FAIL'));
  await withMetrics((m) => { m.pages[5].outside = [{ kind: 'text-outside-trim' }]; }, () => assert.equal(preflight().by.P19.status, 'FAIL'));
});

test('blank page -> P17 FAIL unless declared intentional', async () => {
  const blank = (m) => { Object.assign(m.pages[13], { text_chars: 0, image_ratio: 0, bg_fill: null, pixel_stddev: 0.1 }); };
  await withMetrics(blank, () => { const { by } = preflight(); assert.equal(by.P17.status, 'FAIL'); assert.match(by.P17.detail, /p14/); });
  await withMetrics((m) => { blank(m); m.pages[13].intentional_blank = true; }, () => assert.equal(preflight().by.P17.status, 'PASS'));
});

test('page numbers: duplicate, missing and wrong folio -> P20 FAIL', async () => {
  await withMetrics((m) => { m.pages[5].folio = { text: '5', expected: '6' }; }, () => assert.equal(preflight().by.P20.status, 'FAIL')); // duplicate of p5 AND wrong
  await withMetrics((m) => { m.pages[5].folio = null; }, () => { const { by } = preflight(); assert.equal(by.P20.status, 'FAIL'); assert.match(by.P20.detail, /missing/); });
  await withMetrics((m) => { m.pages[6].folio = { text: '6', expected: '7' }; }, () => assert.match(preflight().by.P20.detail, /duplicated|shows/));
});

test('broken image -> P18 FAIL; safe-area violation -> P21 WARNING; short bleed -> P23 WARNING', async () => {
  await withMetrics((m) => { m.pages.find((p) => p.images.length).images[0].ok = false; }, () => assert.equal(preflight().by.P18.status, 'FAIL'));
  await withMetrics((m) => { m.pages[5].safe_violations = 2; }, () => assert.equal(preflight().by.P21.status, 'WARNING'));
  await withMetrics((m) => { m.pages[0].bleed_short = [{ file: 'x.jpg', edges: ['top'] }]; }, () => assert.equal(preflight().by.P23.status, 'WARNING'));
});

test('contents entry lost -> P31 FAIL; orphan lines -> P29 WARNING (heuristic); under-filled page -> P30 WARNING (heuristic)', async () => {
  await withMetrics((m) => { m.pages[1].toc_items = { total: 12, fitting: 8 }; }, () => { const { by } = preflight(); assert.equal(by.P31.status, 'FAIL'); assert.match(by.P31.detail, /12 entries/); });
  await withMetrics((m) => { m.pages[6].orphan_lines = [{ text: 'る。', lines: 5 }]; }, () => { const { by } = preflight(); assert.equal(by.P29.status, 'WARNING'); assert.equal(by.P29.kind, 'HEURISTIC'); });
  await withMetrics((m) => { Object.assign(m.pages[5], { text_occupancy: 0.2, content_extent_live: 0.3 }); }, () => { const { by } = preflight(); assert.equal(by.P30.status, 'WARNING'); assert.match(by.P30.detail, /p6/); });
});

test('stale PDF: article, caption, image bytes, flatplan, issue.yaml, theme_overrides, issue theme.css, credits each -> P10 FAIL', async () => {
  const cases = [
    ['article', path.join(src, 'articles/editors-note.md'), (s) => `${s}\n追記\n`],
    ['caption', path.join(src, 'captions/captions.yaml'), (s) => s.replace('夕方、桟橋に残る光。', '夕方、桟橋に残る光')],
    ['flatplan', path.join(src, 'flatplan.yaml'), (s) => s.replace('variant: qa', 'variant: qa-portrait')],
    ['issue.yaml', path.join(src, 'issue.yaml'), (s) => s.replace('bleed: 3', 'bleed: 4')],
    ['theme_overrides', path.join(src, 'issue.yaml'), (s) => `${s}theme_overrides:\n  --color-accent: "#00aa00"\n`],
    ['issue theme.css', path.join(src, 'theme.css'), (s) => `${s}\n.x{color:red}\n`],
    ['credits', path.join(src, 'credits.yaml'), (s) => s.replace('汐田 結', '汐田 ゆい')],
  ];
  fs.writeFileSync(path.join(src, 'theme.css'), '/* issue theme */\n');
  const h0 = preflight().by.P10; // adding an (empty) theme.css is itself a source change
  assert.equal(h0.status, 'FAIL');
  fs.rmSync(path.join(src, 'theme.css'));
  assert.equal(preflight().by.P10.status, 'PASS');
  for (const [name, file, fn] of cases) {
    if (!fs.existsSync(file)) fs.writeFileSync(file, '');
    await withText(file, fn, () => { const { by } = preflight(); assert.equal(by.P10.status, 'FAIL', `${name} must make the PDF stale`); });
    if (name === 'issue theme.css') fs.rmSync(file);
  }
  const img = path.join(src, 'images/tide-1.jpg');
  await tamper(img, (b) => Buffer.concat([b, Buffer.from([0, 0, 0])]), () => assert.equal(preflight().by.P10.status, 'FAIL'));
  assert.equal(preflight().by.P10.status, 'PASS', 'restored sources are current again');
});

test('sourceHash covers theme and layout files (CSS change) and ignores notes/', () => {
  const model = { dir: src };
  const roots = ['themes', 'layouts'].map((d) => { const t = fs.mkdtempSync(path.join(ws.root, `h-${d}-`)); fs.writeFileSync(path.join(t, 'a.css'), 'a{}'); return t; });
  const h1 = sourceHash(model, { roots });
  fs.writeFileSync(path.join(roots[0], 'a.css'), 'a{color:red}');
  assert.notEqual(sourceHash(model, { roots }), h1, 'theme CSS change');
  fs.writeFileSync(path.join(roots[0], 'a.css'), 'a{}');
  assert.equal(sourceHash(model, { roots }), h1);
  fs.writeFileSync(path.join(roots[1], 'a.css'), 'a{color:red}');
  assert.notEqual(sourceHash(model, { roots }), h1, 'layout CSS change');
  fs.writeFileSync(path.join(roots[1], 'a.css'), 'a{}');
  fs.writeFileSync(path.join(src, 'notes/README.md'), 'changed memo');
  assert.equal(sourceHash(model, { roots }), h1, 'notes are not part of the book');
});

test('missing image file -> P04 FAIL; unplaced article -> P02 FAIL; invalid spread start -> P01 FAIL', async () => {
  const img = path.join(src, 'images/tide-2.jpg');
  const bak = fs.readFileSync(img);
  fs.rmSync(img);
  try { const { by } = preflight(); assert.equal(by.P04.status, 'FAIL'); assert.equal(by.P10.status, 'FAIL'); } finally { fs.writeFileSync(img, bak); }
  const fp = path.join(src, 'flatplan.yaml');
  await withText(fp, (s) => { const o = yaml.load(s); o.pages = o.pages.filter((e) => e.article !== 'night-road'); return yaml.dump(o, { lineWidth: 200 }); }, () => assert.equal(preflight().by.P02.status, 'FAIL'));
  await withText(fp, (s) => { const o = yaml.load(s); o.pages.find((e) => e.layout === 'photo-essay').pages = [11, 12]; return yaml.dump(o, { lineWidth: 200 }); }, () => assert.equal(preflight().by.P01.status, 'FAIL'));
});

test('render not current: sources changed and only build re-run -> P16 FAIL (PDF current, metrics/PNGs stale)', { timeout: 120000 }, async () => {
  const f = path.join(src, 'articles/editors-note.md');
  const orig = fs.readFileSync(f);
  try {
    fs.appendFileSync(f, '\n追記。\n');
    assert.equal(ws.run('build.mjs', ID).status, 0);
    const { by } = preflight();
    assert.equal(by.P10.status, 'PASS');
    assert.equal(by.P16.status, 'FAIL');
  } finally { fs.writeFileSync(f, orig); }
});

test('missing caption -> P05 FAIL (validate only warns)', async () => {
  await withText(path.join(src, 'captions/captions.yaml'), (s) => { const o = yaml.load(s); delete o['stage-inline.jpg']; return yaml.dump(o, { lineWidth: 200 }); }, () => {
    const { by } = preflight();
    assert.equal(by.P05.status, 'FAIL');
    assert.match(by.P05.detail, /stage-inline\.jpg/);
  });
});

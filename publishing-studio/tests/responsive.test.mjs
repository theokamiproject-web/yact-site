// The SAME issue and the SAME components at A5 and B5 must both build, fit, and keep their proportions.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { PDFDocument } from 'pdf-lib';
import * as yaml from 'js-yaml';
import { workspace } from './helpers.mjs';

const ws = workspace();
test.after(() => ws.cleanup());

test('A5 issue re-set as B5 (no other change): builds, no FAIL, regions keep their proportions', { timeout: 240000 }, async () => {
  const d = path.join(ws.issues, 'as-b5');
  fs.cpSync(path.join(ws.issues, 'test-issue-01'), d, { recursive: true });
  const f = path.join(d, 'issue.yaml');
  const issue = yaml.load(fs.readFileSync(f, 'utf8'));
  Object.assign(issue, { id: 'as-b5', format: 'B5', width: 182, height: 257 });
  fs.writeFileSync(f, yaml.dump(issue));
  assert.equal(ws.run('all.mjs', 'test-issue-01').status, 0);
  const rb = ws.run('all.mjs', 'as-b5');
  assert.equal(rb.status, 0, rb.stdout + rb.stderr);
  const A = JSON.parse(fs.readFileSync(path.join(ws.output, 'test-issue-01/metrics.json'))).pages;
  const B = JSON.parse(fs.readFileSync(path.join(ws.output, 'as-b5/metrics.json'))).pages;
  const pdf = await PDFDocument.load(fs.readFileSync(path.join(ws.output, 'as-b5/as-b5.pdf')));
  assert.equal(pdf.getPageCount(), 16);
  assert.ok(Math.abs(pdf.getPage(0).getTrimBox().width * 25.4 / 72 - 182) < 0.3);
  for (let i = 0; i < 16; i++) {
    const a = A[i], b = B[i];
    assert.equal(b.overflow.length + b.outside.length, 0, `p${b.n} overflows at B5`);
    // composition geometry is page-relative: image share of the page and region proportions are preserved
    assert.ok(Math.abs(a.image_ratio - b.image_ratio) < 0.03, `p${a.n} image_ratio ${a.image_ratio} vs ${b.image_ratio}`);
    // (pages with body text hold more characters at B5, so only geometry-only pages are compared)
    if (!a.fit_frames.length) assert.ok(Math.abs(a.ink_ratio - b.ink_ratio) < 0.12, `p${a.n} ink_ratio ${a.ink_ratio} vs ${b.ink_ratio}`);
    // type scales with the page but never below the physical minimum
    assert.ok(b.min_font_pt === null || b.min_font_pt >= 7 - 0.05, `p${b.n} min font ${b.min_font_pt}pt`);
    if (a.fit_frames.length) assert.ok(b.fit_frames[0].w > a.fit_frames[0].w * 1.15, `p${a.n}: text frame must widen with the page`);
  }
  const bodyA = A[5].fit_frames[0].fs, bodyB = B[5].fit_frames[0].fs;
  assert.ok(bodyB > bodyA && bodyB < bodyA * 1.25, `body size scales gently (${bodyA}mm -> ${bodyB}mm)`);
});

test('TEST ISSUE 02 (B5, 24 pages) builds with no FAIL and keeps every contents entry', { timeout: 240000 }, async () => {
  const r = ws.run('all.mjs', 'test-issue-02');
  assert.equal(r.status, 0, r.stdout + r.stderr);
  const out = path.join(ws.output, 'test-issue-02');
  const pdf = await PDFDocument.load(fs.readFileSync(path.join(out, 'test-issue-02.pdf')));
  assert.equal(pdf.getPageCount(), 24);
  const mx = JSON.parse(fs.readFileSync(path.join(out, 'metrics.json'))).pages;
  const toc = mx.find((p) => p.layout === 'contents').toc_items;
  assert.equal(toc.fitting, toc.total, 'no contents entry may be lost');
  const txt = (await import('node:child_process')).spawnSync('pdftotext', ['-f', '2', '-l', '2', '-layout', path.join(out, 'test-issue-02.pdf'), '-'], { encoding: 'utf8' }).stdout;
  for (const t of ['はじめに', '朝の商店街', '河口', '七海 ひな', '路地と橋', '丘の上', '松原 悟', '夕暮れから夜へ', '三代目は急がない', 'あとがき']) assert.ok(txt.includes(t), `contents page lists "${t}"`);
});

test('contents that cannot fit FAIL validation (never build-success-with-loss)', { timeout: 120000 }, async () => {
  const d = path.join(ws.issues, 'toc-big');
  fs.cpSync(path.join(ws.issues, 'test-issue-02'), d, { recursive: true });
  const fp = path.join(d, 'flatplan.yaml');
  const o = yaml.load(fs.readFileSync(fp, 'utf8'));
  o.pages.find((e) => e.layout === 'contents').variant = 'large';
  fs.writeFileSync(fp, yaml.dump(o, { lineWidth: 200 }));
  const v = ws.run('validate.mjs', 'toc-big');
  assert.equal(v.status, 1, v.stdout);
  assert.match(v.stdout, /CONTENTS_OVERFLOW/);
  const b = ws.run('build.mjs', 'toc-big');
  assert.equal(b.status, 1);
  assert.ok(!fs.existsSync(path.join(ws.output, 'toc-big/toc-big.pdf')), 'no PDF is produced');
});

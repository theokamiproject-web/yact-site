// End-to-end: new-issue -> validate -> build (Vivliostyle) -> render -> critic pack -> preflight, in an isolated workspace.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { PDFDocument } from 'pdf-lib';
import { workspace } from './helpers.mjs';

const ws = workspace();
test.after(() => ws.cleanup());

test('new-issue creates a valid issue from the template; rejects duplicates and bad ids', () => {
  const r = ws.run('new-issue.mjs', 'issue-77', '--title', 'テスト号');
  assert.equal(r.status, 0, r.stderr);
  for (const f of ['issue.yaml', 'editorial.yaml', 'flatplan.yaml', 'credits.yaml', 'articles', 'images', 'captions', 'notes']) assert.ok(fs.existsSync(path.join(ws.issues, 'issue-77', f)), f);
  assert.match(fs.readFileSync(path.join(ws.issues, 'issue-77/issue.yaml'), 'utf8'), /id: issue-77/);
  assert.equal(ws.run('new-issue.mjs', 'issue-77').status, 1);
  assert.equal(ws.run('new-issue.mjs', 'Bad_ID').status, 1);
  const v = ws.run('validate.mjs', 'issue-77');
  assert.equal(v.status, 0, v.stdout + v.stderr);
});

test('validate CLI: exit 0 for the sample issue', () => {
  const v = ws.run('validate.mjs', 'test-issue-01');
  assert.equal(v.status, 0, v.stdout);
  assert.match(v.stdout, /0 error/);
});

test('validate CLI: missing image -> exit 1 and a MISSING_ASSET message', () => {
  fs.cpSync(path.join(ws.issues, 'test-issue-01'), path.join(ws.issues, 'broken-img'), { recursive: true });
  fs.rmSync(path.join(ws.issues, 'broken-img/images/tide-2.jpg'));
  const v = ws.run('validate.mjs', 'broken-img');
  assert.equal(v.status, 1);
  assert.match(v.stdout, /MISSING_ASSET/);
});

test('publication:all on the sample issue: PDF, page PNGs, contact sheets, critic pack, preflight', { timeout: 180000 }, async () => {
  const r = ws.run('all.mjs', 'test-issue-01');
  assert.equal(r.status, 0, r.stdout + r.stderr);
  const out = path.join(ws.output, 'test-issue-01');

  const pdf = await PDFDocument.load(fs.readFileSync(path.join(out, 'test-issue-01.pdf')));
  assert.equal(pdf.getPageCount(), 16, 'PDF page count');
  const tb = pdf.getPage(0).getTrimBox();
  assert.ok(Math.abs(tb.width * 25.4 / 72 - 148) < 0.3 && Math.abs(tb.height * 25.4 / 72 - 210) < 0.3, 'A5 trim box');

  const pngs = fs.readdirSync(path.join(out, 'pages')).filter((f) => f.endsWith('.png'));
  assert.equal(pngs.length, 16, 'rendered page count');
  for (const f of ['contact-4xN.png', 'contact-8xN.png', 'contact-spreads.png']) assert.ok(fs.statSync(path.join(out, 'contact', f)).size > 5000, f);

  const mx = JSON.parse(fs.readFileSync(path.join(out, 'metrics.json')));
  assert.equal(mx.pages.length, 16);
  assert.ok(mx.pages.every((p) => typeof p.whitespace_ratio === 'number' && typeof p.image_ratio === 'number'));

  // critic pack: blind must not contain editorial context
  const blind = path.join(out, 'review-pack/blind');
  assert.equal(fs.readdirSync(path.join(blind, 'pages')).length, 16);
  assert.ok(!fs.existsSync(path.join(blind, 'editorial.yaml')) && !fs.existsSync(path.join(blind, 'flatplan.yaml')));
  assert.ok(fs.existsSync(path.join(out, 'review-pack/context/editorial.yaml')));
  for (const s of ['blind', 'context', 'rereview']) assert.ok(fs.existsSync(path.join(ws.issues, 'test-issue-01/reviews', `critic-${s}.md`)));
  const fp = JSON.parse(fs.readFileSync(path.join(out, 'fingerprint.json')));
  assert.equal(fp.axes.length, 19);
  assert.ok(fp.axes.every((a) => ['machine', 'hybrid', 'visual'].includes(a.mode)));
  assert.ok(fs.existsSync(path.join(out, 'rhythm.md')));
  assert.ok(fs.existsSync(path.join(out, 'critic-report.json')));

  // preflight: no FAIL, and unverifiable items are not reported as PASS
  const pf = JSON.parse(fs.readFileSync(path.join(out, 'preflight.json')));
  assert.equal(pf.counts.FAIL, 0, JSON.stringify(pf.items.filter((i) => i.status === 'FAIL')));
  const by = Object.fromEntries(pf.items.map((i) => [i.code, i.status]));
  assert.equal(by.P09, 'PASS');
  assert.equal(by.P26, 'MANUAL CHECK');
  assert.equal(by.P27, 'MANUAL CHECK');
  assert.ok(fs.existsSync(path.join(out, 'preflight.md')));
});

test('preflight FAILs on overflowing text and on a PDF that no longer matches the sources', { timeout: 180000 }, () => {
  const dir = path.join(ws.issues, 'test-issue-01/articles/editors-note.md');
  const orig = fs.readFileSync(dir, 'utf8');
  // stale: change sources after the PDF was built
  fs.writeFileSync(dir, orig + '\n追記です。\n');
  let pf = ws.run('preflight.mjs', 'test-issue-01');
  assert.equal(pf.status, 1);
  assert.match(pf.stdout, /FAIL\s+P10 PDF is current/);
  // overflow: far more text than the frame holds
  fs.writeFileSync(dir, orig + '\n' + Array.from({ length: 14 }, (_, i) => `${i}番目の段落です。` + 'あいうえお'.repeat(40)).join('\n\n') + '\n');
  assert.equal(ws.run('build.mjs', 'test-issue-01').status, 0);
  assert.equal(ws.run('render-pages.mjs', 'test-issue-01').status, 0);
  pf = ws.run('preflight.mjs', 'test-issue-01');
  assert.equal(pf.status, 1);
  assert.match(pf.stdout, /FAIL\s+P19 overflow/);
  fs.writeFileSync(dir, orig);
});

test('critic --check: completed reviews are validated and produce critic-report.json', () => {
  const reviews = path.join(ws.issues, 'test-issue-01/reviews');
  const cats = ['readability', 'hierarchy', 'visual-rhythm', 'consistency', 'originality', 'editorial-rhythm', 'page-balance', 'typography', 'image-usage', 'issue-identity'];
  const mk = (stage, extra = '') => `---\nstage: ${stage}\nstatus: complete\nreviewer: publication-critic\n---\n## Scores (1–5)\n| category | score | note |\n|---|:-:|---|\n${cats.map((c) => `| ${c} | 4 | ok |`).join('\n')}\n## Findings\n${extra}\n## Emergent fingerprint\n- none observed\n`;
  fs.writeFileSync(path.join(reviews, 'critic-blind.md'), mk('blind', '### F-001 [MEDIUM] page-balance — 疎なページ\n- Pages: 14\n- Problem: 本文が少ない\n- Evidence: fit_fill 0.35\n- Fix: 原稿を追加'));
  fs.writeFileSync(path.join(reviews, 'critic-context.md'), mk('context'));
  fs.writeFileSync(path.join(reviews, 'critic-rereview.md'), mk('rereview', '## Previous findings\n- F-001: wontfix — 意図した余白'));
  const r = ws.run('critic-pack.mjs', 'test-issue-01', '--check');
  assert.equal(r.status, 0, r.stdout + r.stderr);
  const rep = JSON.parse(fs.readFileSync(path.join(ws.output, 'test-issue-01/critic-report.json'), 'utf8'));
  assert.equal(rep.stages.blind.findings[0].id, 'F-001');
  assert.equal(rep.stages.rereview.dispositions[0].status, 'wontfix');
  fs.writeFileSync(path.join(reviews, 'critic-rereview.md'), mk('rereview'));
  assert.equal(ws.run('critic-pack.mjs', 'test-issue-01', '--check').status, 1, 'missing disposition must fail');
});

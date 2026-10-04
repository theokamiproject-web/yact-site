// The DOM measurements themselves (not just the checks built on them), against synthetic pages.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { launch } from '../scripts/lib/browser.mjs';
import { collectMetrics } from '../scripts/lib/metrics.mjs';
import { PS } from './helpers.mjs';

const issue = { width: 148, height: 210, bleed: 3 };
const css = ['tokens', 'typography', 'page', 'grid', 'components'].map((n) => fs.readFileSync(path.join(PS, 'themes/base', `${n}.css`), 'utf8')).join('\n')
  + fs.readdirSync(path.join(PS, 'layouts')).filter((d) => fs.existsSync(path.join(PS, 'layouts', d, 'style.css'))).map((d) => fs.readFileSync(path.join(PS, 'layouts', d, 'style.css'), 'utf8')).join('\n');

async function measure(pagesHtml) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ps-met-'));
  fs.writeFileSync(path.join(dir, 'index.html'), `<!doctype html><meta charset="utf-8"><style>${css}</style><body class="book">${pagesHtml}</body>`);
  const b = await launch();
  try { return (await collectMetrics(b, dir, issue)).pages; } finally { await b.close(); fs.rmSync(dir, { recursive: true, force: true }); }
}
const page = (n, inner, attrs = '') => `<section class="page" data-page="${n}" data-side="${n % 2 ? 'right' : 'left'}" data-layout="t" data-variant="v" data-chrome="full" ${attrs}>${inner}<div class="folio">${n}</div></section>`;
const live = (inner) => `<div class="live"><div class="c-all fit" style="height:40mm">${inner}</div></div>`;
const long = '本文の文章です。'.repeat(120);

test('.fit overflow is detected independently of the outside-trim check', { timeout: 60000 }, async () => {
  const [ok, over] = await measure(page(1, live('<div class="body"><p>短い。</p></div>')) + page(2, live(`<div class="body"><p>${long}</p></div>`)));
  assert.equal(ok.overflow.length, 0);
  assert.equal(over.overflow.length, 1, 'clipped inside its frame');
  assert.equal(over.outside.length, 0, 'nothing leaves the trim box, so ONLY the .fit check can see this');
});

test('text outside the trim box is detected', { timeout: 60000 }, async () => {
  const [p] = await measure(page(1, '<p style="position:absolute;left:-30mm;top:20mm;width:20mm">はみ出し</p>'));
  assert.ok(p.outside.some((o) => o.kind === 'text-outside-trim'));
});

test('text frames report measured width/height/columns/font size/leading; occupancy follows the text amount', { timeout: 60000 }, async () => {
  const [a, b] = await measure(page(1, `<div class="live"><div class="c-all fit cols-2" style="height:60mm"><div class="body"><p>${'あ'.repeat(60)}</p></div></div></div>`) + page(2, `<div class="live"><div class="c-all fit cols-2" style="height:60mm"><div class="body"><p>${'あ'.repeat(600)}</p></div></div></div>`));
  const f = a.fit_frames[0];
  assert.equal(f.cols, 2);
  assert.ok(Math.abs(f.h - 60) < 0.2 && f.w > 100 && f.fs > 2.9 && f.fs < 3.1 && Math.abs(f.lh - 5.5) < 0.1, JSON.stringify(f));
  assert.ok(a.text_occupancy < 0.3);
  assert.ok(b.text_occupancy > 0.9);
});

test('orphan lines: a last line of one or two characters is reported, a full last line is not', { timeout: 60000 }, async () => {
  // measure = 118mm / 3mm = 39 chars per line
  const [orphan, fine] = await measure(page(1, live(`<div class="body"><p class="noindent">${'あ'.repeat(40)}。</p></div>`)) + page(2, live(`<div class="body"><p class="noindent">${'あ'.repeat(60)}</p></div>`)));
  assert.equal(orphan.orphan_lines.length, 1, JSON.stringify(orphan.orphan_lines));
  assert.equal(fine.orphan_lines.length, 0);
});

test('content extent measures how far down the page content reaches', { timeout: 60000 }, async () => {
  const [short, tall] = await measure(page(1, live('<div class="body"><p>一行だけ</p></div>')) + page(2, `<div class="live"><div class="c-all fit" style="height:170mm"><div class="body"><p>${long}${long}</p></div></div></div>`));
  assert.ok(short.content_extent_live < 0.35, short.content_extent_live);
  assert.ok(tall.content_extent_live > 0.85, tall.content_extent_live);
});

test('body_pt measures running text (.body) only; null where a page has none', { timeout: 60000 }, async () => {
  const [withBody, without] = await measure(page(1, live('<p class="deck">デッキ</p><div class="body"><p>本文</p></div>')) + page(2, '<div class="live"><h1>見出しだけ</h1><p class="lead">リード</p></div>'));
  assert.equal(withBody.body_pt, 8.5);
  assert.equal(without.body_pt, null);
});

test('contents entries that do not fit are counted', { timeout: 60000 }, async () => {
  const items = (n) => Array.from({ length: n }, () => '<li class="toc-item"><span class="toc-p">03</span><div class="toc-t"><h2>タイトル</h2></div></li>').join('');
  const [few, many] = await measure(page(1, `<div class="live toc"><ol class="toc-list c-all">${items(4)}</ol></div>`) + page(2, `<div class="live toc"><ol class="toc-list c-all">${items(40)}</ol></div>`));
  assert.deepEqual(few.toc_items, { total: 4, fitting: 4 });
  assert.equal(many.toc_items.total, 40);
  assert.ok(many.toc_items.fitting < 40 && many.toc_items.fitting > 4);
});

test('CSS cascade: component classes win over the base heading rules (RC1 `.page h1` specificity accident)', { timeout: 60000 }, async () => {
  const [p] = await measure(page(1, '<div class="live"><h1 class="cv-title">TITLE</h1><h1 class="fo-title">T</h1></div>'));
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ps-cas-'));
  fs.writeFileSync(path.join(dir, 'index.html'), `<!doctype html><meta charset="utf-8"><style>${css}</style><section class="page" data-page="1" data-side="right"><h1 class="cv-title" id="a">T</h1></section>`);
  const b = await launch();
  try {
    const pg = await b.newPage();
    await pg.goto(`file://${dir}/index.html`);
    const px = await pg.evaluate(() => parseFloat(getComputedStyle(document.getElementById('a')).fontSize));
    assert.ok(Math.abs(px * 0.75 - 56) < 0.5, `.cv-title must be 56pt (display size), got ${px * 0.75}pt`);
  } finally { await b.close(); }
  assert.ok(p);
});

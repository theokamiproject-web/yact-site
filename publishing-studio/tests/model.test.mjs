import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { PS, clone } from './helpers.mjs';
import { loadIssue } from '../scripts/lib/load.mjs';
import { validateModel, hasErrors } from '../scripts/lib/validate-model.mjs';
import { checkSchema } from '../scripts/lib/schema.mjs';

const base = loadIssue('test-issue-01');
const codes = async (m) => (await validateModel(m)).filter((f) => f.level === 'error').map((f) => f.code);
const mutate = (fn) => { const m = { ...base, issue: clone(base.issue), flatplan: clone(base.flatplan), articles: clone(base.articles), images: { ...base.images }, captions: clone(base.captions), loadErrors: [] }; fn(m); return m; };

test('sample issue validates with no errors', async () => {
  const f = await validateModel(base);
  assert.deepEqual(f.filter((x) => x.level === 'error'), []);
  assert.equal(hasErrors(f), false);
});

test('schema: issue.yaml/editorial.yaml/flatplan.yaml/articles conform', () => {
  assert.deepEqual(checkSchema('issue', base.issue), []);
  assert.deepEqual(checkSchema('editorial', base.editorial), []);
  assert.deepEqual(checkSchema('flatplan', base.flatplan), []);
  for (const a of Object.values(base.articles)) assert.deepEqual(checkSchema('article', a.meta), [], a.file);
});

test('schema: rejects bad issue (missing field, bad enum, unknown key)', () => {
  const bad = { ...clone(base.issue), binding: 'glue', extra: 1 };
  delete bad.width;
  const msgs = checkSchema('issue', bad).map((e) => e.message).join('|');
  assert.match(msgs, /width/);
  assert.match(msgs, /binding|allowed/);
  assert.match(msgs, /extra/);
});

test('page count: issue.pages larger than flatplan -> FLATPLAN_GAP; not multiple of 4 -> error', async () => {
  assert.ok((await codes(mutate((m) => { m.issue.pages = 20; }))).includes('FLATPLAN_GAP'));
  const c = await codes(mutate((m) => { m.issue.pages = 15; }));
  assert.ok(c.includes('PAGES_NOT_MULTIPLE_OF_4'));
  assert.ok(c.includes('FLATPLAN_RANGE'));
});

test('flatplan: duplicate page -> FLATPLAN_OVERLAP; gap -> FLATPLAN_GAP', async () => {
  assert.ok((await codes(mutate((m) => { m.flatplan.pages[1].pages = [1]; }))).includes('FLATPLAN_OVERLAP'));
  assert.ok((await codes(mutate((m) => { m.flatplan.pages.splice(1, 1); }))).includes('FLATPLAN_GAP'));
});

test('missing article file -> ARTICLE_MISSING', async () => {
  assert.ok((await codes(mutate((m) => { delete m.articles['harbor-theater']; }))).includes('ARTICLE_MISSING'));
});

test('article not placed -> ARTICLE_NOT_PLACED', async () => {
  const c = await codes(mutate((m) => { m.flatplan.pages = m.flatplan.pages.filter((e) => e.article !== 'night-road'); }));
  assert.ok(c.includes('ARTICLE_NOT_PLACED'));
});

test('invalid layout / variant / span / spread parity', async () => {
  assert.ok((await codes(mutate((m) => { m.flatplan.pages[2].layout = 'poster'; }))).includes('UNKNOWN_LAYOUT'));
  assert.ok((await codes(mutate((m) => { m.flatplan.pages[2].variant = 'neon'; }))).includes('UNKNOWN_VARIANT'));
  const span = mutate((m) => { const e = m.flatplan.pages.find((x) => x.layout === 'feature-opener'); e.variant = 'hero-top'; });
  assert.ok((await codes(span)).includes('SPAN_MISMATCH'));
  const par = mutate((m) => { const e = m.flatplan.pages.find((x) => x.layout === 'photo-essay'); e.pages = [11, 12]; });
  assert.ok((await codes(par)).includes('SPREAD_PARITY'));
});

test('missing image file -> MISSING_ASSET; missing required input -> MISSING_INPUT', async () => {
  assert.ok((await codes(mutate((m) => { delete m.images['harbor-hero.jpg']; }))).includes('MISSING_ASSET'));
  assert.ok((await codes(mutate((m) => { m.articles['harbor-theater'].meta.assets = []; }))).includes('MISSING_INPUT'));
});

test('missing caption is a warning at validate time', async () => {
  const f = await validateModel(mutate((m) => { delete m.captions['tide-2.jpg']; }));
  assert.ok(f.some((x) => x.code === 'MISSING_CAPTION' && x.level === 'warning'));
});

const frame = (o = {}) => ({ w: 96, h: 118, cols: 1, gap: 0, fs: 3, lh: 5.5, ...o });
test('text volume uses MEASURED frames: overlong body -> TEXT_MAY_OVERFLOW; no frames => text checks skipped', async () => {
  const m = mutate((m) => { m.articles['editors-note'].blocks = Array.from({ length: 30 }, () => ({ type: 'p', md: 'あ'.repeat(120) })); });
  const probe = { frames: new Map([[3, frame()]]), metrics: [] };
  assert.ok((await validateModel(m, { probe })).some((x) => x.code === 'TEXT_MAY_OVERFLOW'));
  assert.ok(!(await validateModel(m)).some((x) => x.code === 'TEXT_MAY_OVERFLOW'), 'without a probe there is nothing to measure against');
});

test('TEXT_NOT_PLACED: article with body text but no text layout', async () => {
  const c = await codes(mutate((m) => { for (const e of m.flatplan.pages.filter((x) => x.article === 'night-road')) { e.layout = 'divider'; e.variant = 'ink'; } }));
  assert.ok(c.includes('TEXT_NOT_PLACED'));
});

test('CONTENTS_OVERFLOW / LAYOUT_OVERFLOW are errors, raised from the measured layout probe', async () => {
  const mk = (extra) => ({ n: 2, layout: 'contents', variant: 'list', overflow: [], outside: [], toc_items: null, ...extra });
  const f1 = await validateModel(base, { probe: { frames: new Map(), metrics: [mk({ toc_items: { total: 12, fitting: 8 } })] } });
  const e1 = f1.find((x) => x.code === 'CONTENTS_OVERFLOW');
  assert.equal(e1.level, 'error');
  assert.match(e1.message, /12 entries but only 8 fit/);
  const f2 = await validateModel(base, { probe: { frames: new Map(), metrics: [mk({ outside: [{ kind: 'text-outside-trim' }] })] } });
  assert.equal(f2.find((x) => x.code === 'LAYOUT_OVERFLOW').level, 'error');
  const ok = await validateModel(base, { probe: { frames: new Map(), metrics: [mk({ toc_items: { total: 5, fitting: 5 } })] } });
  assert.ok(!ok.some((x) => x.level === 'error'));
});

test('loader reports YAML errors without throwing', () => {
  const m = loadIssue('does-not-exist');
  assert.equal(m.loadErrors[0].code, 'ISSUE_MISSING');
});

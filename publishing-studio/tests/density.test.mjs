// P1-5: density rules are contract-driven. Accidental sparseness is caught; declared intent and composed pages are not flagged.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import * as yaml from 'js-yaml';
import { workspace } from './helpers.mjs';
import { loadRegistry } from '../scripts/lib/registry.mjs';
import { DENSITY } from '../layouts/_contracts.mjs';
import { contractFor } from '../scripts/lib/density.mjs';

const ws = workspace();
test.after(() => ws.cleanup());
const edit = (f, fn) => fs.writeFileSync(f, fn(fs.readFileSync(f, 'utf8')));
const issueCopy = (name) => { const d = path.join(ws.issues, name); fs.cpSync(path.join(ws.issues, 'test-issue-01'), d, { recursive: true }); return d; };

test('every component has a density contract; text components are not sparse_allowed and have a range for every role', async () => {
  const reg = await loadRegistry();
  for (const c of Object.values(reg.components)) {
    assert.ok(DENSITY[c.name], `${c.name}: missing density contract`);
    if (c.text && !['column', 'profile'].includes(c.name)) {
      assert.equal(DENSITY[c.name].sparse_allowed, false, c.name);
      for (const role of ['first', 'middle', 'last', 'only']) assert.ok(Array.isArray(DENSITY[c.name].occupancy[role]), `${c.name}.${role}`);
    }
  }
  assert.equal(DENSITY.contents.capacity.overflow_strategy, 'error');
});

test('the contract depends on the page role: a LAST page may be part-filled, a MIDDLE page may not (no single global threshold)', async () => {
  const reg = await loadRegistry();
  const fb = reg.components['feature-body'];
  assert.ok(contractFor(fb, 'last').expected[0] < contractFor(fb, 'middle').expected[0]);
  assert.equal(contractFor(reg.components['quote-page'], 'only').sparseAllowed, true);
  assert.equal(contractFor(reg.components['photo-essay'], 'only').sparseAllowed, true);
  assert.equal(contractFor(reg.components.divider, 'only').sparseAllowed, true);
});

test('accidental sparseness is flagged; declared intent (with a reason) is not; quote/photo pages never are', { timeout: 200000 }, () => {
  const d = issueCopy('thin');
  // shrink the feature article so its MIDDLE page (p6, feature-body/two-col) is mostly empty
  edit(path.join(d, 'articles/harbor-theater.md'), (s) => s.slice(0, s.indexOf('---', 4) + 4) + '潮見町の港には、倉庫がある。\n\n短い段落。\n');
  const v = JSON.parse(ws.run('validate.mjs', 'thin', '--json').stdout);
  const under = v.filter((f) => f.code === 'TEXT_UNDERFILLED' || f.code === 'TEXT_PAGE_EMPTY');
  assert.ok(under.length >= 1, JSON.stringify(v.map((f) => f.code)));
  assert.ok(under.every((f) => !/p(10|11|12)\b/.test(f.where)), 'quote / photo pages are never flagged');
  ws.run('all.mjs', 'thin');
  const pf = JSON.parse(fs.readFileSync(path.join(ws.output, 'thin/preflight.json')));
  assert.equal(pf.items.find((i) => i.code === 'P30').status, 'WARNING');
  assert.equal(pf.items.find((i) => i.code === 'P30').kind, 'HEURISTIC');

  // declaring intent without a reason is an error; with a reason it silences exactly that page
  const fp = path.join(d, 'flatplan.yaml');
  const mark = (note) => edit(fp, (s) => { const o = yaml.load(s); for (const e of o.pages.filter((x) => x.article === 'harbor-theater' && x.layout === 'feature-body')) { e.intentional_sparse = true; if (note) e.notes = note; else delete e.notes; } return yaml.dump(o, { lineWidth: 200 }); });
  mark('');
  const bad = JSON.parse(ws.run('validate.mjs', 'thin', '--json').stdout);
  assert.ok(bad.some((f) => f.code === 'INTENT_NEEDS_NOTE' && f.level === 'error'));
  mark('特集を短い導入だけにした（編集判断）');
  const ok = JSON.parse(ws.run('validate.mjs', 'thin', '--json').stdout);
  assert.ok(!ok.some((f) => ['TEXT_UNDERFILLED', 'TEXT_PAGE_EMPTY', 'INTENT_NEEDS_NOTE'].includes(f.code) && /p[67]\b/.test(f.where)), JSON.stringify(ok.filter((f) => f.level !== 'info').map((f) => [f.code, f.where])));
});

// RC2 criteria for the two example issues: validate clean, no FAIL, no unexpected WARNING, nothing under-filled,
// no orphan lines, no text beyond its frame, no stray warnings left "to demonstrate a bug".
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import * as yaml from 'js-yaml';
import { workspace, PS } from './helpers.mjs';

const ws = workspace();
test.after(() => ws.cleanup());

for (const id of ['test-issue-01', 'test-issue-02']) {
  test(`${id}: validate clean; all passes; only the documented warnings remain`, { timeout: 240000 }, () => {
    const v = JSON.parse(ws.run('validate.mjs', id, '--json').stdout);
    assert.deepEqual(v.filter((f) => f.level !== 'info'), [], 'validate must have no errors and no warnings');
    const a = ws.run('all.mjs', id);
    assert.equal(a.status, 0, a.stdout.slice(-600));
    const pf = JSON.parse(fs.readFileSync(path.join(ws.output, id, 'preflight.json')));
    assert.equal(pf.counts.FAIL, 0);
    const expected = yaml.load(fs.readFileSync(path.join(PS, 'issues', id, 'expected-warnings.yaml'), 'utf8'));
    for (const [code, why] of Object.entries(expected)) assert.ok(String(why).length > 20, `${code}: a warning kept on purpose needs a real reason`);
    const warned = pf.items.filter((i) => i.status === 'WARNING').map((i) => i.code).sort();
    assert.deepEqual(warned, Object.keys(expected).sort(), `unexpected / vanished warnings: ${JSON.stringify(pf.items.filter((i) => i.status === 'WARNING').map((i) => [i.code, i.detail.slice(0, 90)]))}`);
    const mx = JSON.parse(fs.readFileSync(path.join(ws.output, id, 'metrics.json'))).pages;
    for (const p of mx) {
      assert.equal(p.orphan_lines.length, 0, `p${p.n} orphan lines`);
      assert.equal(p.overflow.length + p.outside.length, 0, `p${p.n} overflow`);
      assert.ok(p.text_occupancy === null || p.text_occupancy <= 1.0, `p${p.n} occupancy ${p.text_occupancy}`);
      assert.ok(p.min_font_pt === null || p.min_font_pt >= 7 - 0.05, `p${p.n} min font ${p.min_font_pt}`);
    }
  });
}

test('TEST ISSUE 02 declares its intentionally sparse pages with a reason; accidental sparseness elsewhere would be flagged', () => {
  const fp = yaml.load(fs.readFileSync(path.join(PS, 'issues/test-issue-02/flatplan.yaml'), 'utf8'));
  const declared = fp.pages.filter((e) => e.intentional_sparse);
  assert.ok(declared.length >= 1);
  for (const e of declared) assert.ok(String(e.notes).length > 10, `p${e.pages}: reason required`);
});

// P1-7: reviews are an audit record. --reset must never silently destroy them; the pipeline must not touch them;
// reviews are bound to the output they describe.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { workspace } from './helpers.mjs';
import { isAuthored, reviewTemplate, parseReview, checkReviews, freshStages, openSevere, CATEGORIES } from '../scripts/lib/critic.mjs';

const ws = workspace();
const ID = 'test-issue-01';
const rdir = path.join(ws.issues, ID, 'reviews');
const out = path.join(ws.output, ID);
test.after(() => ws.cleanup());
const sha = (f) => crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex');
const critic = (...a) => ws.run('critic-pack.mjs', ID, ...a);
const issue = { id: ID, title: 'T', pages: 16 };
const scores = CATEGORIES.map((c) => `| ${c} | 4 | ok |`).join('\n');
const complete = (stage, hash, body = '') => `---\nstage: ${stage}\nstatus: complete\nreviewer: someone\nsource_hash: ${hash ?? ''}\n---\n## Scores (1–5)\n| category | score | note |\n|---|:-:|---|\n${scores}\n## Findings\n${body}\n## Emergent fingerprint\n- none observed\n`;

test('setup: one real build creates the pack and the (empty) review templates', { timeout: 200000 }, () => {
  fs.rmSync(rdir, { recursive: true, force: true });
  const a = ws.run('all.mjs', ID);
  assert.equal(a.status, 0, a.stdout + a.stderr);
  for (const s of ['blind', 'context', 'rereview']) assert.ok(fs.existsSync(path.join(rdir, `critic-${s}.md`)));
  assert.ok(fs.existsSync(path.join(out, 'review-pack/PACK.json')));
  assert.ok(fs.existsSync(path.join(out, 'review-pack/context/auto-diff.md')));
});

test('isAuthored: an untouched template is not authored; status, findings, scores or reviewer make it authored', () => {
  assert.equal(isAuthored(reviewTemplate('blind', issue)), false);
  assert.equal(isAuthored(reviewTemplate('blind', issue).replace('status: pending', 'status: complete')), true);
  assert.equal(isAuthored(reviewTemplate('blind', issue).replace('reviewer:', 'reviewer: me')), true);
  assert.equal(isAuthored(reviewTemplate('blind', issue).replace('| readability |  |', '| readability | 3 |')), true);
  assert.equal(isAuthored(`${reviewTemplate('blind', issue)}\n### F-001 [HIGH] visual-rhythm — x\n- Pages: 1\n- Problem: p\n- Evidence: e\n- Fix: f\n`), true);
});

test('re-running the pipeline never changes an authored review (byte-identical) and writes no timestamps into it', () => {
  fs.writeFileSync(path.join(rdir, 'critic-blind.md'), complete('blind', 'abc', '### F-001 [LOW] typography — x\n- Pages: 1\n- Problem: p\n- Evidence: e\n- Fix: f\n'));
  const before = ['blind', 'context', 'rereview'].map((s) => sha(path.join(rdir, `critic-${s}.md`)));
  const snapBefore = sha(path.join(rdir, 'auto-findings.snapshot.json'));
  const r = critic();
  assert.equal(r.status, 0, r.stdout + r.stderr);
  const after = ['blind', 'context', 'rereview'].map((s) => sha(path.join(rdir, `critic-${s}.md`)));
  assert.deepEqual(after, before);
  assert.equal(sha(path.join(rdir, 'auto-findings.snapshot.json')), snapBefore, 'first-pack snapshot is kept');
});

test('--reset REFUSES while any review holds work, and changes nothing', () => {
  const before = ['blind', 'context', 'rereview'].map((s) => sha(path.join(rdir, `critic-${s}.md`)));
  const r = critic('--reset');
  assert.equal(r.status, 1);
  assert.match(r.stderr, /refusing --reset/);
  assert.match(r.stderr, /--force/);
  assert.deepEqual(['blind', 'context', 'rereview'].map((s) => sha(path.join(rdir, `critic-${s}.md`))), before);
  assert.ok(!fs.existsSync(path.join(rdir, 'archive')), 'nothing archived because nothing was destroyed');
});

test('--reset --force archives every review file (timestamped) before writing empty templates', () => {
  const original = fs.readFileSync(path.join(rdir, 'critic-blind.md'), 'utf8');
  const r = critic('--reset', '--force');
  assert.equal(r.status, 0, r.stdout + r.stderr);
  const arch = fs.readdirSync(path.join(rdir, 'archive'));
  assert.equal(arch.length, 1);
  assert.match(arch[0], /^\d{8}-\d{6}/);
  assert.equal(fs.readFileSync(path.join(rdir, 'archive', arch[0], 'critic-blind.md'), 'utf8'), original, 'the archive holds the exact previous content');
  assert.equal(isAuthored(fs.readFileSync(path.join(rdir, 'critic-blind.md'), 'utf8')), false, 'fresh template written');
});

test('--reset without --force is allowed when nothing has been authored', () => {
  assert.equal(critic('--reset').status, 0);
});

test('reviews are bound to the output: matching source_hash is fresh, anything else is stale and does not gate', () => {
  const pack = JSON.parse(fs.readFileSync(path.join(out, 'review-pack/PACK.json'), 'utf8'));
  const high = '### F-001 [HIGH] typography — x\n- Pages: 2\n- Problem: p\n- Evidence: e\n- Fix: f\n';
  const mk = (stage, h) => ({ file: stage, ...parseReview(complete(stage, h, stage === 'blind' ? high : '')) });
  const freshReviews = { blind: mk('blind', pack.source_hash) };
  assert.deepEqual(freshStages(freshReviews, pack.source_hash), ['blind']);
  assert.equal(openSevere(freshReviews, pack.source_hash).length, 1, 'a fresh open HIGH gates');
  const staleReviews = { blind: mk('blind', 'old-hash') };
  assert.deepEqual(freshStages(staleReviews, pack.source_hash), []);
  assert.equal(openSevere(staleReviews, pack.source_hash).length, 0, 'a review of an older output does not gate the new one');
  const { stale } = checkReviews(staleReviews, issue, { sourceHash: pack.source_hash });
  assert.match(stale[0], /different version/);
});

test('preflight P27: no review -> MANUAL CHECK; stale review -> MANUAL CHECK; fresh review with open HIGH -> FAIL', () => {
  const pack = JSON.parse(fs.readFileSync(path.join(out, 'review-pack/PACK.json'), 'utf8'));
  const p27 = () => { ws.run('preflight.mjs', ID); return JSON.parse(fs.readFileSync(path.join(out, 'preflight.json'))).items.find((i) => i.code === 'P27'); };
  assert.equal(p27().status, 'MANUAL CHECK');
  const high = '### F-001 [HIGH] typography — x\n- Pages: 2\n- Problem: p\n- Evidence: e\n- Fix: f\n';
  fs.writeFileSync(path.join(rdir, 'critic-blind.md'), complete('blind', 'not-the-current-hash', high));
  const stale = p27();
  assert.equal(stale.status, 'MANUAL CHECK');
  assert.match(stale.detail, /not bound to the current output/);
  fs.writeFileSync(path.join(rdir, 'critic-blind.md'), complete('blind', pack.source_hash, high));
  const fresh = p27();
  assert.equal(fresh.status, 'FAIL');
  assert.match(fresh.detail, /F-001/);
});

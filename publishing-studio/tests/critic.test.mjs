import test from 'node:test';
import assert from 'node:assert/strict';
import { reviewTemplate, parseReview, checkReviews, CATEGORIES } from '../scripts/lib/critic.mjs';

const issue = { id: 'x', title: 'X', pages: 16 };
const scores = CATEGORIES.map((c) => `| ${c} | 3 | ok |`).join('\n');
const doc = (stage, status, body) => `---\nstage: ${stage}\nstatus: ${status}\nreviewer: publication-critic\n---\n## Scores (1–5)\n\n| category | score | note |\n|---|:-:|---|\n${scores}\n\n## Findings\n${body}\n\n## Emergent fingerprint\n- 茜色の罫線が反復\n`;
const finding = (id, sev = 'HIGH', pages = '6, 7') => `### ${id} [${sev}] visual-rhythm — タイトル\n- Pages: ${pages}\n- Problem: 問題\n- Evidence: 根拠\n- Fix: 修正案\n`;
const rev = (stage, md) => ({ file: stage, ...parseReview(md) });

test('template is pending, has all categories and the three required sections', () => {
  const md = reviewTemplate('blind', issue, null);
  const r = parseReview(md);
  assert.equal(r.meta.status, 'pending');
  assert.deepEqual(Object.keys(r.scores).sort(), [...CATEGORIES].sort());
  assert.match(md, /AUTO:BEGIN/);
  assert.match(md, /Emergent fingerprint/);
});

test('pending stages are reported as pending, not as problems', () => {
  const reviews = Object.fromEntries(['blind', 'context', 'rereview'].map((s) => [s, rev(s, reviewTemplate(s, issue, null))]));
  const { problems, pending } = checkReviews(reviews, issue);
  assert.equal(pending.length, 3);
  assert.deepEqual(problems, []);
});

test('complete review: parses findings (problem/evidence/pages/severity/fix) and validates', () => {
  const r = rev('blind', doc('blind', 'complete', `${finding('F-001')}\n${finding('F-002', 'LOW', '3')}`));
  assert.equal(r.findings.length, 2);
  assert.deepEqual(r.findings[0].pages, [6, 7]);
  assert.equal(r.findings[1].severity, 'LOW');
  const { problems, report } = checkReviews({ blind: r }, issue);
  assert.deepEqual(problems.filter((p) => !p.startsWith('context') && !p.startsWith('rereview')), []);
  assert.equal(report.stages.blind.findings.length, 2);
});

test('invalid severity, missing fix, bad page, duplicate id and empty scores are flagged', () => {
  const body = `${finding('F-001', 'CRITICAL')}\n### F-002 [HIGH] visual-rhythm — x\n- Pages: 99\n- Problem: p\n- Evidence: e\n- Fix:\n\n${finding('F-002')}`;
  const r = rev('blind', doc('blind', 'complete', body).replace('| readability | 3 | ok |', '| readability |  | ok |'));
  const { problems } = checkReviews({ blind: r }, issue);
  const all = problems.join('\n');
  assert.match(all, /severity "CRITICAL"/);
  assert.match(all, /"fix" is empty/);
  assert.match(all, /page 99 out of range/);
  assert.match(all, /duplicate finding id/);
  assert.match(all, /score for "readability"/);
});

test('rereview requires a disposition for every MEDIUM+ finding of earlier stages', () => {
  const blind = rev('blind', doc('blind', 'complete', `${finding('F-001')}\n${finding('F-002', 'LOW', '2')}`));
  const context = rev('context', doc('context', 'complete', finding('F-003', 'MEDIUM', '9')));
  const missing = rev('rereview', doc('rereview', 'complete', '## Previous findings\n- F-001: fixed — 確認'));
  const bad = checkReviews({ blind, context, rereview: missing }, issue).problems.join('\n');
  assert.match(bad, /no disposition for F-003/);
  assert.doesNotMatch(bad, /no disposition for F-002/); // LOW needs none
  const ok = rev('rereview', doc('rereview', 'complete', '## Previous findings\n- F-001: fixed — 確認\n- F-003: wontfix — 編集判断'));
  assert.deepEqual(checkReviews({ blind, context, rereview: ok }, issue).problems, []);
});

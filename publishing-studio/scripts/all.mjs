#!/usr/bin/env node
// validate -> build -> render -> critic preparation -> preflight
import fs from 'node:fs';
import path from 'node:path';
import { parseArgs, outDir, REPO_ROOT } from './lib/paths.mjs';
import { overrideRequested, issueBoundary } from './lib/boundary.mjs';
import { loadIssue } from './lib/load.mjs';
import { validateModel, hasErrors } from './lib/validate-model.mjs';
import { buildPdf } from './lib/build.mjs';
import { renderPages } from './lib/render.mjs';
import { prepareCritic, checkCritic } from './lib/critic-run.mjs';
import { runPreflight, preflightMarkdown } from './lib/preflight.mjs';

const { positional, flags } = parseArgs(process.argv.slice(2));
const id = positional[0];
if (!id) {
  console.error('usage: npm run publication:all -- <issue-id> [--marks]');
  process.exit(2);
}
const step = (n, t) => console.log(`\n[${n}/5] ${t}`);
try {
  step(1, 'validate');
  const findings = await validateModel(loadIssue(id));
  for (const f of findings.filter((x) => x.level !== 'info')) console.log(`  ${f.level.toUpperCase()} ${f.code}: ${f.message}${f.where ? ` [${f.where}]` : ''}`);
  const model0 = loadIssue(id);
  const bnd = issueBoundary(model0.dir, { allowPublicTree: overrideRequested(flags) });
  for (const f of bnd.findings) console.log(`  ${bnd.overridden ? 'OVERRIDDEN' : 'ERROR'} ${f.code}: ${f.message}`);
  if (!bnd.ok) throw new Error('publishing boundary violation');
  if (hasErrors(findings)) throw new Error('validation failed');
  step(2, 'build (Vivliostyle PDF)');
  await buildPdf(id, { marks: !!flags.marks, allowPublicTree: overrideRequested(flags) });
  step(3, 'render pages + contact sheets + metrics');
  await renderPages(id);
  step(4, 'critic preparation (review pack, rhythm, fingerprint)');
  await prepareCritic(id);
  checkCritic(id);
  step(5, 'preflight');
  const r = await runPreflight(id);
  const out = outDir(id);
  fs.writeFileSync(path.join(out, 'preflight.json'), JSON.stringify(r, null, 2));
  fs.writeFileSync(path.join(out, 'preflight.md'), preflightMarkdown(r));
  // the critic pack embeds preflight.md; refresh it now that it exists
  fs.copyFileSync(path.join(out, 'preflight.md'), path.join(out, 'review-pack/context/preflight.md'));
  for (const i of r.items.filter((x) => x.status !== 'PASS')) console.log(`  ${i.status.padEnd(12)} ${i.code} ${i.check}: ${i.detail}`);
  console.log(`\npublication:all ${id}: preflight ${r.verdict} (PASS ${r.counts.PASS}, WARNING ${r.counts.WARNING}, FAIL ${r.counts.FAIL}, MANUAL CHECK ${r.counts['MANUAL CHECK']})`);
  console.log(`outputs: ${path.relative(REPO_ROOT, out)}/ {${id}.pdf, pages/, contact/, rhythm.md, fingerprint.json, review-pack/, preflight.md}`);
  process.exit(r.counts.FAIL ? 1 : 0);
} catch (e) {
  console.error(`\npublication:all failed: ${e.message}`);
  process.exit(1);
}

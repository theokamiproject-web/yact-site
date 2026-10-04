#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { parseArgs, outDir, REPO_ROOT } from './lib/paths.mjs';
import { runPreflight, preflightMarkdown } from './lib/preflight.mjs';

const { positional } = parseArgs(process.argv.slice(2));
const id = positional[0];
if (!id) {
  console.error('usage: npm run publication:preflight -- <issue-id>');
  process.exit(2);
}
try {
  const r = await runPreflight(id);
  const out = outDir(id);
  fs.mkdirSync(out, { recursive: true });
  fs.writeFileSync(path.join(out, 'preflight.json'), JSON.stringify(r, null, 2));
  fs.writeFileSync(path.join(out, 'preflight.md'), preflightMarkdown(r));
  for (const i of r.items) console.log(`${i.status.padEnd(12)} ${i.code} ${i.check}${i.status === 'PASS' ? '' : `\n             ${i.detail}`}`);
  console.log(`\npreflight ${id}: ${r.verdict} (PASS ${r.counts.PASS}, WARNING ${r.counts.WARNING}, FAIL ${r.counts.FAIL}, MANUAL CHECK ${r.counts['MANUAL CHECK']})`);
  console.log(`report: ${path.relative(REPO_ROOT, path.join(out, 'preflight.md'))}`);
  process.exit(r.counts.FAIL ? 1 : 0);
} catch (e) {
  console.error(`preflight failed: ${e.stack}`);
  process.exit(1);
}

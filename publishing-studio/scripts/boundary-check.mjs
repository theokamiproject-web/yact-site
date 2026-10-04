#!/usr/bin/env node
// usage: node boundary-check.mjs [--staged] [--classify <path>] [--issue <id>]
// Fails (exit 1) when private source / generated private files are tracked (or staged) in Git.
import path from 'node:path';
import { parseArgs, REPO_ROOT, issueDir } from './lib/paths.mjs';
import { trackedViolations, classifyRepoPath, issueBoundary, overrideRequested, OVERRIDE_FLAG } from './lib/boundary.mjs';

const { positional, flags } = parseArgs(process.argv.slice(2).map((a) => (a === '--classify' ? '--classify' : a)));
if (flags.classify) {
  for (const p of positional) console.log(`${classifyRepoPath(path.relative(REPO_ROOT, path.resolve(p)))}\t${p}`);
  process.exit(0);
}
let bad = 0;
if (flags.issue || positional[0]) {
  const id = positional[0];
  const r = issueBoundary(issueDir(id), { allowPublicTree: overrideRequested(flags) });
  for (const f of r.findings) console.error(`${r.overridden ? 'OVERRIDDEN' : 'FAIL'} ${f.code}: ${f.message}`);
  bad += r.ok ? 0 : 1;
  if (!r.findings.length) console.log(`issue ${id}: ${r.class}, boundary ok`);
} else {
  const v = trackedViolations({ repoRoot: REPO_ROOT, staged: !!flags.staged });
  for (const x of v) console.error(`FAIL ${x.cls}: ${x.file} must not be ${flags.staged ? 'committed' : 'tracked'}`);
  if (v.length) console.error(`\nPrivate/generated files are never committed to this (GitHub Pages) repository. Keep real issues in publishing-studio/workspace/ (ignored) or outside the repository.\nOverride only for a deliberate release: publishing-studio/publish/<id>/.`);
  bad += v.length ? 1 : 0;
  if (!v.length) console.log(`boundary ok (${flags.staged ? 'staged files' : 'tracked files'})`);
}
process.exit(bad ? 1 : 0);

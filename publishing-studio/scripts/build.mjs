#!/usr/bin/env node
import { parseArgs, REPO_ROOT } from './lib/paths.mjs';
import { overrideRequested } from './lib/boundary.mjs';
import { buildPdf, buildWeb } from './lib/build.mjs';
import path from 'node:path';

const { positional, flags } = parseArgs(process.argv.slice(2));
const id = positional[0];
if (!id) {
  console.error('usage: npm run publication:build -- <issue-id> [--marks] [--web-only]');
  process.exit(2);
}
try {
  if (flags['web-only']) {
    const { web } = await buildWeb(id, { marks: !!flags.marks, allowPublicTree: overrideRequested(flags) });
    console.log(`web build: ${path.relative(REPO_ROOT, web)}/index.html`);
  } else {
    const { pdf } = await buildPdf(id, { marks: !!flags.marks, allowPublicTree: overrideRequested(flags) });
    console.log(`PDF: ${path.relative(REPO_ROOT, pdf)}`);
  }
} catch (e) {
  console.error(`build failed: ${e.message}`);
  process.exit(1);
}

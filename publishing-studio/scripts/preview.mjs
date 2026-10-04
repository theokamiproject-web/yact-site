#!/usr/bin/env node
// Build the web version, then open Vivliostyle's live preview (spreads, real pagination, crop marks via --marks).
import { spawn } from 'node:child_process';
import path from 'node:path';
import { parseArgs, REPO_ROOT } from './lib/paths.mjs';
import { overrideRequested } from './lib/boundary.mjs';
import { buildWeb, vivliostyleBin, browserArgs } from './lib/build.mjs';

const { positional, flags } = parseArgs(process.argv.slice(2));
const id = positional[0];
if (!id) {
  console.error('usage: npm run publication:preview -- <issue-id> [--marks] [--no-open]');
  process.exit(2);
}
try {
  const { web } = await buildWeb(id, { marks: !!flags.marks, allowPublicTree: overrideRequested(flags) });
  const entry = path.join(web, 'index.html');
  console.log(`web build: ${path.relative(REPO_ROOT, entry)} (open it directly for a quick static preview)`);
  const args = [vivliostyleBin(), 'preview', entry, '-d', ...browserArgs()];
  if (flags['no-open']) args.push('--no-open-viewer');
  console.log('starting Vivliostyle preview (Ctrl+C to stop)...');
  const p = spawn(process.execPath, args, { cwd: REPO_ROOT, stdio: 'inherit' });
  p.on('exit', (c) => process.exit(c ?? 0));
} catch (e) {
  console.error(`preview failed: ${e.message}`);
  process.exit(1);
}

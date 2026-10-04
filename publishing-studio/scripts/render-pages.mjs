#!/usr/bin/env node
import { parseArgs } from './lib/paths.mjs';
import { renderPages } from './lib/render.mjs';

const { positional, flags } = parseArgs(process.argv.slice(2));
const id = positional[0];
if (!id) {
  console.error('usage: npm run publication:render -- <issue-id> [--dpi 110]');
  process.exit(2);
}
try {
  await renderPages(id, { dpi: Number(flags.dpi ?? 110) });
} catch (e) {
  console.error(`render failed: ${e.message}`);
  process.exit(1);
}

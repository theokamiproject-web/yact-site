#!/usr/bin/env node
// Prepare the review pack + critic templates; with --check validate completed reviews and write critic-report.json.
import { parseArgs } from './lib/paths.mjs';
import { prepareCritic, checkCritic } from './lib/critic-run.mjs';

const { positional, flags } = parseArgs(process.argv.slice(2));
const id = positional[0];
if (!id) {
  console.error('usage: npm run publication:critic -- <issue-id> [--check] [--reset]');
  process.exit(2);
}
try {
  if (!flags.check) await prepareCritic(id, { reset: !!flags.reset });
  const r = checkCritic(id);
  console.log(`critic ${id}: ${r.pending.length ? `${r.pending.length} stage(s) pending (MANUAL: reviews not done)` : 'all stages complete'}, ${r.problems.length} structural problem(s), ${r.severe.length} open BLOCKER/HIGH`);
  process.exit(r.problems.length ? 1 : 0);
} catch (e) {
  console.error(`critic failed: ${e.message}`);
  process.exit(1);
}

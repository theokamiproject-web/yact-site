#!/usr/bin/env node
import { parseArgs } from './lib/paths.mjs';
import { loadIssue } from './lib/load.mjs';
import { validateModel, hasErrors } from './lib/validate-model.mjs';
import { issueBoundary, overrideRequested, OVERRIDE_FLAG } from './lib/boundary.mjs';

const { positional, flags } = parseArgs(process.argv.slice(2));
const id = positional[0];
if (!id) {
  console.error('usage: npm run publication:validate -- <issue-id> [--json]');
  process.exit(2);
}
const model = loadIssue(id);
const findings = await validateModel(model);
const bnd = issueBoundary(model.dir, { allowPublicTree: overrideRequested(flags) });
for (const f of bnd.findings) findings.unshift({ level: bnd.overridden ? 'warning' : 'error', code: bnd.overridden ? `${f.code}_OVERRIDDEN` : f.code, message: f.message, where: 'publishing boundary' });
if (flags.json) {
  console.log(JSON.stringify(findings, null, 2));
} else {
  const icon = { error: 'ERROR  ', warning: 'WARNING', info: 'info   ' };
  for (const f of findings) console.log(`${icon[f.level]} ${f.code.padEnd(22)} ${f.message}${f.where ? `  [${f.where}]` : ''}`);
  const n = (l) => findings.filter((f) => f.level === l).length;
  console.log(`\nvalidate ${id}: ${n('error')} error(s), ${n('warning')} warning(s), ${n('info')} info`);
}
process.exit(hasErrors(findings) ? 1 : 0);

#!/usr/bin/env node
// Create a new issue from issues/_template.
import fs from 'node:fs';
import path from 'node:path';
import * as yaml from 'js-yaml';
import { parseArgs, ISSUES_DIR, NEW_ISSUES_DIR, assertId } from './lib/paths.mjs';

const { positional, flags } = parseArgs(process.argv.slice(2));
const id = positional[0];
if (!id) {
  console.error('usage: npm run publication:new -- <issue-id> [--title "TITLE"]');
  process.exit(2);
}
try {
  assertId(id);
  const dest = path.join(NEW_ISSUES_DIR, id);
  if (fs.existsSync(path.join(ISSUES_DIR, id))) throw new Error(`an example/issue named "${id}" already exists`);
  if (fs.existsSync(dest)) throw new Error(`issue already exists: ${dest}`);
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.cpSync(path.join(ISSUES_DIR, '_template'), dest, { recursive: true });
  const f = path.join(dest, 'issue.yaml');
  const issue = yaml.load(fs.readFileSync(f, 'utf8'));
  issue.id = id;
  const num = id.match(/(\d+)\s*$/)?.[1];
  if (num) issue.issue_number = Number(num);
  if (typeof flags.title === 'string') issue.title = flags.title;
  fs.writeFileSync(f, yaml.dump(issue, { lineWidth: 100 }));
  console.log(`created ${path.relative(process.cwd(), dest)}\nnext: edit issue.yaml / editorial.yaml / articles/ / flatplan.yaml, then`);
  console.log(`  npm run publication:validate -- ${id}\n  npm run publication:all -- ${id}`);
} catch (e) {
  console.error(e.message);
  process.exit(1);
}

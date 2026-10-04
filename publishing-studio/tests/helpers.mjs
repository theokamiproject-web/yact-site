import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

export const PS = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
export const script = (n) => path.join(PS, 'scripts', n);

/** Isolated workspace: copies _template and test-issue-01 so tests never touch real issues/output. */
export function workspace() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'ps-test-'));
  const issues = path.join(root, 'issues');
  const output = path.join(root, 'output');
  fs.mkdirSync(output, { recursive: true });
  for (const d of ['_template', 'test-issue-01']) fs.cpSync(path.join(PS, 'issues', d), path.join(issues, d), { recursive: true });
  fs.rmSync(path.join(issues, 'test-issue-01/reviews'), { recursive: true, force: true });
  const env = { ...process.env, PS_ISSUES_DIR: issues, PS_OUTPUT_DIR: output };
  const run = (name, ...args) => spawnSync(process.execPath, [script(name), ...args], { env, encoding: 'utf8', timeout: 170000 });
  return { root, issues, output, env, run, cleanup: () => fs.rmSync(root, { recursive: true, force: true }) };
}

export const clone = (o) => structuredClone(o);

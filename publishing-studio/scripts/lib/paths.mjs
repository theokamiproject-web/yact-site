import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const PS_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
export const REPO_ROOT = path.resolve(PS_ROOT, '..');
export const ISSUES_DIR = process.env.PS_ISSUES_DIR ? path.resolve(process.env.PS_ISSUES_DIR) : path.join(PS_ROOT, 'issues');
export const OUTPUT_DIR = process.env.PS_OUTPUT_DIR ? path.resolve(process.env.PS_OUTPUT_DIR) : path.join(PS_ROOT, 'output');
export const THEMES_DIR = path.join(PS_ROOT, 'themes');
export const LAYOUTS_DIR = path.join(PS_ROOT, 'layouts');
export const SCHEMAS_DIR = path.join(PS_ROOT, 'schemas');

export const ID_RE = /^[a-z0-9][a-z0-9-]*$/;

export function assertId(id) {
  if (!id || !ID_RE.test(id)) {
    throw new Error(`invalid issue id "${id ?? ''}" (lowercase letters, digits, "-")`);
  }
  return id;
}
export const issueDir = (id) => path.join(ISSUES_DIR, assertId(id));
export const outDir = (id) => path.join(OUTPUT_DIR, assertId(id));

/** Parse `<issue-id> [--flag] [--key value]` style CLI args. */
export function parseArgs(argv) {
  const positional = [];
  const flags = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith('--')) {
      const key = a.slice(2);
      const next = argv[i + 1];
      if (next !== undefined && !next.startsWith('--') && ['title', 'dpi', 'format'].includes(key)) {
        flags[key] = next;
        i++;
      } else flags[key] = true;
    } else positional.push(a);
  }
  return { positional, flags };
}

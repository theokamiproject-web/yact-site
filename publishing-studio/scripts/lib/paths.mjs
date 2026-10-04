import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const PS_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
export const REPO_ROOT = process.env.PS_REPO_ROOT ? path.resolve(process.env.PS_REPO_ROOT) : path.resolve(PS_ROOT, '..');
/** Example issues (committable, listed in boundary.json) and the template live here. */
export const EXAMPLES_DIR = path.join(PS_ROOT, 'issues');
/** Real issues are created here by default; the directory is git-ignored (see boundary.json / .gitignore). */
export const WORKSPACE_ISSUES_DIR = path.join(PS_ROOT, 'workspace', 'issues');
const ENV_ISSUES = process.env.PS_ISSUES_DIR ? path.resolve(process.env.PS_ISSUES_DIR) : null;
/** Where the template and examples are read from (PS_ISSUES_DIR overrides, used by tests). */
export const ISSUES_DIR = ENV_ISSUES ?? EXAMPLES_DIR;
/** Where `publication:new` writes (PS_ISSUES_DIR overrides). */
export const NEW_ISSUES_DIR = ENV_ISSUES ?? WORKSPACE_ISSUES_DIR;
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
/** Resolution order: PS_ISSUES_DIR (if set) → workspace/issues/<id> → issues/<id> (examples). */
export function issueDir(id) {
  assertId(id);
  if (ENV_ISSUES) return path.join(ENV_ISSUES, id);
  for (const root of [WORKSPACE_ISSUES_DIR, EXAMPLES_DIR]) {
    const d = path.join(root, id);
    if (fs.existsSync(d)) return d;
  }
  return path.join(WORKSPACE_ISSUES_DIR, id);
}
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
      if (next !== undefined && !next.startsWith('--') && ['title', 'dpi', 'format', 'reason'].includes(key)) {
        flags[key] = next;
        i++;
      } else flags[key] = true;
    } else positional.push(a);
  }
  return { positional, flags };
}

// Publishing boundary: classify every path and refuse to process / commit private source inside the public tree.
// The repository root is served by GitHub Pages, so anything tracked (or about to be tracked) is potentially public.
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { PS_ROOT } from './paths.mjs';

export const CLASSES = ['PRIVATE_SOURCE', 'BUILD_TEMP', 'GENERATED_PRIVATE', 'PUBLISHABLE', 'SYSTEM'];
export const OVERRIDE_FLAG = '--i-understand-private-source-may-be-published';
export const OVERRIDE_ENV = 'PS_ALLOW_PUBLIC_TREE';
export const OVERRIDE_ENV_VALUE = 'I_UNDERSTAND_PRIVATE_SOURCE_MAY_BE_PUBLISHED';

export function loadManifest(psRoot = PS_ROOT) {
  return JSON.parse(fs.readFileSync(path.join(psRoot, 'boundary.json'), 'utf8'));
}

const posix = (p) => p.split(path.sep).join('/');

/** Classify a path relative to publishing-studio/ (posix separators). */
export function classify(relToPS, manifest = loadManifest()) {
  const p = posix(relToPS).replace(/^\.\//, '');
  const seg = p.split('/');
  const examples = new Set(manifest.examples);
  if (seg[0] === 'workspace') return /^workspace\/(README\.md|issues\/\.gitkeep)$/.test(p) ? 'SYSTEM' : 'PRIVATE_SOURCE';
  if (seg[0] === 'issues') {
    if (seg.length === 1 || p === 'issues/.gitkeep') return 'SYSTEM';
    return examples.has(seg[1]) ? 'PUBLISHABLE' : 'PRIVATE_SOURCE';
  }
  if (seg[0] === 'output') {
    if (seg[1] === '.gitkeep' || seg.length === 1) return 'SYSTEM';
    return ['web', 'pages', 'contact', 'review-pack'].includes(seg[2]) ? 'BUILD_TEMP' : 'GENERATED_PRIVATE';
  }
  if (seg[0] === manifest.publish_dir) return 'PUBLISHABLE';
  return 'SYSTEM';
}

/** Classify a path relative to the repository root. */
export function classifyRepoPath(relToRepo, manifest = loadManifest()) {
  const p = posix(relToRepo);
  if (p.startsWith('publishing-studio/')) return classify(p.slice('publishing-studio/'.length), manifest);
  return p === 'index.html' || p.startsWith('img/') ? 'PUBLISHABLE' : 'SYSTEM';
}

const git = (args, cwd) => spawnSync('git', args, { cwd, encoding: 'utf8' });

export function repoRootOf(dir) {
  const r = git(['rev-parse', '--show-toplevel'], dir);
  return r.status === 0 ? fs.realpathSync(r.stdout.trim()) : null;
}

/** Tracked (or staged) files that must never be in Git. */
export function trackedViolations({ repoRoot, staged = false, manifest = loadManifest() }) {
  const r = staged ? git(['diff', '--cached', '--name-only', '--diff-filter=ACMR'], repoRoot) : git(['ls-files'], repoRoot);
  if (r.status !== 0) throw new Error(`git failed: ${r.stderr}`);
  return r.stdout.split('\n').filter(Boolean).map((f) => ({ file: f, cls: classifyRepoPath(f, manifest) })).filter((x) => ['PRIVATE_SOURCE', 'BUILD_TEMP', 'GENERATED_PRIVATE'].includes(x.cls));
}

/**
 * Is this issue directory safe to process? Private source inside a Git work tree is only acceptable when Git
 * ignores it and does not track it. Returns {ok, overridden, class, findings[]}.
 */
export function issueBoundary(dir, { psRoot = PS_ROOT, allowPublicTree = false, manifest = loadManifest(psRoot) } = {}) {
  const real = fs.existsSync(dir) ? fs.realpathSync(dir) : path.resolve(dir);
  const id = path.basename(real);
  const out = { dir: real, id, findings: [], ok: true, overridden: false };
  const exampleRoot = fs.existsSync(path.join(psRoot, 'issues')) ? fs.realpathSync(path.join(psRoot, 'issues')) : path.join(psRoot, 'issues');
  if (path.dirname(real) === exampleRoot && manifest.examples.includes(id)) return { ...out, class: 'PUBLISHABLE' };
  out.class = 'PRIVATE_SOURCE';
  const probeDir = fs.existsSync(real) ? real : path.dirname(real);
  const root = repoRootOf(probeDir);
  if (!root) return out; // not inside a Git work tree: nothing can be committed or served from here
  const tracked = git(['ls-files', '--', real], root).stdout.split('\n').filter(Boolean);
  if (tracked.length) out.findings.push({ code: 'BOUNDARY_TRACKED', message: `private issue "${id}" has ${tracked.length} file(s) tracked by Git (e.g. ${tracked[0]}). They are public once pushed to a Pages repository. Remove them from Git (git rm -r --cached) and keep the issue in workspace/ or outside the repository.` });
  const ignored = git(['check-ignore', '-q', '--', path.join(real, 'articles', 'x.md')], root).status === 0;
  if (!ignored) out.findings.push({ code: 'BOUNDARY_NOT_IGNORED', message: `private issue "${id}" is inside the Git work tree (${path.relative(root, real)}) and is not git-ignored, so it can be committed and published. Create real issues with "npm run publication:new" (workspace/issues/, ignored) or move it outside the repository. Example issues must be listed in publishing-studio/boundary.json.` });
  if (out.findings.length) {
    if (allowPublicTree) out.overridden = true;
    else out.ok = false;
  }
  return out;
}

export function overrideRequested(flags = {}) {
  return !!flags[OVERRIDE_FLAG.slice(2)] || process.env[OVERRIDE_ENV] === OVERRIDE_ENV_VALUE;
}

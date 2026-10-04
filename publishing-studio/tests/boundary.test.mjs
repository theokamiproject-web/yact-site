import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { classify, classifyRepoPath, issueBoundary, trackedViolations, loadManifest } from '../scripts/lib/boundary.mjs';
import { PS } from './helpers.mjs';

const git = (cwd, ...a) => spawnSync('git', a, { cwd, encoding: 'utf8' });
const M = loadManifest(PS);

test('classification: every file is one of the five classes', () => {
  const t = [
    ['workspace/issues/a/articles/x.md', 'PRIVATE_SOURCE'], ['workspace/README.md', 'SYSTEM'],
    ['issues/real-issue/articles/x.md', 'PRIVATE_SOURCE'], ['issues/real-issue/notes/memo.md', 'PRIVATE_SOURCE'], ['issues/real-issue/images/a.jpg', 'PRIVATE_SOURCE'], ['issues/real-issue/editorial.yaml', 'PRIVATE_SOURCE'],
    ['issues/test-issue-01/articles/cover.md', 'PUBLISHABLE'], ['issues/_template/issue.yaml', 'PUBLISHABLE'],
    ['output/x/web/index.html', 'BUILD_TEMP'], ['output/x/review-pack/blind/BLIND.md', 'BUILD_TEMP'], ['output/x/x.pdf', 'GENERATED_PRIVATE'], ['output/x/preflight.json', 'GENERATED_PRIVATE'],
    ['publish/x/x.pdf', 'PUBLISHABLE'], ['scripts/lib/build.mjs', 'SYSTEM'], ['layouts/cover/index.mjs', 'SYSTEM'], ['docs/RC1_REPAIR_LOG.md', 'SYSTEM'],
  ];
  for (const [p, c] of t) assert.equal(classify(p, M), c, p);
  assert.equal(classifyRepoPath('index.html', M), 'PUBLISHABLE');
  assert.equal(classifyRepoPath('publishing-studio/issues/zz/articles/a.md', M), 'PRIVATE_SOURCE');
});

test('boundary.json examples and the repository .gitignore allow-list are identical', () => {
  const ig = fs.readFileSync(path.join(PS, '..', '.gitignore'), 'utf8');
  const allowed = [...ig.matchAll(/^!publishing-studio\/issues\/([^/\n]+)\/?$/gm)].map((m) => m[1]).sort();
  assert.deepEqual(allowed, [...M.examples].sort());
});

test('nothing private or generated is tracked in this repository', () => {
  const root = path.resolve(PS, '..');
  assert.deepEqual(trackedViolations({ repoRoot: root, manifest: M }), []);
});

function fixture({ ignore = true, track = false } = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'ps-bnd-'));
  git(root, 'init', '-q');
  git(root, 'config', 'user.email', 't@t'); git(root, 'config', 'user.name', 't');
  const ps = path.join(root, 'publishing-studio');
  fs.mkdirSync(path.join(ps, 'issues/test-issue-01'), { recursive: true });
  fs.mkdirSync(path.join(ps, 'issues/my-real-issue/articles'), { recursive: true });
  fs.writeFileSync(path.join(ps, 'issues/my-real-issue/articles/a.md'), 'secret');
  fs.writeFileSync(path.join(ps, 'boundary.json'), JSON.stringify({ examples: ['test-issue-01'], publish_dir: 'publish' }));
  if (ignore) fs.writeFileSync(path.join(root, '.gitignore'), 'publishing-studio/issues/*\n!publishing-studio/issues/test-issue-01/\n');
  if (track) git(root, 'add', '-f', 'publishing-studio/issues/my-real-issue/articles/a.md');
  return { root, ps, dir: path.join(ps, 'issues/my-real-issue') };
}

test('private issue inside the work tree and NOT ignored => FAIL', () => {
  const f = fixture({ ignore: false });
  const r = issueBoundary(f.dir, { psRoot: f.ps });
  assert.equal(r.ok, false);
  assert.ok(r.findings.some((x) => x.code === 'BOUNDARY_NOT_IGNORED'));
});

test('private issue ignored by git and untracked => ok', () => {
  const f = fixture({ ignore: true });
  assert.equal(issueBoundary(f.dir, { psRoot: f.ps }).ok, true);
});

test('private issue force-tracked despite ignore => FAIL (and staged detection)', () => {
  const f = fixture({ ignore: true, track: true });
  const r = issueBoundary(f.dir, { psRoot: f.ps });
  assert.equal(r.ok, false);
  assert.ok(r.findings.some((x) => x.code === 'BOUNDARY_TRACKED'));
  const staged = trackedViolations({ repoRoot: f.root, staged: true, manifest: JSON.parse(fs.readFileSync(path.join(f.ps, 'boundary.json'), 'utf8')) });
  assert.equal(staged.length, 1);
});

test('explicit override is accepted but reported as overridden', () => {
  const f = fixture({ ignore: false });
  const r = issueBoundary(f.dir, { psRoot: f.ps, allowPublicTree: true });
  assert.equal(r.ok, true);
  assert.equal(r.overridden, true);
});

test('allow-listed example inside the public tree is ok; issue outside any git tree is ok', () => {
  const f = fixture({ ignore: false });
  assert.equal(issueBoundary(path.join(f.ps, 'issues/test-issue-01'), { psRoot: f.ps }).ok, true);
  const out = fs.mkdtempSync(path.join(os.tmpdir(), 'ps-out-'));
  fs.mkdirSync(path.join(out, 'x'));
  assert.equal(issueBoundary(path.join(out, 'x'), { psRoot: f.ps }).ok, true);
});

test('CLI: boundary-check --staged exits 1 when a private file is staged, 0 when clean', () => {
  const f = fixture({ ignore: true, track: true });
  const env = { ...process.env, PS_REPO_ROOT: f.root };
  const bad = spawnSync(process.execPath, [path.join(PS, 'scripts/boundary-check.mjs'), '--staged'], { cwd: f.root, encoding: 'utf8', env });
  assert.equal(bad.status, 1, bad.stdout + bad.stderr);
  assert.match(bad.stderr, /PRIVATE_SOURCE/);
  git(f.root, 'reset', '-q');
  const ok = spawnSync(process.execPath, [path.join(PS, 'scripts/boundary-check.mjs'), '--staged'], { cwd: f.root, encoding: 'utf8', env });
  assert.equal(ok.status, 0, ok.stdout + ok.stderr);
});

test('pre-commit hook and CI workflow exist and call the boundary check', () => {
  const root = path.resolve(PS, '..');
  const hook = path.join(root, '.githooks/pre-commit');
  assert.ok(fs.statSync(hook).mode & 0o111, 'hook must be executable');
  assert.match(fs.readFileSync(hook, 'utf8'), /boundary-check\.mjs --staged/);
  assert.match(fs.readFileSync(path.join(root, '.github/workflows/publishing-boundary.yml'), 'utf8'), /boundary-check\.mjs/);
});

test('new-issue defaults to the git-ignored workspace/ (real issues never land in the public tree)', () => {
  const id = `zz-ws-${process.pid}`;
  const env = { ...process.env }; delete env.PS_ISSUES_DIR;
  const r = spawnSync(process.execPath, [path.join(PS, 'scripts/new-issue.mjs'), id], { encoding: 'utf8', env });
  const dir = path.join(PS, 'workspace/issues', id);
  try {
    assert.equal(r.status, 0, r.stderr);
    assert.ok(fs.existsSync(path.join(dir, 'issue.yaml')));
    assert.equal(git(path.resolve(PS, '..'), 'check-ignore', '-q', path.join(dir, 'articles/x.md')).status, 0, 'must be git-ignored');
    assert.equal(issueBoundary(dir, { psRoot: PS }).ok, true);
  } finally { fs.rmSync(dir, { recursive: true, force: true }); }
});

test('validate / build / all REFUSE an issue that private source would make public; the override is explicit', () => {
  const f = fixture({ ignore: false });
  const issues = path.join(f.ps, 'issues');
  fs.cpSync(path.join(PS, 'issues/_template'), path.join(issues, 'issue-x'), { recursive: true });
  const env = { ...process.env, PS_ISSUES_DIR: issues, PS_OUTPUT_DIR: path.join(f.root, 'out') };
  const run = (script, ...a) => spawnSync(process.execPath, [path.join(PS, 'scripts', script), 'issue-x', ...a], { encoding: 'utf8', env });
  for (const s of ['validate.mjs', 'build.mjs', 'all.mjs']) {
    const r = run(s);
    assert.equal(r.status, 1, `${s}: ${r.stdout}${r.stderr}`);
    assert.match(r.stdout + r.stderr, /BOUNDARY_NOT_IGNORED/, s);
  }
  const ov = run('validate.mjs', '--i-understand-private-source-may-be-published');
  assert.equal(ov.status, 0, ov.stdout);
  assert.match(ov.stdout, /OVERRIDDEN/);
  fs.appendFileSync(path.join(f.root, '.gitignore'), 'publishing-studio/issues/issue-x/\n');
  assert.equal(run('validate.mjs').status, 0, 'ignored => ok');
});

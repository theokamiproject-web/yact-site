// build: model -> output/<id>/web (HTML+CSS+images) -> output/<id>/<id>.pdf (Vivliostyle)
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { outDir, PS_ROOT, REPO_ROOT } from './paths.mjs';
import { loadIssue } from './load.mjs';
import { validateModel, hasErrors } from './validate-model.mjs';
import { loadRegistry } from './registry.mjs';
import { compose } from './compose.mjs';
import { resolveTheme, pageSetupCss } from './theme.mjs';
import { findChromium, sandboxPolicy } from './browser.mjs';
import { issueBoundary } from './boundary.mjs';

const require = createRequire(import.meta.url);

function walk(dir, out = []) {
  if (!fs.existsSync(dir)) return out;
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, out);
    else out.push(p);
  }
  return out;
}

/** Hash of everything that affects the PDF: issue sources, themes, layouts. */
export function sourceHash(model) {
  const h = crypto.createHash('sha1');
  const files = [...walk(model.dir), ...walk(path.join(PS_ROOT, 'themes')), ...walk(path.join(PS_ROOT, 'layouts'))]
    .filter((f) => !f.includes(`${path.sep}notes${path.sep}`) && !f.includes(`${path.sep}reviews${path.sep}`))
    .sort();
  for (const f of files) {
    h.update(path.relative(PS_ROOT, f));
    h.update(fs.readFileSync(f));
  }
  return h.digest('hex');
}

export async function buildWeb(id, { marks = false, log = console.log, allowPublicTree = false } = {}) {
  const model = loadIssue(id);
  const bnd = issueBoundary(model.dir, { allowPublicTree });
  for (const f of bnd.findings) log(`  ${bnd.overridden ? 'OVERRIDDEN' : 'ERROR'} ${f.code}: ${f.message}`);
  if (!bnd.ok) throw new Error('publishing boundary violation (private source would be public); see above');
  const findings = await validateModel(model);
  for (const f of findings.filter((x) => x.level === 'error')) log(`  ERROR ${f.code}: ${f.message}${f.where ? ` (${f.where})` : ''}`);
  if (hasErrors(findings)) throw new Error('validation failed; fix the errors above (npm run publication:validate -- ' + id + ')');

  const reg = await loadRegistry();
  const { html, pages, toc } = await compose(model);
  const out = outDir(id);
  const web = path.join(out, 'web');
  fs.rmSync(web, { recursive: true, force: true });
  fs.mkdirSync(path.join(web, 'css'), { recursive: true });
  fs.mkdirSync(path.join(web, 'images'), { recursive: true });

  const theme = resolveTheme(model);
  fs.writeFileSync(path.join(web, 'css/theme.css'), theme.map((t) => `/* ==== ${t.source} ==== */\n${t.css}`).join('\n\n'));
  fs.writeFileSync(path.join(web, 'css/layouts.css'), reg.styles.map((s) => `/* ==== layouts/${s.family} ==== */\n${s.css}`).join('\n\n'));
  fs.writeFileSync(path.join(web, 'css/page-setup.css'), pageSetupCss(model.issue, { marks }));
  for (const [f, src] of Object.entries(model.images)) fs.copyFileSync(src, path.join(web, 'images', f));
  fs.writeFileSync(path.join(web, 'index.html'), html);
  fs.writeFileSync(path.join(web, 'pages.json'), JSON.stringify({ issue: model.issue, pages, toc }, null, 2));
  return { model, web, pages, findings, boundary_override: bnd.overridden };
}

function run(cmd, args, { cwd, log }) {
  return new Promise((resolve, reject) => {
    const p = spawn(cmd, args, { cwd, stdio: ['ignore', 'pipe', 'pipe'] });
    let buf = '';
    p.stdout.on('data', (d) => (buf += d));
    p.stderr.on('data', (d) => (buf += d));
    p.on('error', reject);
    p.on('close', (code) => (code === 0 ? resolve(buf) : reject(new Error(`${cmd} exited ${code}\n${buf.split('\n').slice(-15).join('\n')}`))));
  });
}

export function vivliostyleBin() {
  return path.join(path.dirname(require.resolve('@vivliostyle/cli/package.json')), 'dist/cli.js');
}
export function vivliostyleVersion() {
  return require('@vivliostyle/cli/package.json').version;
}

export function browserArgs() {
  const b = findChromium();
  // Vivliostyle CLI disables the Chromium sandbox unless told otherwise: opt IN to the sandbox by default.
  return [...(b ? ['--executable-browser', b] : []), ...(sandboxPolicy().noSandbox ? [] : ['--sandbox'])];
}

export async function buildPdf(id, { marks = false, log = console.log, allowPublicTree = false } = {}) {
  const { model, web, pages, boundary_override } = await buildWeb(id, { marks, log, allowPublicTree });
  const out = outDir(id);
  const pdf = path.join(out, `${id}.pdf`);
  const args = [vivliostyleBin(), 'build', path.join(web, 'index.html'), '-d', '-o', pdf, '-l', model.issue.language, '--title', model.issue.title, ...browserArgs(), '--log-level', 'silent'];
  log(`  vivliostyle ${vivliostyleVersion()} -> ${path.relative(REPO_ROOT, pdf)}${marks ? ' (crop marks)' : ''}`);
  await run(process.execPath, args, { cwd: REPO_ROOT, log });
  const manifest = {
    issue: id,
    built_at: new Date().toISOString(),
    source_hash: sourceHash(model),
    pdf: path.basename(pdf),
    marks,
    boundary_override: !!boundary_override,
    bleed_mm: model.issue.bleed,
    trim_mm: [model.issue.width, model.issue.height],
    expected_pages: model.issue.pages,
    vivliostyle: vivliostyleVersion(),
    pages: pages.map(({ n, layout, variant, article }) => ({ n, layout, variant, article })),
  };
  fs.writeFileSync(path.join(out, 'build.json'), JSON.stringify(manifest, null, 2));
  return { pdf, web, manifest };
}

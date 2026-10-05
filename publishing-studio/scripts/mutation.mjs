#!/usr/bin/env node
// Mutation testing of the test suite. Each mutation breaks one behaviour in a SANDBOX COPY of publishing-studio/ (the real tree is
// never touched); the mapped tests must FAIL ("KILLED"). A mutation that no test notices "SURVIVED" = an untested behaviour.
// usage: node publishing-studio/scripts/mutation.mjs [id-prefix ...]   (writes reviews/evidence-rc2/mutation.json)
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { PS_ROOT, REPO_ROOT } from './lib/paths.mjs';

const only = process.argv.slice(2);
const T = (...f) => f.map((n) => `${n}.test.mjs`);
export const MUTATIONS = [
  ['M01', '.fit overflow detection disabled', 'scripts/lib/metrics.mjs', "if (el.scrollHeight > el.clientHeight + 1 || el.scrollWidth > el.clientWidth + 1) {", 'if (false) {', T('metrics')],
  ['M02', 'spread must start on an even page: check removed', 'scripts/lib/validate-model.mjs', 'e.pages[0] % 2 !== 0)', 'false)', T('model')],
  ['M03', 'stale-PDF hash made constant', 'scripts/lib/build.mjs', "return h.digest('hex');", "return 'constant';", T('preflight')],
  ['M04', 'Q/A orphan rule removed', 'scripts/lib/text.mjs', "const needWithAnswer = need + (b.type === 'q' && queue[1]?.type === 'a' ? blockLines(queue[1], perLine) : 0);", 'const needWithAnswer = need;', T('text')],
  ['M05', 'component CSS specificity: .page h1 restored', 'themes/base/typography.css', ':where(.page) h1 {', '.page h1 {', T('metrics')],
  ['M06', 'PDF page-count check always passes', 'scripts/lib/preflight.mjs', "n === model.issue.pages ? 'PASS' : 'FAIL', `PDF has", "true ? 'PASS' : 'FAIL', `PDF has", T('preflight')],
  ['M07', 'rereview disposition check removed', 'scripts/lib/critic.mjs', '!disp.has(f.id)) problems.push', 'false) problems.push', T('critic')],
  ['M08', 'missing caption FAIL downgraded to WARNING', 'scripts/lib/preflight.mjs', "{ warnAs: 'FAIL', okText: 'every captioned image has a caption' }", "{ warnAs: 'WARNING', okText: 'every captioned image has a caption' }", T('preflight')],
  ['M09', 'folio problems ignored', 'scripts/lib/preflight.mjs', "pnProblems.length ? 'FAIL' : 'PASS'", "'PASS'", T('preflight')],
  ['M10', 'blank-page check disabled', 'scripts/lib/preflight.mjs', "blank.length ? 'FAIL' : 'PASS'", "'PASS'", T('preflight')],
  ['M11', 'safe-area check disabled', 'scripts/lib/preflight.mjs', "safe.length ? 'WARNING' : 'PASS'", "'PASS'", T('preflight')],
  ['M12', 'image resolution check disabled', 'scripts/lib/preflight.mjs', "lo.length ? 'FAIL' : mid.length ? 'WARNING' : 'PASS'", "'PASS'", T('preflight')],
  ['M13', 'bleed-box check disabled', 'scripts/lib/preflight.mjs', "bad.length ? 'FAIL' : 'PASS', bad.length ? `BleedBox", "false ? 'FAIL' : 'PASS', bad.length ? `BleedBox", T('preflight')],
  ['M14', 'blind pack leaks the flatplan', 'scripts/lib/critic-run.mjs', "for (const f of ['editorial.yaml', 'flatplan.yaml']) fs.copyFileSync(path.join(issueDir(id), f), path.join(ctx, f));", "for (const f of ['editorial.yaml', 'flatplan.yaml']) { fs.copyFileSync(path.join(issueDir(id), f), path.join(ctx, f)); fs.copyFileSync(path.join(issueDir(id), f), path.join(blind, f)); }", T('pipeline')],
  ['M15', 'contents overflow check removed (validate)', 'scripts/lib/validate-model.mjs', 'm.toc_items.fitting < m.toc_items.total) add(', 'false) add(', T('model')],
  ['M16', 'contents completeness check removed (preflight)', 'scripts/lib/preflight.mjs', "tocBad.length ? 'FAIL' : 'PASS'", "'PASS'", T('preflight')],
  ['M17', 'publishing boundary: not-ignored check removed', 'scripts/lib/boundary.mjs', 'if (!ignored) out.findings.push', 'if (false) out.findings.push', ['boundary.test.mjs', '--test-name-pattern=NOT ignored|REFUSE']],
  ['M18', 'manuscript HTML passes through unescaped', 'scripts/lib/text.mjs', 'html: ({ text }) => escapeHtml(text),', 'html: ({ text }) => text,', T('security')],
  ['M19', 'image URL percent-encoding removed', 'layouts/_shared.mjs', 'src="images/${esc(encodeURIComponent(file))}"', 'src="images/${esc(file)}"', T('security')],
  ['M20', 'Chromium sandbox disabled by default', 'scripts/lib/browser.mjs', "  return { noSandbox: false };\n}\n\nlet noticed", "  return { noSandbox: true, reason: 'default' };\n}\n\nlet noticed", T('security')],
  ['M21', 'theme external-resource check removed', 'scripts/lib/validate-model.mjs', "if (/@import|url", "if (false && /@import|url", T('security')],
  ['M22', 'critic --reset overwrites authored reviews', 'scripts/lib/critic-run.mjs', 'if (authored.length && !force) throw', 'if (false) throw', T('critic-protection')],
  ['M23', 'stale reviews gate the new output', 'scripts/lib/critic.mjs', "(!sourceHash || String(reviews[s].meta.source_hash ?? '') === sourceHash)", '(true)', T('critic-protection')],
  ['M24', 'page-relative token replaced by a millimetre literal', 'themes/base/tokens.css', '--opener-hero-h: calc(var(--page-h) * 0.5333);', '--opener-hero-h: 112mm;', T('layout-tokens')],
  ['M25', 'density heuristics return nothing', 'scripts/lib/density.mjs', "    if (!lowOcc && !lowExt) continue;", "    continue;", T('density')],
  ['M26', 'orphan-line measurement disabled', 'scripts/lib/metrics.mjs', 'if (keys.length >= 2 && lines.get(keys.at(-1)) < fsPx * 2.2)', 'if (false)', T('metrics')],
  ['M27', 'undefined grid helper class (c-1-5 removed)', 'themes/base/grid.css', '.c-1-5 { grid-column: 1 / span 5; }', '', T('layout-tokens')],
  ['M28', 'text capacity ignores measured columns', 'scripts/lib/text.mjs', 'f.cols * perCol - (f.cols > 1 ? f.cols : 0)', 'perCol', T('text')],
];

function sandbox() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'ps-mut-'));
  fs.symlinkSync(path.join(REPO_ROOT, 'node_modules'), path.join(root, 'node_modules'));
  fs.cpSync(PS_ROOT, path.join(root, 'publishing-studio'), { recursive: true, filter: (s) => !/\/(output|workspace|reviews)(\/|$)/.test(s) });
  fs.copyFileSync(path.join(REPO_ROOT, 'package.json'), path.join(root, 'package.json'));
  fs.copyFileSync(path.join(REPO_ROOT, '.gitignore'), path.join(root, '.gitignore'));
  return root;
}

const root = sandbox();
const ps = path.join(root, 'publishing-studio');
const results = {};
for (const [id, name, file, from, to, tests] of MUTATIONS) {
  if (only.length && !only.some((o) => id.startsWith(o.toUpperCase()))) continue;
  const f = path.join(ps, file);
  const orig = fs.readFileSync(f, 'utf8');
  if (!orig.includes(from)) { results[id] = { name, result: 'NOT APPLICABLE (pattern missing: the code moved; update this table)' }; console.log(id, results[id].result); continue; }
  fs.writeFileSync(f, orig.replace(from, to));
  const files = tests.filter((t) => t.endsWith('.mjs')).map((t) => path.join(ps, 'tests', t));
  const extra = tests.filter((t) => t.startsWith('--'));
  const r = spawnSync(process.execPath, ['--test', ...extra, ...files], { encoding: 'utf8', timeout: 590000, env: { ...process.env, PS_ISSUES_DIR: '', PS_OUTPUT_DIR: '' } });
  fs.writeFileSync(f, orig);
  const failed = [...r.stdout.matchAll(/^not ok \d+ - (.*)$/gm)].map((m) => m[1]);
  results[id] = { name, tests: tests.join(' '), result: failed.length ? 'KILLED' : 'SURVIVED', by: failed.slice(0, 2) };
  console.log(`${id} ${results[id].result.padEnd(8)} ${name}${failed.length ? `  <- ${failed[0].slice(0, 80)}` : ''}`);
}
fs.rmSync(root, { recursive: true, force: true });
const outDir = path.join(PS_ROOT, 'reviews/evidence-rc2');
fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(path.join(outDir, only.length ? `mutation-${only.join('_')}.json` : 'mutation.json'), JSON.stringify(results, null, 1));
const survived = Object.values(results).filter((x) => x.result !== 'KILLED');
console.log(`\n${Object.keys(results).length - survived.length}/${Object.keys(results).length} mutations killed`);
process.exit(survived.length ? 1 : 0);

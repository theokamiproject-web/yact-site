// RC1: mutation testing of the test suite (in SANDBOX). Each mutation must make >=1 test fail; if none fails the behaviour is untested.
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
const SBX = process.env.SBX;
const only = process.argv.slice(2);
const M = [
  ['m1 overflow detection disabled (metrics)', 'scripts/lib/metrics.mjs', "if (el.scrollHeight > el.clientHeight + 1 || el.scrollWidth > el.clientWidth + 1) {", 'if (false) {'],
  ['m2 spread parity check removed (validate)', 'scripts/lib/validate-model.mjs', "e.pages[0] % 2 !== 0)", 'false)'],
  ['m3 staleness hash constant (build)', 'scripts/lib/build.mjs', "return h.digest('hex');", "return 'constant';"],
  ['m4 Q/A orphan rule removed (text)', 'scripts/lib/text.mjs', "const needed = cost + (b.type === 'q' && queue[1]?.type === 'a' ? blockCost(queue[1]) : 0);", 'const needed = cost;'],
  ['m5 :where specificity fix reverted (css)', 'themes/base/typography.css', ':where(.page) h1 {', '.page h1 {'],
  ['m6 PDF page-count check always PASS (preflight)', 'scripts/lib/preflight.mjs', "n === model.issue.pages ? 'PASS' : 'FAIL', `PDF has", "true ? 'PASS' : 'FAIL', `PDF has"],
  ['m7 rereview disposition check removed (critic)', 'scripts/lib/critic.mjs', "!disp.has(f.id)) problems.push", "false) problems.push"],
  ['m8 missing caption FAIL->WARNING (preflight)', 'scripts/lib/preflight.mjs', "{ warnAs: 'FAIL', okText: 'every captioned image has a caption' }", "{ warnAs: 'WARNING', okText: 'every captioned image has a caption' }"],
  ['m9 page-number problems ignored (preflight)', 'scripts/lib/preflight.mjs', "pnProblems.length ? 'FAIL' : 'PASS'", "'PASS'"],
  ['m10 blank-page check disabled (preflight)', 'scripts/lib/preflight.mjs', "blank.length ? 'FAIL' : 'PASS'", "'PASS'"],
  ['m11 safe-area check disabled (preflight)', 'scripts/lib/preflight.mjs', "safe.length ? 'WARNING' : 'PASS'", "'PASS'"],
  ['m12 ppi check disabled (preflight)', 'scripts/lib/preflight.mjs', "lo.length ? 'FAIL' : mid.length ? 'WARNING' : 'PASS'", "'PASS'"],
  ['m13 bleed box check disabled (preflight)', 'scripts/lib/preflight.mjs', "bad.length ? 'FAIL' : 'PASS', bad.length ? `BleedBox", "false ? 'FAIL' : 'PASS', bad.length ? `BleedBox"],
  ['m14 blind pack leaks flatplan (critic-run)', 'scripts/lib/critic-run.mjs', "for (const f of ['editorial.yaml', 'flatplan.yaml']) fs.copyFileSync(path.join(issueDir(id), f), path.join(ctx, f));", "for (const f of ['editorial.yaml', 'flatplan.yaml']) { fs.copyFileSync(path.join(issueDir(id), f), path.join(ctx, f)); fs.copyFileSync(path.join(issueDir(id), f), path.join(blind, f)); }"],
];
const out = {};
for (const [name, file, from, to] of M) {
  if (only.length && !only.some((o) => name.startsWith(o))) continue;
  const f = path.join(SBX, file);
  const orig = fs.readFileSync(f, 'utf8');
  if (!orig.includes(from)) { out[name] = 'MUTATION NOT APPLICABLE (pattern missing)'; console.log(name, out[name]); continue; }
  fs.writeFileSync(f, orig.replace(from, to));
  const r = spawnSync(process.execPath, ['--test', path.join(SBX, 'tests') + '/*.test.mjs'].flatMap((x) => (x.includes('*') ? fs.readdirSync(path.join(SBX, 'tests')).filter((n) => n.endsWith('.test.mjs')).map((n) => path.join(SBX, 'tests', n)) : [x])), { encoding: 'utf8', timeout: 170000 });
  fs.writeFileSync(f, orig);
  const fails = [...r.stdout.matchAll(/^not ok \d+ - (.*)$/gm)].map((m) => m[1]);
  out[name] = fails.length ? `KILLED by: ${fails.join(' | ').slice(0, 160)}` : 'SURVIVED (no test failed)';
  console.log(name, '=>', out[name]);
}
fs.writeFileSync(path.join(path.dirname(new URL(import.meta.url).pathname), `../evidence/D-mutation${only.length ? '-' + only.join('_') : ''}.json`), JSON.stringify(out, null, 1));

// RC1: staleness detection + reproducibility, in a sandbox copy. usage: SBX=/path/publishing-studio node stale-repro.mjs
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { spawnSync, execFileSync } from 'node:child_process';
import sharp from 'sharp';

const SBX = process.env.SBX;
const run = (s, ...a) => spawnSync(process.execPath, [path.join(SBX, 'scripts', s), ...a], { encoding: 'utf8', timeout: 175000 });
const id = 'adv-stale';
const dir = path.join(SBX, 'issues', id);
fs.rmSync(dir, { recursive: true, force: true });
fs.cpSync(path.join(SBX, 'issues/test-issue-01'), dir, { recursive: true });
fs.rmSync(path.join(dir, 'reviews'), { recursive: true, force: true });
const sha = (f) => crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex').slice(0, 12);
const out = {};

// ---- reproducibility
let r = run('all.mjs', id);
out.baseline_all_exit = r.status;
const pdf = path.join(SBX, 'output', id, `${id}.pdf`);
const pngs = () => fs.readdirSync(path.join(SBX, 'output', id, 'pages')).sort().map((f) => [f, sha(path.join(SBX, 'output', id, 'pages', f))]);
const run1 = { pdf: sha(pdf), pngs: pngs(), info: execFileSync('pdfinfo', [pdf]).toString().split('\n').filter((l) => /Date|Producer|Creator|Title/.test(l)) };
fs.copyFileSync(pdf, path.join(SBX, 'output', id, 'run1.pdf'));
await new Promise((res) => setTimeout(res, 2100));
run('build.mjs', id); run('render-pages.mjs', id);
const run2 = { pdf: sha(pdf), pngs: pngs(), info: execFileSync('pdfinfo', [pdf]).toString().split('\n').filter((l) => /Date|Producer|Creator|Title/.test(l)) };
out.repro = { pdf_identical: run1.pdf === run2.pdf, pdf_sha: [run1.pdf, run2.pdf], png_identical: JSON.stringify(run1.pngs) === JSON.stringify(run2.pngs), png_diff_count: run1.pngs.filter(([f, h], i) => run2.pngs[i][1] !== h).length, metadata_run1: run1.info, metadata_run2: run2.info };
// text-level equality
const txt = (f) => execFileSync('pdftotext', ['-layout', f, '-']).toString();
out.repro.text_identical = txt(path.join(SBX, 'output', id, 'run1.pdf')) === txt(pdf);

// ---- staleness
const P10 = (res) => (res.stdout.match(/(PASS|FAIL|WARNING)\s+P10/) ?? [])[1] ?? 'absent';
const P16 = (res) => (res.stdout.match(/(PASS|FAIL|WARNING)\s+P16/) ?? [])[1] ?? 'absent';
const files = {
  'article body': [path.join(dir, 'articles/editors-note.md'), (s) => `${s}\n追記。\n`],
  'article front matter (title)': [path.join(dir, 'articles/harbor-theater.md'), (s) => s.replace('倉庫が劇場になる日', '倉庫が劇場になる日々')],
  'caption': [path.join(dir, 'captions/captions.yaml'), (s) => s.replace('夕方、桟橋に残る光。', '夕方、桟橋に残る光')],
  'credits': [path.join(dir, 'credits.yaml'), (s) => s.replace('汐田 結', '汐田 ゆい')],
  'editorial.yaml': [path.join(dir, 'editorial.yaml'), (s) => s.replace('varied', 'steady')],
  'issue.yaml (title)': [path.join(dir, 'issue.yaml'), (s) => s.replace('TEST ISSUE 01', 'TEST ISSUE 01b')],
  'issue.yaml (bleed)': [path.join(dir, 'issue.yaml'), (s) => s.replace('bleed: 3', 'bleed: 5')],
  'flatplan (variant)': [path.join(dir, 'flatplan.yaml'), (s) => s.replace('variant: qa', 'variant: qa-portrait')],
  'flatplan (notes only)': [path.join(dir, 'flatplan.yaml'), (s) => s.replace('表紙。夕暮れの港', '表紙。夕暮れの港。')],
  'images.yaml (focal)': [path.join(dir, 'images/images.yaml'), (s) => s.replace('focal: [0.6, 0.55]', 'focal: [0.2, 0.2]')],
  'theme_overrides (issue.yaml)': [path.join(dir, 'issue.yaml'), (s) => s.replace('theme: base', 'theme: base\ntheme_overrides:\n  --color-accent: "#00aa00"')],
  'themes/base/tokens.css': [path.join(SBX, 'themes/base/tokens.css'), (s) => s.replace('#c8452d', '#0044cc')],
  'layouts/feature/style.css': [path.join(SBX, 'layouts/feature/style.css'), (s) => `${s}\n.fo-title{color:red}\n`],
  'layouts/feature/index.mjs': [path.join(SBX, 'layouts/feature/index.mjs'), (s) => s.replace("'特集'", "'特集'") + '\n// touched\n'],
  'scripts/lib/compose.mjs (build logic)': [path.join(SBX, 'scripts/lib/compose.mjs'), (s) => `${s}\n// touched\n`],
  'scripts/lib/metrics.mjs (measure logic)': [path.join(SBX, 'scripts/lib/metrics.mjs'), (s) => `${s}\n// touched\n`],
  'notes/ (expected: ignored)': [path.join(dir, 'notes/README.md'), (s) => `${s}\nmemo\n`],
};
const imgFile = path.join(dir, 'images/tide-1.jpg');
out.stale = {};
const restoreAll = () => { run('build.mjs', id); run('render-pages.mjs', id); };
for (const [name, [f, fn]] of Object.entries(files)) {
  const orig = fs.readFileSync(f, 'utf8');
  fs.writeFileSync(f, fn(orig));
  const res = run('preflight.mjs', id);
  out.stale[name] = { P10_after_source_change: P10(res), exit: res.status };
  fs.writeFileSync(f, orig);
}
{
  const orig = fs.readFileSync(imgFile);
  await sharp(orig).modulate({ brightness: 0.5 }).jpeg().toFile(imgFile + '.tmp'); fs.renameSync(imgFile + '.tmp', imgFile);
  const res = run('preflight.mjs', id);
  out.stale['image bytes (tide-1.jpg)'] = { P10_after_source_change: P10(res), exit: res.status };
  fs.writeFileSync(imgFile, orig);
}
// build-only (no render) -> metrics/PNG staleness
fs.appendFileSync(path.join(dir, 'articles/editors-note.md'), '\n追記。\n');
run('build.mjs', id);
const res2 = run('preflight.mjs', id);
out.stale['article changed, build run, render NOT run'] = { P10: P10(res2), P16_render_current: P16(res2), exit: res2.status };
console.log(JSON.stringify(out, null, 1));
fs.writeFileSync(path.join(path.dirname(new URL(import.meta.url).pathname), '../evidence/D-stale-repro.json'), JSON.stringify(out, null, 1));

// RC1 adversarial harness. Runs mutations in a SANDBOX COPY of publishing-studio (never the repo).
// usage: SBX=/path/to/sandbox/publishing-studio node adversarial.mjs [caseId ...]
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import sharp from 'sharp';
import * as yaml from 'js-yaml';

const SBX = process.env.SBX;
const base = path.join(SBX, 'issues/test-issue-01');
const run = (script, ...args) => spawnSync(process.execPath, [path.join(SBX, 'scripts', script), ...args], { encoding: 'utf8', timeout: 175000, env: process.env });
const rd = (d, f) => fs.readFileSync(path.join(d, f), 'utf8');
const wr = (d, f, s) => fs.writeFileSync(path.join(d, f), s);
const ymod = (d, f, fn) => { const o = yaml.load(rd(d, f)); fn(o); wr(d, f, yaml.dump(o, { lineWidth: 200 })); };
const art = (d, id, fn) => { const f = `articles/${id}.md`; const m = rd(d, f).match(/^---\n([\s\S]*?)\n---\n?([\s\S]*)$/); const meta = yaml.load(m[1]); const r = fn(meta, m[2]) ?? {}; wr(d, f, `---\n${yaml.dump(r.meta ?? meta, { lineWidth: 400 })}---\n${r.body ?? m[2]}`); };
const img = (d, f, w, h, c = '#4a6a88') => sharp({ create: { width: w, height: h, channels: 3, background: c } }).jpeg({ quality: 70 }).toFile(path.join(d, 'images', f));

const cases = {
  '01-long-title': { exp: 'validate/preflight should flag or layout should contain a very long headline without collision', mut: (d) => { for (const id of ['harbor-theater', 'interview-hamabe']) art(d, id, (m) => { m.title = 'とても長い見出しが一つの記事に付けられてしまった場合でもレイアウトは崩れてはならない'.repeat(2); }); } },
  '02-short-body': { exp: 'warnings (TEXT_PAGE_EMPTY/SPARSE); build ok', mut: (d) => { art(d, 'night-road', () => ({ body: '短い。\n' })); art(d, 'harbor-theater', () => ({ body: '短い本文。\n' })); } },
  '03-long-body': { exp: 'TEXT_MAY_OVERFLOW warning; preflight FAIL on clipped text', mut: (d) => { art(d, 'harbor-theater', (m, b) => ({ body: `${b}\n${b}\n${b}` })); } },
  '04-no-image': { exp: 'clear validation error (MISSING_INPUT)', mut: (d) => { art(d, 'harbor-theater', (m) => { m.assets = []; }); art(d, 'cover', (m) => { m.assets = []; }); } },
  '05-missing-image': { exp: 'MISSING_ASSET error', mut: (d) => { art(d, 'harbor-theater', (m) => { m.assets = [{ image: 'nonexistent.jpg', role: 'hero' }]; }); } },
  '06-extreme-portrait': { exp: 'builds; extreme crop visible; preflight should warn about aspect/crop or ppi', mut: async (d) => { await img(d, 'stage-inline.jpg', 300, 6000); await img(d, 'portrait-hamabe.jpg', 200, 8000); } },
  '07-extreme-landscape': { exp: 'builds; extreme crop; low ppi flagged (hero 6000x200 on a 308mm spread is fine px-wise but 200px high)', mut: async (d) => { await img(d, 'harbor-hero.jpg', 6000, 200); await img(d, 'tide-2.jpg', 6000, 150); } },
  '08-no-caption': { exp: 'validate warning; preflight FAIL P05', mut: (d) => { ymod(d, 'captions/captions.yaml', (o) => { delete o['stage-inline.jpg']; delete o['harbor-hero.jpg']; }); } },
  '09-long-caption': { exp: 'long captions must not overflow/clip silently', mut: (d) => { ymod(d, 'captions/captions.yaml', (o) => { o['tide-1.jpg'].caption = '非常に長いキャプション。'.repeat(40); o['stage-inline.jpg'].caption = '非常に長いキャプション。'.repeat(40); o['harbor-hero.jpg'].caption = '非常に長いキャプション。'.repeat(40); }); } },
  '10-unplaced-article': { exp: 'ARTICLE_NOT_PLACED error, all.mjs exits non-zero', mut: (d) => { ymod(d, 'flatplan.yaml', (o) => { o.pages = o.pages.filter((e) => e.article !== 'night-road'); }); } },
  '11-duplicate-page': { exp: 'FLATPLAN_OVERLAP + FLATPLAN_GAP', mut: (d) => { ymod(d, 'flatplan.yaml', (o) => { o.pages.find((e) => e.pages[0] === 6).pages = [7]; }); } },
  '12-spread-parity': { exp: 'SPREAD_PARITY error', mut: (d) => { ymod(d, 'flatplan.yaml', (o) => { o.pages.find((e) => e.layout === 'photo-essay').pages = [11, 12]; }); } },
  '13a-pages-20': { exp: 'FLATPLAN_GAP errors', mut: (d) => { ymod(d, 'issue.yaml', (o) => { o.pages = 20; }); } },
  '13b-pages-12': { exp: 'FLATPLAN_RANGE errors', mut: (d) => { ymod(d, 'issue.yaml', (o) => { o.pages = 12; }); } },
  '14-theme-font-12pt': { exp: 'build ok; text overflow must be detected (P19 FAIL) or capacity estimate must adapt', mut: (d) => { ymod(d, 'issue.yaml', (o) => { o.theme_overrides = { '--fs-body': '12pt' }; }); } },
  '15-theme-margins': { exp: 'safe-area / overflow / spine issues detected', mut: (d) => { ymod(d, 'issue.yaml', (o) => { o.theme_overrides = { '--margin-inner': '30mm', '--margin-outer': '4mm', '--margin-top': '8mm', '--margin-bottom': '8mm' }; }); } },
  '20-blank-page': { exp: 'blank page FAIL (P17) unless intentional', mut: (d) => { wr(d, 'articles/blank.md', '---\nid: blank\ntitle: 空\ntype: essay\npriority: 3\ntarget_pages: 1\nin_contents: false\n---\n'); art(d, 'colophon', (m) => { m.status = 'spiked'; }); ymod(d, 'flatplan.yaml', (o) => { const e = o.pages.find((x) => x.pages[0] === 15); e.article = 'blank'; e.layout = 'essay'; e.variant = 'body'; }); } },
  '21-special-filename': { exp: 'images with spaces / Japanese / # in the name should work (or be rejected clearly)', mut: (d) => { fs.renameSync(path.join(d, 'images/tide-3.jpg'), path.join(d, 'images/タイド 3 #a.jpg')); ymod(d, 'captions/captions.yaml', (o) => { o['タイド 3 #a.jpg'] = o['tide-3.jpg']; delete o['tide-3.jpg']; }); ymod(d, 'images/images.yaml', (o) => { o['タイド 3 #a.jpg'] = o['tide-3.jpg']; delete o['tide-3.jpg']; }); art(d, 'photo-tide', (m) => { m.assets = m.assets.map((a) => (a.image === 'tide-3.jpg' ? { ...a, image: 'タイド 3 #a.jpg' } : a)); }); } },
  '22-raw-html': { exp: 'raw HTML/script in a manuscript must not execute or restyle the page', mut: (d) => { art(d, 'editors-note', (m, b) => ({ body: `${b}\n<style>.page{display:none!important}</style>\n<script>document.title='PWNED'</script>\n<img src=x onerror="document.body.dataset.pwn=1">\n` })); } },
  '23-article-type-mismatch': { exp: 'semantic check: essay article placed in interview-body / feature in cover', mut: (d) => { ymod(d, 'flatplan.yaml', (o) => { const e = o.pages.find((x) => x.pages[0] === 14); e.layout = 'interview-body'; e.variant = 'qa'; }); } },
  '24-duplicate-article-id': { exp: 'duplicate article ids must be an error', mut: (d) => { fs.copyFileSync(path.join(d, 'articles/editors-note.md'), path.join(d, 'articles/editors-note-copy.md')); } },
};

const only = process.argv.slice(2);
const results = {};
for (const [id, c] of Object.entries(cases)) {
  if (only.length && !only.some((o) => id.startsWith(o))) continue;
  const iid = `adv-${id}`;
  const dir = path.join(SBX, 'issues', iid);
  fs.rmSync(dir, { recursive: true, force: true });
  fs.cpSync(base, dir, { recursive: true });
  fs.rmSync(path.join(dir, 'reviews'), { recursive: true, force: true });
  const r = { expected: c.exp };
  try {
    await c.mut(dir);
    const v = run('validate.mjs', iid, '--json');
    try { r.validate = { exit: v.status, findings: JSON.parse(v.stdout).filter((f) => f.level !== 'info').map((f) => `${f.level}:${f.code}${f.where ? `@${f.where}` : ''}`) }; } catch { r.validate = { exit: v.status, raw: (v.stdout + v.stderr).slice(0, 300) }; }
    const a = run('all.mjs', iid);
    r.all_exit = a.status;
    r.all_tail = (a.stdout + a.stderr).split('\n').filter((l) => /FAIL|failed|ERROR|Error/.test(l)).slice(0, 4).join(' | ').slice(0, 400);
    const pf = path.join(SBX, 'output', iid, 'preflight.json');
    if (fs.existsSync(pf)) { const j = JSON.parse(fs.readFileSync(pf, 'utf8')); r.preflight = { verdict: j.verdict, nonpass: j.items.filter((i) => !['PASS', 'MANUAL CHECK'].includes(i.status)).map((i) => `${i.status} ${i.code} ${i.detail.slice(0, 110)}`) }; }
  } catch (e) { r.harness_error = e.message; }
  results[id] = r;
  console.log(`\n### ${id}\n${JSON.stringify(r, null, 1)}`);
}
const EVIDENCE = process.env.EVIDENCE_DIR ?? path.join(path.dirname(new URL(import.meta.url).pathname), '../evidence'); // RC2 sets EVIDENCE_DIR so RC1 evidence is never overwritten
fs.mkdirSync(EVIDENCE, { recursive: true });
fs.writeFileSync(path.join(EVIDENCE, `F-adversarial${only.length ? '-' + only.join('_') : ''}.json`), JSON.stringify(results, null, 1));

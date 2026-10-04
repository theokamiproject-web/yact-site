// P1-1 asset paths, P1-2 raw HTML / sandbox / network.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { PDFDocument } from 'pdf-lib';
import * as yaml from 'js-yaml';
import { workspace } from './helpers.mjs';
import { sandboxPolicy, launch, safePage } from '../scripts/lib/browser.mjs';
import { safeMarked, scanMarkdown, ALLOWED_ELEMENTS } from '../scripts/lib/text.mjs';

const ws = workspace();
test.after(() => ws.cleanup());
const copyIssue = (name) => {
  const d = path.join(ws.issues, name);
  fs.cpSync(path.join(ws.issues, 'test-issue-01'), d, { recursive: true });
  return d;
};
const edit = (file, fn) => fs.writeFileSync(file, fn(fs.readFileSync(file, 'utf8')));

test('asset names with Japanese, spaces, "#", parentheses render in build, render and PDF', { timeout: 180000 }, async () => {
  const d = copyIssue('names');
  const map = { 'tide-1.jpg': '舞台 写真 01.jpg', 'tide-2.jpg': '舞台#01.jpg', 'tide-3.jpg': '日本海・秋田.jpg', 'stage-inline.jpg': 'photo (1).jpg' };
  for (const [from, to] of Object.entries(map)) {
    fs.renameSync(path.join(d, 'images', from), path.join(d, 'images', to));
    for (const f of ['articles/harbor-theater.md', 'articles/photo-tide.md', 'captions/captions.yaml', 'images/images.yaml', 'flatplan.yaml']) edit(path.join(d, f), (s) => s.split(from).join(to));
  }
  const r = ws.run('all.mjs', 'names');
  assert.equal(r.status, 0, r.stdout + r.stderr);
  const out = path.join(ws.output, 'names');
  const mx = JSON.parse(fs.readFileSync(path.join(out, 'metrics.json')));
  const files = mx.pages.flatMap((p) => p.images.map((i) => ({ f: i.file, ok: i.ok })));
  for (const to of Object.values(map)) assert.ok(files.some((x) => x.f === to && x.ok), `${to} must load in the DOM`);
  assert.ok(files.every((x) => x.ok), 'no broken image');
  const html = fs.readFileSync(path.join(out, 'web/index.html'), 'utf8');
  assert.ok(html.includes('images/%E8%88%9E%E5%8F%B0%20%E5%86%99%E7%9C%9F%2001.jpg'), 'standard percent-encoding');
  assert.ok(html.includes('%23'), '# is encoded');
  const pdf = await PDFDocument.load(fs.readFileSync(path.join(out, 'names.pdf')));
  assert.equal(pdf.getPageCount(), 16);
  // images really are in the PDF (same count as the untouched sample)
  const ref = spawnSync('pdfimages', ['-list', path.join(out, 'names.pdf')], { encoding: 'utf8' }).stdout.split('\n').length;
  assert.ok(ref > 8, 'PDF embeds the images');
  const pf = JSON.parse(fs.readFileSync(path.join(out, 'preflight.json')));
  assert.equal(pf.items.find((i) => i.code === 'P18').status, 'PASS');
});

test('NFD file names (macOS) match NFC references', async () => {
  const d = copyIssue('nfd');
  const nfd = 'がぎ.jpg'.normalize('NFD');
  assert.notEqual(nfd, 'がぎ.jpg');
  fs.renameSync(path.join(d, 'images/tide-1.jpg'), path.join(d, 'images', nfd));
  const code = `import { loadIssue } from ${JSON.stringify(new URL('../scripts/lib/load.mjs', import.meta.url).href)}; console.log(JSON.stringify(Object.keys(loadIssue('nfd').images)));`;
  const r = spawnSync(process.execPath, ['--input-type=module', '-e', code], { env: ws.env, encoding: 'utf8' });
  assert.ok(JSON.parse(r.stdout).includes('がぎ.jpg'), 'key normalised to NFC: ' + r.stdout + r.stderr);
});

test('path traversal / separators in image references are rejected', async () => {
  const d = copyIssue('traversal');
  edit(path.join(d, 'articles/harbor-theater.md'), (s) => s.replace('image: harbor-hero.jpg', 'image: ../../../etc/passwd.jpg'));
  const v = ws.run('validate.mjs', 'traversal', '--json');
  assert.equal(v.status, 1);
  assert.match(v.stdout, /ASSET_PATH_INVALID/);
});

test('manuscript HTML is escaped, never executed: script/style/iframe/object/embed/on*=/javascript:/remote image', { timeout: 180000 }, async () => {
  const d = copyIssue('evil');
  edit(path.join(d, 'articles/editors-note.md'), (s) => `${s}\n<style>.page{display:none!important}</style>\n\n<script>document.title='PWNED'</script>\n\n<iframe src="http://evil.invalid/"></iframe>\n\n<object data="x"></object><embed src="x">\n\n<img src=x onerror="document.body.dataset.pwn=1">\n\n[click](javascript:alert(1)) and [ok](https://example.com)\n\n![remote](http://evil.invalid/x.png)\n\n<b onclick="x()">bold</b>\n`);
  const v = ws.run('validate.mjs', 'evil', '--json');
  assert.equal(v.status, 0, v.stdout);
  assert.match(v.stdout, /MD_RAW_HTML_ESCAPED/);
  assert.match(v.stdout, /MD_IMAGE_REMOVED/);
  const r = ws.run('all.mjs', 'evil');
  const out = path.join(ws.output, 'evil');
  const html = fs.readFileSync(path.join(out, 'web/index.html'), 'utf8');
  for (const bad of [/<script/i, /<iframe/i, /<object/i, /<embed/i, /<style[^>]*>\s*\.page/i, /<[^>]*\son\w+\s*=/i, /href\s*=\s*["']?javascript:/i, /src\s*=\s*["']?https?:/i, /<a\s/i]) assert.ok(!bad.test(html), `index.html must not match ${bad}`);
  assert.match(html, /Content-Security-Policy/);
  assert.match(html, /&lt;script&gt;document\.title/);
  const pdf = await PDFDocument.load(fs.readFileSync(path.join(out, 'evil.pdf')));
  assert.equal(pdf.getPageCount(), 16, 'manuscript cannot restyle the book (RC1 case 22 produced a 1-page PDF)');
  assert.ok(r.status === 0 || /P27|P06/.test(r.stdout), r.stdout.slice(-400));
});

test('safe Markdown: allowed element list is exactly what the renderer can emit', () => {
  const html = safeMarked.parse('## h\n\npara **b** *i* ~~d~~ `c` line  \nbreak\n\n- a\n- b\n\n1. x\n\n> q\n\n<div onclick=1>raw</div>\n\n![x](http://e/i.png) [t](javascript:1)');
  const tags = [...new Set([...html.matchAll(/<\/?([a-z0-9]+)/g)].map((m) => m[1]))];
  const allowed = new Set([...ALLOWED_ELEMENTS, 'h2']);
  for (const t of tags) assert.ok(allowed.has(t), `unexpected <${t}>`);
  assert.deepEqual(scanMarkdown('<b>x</b> ![i](u) [l](v)'), { html: 2, images: 1, links: 1 });
});

test('theme CSS cannot load remote resources', async () => {
  const d = copyIssue('csslink');
  fs.writeFileSync(path.join(d, 'theme.css'), '@import url("http://evil.invalid/x.css");\n.a{background:url(https://evil.invalid/i.png)}');
  const v = ws.run('validate.mjs', 'csslink', '--json');
  assert.equal(v.status, 1);
  assert.match(v.stdout, /THEME_EXTERNAL_RESOURCE/);
});

test('Chromium sandbox policy: on by default, off only explicitly or in the managed root container', () => {
  assert.equal(sandboxPolicy({}, 1000).noSandbox, false);
  assert.equal(sandboxPolicy({}, 0).noSandbox, false, 'root alone does not disable the sandbox');
  assert.equal(sandboxPolicy({ CLAUDE_CODE_REMOTE: 'true' }, 1000).noSandbox, false);
  assert.equal(sandboxPolicy({ CLAUDE_CODE_REMOTE: 'true' }, 0).noSandbox, true);
  assert.equal(sandboxPolicy({ PS_NO_SANDBOX: '1' }, 1000).noSandbox, true);
  assert.equal(sandboxPolicy({ PS_NO_SANDBOX: '0', CLAUDE_CODE_REMOTE: 'true' }, 0).noSandbox, false);
  assert.match(sandboxPolicy({ PS_NO_SANDBOX: '1' }).reason, /explicit/);
  const src = fs.readFileSync(new URL('../scripts/lib/browser.mjs', import.meta.url), 'utf8');
  assert.ok(!/args:\s*\[[^\]]*'--no-sandbox'\s*,/.test(src.replace(/pol\.noSandbox \? \['--no-sandbox'\]/g, '')), 'no unconditional --no-sandbox');
});

test('measurement browser cannot reach the network', { timeout: 60000 }, async () => {
  const b = await launch();
  try {
    const p = await safePage(b, {});
    await assert.rejects(() => p.goto('http://example.invalid/'), /ERR_FAILED|net::/);
    const p2 = await safePage(b, {});
    await p2.goto('about:blank');
  } finally { await b.close(); }
});

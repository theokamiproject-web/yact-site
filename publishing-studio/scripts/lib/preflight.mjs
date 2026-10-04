// Preflight: PASS | WARNING | FAIL | MANUAL CHECK. Never reports what it could not verify as passed.
import fs from 'node:fs';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import sharp from 'sharp';
import { PDFDocument } from 'pdf-lib';
import { outDir, issueDir } from './paths.mjs';
import { loadIssue } from './load.mjs';
import { validateModel } from './validate-model.mjs';
import { sourceHash } from './build.mjs';
import { loadReviews, openSevere } from './critic.mjs';
import { issueBoundary, overrideRequested } from './boundary.mjs';

const exec = promisify(execFile);
const MM = 25.4 / 72;
const mm = (pt) => +(pt * MM).toFixed(2);

export async function runPreflight(id) {
  const model = loadIssue(id);
  const out = outDir(id);
  const items = [];
  const add = (code, check, status, detail, pages = []) => items.push({ code, check, status, detail, pages });
  const findings = await validateModel(model);
  const by = (...codes) => findings.filter((f) => codes.includes(f.code));
  const group = (code, check, codes, { warnAs = 'WARNING', okText }) => {
    const errs = by(...codes).filter((f) => f.level === 'error');
    const warns = by(...codes).filter((f) => f.level === 'warning');
    const fmt = (l) => l.slice(0, 6).map((f) => f.message).join(' / ') + (l.length > 6 ? ` (+${l.length - 6})` : '');
    if (errs.length) add(code, check, 'FAIL', fmt(errs));
    else if (warns.length) add(code, check, warnAs, fmt(warns));
    else add(code, check, 'PASS', okText);
  };

  // ---- publishing boundary
  {
    const prevBuild = fs.existsSync(path.join(out, 'build.json')) ? JSON.parse(fs.readFileSync(path.join(out, 'build.json'), 'utf8')) : null;
    const b = issueBoundary(model.dir, { allowPublicTree: overrideRequested({}) || !!prevBuild?.boundary_override });
    if (!b.findings.length) add('P00', 'publishing boundary (private source not in the public tree)', 'PASS', `issue is ${b.class}; not tracked/ignorable as required`);
    else add('P00', 'publishing boundary (private source not in the public tree)', b.overridden ? 'WARNING' : 'FAIL', `${b.overridden ? 'OVERRIDDEN by the user: ' : ''}${b.findings.map((f) => f.code).join(', ')}`);
  }

  // ---- model / flatplan
  const modelCodes = new Set(['FLATPLAN_GAP', 'FLATPLAN_OVERLAP', 'FLATPLAN_RANGE', 'SPAN_MISMATCH', 'SPREAD_PARITY', 'SPREAD_NOT_CONSECUTIVE', 'PAGES_NOT_MULTIPLE_OF_4', 'PAGES_ODD', 'SCHEMA', 'FILE_MISSING', 'YAML_PARSE', 'ISSUE_MISSING', 'MISSING_INPUT', 'ARTICLE_NO_FRONTMATTER', 'ARTICLE_DUPLICATE']);
  group('P01', 'flatplan / schema validity', [...modelCodes], { okText: 'issue.yaml, editorial.yaml, flatplan.yaml and articles validate; every page 1..N is placed exactly once' });
  group('P02', 'article not placed', ['ARTICLE_NOT_PLACED', 'ARTICLE_MISSING', 'TEXT_NOT_PLACED'], { okText: 'every non-spiked article is placed; every body text has a text layout' });
  group('P03', 'unknown layout / variant', ['UNKNOWN_LAYOUT', 'UNKNOWN_VARIANT'], { okText: 'all layouts and variants exist in the registry' });
  group('P04', 'missing asset', ['MISSING_ASSET'], { okText: 'all referenced images exist in images/' });
  group('P05', 'missing caption', ['MISSING_CAPTION'], { warnAs: 'FAIL', okText: 'every captioned image has a caption' });
  group('P06', 'editorial fit (target_pages / text volume)', ['TARGET_PAGES', 'TEXT_MAY_OVERFLOW', 'TEXT_PAGE_EMPTY', 'TEXT_PAGE_SPARSE'], { okText: 'article page counts match target_pages; text volume fits estimated frames' });
  const known = new Set([...modelCodes, 'ARTICLE_NOT_PLACED', 'ARTICLE_MISSING', 'TEXT_NOT_PLACED', 'UNKNOWN_LAYOUT', 'UNKNOWN_VARIANT', 'MISSING_ASSET', 'MISSING_CAPTION', 'TARGET_PAGES', 'TEXT_MAY_OVERFLOW', 'TEXT_PAGE_EMPTY', 'TEXT_PAGE_SPARSE', 'IMAGE_UNUSED']);
  const other = findings.filter((f) => !known.has(f.code) && f.level !== 'info');
  if (other.length) add('P07', 'other model findings', other.some((f) => f.level === 'error') ? 'FAIL' : 'WARNING', other.slice(0, 6).map((f) => f.message).join(' / '));

  // ---- expected vs actual page count
  const fatalModel = findings.some((f) => f.level === 'error');
  const flatMax = Math.max(0, ...(model.flatplan?.pages ?? []).flatMap((e) => e.pages ?? []));
  add('P08', 'expected page count', model.issue && flatMax === model.issue.pages ? 'PASS' : 'FAIL', `issue.pages=${model.issue?.pages}, flatplan max page=${flatMax}`);

  const pdfPath = path.join(out, `${id}.pdf`);
  const buildFile = path.join(out, 'build.json');
  const mxFile = path.join(out, 'metrics.json');
  const build = fs.existsSync(buildFile) ? JSON.parse(fs.readFileSync(buildFile, 'utf8')) : null;
  const mx = fs.existsSync(mxFile) ? JSON.parse(fs.readFileSync(mxFile, 'utf8')) : null;
  const hash = fatalModel ? null : sourceHash(model);

  let pdf = null;
  if (!fs.existsSync(pdfPath) || !build) {
    add('P09', 'actual PDF page count', 'FAIL', `no PDF/build.json. Run: npm run publication:build -- ${id}`);
  } else {
    pdf = await PDFDocument.load(fs.readFileSync(pdfPath));
    const n = pdf.getPageCount();
    add('P09', 'actual PDF page count', n === model.issue.pages ? 'PASS' : 'FAIL', `PDF has ${n} page(s), expected ${model.issue.pages}${n !== model.issue.pages ? ' (a page overflowed or a section was dropped)' : ''}`);
    add('P10', 'PDF is current', hash && build.source_hash === hash ? 'PASS' : 'FAIL', hash ? (build.source_hash === hash ? 'PDF matches current sources' : 'sources changed after the PDF was built; rebuild') : 'cannot hash sources (model invalid)');
  }

  if (pdf) {
    const issue = model.issue;
    const boxes = pdf.getPages().map((p) => ({ trim: p.getTrimBox(), bleed: p.getBleedBox(), media: p.getMediaBox() }));
    const [W, H] = [issue.width / MM, issue.height / MM];
    const badSize = boxes.map((b, i) => (Math.abs(b.trim.width - W) > 0.6 || Math.abs(b.trim.height - H) > 0.6 ? i + 1 : 0)).filter(Boolean);
    add('P11', 'page size (TrimBox)', badSize.length ? 'FAIL' : 'PASS', badSize.length ? `TrimBox differs from ${issue.width}x${issue.height}mm on p${badSize.join(',')} (found ${mm(boxes[badSize[0] - 1].trim.width)}x${mm(boxes[badSize[0] - 1].trim.height)}mm)` : `all pages ${issue.width}x${issue.height}mm`);
    if (issue.bleed === 0) add('P12', 'bleed', 'MANUAL CHECK', 'issue.bleed is 0: confirm with the printer that no bleed is required');
    else {
      const bad = boxes.map((b, i) => {
        const d = [b.trim.x - b.bleed.x, b.trim.y - b.bleed.y, b.bleed.x + b.bleed.width - (b.trim.x + b.trim.width), b.bleed.y + b.bleed.height - (b.trim.y + b.trim.height)];
        return d.some((v) => Math.abs(v - issue.bleed / MM) > 0.6) ? i + 1 : 0;
      }).filter(Boolean);
      add('P12', 'bleed (BleedBox)', bad.length ? 'FAIL' : 'PASS', bad.length ? `BleedBox is not ${issue.bleed}mm outside TrimBox on p${bad.join(',')}` : `BleedBox = TrimBox + ${issue.bleed}mm on all sides`);
    }
    const hasMarksArea = boxes.every((b) => b.media.width > b.bleed.width + 10);
    if (build.marks) add('P13', 'crop marks', hasMarksArea ? 'PASS' : 'FAIL', hasMarksArea ? 'MediaBox is larger than BleedBox (crop-mark area present). Mark content itself is not inspected' : 'built with --marks but MediaBox has no margin for marks');
    else add('P13', 'crop marks', 'MANUAL CHECK', 'built without crop marks. Ask the printer whether they add them; rebuild with: npm run publication:build -- ' + id + ' --marks');

    // fonts
    try {
      const { stdout } = await exec('pdffonts', [pdfPath]);
      const rows = stdout.split('\n').slice(2).map((l) => l.match(/^(\S+)\s+(.+?)\s{2,}(\S+)\s+(yes|no)\s+(yes|no)\s+(yes|no)\s/)).filter(Boolean).map((m) => ({ name: m[1], type: m[2].trim(), emb: m[4] }));
      if (!rows.length) throw new Error('no font rows parsed');
      const notEmb = rows.filter((r) => r.emb !== 'yes');
      const t3 = rows.filter((r) => r.type === 'Type 3');
      if (notEmb.length) add('P14', 'fonts embedded', 'FAIL', `not embedded: ${[...new Set(notEmb.map((r) => r.name))].join(', ')}`);
      else if (t3.length) add('P14', 'fonts embedded', 'WARNING', `all ${rows.length} font object(s) embedded, but ${t3.length} are Type 3 (Chromium output). Some printers' preflight rejects Type 3; confirm with the printer`);
      else add('P14', 'fonts embedded', 'PASS', `${rows.length} font object(s), all embedded`);
    } catch {
      add('P14', 'fonts embedded', 'MANUAL CHECK', 'pdffonts (poppler-utils) not available; embedding not verified');
    }
  }

  // missing fonts (system) for the theme's declared first-choice families
  if (mx?.tokens) {
    let installed = null;
    try { installed = (await exec('fc-list', [':', 'family'])).stdout; } catch { /* fc-list missing */ }
    if (installed === null) add('P15', 'missing font', 'MANUAL CHECK', 'fc-list not available; theme fonts not checked');
    else {
      const wanted = ['--font-body', '--font-heading', '--font-display'].map((k) => [k, mx.tokens[k]?.split(',')[0]?.replace(/["']/g, '').trim()]).filter(([, v]) => v);
      const missing = wanted.filter(([, f]) => !installed.toLowerCase().includes(f.toLowerCase()));
      add('P15', 'missing font', missing.length ? 'WARNING' : 'PASS', missing.length ? `first-choice font not installed (a fallback was used): ${missing.map(([k, f]) => `${k}=${f}`).join(', ')}` : `first-choice fonts present: ${[...new Set(wanted.map(([, f]) => f))].join(', ')}`);
    }
  }

  // ---- DOM metrics based
  const mxOk = mx && hash && mx.source_hash === hash;
  if (!mx) {
    for (const [c, k] of [['P16', 'blank pages'], ['P17', 'broken images'], ['P18', 'overflow / text clipping'], ['P19', 'page numbers'], ['P20', 'safe area'], ['P21', 'image resolution'], ['P22', 'bleed coverage of full-bleed images']]) add(c, k, 'MANUAL CHECK', `no metrics.json (not verified). Run: npm run publication:render -- ${id}`);
  } else {
    if (!mxOk) add('P16', 'render is current', 'FAIL', 'metrics.json/page PNGs are older than the sources; re-run render');
    const pg = mx.pages;
    const blank = pg.filter((m) => !m.intentional_blank && ((m.text_chars === 0 && m.image_ratio === 0 && !m.bg_fill) || (m.pixel_stddev ?? 99) < 0.8 && m.text_chars === 0));
    add('P17', 'blank pages', blank.length ? 'FAIL' : 'PASS', blank.length ? `blank (no text/image, uniform pixels): p${blank.map((m) => m.n).join(',')}. Set intentional_blank: true in the flatplan if deliberate` : `no blank pages (DOM + rendered-pixel check, ${pg.length}p)`, blank.map((m) => m.n));
    const broken = pg.flatMap((m) => m.images.filter((i) => !i.ok).map((i) => ({ n: m.n, f: i.file })));
    add('P18', 'broken images', broken.length ? 'FAIL' : 'PASS', broken.length ? broken.map((b) => `p${b.n} ${b.f}`).join(', ') : `${pg.reduce((a, m) => a + m.images.length, 0)} placed image(s) decoded`, broken.map((b) => b.n));
    const ov = pg.filter((m) => m.overflow.length || m.outside.length);
    add('P19', 'overflow / text clipping', ov.length ? 'FAIL' : 'PASS', ov.length ? ov.map((m) => `p${m.n}: ${[...m.overflow.map((o) => `${o.el} clipped`), ...m.outside.map((o) => o.kind)].join(', ')}`).join(' / ') : 'no clipped text frames, nothing outside the trim box', ov.map((m) => m.n));
    const noFolio = pg.filter((m) => m.chrome !== 'none' && !m.folio);
    const wrong = pg.filter((m) => m.folio && m.folio.text !== String(m.n));
    const seen = {};
    for (const m of pg) if (m.folio) (seen[m.folio.text] ??= []).push(m.n);
    const dup = Object.entries(seen).filter(([, v]) => v.length > 1);
    const pnProblems = [...noFolio.map((m) => `p${m.n} missing`), ...wrong.map((m) => `p${m.n} shows "${m.folio.text}"`), ...dup.map(([t, v]) => `"${t}" duplicated on p${v.join(',')}`)];
    add('P20', 'page numbers (missing / duplicate / wrong)', pnProblems.length ? 'FAIL' : 'PASS', pnProblems.length ? pnProblems.join('; ') : `${pg.filter((m) => m.folio).length} folio(s) correct and unique; ${pg.filter((m) => m.chrome === 'none').length} page(s) intentionally without folio`);
    const safe = pg.filter((m) => m.safe_violations);
    add('P21', 'safe area (text ≥ 5mm from trim)', safe.length ? 'WARNING' : 'PASS', safe.length ? `text inside the safe margin on p${safe.map((m) => m.n).join(',')}` : 'all text clear of the trim edge', safe.map((m) => m.n));
    const imgs = pg.flatMap((m) => m.images.map((i) => ({ ...i, n: m.n }))).filter((i) => i.ppi > 0);
    const lo = imgs.filter((i) => i.ppi < 100), mid = imgs.filter((i) => i.ppi >= 100 && i.ppi < 200);
    const minPpi = imgs.length ? Math.min(...imgs.map((i) => i.ppi)) : null;
    add('P22', 'image resolution (effective ppi at placed size)', lo.length ? 'FAIL' : mid.length ? 'WARNING' : 'PASS', imgs.length ? `min ${minPpi}ppi (DOM-derived; ≥200 ok, <100 fail)${lo.length ? `; <100: ${lo.map((i) => `p${i.n} ${i.file} ${i.ppi}`).join(', ')}` : ''}${mid.length ? `; <200: ${mid.map((i) => `p${i.n} ${i.file} ${i.ppi}`).join(', ')}` : ''}` : 'no images');
    const bs = pg.filter((m) => m.bleed_short?.length);
    add('P23', 'full-bleed images extend into the bleed', bs.length ? 'WARNING' : 'PASS', bs.length ? bs.map((m) => `p${m.n}: ${m.bleed_short.map((b) => `${b.file} (${b.edges.join('/')})`).join(', ')}`).join(' / ') : 'images touching the trim edge also cover the bleed (spine edges excluded)', bs.map((m) => m.n));
  }

  // ---- colour
  const spaces = {};
  for (const [f, p] of Object.entries(model.images)) {
    try { const md = await sharp(p).metadata(); (spaces[md.space ?? 'unknown'] ??= []).push(f); } catch { (spaces.undecodable ??= []).push(f); }
  }
  if (spaces.undecodable) add('P24', 'image files decodable', 'FAIL', `cannot decode: ${spaces.undecodable.join(', ')}`);
  const rgb = Object.entries(spaces).filter(([s]) => ['srgb', 'rgb', 'b-w', 'unknown'].includes(s)).flatMap(([, v]) => v);
  const cmyk = spaces.cmyk ?? [];
  add('P25', 'image colour space (RGB/CMYK)', rgb.length ? 'WARNING' : cmyk.length ? 'PASS' : 'PASS', `${rgb.length} RGB/grey source image(s), ${cmyk.length} CMYK. v0.1 does not convert colours; the printer (or a later step) must convert RGB→CMYK${rgb.length ? `: ${rgb.slice(0, 5).join(', ')}${rgb.length > 5 ? '…' : ''}` : ''}`);
  add('P26', 'PDF colour / PDF-X conformance', 'MANUAL CHECK', 'PDF is generated as RGB by Chromium. CMYK conversion, output intent and PDF/X conformance are NOT verified in v0.1; confirm with the printer\'s preflight');

  // ---- review gates
  const reviews = loadReviews(path.join(issueDir(id), 'reviews'));
  const complete = Object.values(reviews).filter((r) => r.meta.status === 'complete').length;
  const severe = openSevere(reviews);
  if (!Object.keys(reviews).length || !complete) add('P27', 'Publication Critic (blind/context/rereview)', 'MANUAL CHECK', 'critic reviews not completed. Run npm run publication:critic -- ' + id + ' and have publication-critic fill critic-*.md');
  else if (severe.length) add('P27', 'Publication Critic (blind/context/rereview)', 'FAIL', `open BLOCKER/HIGH: ${severe.map((f) => `${f.id}(${f.severity})`).join(', ')}`);
  else add('P27', 'Publication Critic (blind/context/rereview)', complete < 3 ? 'WARNING' : 'PASS', `${complete}/3 stages complete, no open BLOCKER/HIGH${complete < 3 ? '; rereview not done' : ''}`);
  const pr = path.join(issueDir(id), 'reviews', 'proofread.md');
  const prDone = fs.existsSync(pr) && /status:\s*complete/.test(fs.readFileSync(pr, 'utf8'));
  add('P28', 'Proofreader pass', prDone ? 'PASS' : 'MANUAL CHECK', prDone ? 'reviews/proofread.md is complete' : 'no completed reviews/proofread.md. Typos, notation and caption correspondence are not machine-verified');

  const count = (s) => items.filter((i) => i.status === s).length;
  const verdict = count('FAIL') ? 'FAIL' : count('WARNING') ? 'WARNING' : count('MANUAL CHECK') ? 'MANUAL CHECK' : 'PASS';
  return { issue: id, generated_at: new Date().toISOString(), verdict, counts: { PASS: count('PASS'), WARNING: count('WARNING'), FAIL: count('FAIL'), 'MANUAL CHECK': count('MANUAL CHECK') }, items };
}

export function preflightMarkdown(r) {
  const icon = { PASS: 'PASS', WARNING: 'WARNING', FAIL: 'FAIL', 'MANUAL CHECK': 'MANUAL CHECK' };
  const L = [`# Preflight — ${r.issue}`, '', `**${r.verdict}**　PASS ${r.counts.PASS} / WARNING ${r.counts.WARNING} / FAIL ${r.counts.FAIL} / MANUAL CHECK ${r.counts['MANUAL CHECK']}`, '', '> MANUAL CHECK = v0.1 では自動確認できない項目。確認済みではありません。', '', '| id | check | status | detail |', '|---|---|---|---|'];
  for (const i of r.items) L.push(`| ${i.code} | ${i.check} | **${icon[i.status]}** | ${i.detail.replace(/\|/g, '\\|')} |`);
  return L.join('\n') + '\n';
}

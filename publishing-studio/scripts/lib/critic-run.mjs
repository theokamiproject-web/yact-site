#!/usr/bin/env node
// Prepare the review pack + critic templates; with --check validate completed reviews and write critic-report.json.
import fs from 'node:fs';
import path from 'node:path';
import { outDir, issueDir, REPO_ROOT } from './paths.mjs';
import { loadIssue } from './load.mjs';
import { sourceHash } from './build.mjs';
import { analyzeRhythm, rhythmMarkdown, computeFingerprint } from './analysis.mjs';
import { loadRegistry } from './registry.mjs';
import { reviewTemplate, loadReviews, checkReviews, openSevere, isAuthored, archiveReviews, STAGES } from './critic.mjs';

const rel = (p) => path.relative(REPO_ROOT, p);

/**
 * Review files are an AUDIT RECORD, not build artifacts. They are created once from a template and never overwritten:
 * `reset` refuses when any stage holds authored work unless `force` is given, and `force` archives first.
 */
export async function prepareCritic(id, { reset = false, force = false, log = console.log } = {}) {
  const out = outDir(id);
  const reviewsDirEarly = path.join(issueDir(id), 'reviews');
  if (reset) {
    const authored = STAGES.map((s) => path.join(reviewsDirEarly, `critic-${s}.md`)).filter((f) => fs.existsSync(f) && isAuthored(fs.readFileSync(f, 'utf8')));
    if (authored.length && !force) throw new Error(`refusing --reset: ${authored.map((f) => path.basename(f)).join(', ')} contain review work (status/findings/scores). Reviews are an audit record. Re-run with --force to archive them to reviews/archive/<timestamp>/ and start from empty templates.`);
    if (authored.length) log(`  archived ${authored.length} review file(s) to ${rel(archiveReviews(reviewsDirEarly, STAGES.map((s) => path.join(reviewsDirEarly, `critic-${s}.md`)).concat(path.join(reviewsDirEarly, 'auto-findings.snapshot.json'))))}`);
  }
  const mxFile = path.join(out, 'metrics.json');
  if (!fs.existsSync(mxFile)) throw new Error(`no metrics.json. Run: npm run publication:render -- ${id}`);
  const model = loadIssue(id);
  const mx = JSON.parse(fs.readFileSync(mxFile, 'utf8'));
  const stale = mx.source_hash !== sourceHash(model);
  if (stale) log('  WARNING: output is stale (sources changed since the last render). Re-run build + render.');

  const reg = await loadRegistry();
  const rhythm = analyzeRhythm(model, mx, reg);
  const fingerprint = computeFingerprint(model, mx, rhythm);
  fs.writeFileSync(path.join(out, 'rhythm.json'), JSON.stringify(rhythm, null, 2));
  fs.writeFileSync(path.join(out, 'rhythm.md'), rhythmMarkdown(rhythm));
  fs.writeFileSync(path.join(out, 'fingerprint.json'), JSON.stringify({ issue: id, axes: fingerprint }, null, 2));

  // --- pack
  const pack = path.join(out, 'review-pack');
  fs.rmSync(pack, { recursive: true, force: true });
  const blind = path.join(pack, 'blind'), ctx = path.join(pack, 'context');
  fs.mkdirSync(path.join(blind, 'pages'), { recursive: true });
  fs.mkdirSync(path.join(blind, 'contact'), { recursive: true });
  fs.mkdirSync(ctx, { recursive: true });
  const pngs = fs.readdirSync(path.join(out, 'pages')).filter((f) => f.endsWith('.png'));
  for (const f of pngs) fs.copyFileSync(path.join(out, 'pages', f), path.join(blind, 'pages', f));
  for (const f of fs.readdirSync(path.join(out, 'contact'))) fs.copyFileSync(path.join(out, 'contact', f), path.join(blind, 'contact', f));
  const blindMetrics = rhythm.pages.map(({ n, text_chars, image_ratio, whitespace_ratio, intensity, text_occupancy, content_extent, headline_pt, body_pt }) => ({ n, text_chars, image_ratio, whitespace_ratio, intensity, text_occupancy, content_extent, headline_pt, body_pt }));
  fs.writeFileSync(path.join(blind, 'metrics.json'), JSON.stringify(blindMetrics, null, 2));
  fs.writeFileSync(path.join(blind, 'BLIND.md'), `# Blind pack — ${model.issue.title}\n\n**見てよいもの**: このディレクトリのみ（pages/*.png, contact/*.png, metrics.json）。\n**見てはいけないもの**: editorial.yaml, flatplan.yaml, articles/, notes/, context/, 既存のレビュー。\n\n- pages/page-NN.png : 仕上がり寸法の個別ページ（${mx.pages.length}p）\n- contact/contact-4xN.png, contact-8xN.png : 全ページ一覧（リズム確認）\n- contact/contact-spreads.png : 見開き単位（1pは右、${model.issue.pages}pは左）\n- metrics.json : 自動計測値（密度・画像比・余白・強度）。印象評価ではない\n\n手順: contact → 個別ページの順に見る。ページ単体でなく冊子全体の強弱・反復を先に評価する。\n`);
  for (const f of ['editorial.yaml', 'flatplan.yaml']) fs.copyFileSync(path.join(issueDir(id), f), path.join(ctx, f));
  fs.copyFileSync(path.join(out, 'rhythm.md'), path.join(ctx, 'rhythm.md'));
  fs.copyFileSync(path.join(out, 'fingerprint.json'), path.join(ctx, 'fingerprint.json'));
  if (fs.existsSync(path.join(out, 'preflight.md'))) fs.copyFileSync(path.join(out, 'preflight.md'), path.join(ctx, 'preflight.md'));
  fs.writeFileSync(path.join(ctx, 'articles.json'), JSON.stringify(Object.values(model.articles).map((a) => ({ id: a.meta.id, title: a.meta.title, type: a.meta.type, priority: a.meta.priority, target_pages: a.meta.target_pages })), null, 2));
  fs.writeFileSync(path.join(ctx, 'CONTEXT.md'), `# Context pack — ${model.issue.title}\n\nblind pack に加えて以下を参照してよい: editorial.yaml（編集意図）, flatplan.yaml（台割と各ページのnotes）, fingerprint.json（Publication Fingerprint の機械計測部分）, rhythm.md（リズム計測と自動検出）, preflight.md（あれば）。\n\n注意: 記事本文の校正はProofreaderの担当。批評は誌面の読みやすさ・リズム・一貫性・意図との整合に限る。\n`);

  // --- pack identity: reviews bind to this exact output (source_hash)
  const hash = sourceHash(model);
  fs.writeFileSync(path.join(pack, 'PACK.json'), JSON.stringify({ issue: id, source_hash: hash, generated_at: new Date().toISOString(), note: 'copy source_hash into the review front matter' }, null, 2));

  // --- templates: created only when missing (or reset, which is guarded above). Generated numbers never go into authored files.
  const reviewsDir = reviewsDirEarly;
  fs.mkdirSync(reviewsDir, { recursive: true });
  const snapFile = path.join(reviewsDir, 'auto-findings.snapshot.json');
  if (!fs.existsSync(snapFile) || reset) fs.writeFileSync(snapFile, JSON.stringify(rhythm.auto_findings, null, 2));
  const snap = JSON.parse(fs.readFileSync(snapFile, 'utf8'));
  const key = (f) => `${f.category}|${f.problem.replace(/\d+/g, '#')}|${f.pages.join(',')}`;
  const nowK = new Set(rhythm.auto_findings.map(key)), wasK = new Set(snap.map(key));
  fs.writeFileSync(path.join(ctx, 'auto-diff.md'), ['# Auto findings: diff against the first pack (reviews/auto-findings.snapshot.json)', '', ...snap.filter((f) => !nowK.has(key(f))).map((f) => `- RESOLVED ${f.id} ${f.problem}`), ...rhythm.auto_findings.filter((f) => !wasK.has(key(f))).map((f) => `- NEW ${f.id} [${f.severity}] ${f.problem}`), ...rhythm.auto_findings.filter((f) => wasK.has(key(f))).map((f) => `- STILL ${f.id} [${f.severity}] ${f.problem}`), ''].join('\n'));
  for (const s of STAGES) {
    const f = path.join(reviewsDir, `critic-${s}.md`);
    if (!fs.existsSync(f) || reset) fs.writeFileSync(f, reviewTemplate(s, model.issue));
  }
  log(`  review pack: ${rel(pack)}`);
  log(`  rhythm: ${rel(path.join(out, 'rhythm.md'))} (${rhythm.auto_findings.length} auto finding(s)); fingerprint: ${rel(path.join(out, 'fingerprint.json'))}`);
  log(`  critic templates: ${rel(reviewsDir)}/critic-{blind,context,rereview}.md`);
  return { rhythm, fingerprint, reviewsDir, model };
}

export function checkCritic(id, { log = console.log } = {}) {
  const model = loadIssue(id);
  const reviewsDir = path.join(issueDir(id), 'reviews');
  const reviews = loadReviews(reviewsDir);
  const hash = (() => { try { return sourceHash(model); } catch { return undefined; } })();
  const { problems, pending, stale, report } = checkReviews(reviews, model.issue, { sourceHash: hash });
  fs.mkdirSync(outDir(id), { recursive: true });
  fs.writeFileSync(path.join(outDir(id), 'critic-report.json'), JSON.stringify(report, null, 2));
  for (const p of pending) log(`  PENDING  ${p}`);
  for (const p of stale) log(`  STALE    ${p}`);
  for (const p of problems) log(`  INVALID  ${p}`);
  const severe = openSevere(reviews, hash);
  for (const f of severe) log(`  OPEN ${f.severity} ${f.id} p${f.pages.join(',')} ${f.title}`);
  log(`  critic-report.json: ${rel(path.join(outDir(id), 'critic-report.json'))}`);
  return { problems, pending, stale, severe, report };
}


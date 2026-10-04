// Publication Critic support: review templates, md parsing/validation, critic-report.json generation.
// The critic (an agent, separate from the producing agents) writes critic-*.md. Scripts only prepare packs and check structure.
import fs from 'node:fs';
import path from 'node:path';
import * as yaml from 'js-yaml';
import { checkSchema } from './schema.mjs';
import { SEVERITIES } from './analysis.mjs';

export const CATEGORIES = ['readability', 'hierarchy', 'visual-rhythm', 'consistency', 'originality', 'editorial-rhythm', 'page-balance', 'typography', 'image-usage', 'issue-identity'];
export const STAGES = ['blind', 'context', 'rereview'];
const AUTO_BEGIN = '<!-- AUTO:BEGIN -->';
const AUTO_END = '<!-- AUTO:END -->';

const STAGE_HELP = {
  blind: '入力は `review-pack/blind/`（ページPNG・contact sheet・数値のみ）。editorial.yaml / flatplan.yaml / notes / 他のレビューは**見ない**。意図を知らない読者として、読めるか・リズムがあるか・何の雑誌に見えるかを評価する。',
  context: '入力は `review-pack/context/`（editorial.yaml・flatplan・fingerprint・rhythm・preflight）+ blindのpack。編集意図に照らして、意図が誌面に出ているか・意図と実物のズレを評価する。blindの指摘は書き換えず、IDを引用して補強する。',
  rereview: '修正後に再build/再render/`publication:critic`を実行したあとで行う。blind/contextの全指摘（MEDIUM以上は必須）に対し、新しいPNGを見て disposition を付ける。修正で生じた新しい問題（regressed）も探す。',
};

export function reviewTemplate(stage, issue, auto) {
  const rows = CATEGORIES.map((c) => `| ${c} |  |  |`).join('\n');
  return `---
stage: ${stage}
status: pending
reviewer:
round: 1
---
# Publication Critic — ${stage} review (${issue.title})

> ${STAGE_HELP[stage]}
>
> 完了したら front matter を \`status: complete\` にし、\`npm run publication:critic -- ${issue.id} --check\` で構造を検証する。

## Scores (1–5)

| category | score | note |
|---|:-:|---|
${rows}

## Auto findings (scripts / mechanical — do not edit between markers)

${AUTO_BEGIN}
${autoBlock(stage, auto)}
${AUTO_END}

## Findings

<!-- 形式（問題→根拠→該当ページ→重大度→修正案）。ID は全ステージで一意: F-001, F-002 ...
### F-001 [HIGH] visual-rhythm — 一文のタイトル
- Pages: 6, 7
- Problem: 何が問題か
- Evidence: 見たもの（ページ/要素/数値）。auto finding を根拠にする場合は A-xxx を引用
- Fix: 具体的な修正案
-->
${stage === 'rereview' ? `
## Previous findings (disposition)

<!-- blind/context の全指摘について。MEDIUM以上は必須。
- F-001: fixed — 確認した根拠
- F-002: open — 理由
- F-003: regressed — 何が悪化したか
- F-004: wontfix — 編集判断の理由
-->
` : ''}
## Emergent fingerprint

<!-- 台割やfingerprint_targetに書かれていないが、実物に現れている反復的な特徴（視覚的癖・編集的癖）。次号で意図的に維持/排除するか判断する材料。 -->
-
`;
}

function autoBlock(stage, auto) {
  if (!auto) return '(run `publication:critic` after render)';
  const lines = auto.current.map((f) => `- ${f.id} [${f.severity}] ${f.category} p${f.pages.join(',') || '–'}: ${f.problem} — ${f.evidence}`);
  const out = [`generated: ${auto.generated_at}`, '', ...(lines.length ? lines : ['(none)'])];
  if (stage === 'rereview' && auto.snapshot) {
    const key = (f) => `${f.category}|${f.problem.replace(/\d+/g, '#')}|${f.pages.join(',')}`;
    const now = new Set(auto.current.map(key));
    const was = new Set(auto.snapshot.map(key));
    out.push('', '### diff vs snapshot (first pack)');
    out.push(...auto.snapshot.filter((f) => !now.has(key(f))).map((f) => `- RESOLVED ${f.id} ${f.problem}`));
    out.push(...auto.current.filter((f) => !was.has(key(f))).map((f) => `- NEW ${f.id} [${f.severity}] ${f.problem}`));
    out.push(...auto.current.filter((f) => was.has(key(f))).map((f) => `- STILL ${f.id} [${f.severity}] ${f.problem}`));
  }
  return out.join('\n');
}

/** Refresh only the AUTO block of an existing file. */
export function refreshAuto(md, stage, auto) {
  const a = md.indexOf(AUTO_BEGIN), b = md.indexOf(AUTO_END);
  if (a < 0 || b < 0) return md;
  return `${md.slice(0, a + AUTO_BEGIN.length)}\n${autoBlock(stage, auto)}\n${md.slice(b)}`;
}

const stripComments = (s) => s.replace(/<!--[\s\S]*?-->/g, '');

export function parseReview(md) {
  const fm = md.match(/^---\r?\n([\s\S]*?)\r?\n---/);
  const meta = fm ? yaml.load(fm[1]) ?? {} : {};
  const body = stripComments(fm ? md.slice(fm[0].length) : md);
  const scores = {};
  for (const m of body.matchAll(/^\|\s*([a-z-]+)\s*\|\s*([^|]*?)\s*\|/gm)) if (CATEGORIES.includes(m[1])) scores[m[1]] = m[2] === '' ? null : Number(m[2]);
  const findings = [];
  const parts = body.split(/^### (?=F-\d{3}\b)/m).slice(1);
  for (const part of parts) {
    const [head, ...rest] = part.split('\n');
    const h = head.match(/^(F-\d{3})\s*\[([A-Z]+)\]\s*([a-z-]+)\s*[—–-]\s*(.+)$/);
    const f = { id: h?.[1] ?? head.slice(0, 5), severity: h?.[2], category: h?.[3], title: h?.[4]?.trim(), raw_ok: !!h };
    const text = rest.join('\n').split(/^## /m)[0];
    for (const key of ['Pages', 'Problem', 'Evidence', 'Fix']) {
      const m = text.match(new RegExp(`^- ${key}:[ \\t]*([\\s\\S]*?)(?=^- (?:Pages|Problem|Evidence|Fix):|$(?![\\s\\S]))`, 'm'));
      f[key.toLowerCase()] = (m?.[1] ?? '').trim();
    }
    f.pages = f.pages.split(/[,、\s]+/).filter(Boolean).map(Number).filter((n) => Number.isInteger(n));
    findings.push(f);
  }
  const dispositions = [...body.matchAll(/^- (F-\d{3}):\s*(fixed|open|regressed|wontfix)\b\s*[—–:-]?\s*(.*)$/gm)].map((m) => ({ id: m[1], status: m[2], note: m[3].trim() }));
  const em = body.split(/^## Emergent fingerprint\s*$/m)[1];
  const emergent = em ? em.split('\n').map((l) => l.match(/^- (.+)$/)?.[1]?.trim()).filter(Boolean) : [];
  return { meta, scores, findings, dispositions, emergent };
}

export function loadReviews(reviewsDir) {
  const out = {};
  for (const s of STAGES) {
    const f = path.join(reviewsDir, `critic-${s}.md`);
    if (fs.existsSync(f)) out[s] = { file: f, ...parseReview(fs.readFileSync(f, 'utf8')) };
  }
  return out;
}

/** Returns {problems: string[], pending: string[], report} */
export function checkReviews(reviews, issue) {
  const problems = [];
  const pending = [];
  const seen = new Set();
  for (const s of STAGES) {
    const r = reviews[s];
    if (!r) { pending.push(`${s}: file missing`); continue; }
    if (r.meta.stage !== s) problems.push(`${s}: front matter stage must be "${s}"`);
    if (r.meta.status !== 'complete') { pending.push(`${s}: status is ${r.meta.status ?? 'unset'}`); continue; }
    if (!r.meta.reviewer) problems.push(`${s}: reviewer is empty`);
    for (const c of CATEGORIES) if (!Number.isInteger(r.scores[c]) || r.scores[c] < 1 || r.scores[c] > 5) problems.push(`${s}: score for "${c}" must be 1-5`);
    for (const f of r.findings) {
      const w = `${s} ${f.id}`;
      if (!f.raw_ok) { problems.push(`${s}: malformed finding heading "${f.id}" (expected "### F-001 [HIGH] category — title")`); continue; }
      if (seen.has(f.id)) problems.push(`${w}: duplicate finding id`);
      seen.add(f.id);
      if (!SEVERITIES.includes(f.severity)) problems.push(`${w}: severity "${f.severity}" not in ${SEVERITIES.join('/')}`);
      if (!CATEGORIES.includes(f.category)) problems.push(`${w}: category "${f.category}" not in ${CATEGORIES.join('/')}`);
      for (const k of ['problem', 'evidence', 'fix']) if (!f[k]) problems.push(`${w}: "${k}" is empty`);
      for (const p of f.pages) if (p < 1 || p > issue.pages) problems.push(`${w}: page ${p} out of range`);
      if (!f.pages.length && !/global|全体/i.test(`${f.problem} ${f.title}`)) problems.push(`${w}: Pages is empty (write "global" in problem/title if the finding is issue-wide)`);
    }
    if (!r.emergent.length) problems.push(`${s}: "Emergent fingerprint" has no entries (write "none observed" if truly none)`);
  }
  const rr = reviews.rereview;
  if (rr?.meta.status === 'complete') {
    const prior = ['blind', 'context'].flatMap((s) => reviews[s]?.findings ?? []);
    const disp = new Map(rr.dispositions.map((d) => [d.id, d]));
    for (const f of prior) {
      const sev = SEVERITIES.indexOf(f.severity);
      if (sev >= 0 && sev <= SEVERITIES.indexOf('MEDIUM') && !disp.has(f.id)) problems.push(`rereview: no disposition for ${f.id} [${f.severity}]`);
    }
    for (const d of rr.dispositions) if (!prior.some((f) => f.id === d.id)) problems.push(`rereview: disposition for unknown finding ${d.id}`);
  }
  const report = { issue: issue.id, generated_at: new Date().toISOString(), stages: {} };
  for (const s of STAGES) {
    const r = reviews[s];
    if (!r) continue;
    report.stages[s] = { status: r.meta.status === 'complete' ? 'complete' : 'pending', reviewer: r.meta.reviewer || undefined, scores: Object.fromEntries(Object.entries(r.scores).filter(([, v]) => Number.isInteger(v))), emergent_fingerprint: r.emergent, dispositions: r.dispositions, findings: r.findings.filter((f) => f.raw_ok).map(({ raw_ok, ...f }) => f) };
  }
  const sch = checkSchema('critic-report', report);
  for (const e of sch) problems.push(`critic-report.json schema: ${e.path} ${e.message}`);
  return { problems, pending, report };
}

/** Open BLOCKER/HIGH after the latest completed stage (rereview dispositions override earlier findings). */
export function openSevere(reviews) {
  const disp = new Map((reviews.rereview?.meta.status === 'complete' ? reviews.rereview.dispositions : []).map((d) => [d.id, d.status]));
  const all = ['blind', 'context'].flatMap((s) => (reviews[s]?.meta.status === 'complete' ? reviews[s].findings : []));
  const rr = reviews.rereview?.meta.status === 'complete' ? reviews.rereview.findings : [];
  return [...all.filter((f) => !['fixed', 'wontfix'].includes(disp.get(f.id))), ...rr].filter((f) => ['BLOCKER', 'HIGH'].includes(f.severity) && disp.get(f.id) !== 'fixed');
}

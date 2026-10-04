// HEURISTIC density rules driven by the component contracts (layouts/_contracts.mjs) and the page's role in its article.
// "Physically empty" (measurement) is kept apart from "bad design" (judgement): these rules only ever raise warnings.
import { entriesOf } from './inputs.mjs';

/** page number -> 'first' | 'middle' | 'last' | 'only' for text-bearing components, per article. */
export function pageRoles(model, reg) {
  const roles = new Map();
  const byArticle = new Map();
  for (const e of entriesOf(model)) {
    if (!reg.components[e.layout]?.text) continue;
    if (!byArticle.has(e.article)) byArticle.set(e.article, []);
    byArticle.get(e.article).push(e);
  }
  for (const list of byArticle.values()) list.forEach((e, i) => roles.set(e.pages[0], list.length === 1 ? 'only' : i === 0 ? 'first' : i === list.length - 1 ? 'last' : 'middle'));
  return roles;
}

export const entryForPage = (model, n) => entriesOf(model).find((e) => e.pages.includes(n));

/** @returns {{expected:[number,number]|null, sparseAllowed:boolean, extentMin:number|null}} */
export function contractFor(comp, role) {
  const d = comp?.density ?? { sparse_allowed: true };
  return { sparseAllowed: !!d.sparse_allowed, expected: d.occupancy?.[role] ?? null, extentMin: d.extent_min ?? null };
}

/**
 * Post-render heuristics from measurements. Returns findings {code, severity, kind:'HEURISTIC', pages, message, evidence}.
 * Declared intent (`intentional_sparse: true` in the flatplan) and sparse_allowed components are never flagged.
 */
export function densityFindings(model, reg, metrics) {
  const roles = pageRoles(model, reg);
  const out = [];
  const declared = [];
  for (const m of metrics) {
    const e = entryForPage(model, m.n);
    const comp = reg.components[m.layout];
    const role = roles.get(m.n);
    const c = contractFor(comp, role);
    if (e?.intentional_sparse) { declared.push({ page: m.n, note: e.notes }); continue; }
    if (c.sparseAllowed) continue;
    const occ = m.text_occupancy;
    const lowOcc = c.expected && occ !== null && occ < c.expected[0];
    const lowExt = c.extentMin !== null && m.content_extent_live < c.extentMin;
    if (!lowOcc && !lowExt) continue;
    const parts = [];
    if (lowOcc) parts.push(`text occupancy ${occ} < expected ≥${c.expected[0]} for a "${role}" page of its article`);
    if (lowExt) parts.push(`content reaches only ${Math.round(m.content_extent_live * 100)}% of the live area (expected ≥${Math.round(c.extentMin * 100)}%)`);
    const severe = (lowOcc && occ < c.expected[0] * 0.75) || (lowExt && m.content_extent_live < c.extentMin * 0.8);
    out.push({ code: 'UNDERFILLED_PAGE', kind: 'HEURISTIC', severity: severe ? 'MEDIUM' : 'LOW', pages: [m.n], message: `${m.layout}/${m.variant}: ${parts.join('; ')}`, fix: 'adjust the copy / page allocation, choose a component whose density contract fits, or declare the page `intentional_sparse: true` with a reason in the flatplan notes' });
  }
  return { findings: out, declared };
}

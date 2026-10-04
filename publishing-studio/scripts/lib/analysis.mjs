// Magazine rhythm analysis + Publication Fingerprint (machine-measurable subset).
import { entriesOf } from './inputs.mjs';
import { densityFindings, entryForPage } from './density.mjs';

export const SEVERITIES = ['BLOCKER', 'HIGH', 'MEDIUM', 'LOW', 'NOTE'];
export const DEFAULT_TARGET = { max_same_layout_run: 2, max_consecutive_image_heavy: 3, min_intensity_range: 40, max_opener_repeat: 3, min_quiet_pages: 1 };
const OPENERS = new Set(['feature-opener', 'interview-opener']);
// layouts that are composed "quiet" pages by design (a quote / divider on paper)
const QUIET_LAYOUTS = new Set(['contents', 'colophon', 'credits', 'divider', 'quote-page']);

const mean = (a) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : 0);
const stdev = (a) => { const m = mean(a); return Math.sqrt(mean(a.map((x) => (x - m) ** 2))); };
const r1 = (x) => Math.round(x * 10) / 10;
const stats = (a) => ({ min: r1(Math.min(...a)), max: r1(Math.max(...a)), mean: r1(mean(a)), stdev: r1(stdev(a)) });
const bar = (v, max = 100, w = 20) => '█'.repeat(Math.round((v / max) * w)).padEnd(w, '·');

/** Every finding is classed: MEASUREMENT (a fact about the render), HEURISTIC (a rule of thumb), REVIEW_REQUIRED (needs a human). */
export function analyzeRhythm(model, mx, reg) {
  const target = { ...DEFAULT_TARGET, ...(model.editorial?.fingerprint_target ?? {}) };
  const pages = mx.pages.map((m) => ({
    n: m.n, layout: m.layout, variant: m.variant, article: m.article, spread: m.spread,
    text_chars: m.text_chars, text_density: +Math.min(1, m.text_chars / 1400).toFixed(2),
    image_ratio: m.image_ratio, whitespace_ratio: m.whitespace_ratio, visual_elements: m.visual_elements,
    headline_pt: m.headline_pt, body_pt: m.body_pt, intensity: m.measured_intensity, declared_intensity: m.declared_intensity,
    text_occupancy: m.text_occupancy, content_extent: m.content_extent_live, orphan_lines: m.orphan_lines?.length ?? 0, image_heavy: m.image_ratio >= 0.4,
    // quiet = declared by the flatplan, or a composed quiet layout on paper. Under-filled body pages are NOT quiet pages.
    quiet: !!entryForPage(model, m.n)?.intentional_sparse || (QUIET_LAYOUTS.has(m.layout) && m.whitespace_ratio >= 0.6 && m.image_ratio === 0),
  }));
  const findings = [];
  let seq = 0;
  const add = (severity, category, pgs, problem, evidence, fix, kind = 'HEURISTIC') => findings.push({ id: `A-${String(++seq).padStart(3, '0')}`, severity, category, pages: pgs, problem, evidence, fix, source: 'auto', kind });

  // runs over flatplan entries (a spread counts once)
  const entries = entriesOf(model);
  const runs = (keyFn) => {
    const out = [];
    let cur = null;
    for (const e of entries) {
      const k = keyFn(e);
      if (cur && cur.key === k) { cur.entries.push(e); } else { cur = { key: k, entries: [e] }; out.push(cur); }
    }
    return out;
  };
  const layoutRuns = runs((e) => e.layout);
  const maxLayoutRun = Math.max(...layoutRuns.map((r) => r.entries.length));
  for (const r of layoutRuns.filter((r) => r.entries.length > target.max_same_layout_run)) {
    add('MEDIUM', 'visual-rhythm', r.entries.flatMap((e) => e.pages), `同一レイアウト "${r.key}" が${r.entries.length}回連続`, `max_same_layout_run=${target.max_same_layout_run} を超過 (p${r.entries[0].pages[0]}–${r.entries.at(-1).pages.at(-1)})`, '間にquote/photo/dividerなど別型を挟むか、variantを変える');
  }
  const variantRuns = runs((e) => `${e.layout}/${e.variant}`);
  const maxVariantRun = Math.max(...variantRuns.map((r) => r.entries.length));

  // image-heavy runs (pages)
  let run = [];
  const heavyRuns = [];
  for (const p of pages) { if (p.image_heavy) run.push(p); else { if (run.length) heavyRuns.push(run); run = []; } }
  if (run.length) heavyRuns.push(run);
  const maxHeavy = heavyRuns.length ? Math.max(...heavyRuns.map((r) => r.length)) : 0;
  for (const r of heavyRuns.filter((r) => r.length > target.max_consecutive_image_heavy)) {
    add('MEDIUM', 'image-usage', r.map((p) => p.n), `写真主体のページが${r.length}ページ連続`, `image_ratio≥0.40 が連続 (上限 ${target.max_consecutive_image_heavy})`, '文字ページを挟んで写真の山を分ける');
  }

  // dense text runs
  let dr = [];
  const denseRuns = [];
  for (const p of pages) { if (p.text_density >= 0.6) dr.push(p); else { if (dr.length) denseRuns.push(dr); dr = []; } }
  if (dr.length) denseRuns.push(dr);
  for (const r of denseRuns.filter((r) => r.length >= 4)) add('MEDIUM', 'editorial-rhythm', r.map((p) => p.n), `文字密度の高いページが${r.length}ページ連続`, 'text_density≥0.60 が4p以上', '写真・引用・余白ページを挟むか、記事を分割する');

  // intensity range
  const ints = pages.map((p) => p.intensity);
  const range = Math.max(...ints) - Math.min(...ints);
  if (range < target.min_intensity_range) add('HIGH', 'visual-rhythm', [], `冊子全体の強弱が平坦 (振れ幅 ${range})`, `measured_intensity の max-min=${range} < ${target.min_intensity_range}`, '写真見開き/大見出しと、余白の多い静かなページの差をつける');

  // opener repetition
  const openers = entries.filter((e) => OPENERS.has(e.layout));
  const ov = {};
  for (const e of openers) ov[`${e.layout}/${e.variant}`] = (ov[`${e.layout}/${e.variant}`] ?? 0) + 1;
  for (const [k, c] of Object.entries(ov)) if (c > target.max_opener_repeat) add('LOW', 'originality', openers.filter((e) => `${e.layout}/${e.variant}` === k).flatMap((e) => e.pages), `オープナー "${k}" が${c}回反復`, `max_opener_repeat=${target.max_opener_repeat}`, '記事ごとにvariantを変える');

  // quiet pages
  const quiet = pages.filter((p) => p.quiet);
  if (quiet.length < target.min_quiet_pages) add('LOW', 'visual-rhythm', [], `余白の多い静かなページが${quiet.length}枚 (目標 ${target.min_quiet_pages}以上)`, 'whitespace_ratio≥0.60 かつ写真なしの本文ページが不足', '1記事の末尾などに余白ページ/引用ページを置く');

  // plan vs measured intensity drift
  const drift = pages.filter((p) => p.declared_intensity && Math.abs(p.declared_intensity * 20 - p.intensity) > 45);
  if (drift.length) add('NOTE', 'consistency', drift.map((p) => p.n), `台割の visual_intensity と実測の乖離が大きい (${drift.length}p)`, drift.map((p) => `p${p.n}: 計画${p.declared_intensity}/5 vs 実測${p.intensity}/100`).join(', '), '台割の宣言値か、layout/variantを見直す');

  // density heuristics from the component contracts (replaces the old single "fit_fill < 35%" rule)
  const dens = densityFindings(model, reg, mx.pages);
  for (const f of dens.findings) add(f.severity, 'page-balance', f.pages, f.message, `${f.code} (HEURISTIC, component contract)`, f.fix);
  const declaredSparse = dens.declared;
  for (const p of pages) {
    if (p.text_occupancy !== null && p.text_occupancy > 1.02) add('HIGH', 'readability', [p.n], `本文枠が満杯を超過 (occupancy ${p.text_occupancy})`, 'DOM計測: 行数×行送りが枠高を超過', '台割のページ配分を変えるか原稿を削る', 'MEASUREMENT');
    if (p.orphan_lines) add('LOW', 'typography', [p.n], `孤立行（1〜2字+句読点だけの最終行）が${p.orphan_lines}か所`, 'DOM計測: 2行以上の段落/見出し/引用の最終行が2字幅以下', '字間・追い込み・文節折返しで調整する（組版ルール側の対処が望ましい）', 'MEASUREMENT');
  }
  for (const m of mx.pages) {
    if (m.overflow.length) add('BLOCKER', 'readability', [m.n], '本文が枠から溢れて切れている', m.overflow.map((o) => `${o.el}: scroll ${o.scroll.join('x')} > client ${o.client.join('x')}`).join('; '), '文字量を削る/ページを足す/variantを変える', 'MEASUREMENT');
    if (m.outside.length) add('HIGH', 'page-balance', [m.n], '要素が仕上がり線の外にはみ出している', m.outside.map((o) => o.kind).join(', '), '配置を修正する', 'MEASUREMENT');
    if (m.min_font_pt !== null && m.min_font_pt < 6) add('LOW', 'typography', [m.n], `最小文字サイズ ${m.min_font_pt}pt`, '6pt未満の文字がある', 'キャプション等のサイズを上げる', 'MEASUREMENT');
  }

  const spreads = [];
  const byN = Object.fromEntries(pages.map((p) => [p.n, p]));
  for (let n = 2; n < model.issue.pages; n += 2) spreads.push({ pages: [n, n + 1], intensity: [byN[n]?.intensity, byN[n + 1]?.intensity], layouts: [byN[n]?.layout, byN[n + 1]?.layout] });

  return {
    issue: model.id, target,
    summary: {
      intensity: stats(ints), text_chars: stats(pages.map((p) => p.text_chars)), whitespace: stats(pages.map((p) => p.whitespace_ratio)), image_ratio: stats(pages.map((p) => p.image_ratio)),
      max_same_layout_run: maxLayoutRun, max_same_variant_run: maxVariantRun, max_consecutive_image_heavy: maxHeavy, quiet_pages: quiet.map((p) => p.n), intensity_range: range,
      distinct_spread_types: new Set(spreads.map((s) => s.layouts.join('+'))).size, spreads: spreads.length,
    },
    pages, spreads, auto_findings: findings, declared_sparse: declaredSparse,
    review_required: [
      '余白が「美しい」か、意図された沈黙か（underfilled の機械判定は仮説にすぎない）',
      '編集的なリズム（強弱の起伏が読者の体験として成立しているか）',
      '視覚的な緊張感・見開きの力関係',
      '見開き単位での視線の流れ・バランス（contact-spreads.png）',
      '写真の被写体がノド（綴じ目）にかかっていないか',
      '書体・サイズ・字間の印象（D1）、モチーフの一貫性（D6）',
      '編集の声（E6）と見出し・リードの文体',
      '色の印象と表紙のアイデンティティ（I1）',
    ],
  };
}

export function rhythmMarkdown(r) {
  const L = [];
  L.push(`# Magazine Rhythm — ${r.issue}`, '', 'Findings are classed. **MEASUREMENT** = a fact about the render (DOM/CSS). **HEURISTIC** = a rule of thumb that may be wrong. **REVIEW_REQUIRED** = no machine verdict is possible. A measurement is never converted into "good" or "bad" by itself.', '');
  L.push('## MEASUREMENT (per page)', '', '| p | layout/variant | intensity* | text chars | image | whitespace | text occupancy | content extent | orphans | tags |', '|--:|---|:--|--:|--:|--:|--:|--:|--:|---|');
  for (const p of r.pages) L.push(`| ${p.n} | ${p.layout}/${p.variant ?? ''} | \`${bar(p.intensity)}\` ${p.intensity} | ${p.text_chars} | ${p.image_ratio} | ${p.whitespace_ratio} | ${p.text_occupancy ?? '–'} | ${p.content_extent ?? '–'} | ${p.orphan_lines || ''} | ${[p.quiet ? 'quiet(declared/composed)' : '', p.image_heavy ? 'image' : ''].filter(Boolean).join(' ')} |`);
  L.push('', '\\* intensity is a composite of image share, headline scale and fills (0–100): a descriptive number, not a quality score. "text occupancy" = lines set / lines the frame holds; "content extent" = how far down the live area the content reaches.');
  const s = r.summary;
  L.push('', '## MEASUREMENT (summary)', '', `- intensity: min ${s.intensity.min} / max ${s.intensity.max} / mean ${s.intensity.mean} (range ${s.intensity_range}; target ≥ ${r.target.min_intensity_range})`, `- text chars/page: mean ${s.text_chars.mean} (min ${s.text_chars.min}, max ${s.text_chars.max})`, `- longest same-layout run: ${s.max_same_layout_run} (limit ${r.target.max_same_layout_run}); same-variant run: ${s.max_same_variant_run}`, `- longest image-heavy run: ${s.max_consecutive_image_heavy} (limit ${r.target.max_consecutive_image_heavy})`, `- quiet pages (declared or composed): ${s.quiet_pages.join(', ') || 'none'} (target ≥ ${r.target.min_quiet_pages})`, `- distinct spread types: ${s.distinct_spread_types}/${s.spreads}`);
  if (r.declared_sparse?.length) L.push(`- declared intentional_sparse: ${r.declared_sparse.map((d) => `p${d.page} (${d.note})`).join('; ')}`);
  const bykind = (k) => r.auto_findings.filter((f) => f.kind === k);
  for (const [k, title] of [['MEASUREMENT', 'MEASUREMENT findings (facts)'], ['HEURISTIC', 'HEURISTIC findings (rules of thumb — may be wrong; a human decides)']]) {
    L.push('', `## ${title}`, '');
    if (!bykind(k).length) L.push('none');
    for (const f of bykind(k)) L.push(`- **${f.id} [${f.severity}] ${f.category}** p${f.pages.join(',') || '–'} — ${f.problem}  \n  evidence: ${f.evidence}  \n  suggestion: ${f.fix}`);
  }
  L.push('', '## REVIEW_REQUIRED (no machine verdict possible)', '', ...r.review_required.map((m) => `- [ ] ${m}`), '');
  return L.join('\n');
}

export const AXES = [
  ['D1', 'DESIGN', 'Typography', 'hybrid'], ['D2', 'DESIGN', 'Grid', 'hybrid'], ['D3', 'DESIGN', 'White Space', 'machine'], ['D4', 'DESIGN', 'Image Treatment', 'hybrid'],
  ['D5', 'DESIGN', 'Hierarchy', 'hybrid'], ['D6', 'DESIGN', 'Motif', 'visual'], ['D7', 'DESIGN', 'Navigation', 'machine'],
  ['E1', 'EDITORIAL', 'Article Rhythm', 'machine'], ['E2', 'EDITORIAL', 'Opening Pattern', 'machine'], ['E3', 'EDITORIAL', 'Narrative Pace', 'hybrid'], ['E4', 'EDITORIAL', 'Information Density', 'machine'],
  ['E5', 'EDITORIAL', 'Recurring Sections', 'machine'], ['E6', 'EDITORIAL', 'Editorial Voice', 'visual'],
  ['I1', 'ISSUE', 'Issue Identity', 'visual'], ['I2', 'ISSUE', 'Spread Variation', 'machine'], ['I3', 'ISSUE', 'Image Rhythm', 'machine'], ['I4', 'ISSUE', 'Page Density', 'machine'], ['I5', 'ISSUE', 'Repetition', 'machine'], ['I6', 'ISSUE', 'Consistency', 'hybrid'],
];

export function computeFingerprint(model, mx, rhythm) {
  const p = mx.pages;
  const entries = entriesOf(model);
  const imgs = p.flatMap((m) => m.images.map((i) => ({ ...i, page: m.n })));
  const touches = (i) => i.rect_mm.x <= 0.5 || i.rect_mm.y <= 0.5 || i.rect_mm.x + i.rect_mm.w >= model.issue.width - 0.5 || i.rect_mm.y + i.rect_mm.h >= model.issue.height - 0.5;
  const types = {};
  for (const a of Object.values(model.articles)) types[a.meta.type] = (types[a.meta.type] ?? 0) + 1;
  const opener = entries.filter((e) => OPENERS.has(e.layout) || (e.layout === 'essay' && e.variant === 'opener')).map((e) => `p${e.pages[0]} ${e.layout}/${e.variant}`);
  const m = {
    D1: { fonts: [...new Set(p.flatMap((x) => x.fonts))], headline_pt: stats(p.filter((x) => x.headline_pt).map((x) => x.headline_pt)), body_pt: stats(p.filter((x) => x.body_pt).map((x) => x.body_pt)), min_font_pt: Math.min(...p.map((x) => x.min_font_pt ?? 99)), target: model.editorial?.fingerprint_target?.typography ?? null },
    D2: { columns: mx.tokens['--columns'], gutter: mx.tokens['--gutter'], baseline: mx.tokens['--baseline'], margins: [mx.tokens['--margin-top'], mx.tokens['--margin-outer'], mx.tokens['--margin-bottom'], mx.tokens['--margin-inner']], safe_violations: p.reduce((a, x) => a + x.safe_violations, 0) },
    D3: stats(p.map((x) => x.whitespace_ratio)),
    D4: { images: imgs.length, bleed_or_edge: imgs.filter(touches).length, inset: imgs.filter((i) => !touches(i)).length, min_ppi: imgs.length ? Math.min(...imgs.map((i) => i.ppi)) : null },
    D5: { headline_over_body: stats(p.filter((x) => x.headline_pt && x.body_pt).map((x) => x.headline_pt / x.body_pt)), pages_without_heading: p.filter((x) => !x.headline_pt).map((x) => x.n) },
    D6: null,
    D7: { folio_pages: p.filter((x) => x.folio).length, runhead_pages: p.filter((x) => x.has_runhead).length, contents_entries: mx.pages.length ? Object.values(model.articles).filter((a) => a.meta.in_contents !== false && ['feature', 'interview', 'essay', 'photo-essay', 'column', 'profile'].includes(a.meta.type)).length : 0 },
    E1: entries.reduce((acc, e) => { const last = acc.at(-1); if (last?.article === e.article) last.pages += e.pages.length; else acc.push({ article: e.article, pages: e.pages.length }); return acc; }, []),
    E2: { openers: opener, distinct: new Set(opener.map((o) => o.replace(/^p\d+ /, ''))).size },
    E3: { intensity_series: p.map((x) => x.measured_intensity), text_series: p.map((x) => x.text_chars) },
    E4: stats(p.map((x) => x.text_chars)),
    E5: { article_types: types, note: 'N/A for a single issue: recurrence needs >= 2 issues' },
    E6: { editorial_voice: model.editorial?.editorial_voice ?? null },
    I1: { accent: mx.tokens['--color-accent'], accent_2: mx.tokens['--color-accent-2'], full_color_pages: p.filter((x) => x.bg_fill).map((x) => x.n), target_motif: model.editorial?.fingerprint_target?.motif ?? null },
    I2: { distinct_spread_types: rhythm.summary.distinct_spread_types, spreads: rhythm.summary.spreads, note: 'low discriminating power on short issues (almost always every spread differs)' },
    I3: { image_ratio_series: p.map((x) => x.image_ratio), max_consecutive_image_heavy: rhythm.summary.max_consecutive_image_heavy },
    I4: { ink_ratio: stats(p.map((x) => x.ink_ratio)) },
    I5: { max_same_layout_run: rhythm.summary.max_same_layout_run, max_same_variant_run: rhythm.summary.max_same_variant_run },
    I6: { fonts_used: new Set(p.flatMap((x) => x.fonts)).size, folio_mismatch: p.filter((x) => x.folio && x.folio.text !== x.folio.expected).map((x) => x.n), overflow_pages: p.filter((x) => x.overflow.length).map((x) => x.n) },
  };
  const CLS = { machine: 'MEASUREMENT', hybrid: 'HEURISTIC', visual: 'REVIEW_REQUIRED' };
  return AXES.map(([id, group, name, mode]) => ({ id, group, name, mode, class: CLS[mode], measured: m[id], judged_by: mode === 'machine' ? 'script measures a fact' : mode === 'visual' ? 'critic (visual only)' : 'script measures, critic judges' }));
}

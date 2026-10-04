// Publication Model validation: JSON Schema + cross-file semantic checks.
import { checkSchema } from './schema.mjs';
import { loadRegistry } from './registry.mjs';
import { scanMarkdown } from './text.mjs';
import { buildInputs, entriesOf, imageRefs, isEmpty, planText, pagesOf } from './inputs.mjs';

export const FORMATS = { A4: [210, 297], A5: [148, 210], A6: [105, 148], B5: [182, 257], B6: [128, 182] };

/** @returns {Promise<{level:'error'|'warning'|'info', code:string, message:string, where?:string}[]>} */
/** probe: result of probeLayout (measured frames + overflow with no body text). Without it, layout/text-volume checks are skipped. */
export async function validateModel(model, { probe } = {}) {
  const out = [];
  const add = (level, code, message, where) => out.push({ level, code, message, ...(where ? { where } : {}) });
  for (const e of model.loadErrors) add('error', e.code, e.message, e.file);
  if (!model.issue || !model.editorial || !model.flatplan) return out;

  const reg = await loadRegistry();
  for (const [name, data] of [['issue', model.issue], ['editorial', model.editorial], ['flatplan', model.flatplan]]) {
    for (const e of checkSchema(name, data)) add('error', 'SCHEMA', `${e.path}: ${e.message}`, `${name}.yaml`);
  }
  for (const [id, art] of Object.entries(model.articles)) {
    for (const e of checkSchema('article', art.meta)) add('error', 'SCHEMA', `${e.path}: ${e.message}`, art.file);
    if (art.meta.id && model.articleFiles[id] !== `${art.meta.id}.md`) add('warning', 'ARTICLE_FILENAME', `file name ${model.articleFiles[id]} differs from id "${art.meta.id}"`, art.file);
  }
  const { issue, flatplan } = model;
  if (!Array.isArray(flatplan.pages)) return out;

  // --- input safety: manuscripts and theme CSS are untrusted
  const badRef = (f) => typeof f !== 'string' || /[\\/]/.test(f) || f.includes('..') || f.startsWith('.') || /[\u0000-\u001f]/.test(f);
  for (const [id, art] of Object.entries(model.articles)) {
    for (const a of art.meta.assets ?? []) if (badRef(a.image)) add('error', 'ASSET_PATH_INVALID', `image reference ${JSON.stringify(a.image)} must be a plain file name inside images/ (no path separators, "..", or leading dot)`, art.file);
    const sc = scanMarkdown(art.body);
    if (sc.html) add('warning', 'MD_RAW_HTML_ESCAPED', `${sc.html} raw HTML fragment(s) are not allowed in manuscripts and will be printed as literal text`, art.file);
    if (sc.images) add('warning', 'MD_IMAGE_REMOVED', `${sc.images} Markdown image(s) are dropped; place images in images/ and list them in "assets"`, art.file);
    if (sc.links) add('info', 'MD_LINK_AS_TEXT', `${sc.links} link(s) print as plain text`, art.file);
  }
  for (const e of flatplan.pages) for (const f of [...(Array.isArray(e.slots?.images) ? e.slots.images : [e.slots?.images]), e.slots?.image, e.slots?.hero_image].filter((x) => x !== undefined)) if (badRef(f)) add('error', 'ASSET_PATH_INVALID', `slot image reference ${JSON.stringify(f)} must be a plain file name inside images/`, `flatplan p${e.pages?.join('-')}`);
  const cssBlob = `${model.themeCss ?? ''}\n${Object.values(issue.theme_overrides ?? {}).join('\n')}`;
  if (/@import|url\s*\(\s*['"]?\s*(?:[a-z][a-z0-9+.-]*:|\/\/)|expression\s*\(|javascript:/i.test(cssBlob)) add('error', 'THEME_EXTERNAL_RESOURCE', 'theme.css / theme_overrides must not use @import or absolute/remote url(): book builds never load network or scheme URLs', 'theme.css');

  // --- issue consistency
  if (FORMATS[issue.format]) {
    const [w, h] = FORMATS[issue.format];
    if (issue.width !== w || issue.height !== h) add('warning', 'FORMAT_SIZE_MISMATCH', `format ${issue.format} is ${w}x${h}mm but issue.yaml says ${issue.width}x${issue.height}`, 'issue.yaml');
  }
  if (issue.binding === 'saddle-stitch' && issue.pages % 4 !== 0) add('error', 'PAGES_NOT_MULTIPLE_OF_4', `saddle-stitch needs a multiple of 4 pages, got ${issue.pages}`, 'issue.yaml');
  if (issue.binding === 'perfect' && issue.pages % 2 !== 0) add('error', 'PAGES_ODD', `perfect binding needs an even page count, got ${issue.pages}`, 'issue.yaml');

  // --- flatplan entries
  const covered = new Map();
  const placedPages = {};
  const usedImages = new Set();
  const entries = entriesOf(model);
  for (const e of entries) {
    const where = `flatplan p${e.pages.join('-')}`;
    const c = reg.components[e.layout];
    if (!c) {
      add('error', 'UNKNOWN_LAYOUT', `unknown layout "${e.layout}" (available: ${Object.keys(reg.components).join(', ')})`, where);
    } else {
      const variant = e.variant ?? c.defaultVariant;
      if (!c.variants[variant]) add('error', 'UNKNOWN_VARIANT', `layout ${e.layout} has no variant "${variant}" (available: ${Object.keys(c.variants).join(', ')})`, where);
      else if (pagesOf(e, reg) !== e.pages.length) add('error', 'SPAN_MISMATCH', `${e.layout}/${variant} spans ${pagesOf(e, reg)} page(s) but flatplan gives ${e.pages.length}`, where);
    }
    if (e.pages.length === 2 && e.pages[1] !== e.pages[0] + 1) add('error', 'SPREAD_NOT_CONSECUTIVE', `spread pages must be consecutive, got ${e.pages.join(',')}`, where);
    if (e.pages.length === 2 && issue.binding !== 'none' && e.pages[0] % 2 !== 0) add('error', 'SPREAD_PARITY', `a spread must start on an even (left) page, got ${e.pages[0]}`, where);
    for (const p of e.pages) {
      if (p > issue.pages) add('error', 'FLATPLAN_RANGE', `page ${p} exceeds issue.pages=${issue.pages}`, where);
      if (covered.has(p)) add('error', 'FLATPLAN_OVERLAP', `page ${p} is placed twice`, where);
      covered.set(p, e);
    }
    const art = model.articles[e.article];
    if (!art) {
      add('error', 'ARTICLE_MISSING', `article "${e.article}" has no file in articles/`, where);
      continue;
    }
    placedPages[e.article] = (placedPages[e.article] ?? 0) + e.pages.length;
    if (c) {
      const variant = e.variant ?? c.defaultVariant;
      const inputs = buildInputs(model, e);
      for (const k of c.required?.(variant) ?? []) {
        if (isEmpty(inputs[k])) add('error', 'MISSING_INPUT', `${e.layout}/${variant} requires "${k}" (article "${e.article}")`, where);
      }
      const minImg = c.minImages?.[variant];
      if (minImg && (inputs.images?.length ?? 0) < minImg) add('error', 'MISSING_INPUT', `${e.layout}/${variant} needs at least ${minImg} images, got ${inputs.images?.length ?? 0}`, where);
      for (const f of imageRefs(inputs)) {
        usedImages.add(f);
        if (!model.images[f]) add('error', 'MISSING_ASSET', `image "${f}" not found in images/`, where);
        else if (c.captions && !model.captions[f]?.caption && (model.imageMeta[f]?.role ?? 'inline') !== 'decorative') add('warning', 'MISSING_CAPTION', `no caption for "${f}" (captions/*.yaml)`, where);
      }
    }
  }
  for (let p = 1; p <= issue.pages; p++) if (!covered.has(p)) add('error', 'FLATPLAN_GAP', `page ${p} is not in the flatplan`, 'flatplan.yaml');

  // --- articles
  for (const [id, art] of Object.entries(model.articles)) {
    if (art.meta.status === 'spiked') continue;
    if (!placedPages[id]) add('error', 'ARTICLE_NOT_PLACED', `article "${id}" is not placed in the flatplan (set status: spiked to exclude)`, art.file);
    else if (placedPages[id] !== art.meta.target_pages) add('warning', 'TARGET_PAGES', `article "${id}" target_pages=${art.meta.target_pages} but placed on ${placedPages[id]} page(s)`, art.file);
    for (const a of art.meta.assets ?? []) {
      if (!model.images[a.image]) add('error', 'MISSING_ASSET', `asset "${a.image}" listed in article "${id}" not found in images/`, art.file);
    }
  }
  for (const f of Object.keys(model.captions)) if (!model.images[f]) add('warning', 'CAPTION_ORPHAN', `caption for "${f}" but no such image`, 'captions/');
  for (const f of Object.keys(model.images)) if (!usedImages.has(f)) add('info', 'IMAGE_UNUSED', `image "${f}" is not used by any page`, 'images/');

  // --- text allocation estimate (authoritative overflow check is the DOM check in render/preflight)
  const { plan, unplacedText } = planText(model, reg, probe?.frames);
  for (const id of unplacedText) add('error', 'TEXT_NOT_PLACED', `article "${id}" has body text but no text-capable layout in the flatplan`, model.articles[id].file);
  for (const [e, p] of plan) {
    const where = `flatplan p${e.pages.join('-')}`;
    if (p.fill > 1.05) add('warning', 'TEXT_MAY_OVERFLOW', `body text on p${e.pages.join('-')} is estimated at ${Math.round(p.fill * 100)}% of its (measured) frame`, where);
    else if (!p.blocks.length) add('warning', 'TEXT_PAGE_EMPTY', `p${e.pages.join('-')} (${e.layout}) is a text layout but receives no body text; shorten the plan or add copy`, where);
    else if (p.fill < 0.35) add('warning', 'TEXT_PAGE_SPARSE', `body text on p${e.pages.join('-')} fills only ~${Math.round(p.fill * 100)}% of its frame`, where);
  }
  // structural overflow: the page already overflows WITHOUT body text (very long headline/caption, too many contents entries)
  for (const m of probe?.metrics ?? []) {
    const where = `p${m.n} ${m.layout}/${m.variant}`;
    if (m.toc_items && m.toc_items.fitting < m.toc_items.total) add('error', 'CONTENTS_OVERFLOW', `contents lists ${m.toc_items.total} entries but only ${m.toc_items.fitting} fit on this page (${m.layout}/${m.variant}). Use a more compact variant, set in_contents: false on minor articles, or shorten titles. Entries beyond ${m.toc_items.fitting} would be lost.`, where);
    else if (m.overflow.length || m.outside.length) add('error', 'LAYOUT_OVERFLOW', `content already overflows the page with no body text (long headline, deck or caption?): ${[...m.overflow.map((o) => `${o.el} clipped`), ...[...new Set(m.outside.map((o) => o.kind))]].join(', ')}`, where);
  }
  return out;
}

export const hasErrors = (findings) => findings.some((f) => f.level === 'error');

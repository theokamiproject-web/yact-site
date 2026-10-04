// Turn (model, flatplan entry) into component inputs; text allocation; helper queries.
import { allocate } from './text.mjs';
import { variantPages } from './registry.mjs';

export const CONTENT_TYPES = ['feature', 'interview', 'essay', 'photo-essay', 'column', 'profile'];

export function buildInputs(model, entry) {
  const a = model.articles[entry.article]?.meta ?? {};
  const assets = a.assets ?? [];
  const byRole = (...roles) => assets.filter((x) => roles.includes(x.role)).map((x) => x.image);
  const slots = entry.slots ?? {};
  const inputs = {
    issue: model.issue ?? {},
    toc: tocEntries(model),
    article: a,
    title: a.title,
    kicker: a.kicker,
    deck: a.deck,
    intro: a.intro,
    author: a.author,
    author_role: a.author_role,
    source: a.source,
    interviewee: a.interviewee,
    interviewee_role: a.interviewee_role,
    section: a.section,
    pull_quotes: a.pull_quotes ?? [],
    cover_lines: a.cover_lines ?? [],
    hero_image: byRole('hero')[0],
    portrait: byRole('portrait')[0],
    images: byRole('inline', 'sequence', 'transition'),
    ...slots,
  };
  inputs.pull_quote ??= inputs.pull_quotes[0];
  inputs.image ??= Array.isArray(inputs.images) ? inputs.images[0] : inputs.images;
  // `images` slot may be given as one string
  if (typeof inputs.images === 'string') inputs.images = [inputs.images];
  return inputs;
}

export const isEmpty = (v) => v === undefined || v === null || v === '' || (Array.isArray(v) && v.length === 0);

/** Image filenames referenced by component inputs (convention: hero_image, portrait, image, images[]). */
export function imageRefs(inputs) {
  const refs = [];
  for (const k of ['hero_image', 'portrait', 'image']) if (inputs[k]) refs.push(inputs[k]);
  for (const f of inputs.images ?? []) refs.push(f);
  return refs;
}

export function entriesOf(model) {
  return [...(model.flatplan?.pages ?? [])].sort((a, b) => a.pages[0] - b.pages[0]);
}

/** Sequentially allocate each article's body blocks across its text-capable entries. */
export function planText(model, registry) {
  const plan = new Map(); // entry -> {blocks, fill, capacity}
  const byArticle = new Map();
  for (const e of entriesOf(model)) {
    const c = registry.components[e.layout];
    if (!c?.text) continue;
    if (!byArticle.has(e.article)) byArticle.set(e.article, []);
    byArticle.get(e.article).push(e);
  }
  const unplaced = [];
  for (const [id, art] of Object.entries(model.articles)) {
    if (art.meta?.status === 'spiked') continue;
    const entries = byArticle.get(id) ?? [];
    if (!entries.length) {
      if (art.blocks.length) unplaced.push(id);
      continue;
    }
    const caps = entries.map((e) => {
      const c = registry.components[e.layout];
      return c.text.capacity(e.variant ?? c.defaultVariant, buildInputs(model, e));
    });
    const { pages, estimatedFill } = allocate(art.blocks, caps);
    entries.forEach((e, i) => plan.set(e, { blocks: pages[i], fill: estimatedFill[i], capacity: caps[i] }));
  }
  return { plan, unplacedText: unplaced };
}

export function pagesOf(entry, registry) {
  const c = registry.components[entry.layout];
  return c ? variantPages(c, entry.variant) : undefined;
}

/** Entries for the auto-generated contents page. */
export function tocEntries(model) {
  const seen = new Set();
  const out = [];
  for (const e of entriesOf(model)) {
    const a = model.articles[e.article]?.meta;
    if (!a || seen.has(e.article)) continue;
    if (a.in_contents === false || !(a.in_contents === true || CONTENT_TYPES.includes(a.type))) continue;
    seen.add(e.article);
    out.push({ id: e.article, page: e.pages[0], title: a.title, deck: a.deck, kicker: a.kicker, type: a.type, author: a.author });
  }
  return out;
}

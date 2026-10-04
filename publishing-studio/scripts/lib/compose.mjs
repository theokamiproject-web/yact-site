// Compose the Publication Model into one HTML book (one <section.page> per page) + page manifest.
import { loadRegistry, variantPages } from './registry.mjs';
import { buildInputs, entriesOf, tocEntries } from './inputs.mjs';
import { esc } from '../../layouts/_shared.mjs';

/** plan: Map(entry -> {blocks}) from planText; an empty Map composes the book without body text (layout probe). */
export async function compose(model, { plan = new Map() } = {}) {
  const reg = await loadRegistry();
  const toc = tocEntries(model);
  const issue = model.issue;
  const pages = [];

  for (const entry of entriesOf(model)) {
    const c = reg.components[entry.layout];
    const variant = entry.variant ?? c.defaultVariant;
    const inputs = buildInputs(model, entry);
    const text = plan.get(entry)?.blocks ?? [];
    const rendered = c.render({ inputs, variant, text, entry, model, pages: entry.pages });
    const expected = variantPages(c, variant);
    if (rendered.length !== expected) throw new Error(`${entry.layout}/${variant} returned ${rendered.length} page(s), contract says ${expected}`);
    const art = model.articles[entry.article].meta;
    rendered.forEach((r, i) => {
      const n = entry.pages[i];
      const p = typeof r === 'string' ? { html: r } : r;
      const chrome = p.chrome ?? 'full';
      const side = entry.pages.length === 2 || issue.binding !== 'none' ? (n % 2 === 0 ? 'left' : 'right') : 'solo';
      const runLeft = issue.running_header ?? issue.title;
      const runRight = art.section ?? art.title;
      const attrs = [
        `data-page="${n}"`, `data-side="${side}"`, `data-layout="${entry.layout}"`, `data-variant="${variant}"`,
        `data-article="${esc(entry.article)}"`, `data-chrome="${chrome}"`,
        entry.pages.length === 2 ? `data-spread="${entry.pages.join('-')}"` : '',
        p.bg ? `data-bg="${p.bg}"` : '', p.dark ? 'data-on="dark"' : '',
        entry.intentional_blank ? 'data-intentional-blank="true"' : '',
        `data-intensity="${entry.visual_intensity ?? ''}"`,
      ].filter(Boolean).join(' ');
      const runhead = chrome === 'full' ? `<div class="runhead">${esc(side === 'left' ? runLeft : runRight)}</div>` : '';
      const folio = chrome === 'none' ? '' : `<div class="folio" data-folio="${n}">${n}</div>`;
      pages.push({ n, layout: entry.layout, variant, article: entry.article, side, html: `<section class="page" ${attrs}>${p.html}${runhead}${folio}</section>` });
    });
  }
  pages.sort((a, b) => a.n - b.n);
  const html = `<!doctype html>
<html lang="${esc(issue.language)}">
<head>
<meta charset="utf-8">
<title>${esc(issue.title)}${issue.subtitle ? ` — ${esc(issue.subtitle)}` : ''}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; script-src 'none'; object-src 'none'; frame-src 'none'">
<link rel="stylesheet" href="css/theme.css">
<link rel="stylesheet" href="css/layouts.css">
<link rel="stylesheet" href="css/page-setup.css">
</head>
<body class="book" data-issue="${esc(model.id)}" data-pages="${issue.pages}">
${pages.map((p) => p.html).join('\n')}
</body>
</html>
`;
  return { html, pages: pages.map(({ html: _h, ...rest }) => rest), toc };
}

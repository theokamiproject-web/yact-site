// Helpers shared by layout components. Components return HTML strings only; they never touch the filesystem.
import { inline } from '../scripts/lib/text.mjs';
import { marked } from 'marked';

export const esc = (s) => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
export const has = (v) => !(v === undefined || v === null || v === '' || (Array.isArray(v) && !v.length));
export const when = (cond, html) => (cond ? html : '');

export function pos(model, file) {
  const f = model.imageMeta?.[file]?.focal;
  return Array.isArray(f) ? `${Math.round(f[0] * 100)}% ${Math.round(f[1] * 100)}%` : '50% 50%';
}
export function img(model, file, cls = '', style = '') {
  if (!file) return '';
  return `<img class="${cls}" src="images/${esc(file)}" alt="${esc(model.imageMeta?.[file]?.alt ?? model.captions?.[file]?.caption ?? '')}" data-image="${esc(file)}" style="object-position:${pos(model, file)};${style}">`;
}
export function captionHtml(model, file, cls = '') {
  const c = model.captions?.[file];
  if (!c?.caption) return '';
  return `<p class="caption ${cls}" data-caption-for="${esc(file)}">${esc(c.caption)}${c.credit ? `<span class="credit">${esc(c.credit)}</span>` : ''}</p>`;
}
/** <figure> with image + caption. `imgStyle` e.g. "height:60mm". */
export function fig(model, file, { cls = '', imgStyle = '', caption = true } = {}) {
  if (!file) return '';
  return `<figure class="fig ${cls}">${img(model, file, '', imgStyle)}${caption ? captionHtml(model, file) : ''}</figure>`;
}

export function blocksHtml(blocks) {
  return blocks.map((b) => {
    switch (b.type) {
      case 'h': return `<h3>${inline(b.md)}</h3>`;
      case 'q': return `<p class="q"><span class="qm">Q</span>${inline(b.md)}</p>`;
      case 'a': return `<p class="a">${inline(b.md)}</p>`;
      case 'quote': return `<blockquote>${inline(b.md)}</blockquote>`;
      case 'list': return marked.parse(b.md);
      default: return `<p${b.cont ? ' class="cont"' : ''}>${inline(b.md)}</p>`;
    }
  }).join('\n');
}
export const body = (blocks, cls = '') => `<div class="body ${cls}">${blocksHtml(blocks)}</div>`;
export const byline = (i) => when(has(i.author), `<p class="byline">${i.source ? `${esc(i.source)}　` : ''}文 <b>${esc(i.author)}</b>${i.author_role ? `　${esc(i.author_role)}` : ''}</p>`);


/**
 * Estimated characters that fit a text frame (full-width Japanese, 8.5pt on a 5.5mm baseline, base-theme margins).
 * Estimate only: the authoritative check is the DOM overflow/fill measurement (render + preflight).
 * w,h in mm; pass `i` (component inputs) so page size is honoured.
 */
export function frameChars({ w, h, cols = 1, gap = 4, fs = 8.5, lh = 5.5, eff = 1 }) {
  const cw = (w - (cols - 1) * gap) / cols;
  return Math.floor(cols * Math.floor(cw / (fs * 0.3528)) * Math.floor(h / lh) * eff);
}
export const liveBox = (i, { top = 16, bottom = 18, inner = 17, outer = 13 } = {}) => ({ w: (i.issue?.width ?? 148) - inner - outer, h: (i.issue?.height ?? 210) - top - bottom });

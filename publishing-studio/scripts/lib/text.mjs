// Article body -> blocks, and sequential allocation of blocks to pages by character budget.
import { Marked } from 'marked';

/**
 * Manuscript Markdown is UNTRUSTED input. Allowed output elements: p h3 strong em del code br ul ol li blockquote.
 * Raw HTML is escaped and shown as text, images are dropped (use the images/ folder + assets), links print as plain text.
 * Nothing in a manuscript can emit script, style, iframe, object, embed, event-handler attributes or a URL.
 */
const escapeHtml = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
export const safeMarked = new Marked({
  renderer: {
    html: ({ text }) => escapeHtml(text),
    image: () => '',
    link(token) { return this.parser.parseInline(token.tokens); },
  },
});
export const ALLOWED_ELEMENTS = ['p', 'h3', 'strong', 'em', 'del', 'code', 'br', 'ul', 'ol', 'li', 'blockquote'];

/** What a manuscript contains that the sanitiser will neutralise (for validation messages). */
export function scanMarkdown(body) {
  const found = { html: 0, images: 0, links: 0 };
  const walk = (tokens) => { for (const t of tokens ?? []) { if (t.type === 'html') found.html++; if (t.type === 'image') found.images++; if (t.type === 'link') found.links++; walk(t.tokens); walk(t.items); } };
  walk(safeMarked.lexer(body || ''));
  return found;
}

const strip = (s) => s.replace(/[*_`~]/g, '').replace(/\[(.*?)\]\(.*?\)/g, '$1');
export const charLen = (s) => [...strip(s)].length;

/** Parse markdown body into blocks: {type: p|h|q|a|quote|list, md} */
export function parseBlocks(body) {
  const tokens = safeMarked.lexer(body || '');
  const blocks = [];
  for (const t of tokens) {
    if (t.type === 'space') continue;
    if (t.type === 'heading') blocks.push({ type: 'h', md: t.text, depth: t.depth });
    else if (t.type === 'blockquote') blocks.push({ type: 'quote', md: t.text.replace(/^>\s?/gm, '').trim() });
    else if (t.type === 'list') blocks.push({ type: 'list', md: t.raw.trim() });
    else if (t.type === 'paragraph') {
      const m = t.text.match(/^(Q|Ｑ|質問|A|Ａ|回答)[:：]\s*([\s\S]*)$/);
      if (m && /^(Q|Ｑ|質問)$/.test(m[1])) blocks.push({ type: 'q', md: m[2].trim() });
      else if (m) blocks.push({ type: 'a', md: m[2].trim() });
      else blocks.push({ type: 'p', md: t.text.trim() });
    } else blocks.push({ type: 'p', md: (t.raw || '').trim() });
  }
  return blocks;
}

/** Lines available in a measured frame, and characters per line. Columns flow continuously; one line of slack per column (multi-column). */
/**
 * Phrase-based line breaking (word-break: auto-phrase) and kinsoku push a few percent of characters to the next line,
 * so a line is assumed to hold LINE_EFFICIENCY of its theoretical characters. Calibrated on the example issues; the
 * measured text occupancy (metrics) is the authority and a test keeps every sample below 100 %.
 */
export const LINE_EFFICIENCY = 0.96;

export function frameLines(f) {
  const colW = (f.w - (f.cols - 1) * f.gap) / f.cols;
  const perLine = Math.max(1, Math.floor((colW / f.fs) * LINE_EFFICIENCY));
  const perCol = Math.floor(f.h / f.lh);
  return { perLine, lines: Math.max(0, f.cols * perCol - (f.cols > 1 ? f.cols : 0)), capacityChars: Math.max(0, f.cols * perCol * perLine) };
}

/** Lines a block occupies when set in `perLine` characters per line (first-line indent of 1em on plain paragraphs). */
export function blockLines(b, perLine) {
  const n = charLen(b.md);
  switch (b.type) {
    case 'h': return Math.ceil(n / perLine) + 1; // heading + its spacing (one baseline)
    case 'q': return Math.ceil((n + 2) / Math.max(1, perLine - 2)) + 0.5; // hanging "Q" label + space above
    case 'a': return Math.ceil(n / perLine);
    case 'quote': return Math.ceil(n / Math.max(1, perLine - 2)) + 1;
    case 'list': return Math.ceil(n / perLine) + 1;
    default: return Math.ceil((n + (b.cont ? 0 : 1)) / perLine);
  }
}

/** Plain-paragraph sentence split (Japanese full stops, ! ?). */
function splitSentences(md) {
  return md.match(/[^。！？!?]+[。！？!?」』）)]*|[^。！？!?]+$/g) || [md];
}

/**
 * Allocate blocks to pages. `frames` = measured frame per page (see layout probe). The last page takes the remainder.
 * A plain paragraph may be split at a sentence boundary; the continuation is flagged `cont`. A question never ends a page
 * without its answer. Returns {pages: Block[][], estimatedFill: number[] (used lines / frame lines), leftover}.
 */
export function allocate(blocks, frames) {
  const queue = blocks.map((b) => ({ ...b }));
  const pages = [];
  const fill = [];
  frames.forEach((f, i) => {
    const { perLine, lines } = frameLines(f);
    const out = [];
    let used = 0;
    const last = i === frames.length - 1;
    while (queue.length) {
      const b = queue[0];
      const need = blockLines(b, perLine);
      const needWithAnswer = need + (b.type === 'q' && queue[1]?.type === 'a' ? blockLines(queue[1], perLine) : 0);
      if (last || used + needWithAnswer <= lines) {
        out.push(queue.shift());
        used += need;
        continue;
      }
      if (b.type === 'p' && lines - used >= 3) {
        const sents = splitSentences(b.md);
        let take = '';
        let k = 0;
        while (k < sents.length && used + blockLines({ ...b, md: take + sents[k] }, perLine) <= lines) take += sents[k++];
        if (take && k < sents.length) {
          out.push({ ...b, md: take.trim() });
          queue[0] = { ...b, md: sents.slice(k).join('').trim(), cont: true };
          used += blockLines({ ...b, md: take }, perLine);
        }
      }
      break;
    }
    pages.push(out);
    fill.push(lines ? used / lines : 0);
  });
  return { pages, estimatedFill: fill, leftover: queue };
}

export const inline = (md) => safeMarked.parseInline(md ?? '');
export const renderBlock = (md) => safeMarked.parse(md ?? '');

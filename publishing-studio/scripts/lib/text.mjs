// Article body -> blocks, and sequential allocation of blocks to pages by character budget.
import { marked } from 'marked';

const strip = (s) => s.replace(/[*_`~]/g, '').replace(/\[(.*?)\]\(.*?\)/g, '$1');
export const charLen = (s) => [...strip(s)].length;

/** Parse markdown body into blocks: {type: p|h|q|a|quote|list, md} */
export function parseBlocks(body) {
  const tokens = marked.lexer(body || '');
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

// cost of a block beyond its characters, in chars-of-line-capacity (half a line lost per paragraph, headings add spacing)
const OVERHEAD = { p: 10, h: 40, q: 14, a: 10, quote: 30, list: 20 };
export const blockCost = (b) => charLen(b.md) + (OVERHEAD[b.type] ?? 20);

function splitSentences(md) {
  return md.match(/[^。！？!?]+[。！？!?」』）)]*|[^。！？!?]+$/g) || [md];
}

/**
 * Allocate blocks to pages. caps = capacity (chars) per page. The last page takes the remainder.
 * A plain paragraph may be split at a sentence boundary; the continuation is flagged `cont`.
 * Returns {pages: Block[][], estimatedFill: number[]}
 */
export function allocate(blocks, caps) {
  const queue = blocks.map((b) => ({ ...b }));
  const pages = [];
  const fill = [];
  caps.forEach((cap, i) => {
    const out = [];
    let used = 0;
    const last = i === caps.length - 1;
    while (queue.length) {
      const b = queue[0];
      // never strand a question at the foot of a page: it travels with its answer
      const cost = blockCost(b);
      const needed = cost + (b.type === 'q' && queue[1]?.type === 'a' ? blockCost(queue[1]) : 0);
      if (last || used + needed <= cap) {
        out.push(queue.shift());
        used += cost;
        continue;
      }
      if (b.type === 'p' && cap - used >= 90) {
        const sents = splitSentences(b.md);
        let take = '';
        let k = 0;
        while (k < sents.length && used + charLen(take + sents[k]) + OVERHEAD.p <= cap) take += sents[k++];
        if (take && k < sents.length) {
          out.push({ ...b, md: take.trim() });
          queue[0] = { ...b, md: sents.slice(k).join('').trim(), cont: true };
          used += charLen(take) + OVERHEAD.p;
        }
      }
      break;
    }
    pages.push(out);
    fill.push(used / cap);
  });
  return { pages, estimatedFill: fill, leftover: queue };
}

export const inline = (md) => marked.parseInline(md ?? '');

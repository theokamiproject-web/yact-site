import test from 'node:test';
import assert from 'node:assert/strict';
import { allocate, blockLines, frameLines, parseBlocks, charLen } from '../scripts/lib/text.mjs';
import { frameChars } from '../scripts/lib/inputs.mjs';

const frame = (o = {}) => ({ w: 60, h: 55, cols: 1, gap: 0, fs: 3, lh: 5.5, ...o }); // 20 chars/line, 10 lines
const P = (n, extra = {}) => ({ type: 'p', md: 'あ'.repeat(n), ...extra });

test('frame capacity comes from measured geometry (chars/line x lines x columns)', () => {
  // 20 theoretical chars/line x LINE_EFFICIENCY 0.96 (phrase breaking / kinsoku) -> 19
  assert.deepEqual(frameLines(frame()), { perLine: 19, lines: 10, capacityChars: 190 });
  assert.equal(frameChars(frame({ cols: 2, w: 124, gap: 4 })), 2 * 10 * 19);
  assert.equal(frameChars(frame({ h: 2 })), 0);
});

test('multi-column frames: usable lines are columns x lines minus one slack line per column', () => {
  assert.equal(frameLines(frame({ cols: 2, w: 124, gap: 4 })).lines, 18);
  // 2 columns x 10 lines hold 18 lines of text: a 19-line article overflows page 1 into page 2
  const blocks = Array.from({ length: 19 }, () => ({ type: 'a', md: 'あ'.repeat(19) })); // one full line each
  const { pages } = allocate(blocks, [frame({ cols: 2, w: 124, gap: 4 }), frame({ h: 200 })]);
  assert.equal(pages[0].length, 18);
  assert.equal(pages[1].length, 1);
});

test('allocation: fills page 1 first, remainder goes on; the last page takes everything left', () => {
  const blocks = [P(60), P(60), P(60), P(60)]; // 3.05 lines each -> 4 lines each (indent)
  const { pages } = allocate(blocks, [frame(), frame()]);
  assert.equal(pages.flat().length, 4);
  assert.ok(pages[0].length >= 2 && pages[1].length >= 1);
});

test('a paragraph is split at a sentence boundary, continuation flagged `cont`', () => {
  const para = { type: 'p', md: `${'あ'.repeat(30)}。${'い'.repeat(30)}。${'う'.repeat(30)}。` };
  const { pages } = allocate([para], [frame({ h: 16.5 }), frame({ h: 200 })]);
  assert.ok(pages[0].length === 1 && pages[1].length === 1);
  assert.equal(pages[1][0].cont, true);
  assert.equal(charLen(pages[0][0].md) + charLen(pages[1][0].md), charLen(para.md));
});

test('a question never ends a page without its answer (Q&A orphan rule)', () => {
  const blocks = [P(150), { type: 'q', md: 'あ'.repeat(10) }, { type: 'a', md: 'い'.repeat(100) }];
  const { pages } = allocate(blocks, [frame({ h: 55 }), frame({ h: 200 })]);
  assert.equal(pages[0].some((b) => b.type === 'q'), false, 'Q moved with its A to the next page');
  assert.equal(pages[1][0].type, 'q');
  assert.equal(pages[1][1].type, 'a');
});

test('block cost model: line counts follow the measure', () => {
  assert.equal(blockLines(P(20), 20), 2); // 20 chars + 1 em indent -> 2 lines
  assert.equal(blockLines(P(19), 20), 1);
  assert.equal(blockLines(P(20, { cont: true }), 20), 1);
  assert.equal(blockLines({ type: 'h', md: 'あ' }, 20), 2);
});

test('parseBlocks: Q:/A: labels, headings, and no HTML survives', () => {
  const b = parseBlocks('## 見出し\n\nQ: 質問\n\nA: 回答\n\n本文\n\n<div>x</div>');
  assert.deepEqual(b.map((x) => x.type), ['h', 'q', 'a', 'p', 'p']);
  assert.equal(b[2].md, '回答');
});

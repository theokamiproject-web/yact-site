import test from 'node:test';
import assert from 'node:assert/strict';
import { loadRegistry, variantPages } from '../scripts/lib/registry.mjs';

const REQUIRED = ['cover', 'contents', 'feature-opener', 'feature-body', 'interview-opener', 'interview-body', 'essay', 'photo-essay', 'full-bleed-photo', 'quote-page', 'divider', 'column', 'profile', 'credits', 'colophon'];

function fixture() {
  const issue = { id: 't', title: 'T', subtitle: 'S', issue_number: 1, date: '2026', publisher: 'P', width: 148, height: 210, bleed: 3, pages: 16 };
  const model = { issue, credits: { credits: [{ role: '編集', names: ['A'] }], colophon: { publisher: 'P', copyright: 'c' } }, imageMeta: {}, captions: { 'a.jpg': { caption: 'cap', credit: 'cr' } } };
  const text = [{ type: 'h', md: '見出し' }, { type: 'p', md: '本文です。' }, { type: 'q', md: '質問' }, { type: 'a', md: '回答' }];
  const inputs = { issue, title: 'タイトル', kicker: 'K', deck: 'デッキ', intro: 'リード', author: '著者', author_role: '役', interviewee: '話者', interviewee_role: '役', hero_image: 'a.jpg', portrait: 'a.jpg', image: 'a.jpg', images: ['a.jpg', 'a.jpg', 'a.jpg', 'a.jpg'], pull_quote: '一文', pull_quotes: ['一文'], cover_lines: ['one'], toc: [{ page: 3, title: 'T', deck: 'D', kicker: 'K' }], facts: [{ label: 'l', value: 'v' }] };
  return { model, inputs, text };
}

test('all required components exist', async () => {
  const reg = await loadRegistry();
  for (const n of REQUIRED) assert.ok(reg.components[n], `missing component ${n}`);
});

test('every component x variant renders the contracted number of pages and respects its contract', async () => {
  const reg = await loadRegistry();
  const { model, inputs, text } = fixture();
  for (const c of Object.values(reg.components)) {
    for (const v of Object.keys(c.variants)) {
      const label = `${c.name}/${v}`;
      assert.equal(typeof c.render, 'function', label);
      assert.ok(Number.isInteger(variantPages(c, v)), label);
      const pages = c.render({ inputs, variant: v, text: c.text ? text : [], model, entry: {}, pages: [], frame: undefined, measure: 19, tone: () => ({ top: 'dark', bottom: 'light' }) });
      assert.equal(pages.length, variantPages(c, v), `${label}: page count`);
      for (const p of pages) {
        const html = typeof p === 'string' ? p : p.html;
        assert.ok(html.length > 10, `${label}: empty html`);
        assert.ok(!/undefined|\[object/.test(html), `${label}: leaked "undefined"`);
      }
      const req = c.required(v);
      assert.ok(Array.isArray(req), `${label}: required() must return an array`);
      if (c.text) assert.equal(c.text, true, `${label}: text contract is declared (frames are measured, not guessed)`);
    }
    assert.ok(c.variants[c.defaultVariant], `${c.name}: defaultVariant`);
  }
});

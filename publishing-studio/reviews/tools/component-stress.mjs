// RC1: render every component x variant under stress inputs (static check: throws / undefined / NaN / [object).
import { loadRegistry, variantPages } from '../../scripts/lib/registry.mjs';
const reg = await loadRegistry();
const issue = { id: 't', title: 'T', issue_number: 1, width: 148, height: 210, bleed: 3, pages: 16 }; // no subtitle/date/publisher
const longT = 'とても長い見出し'.repeat(20);
const blocks = (n, len) => Array.from({ length: n }, (_, i) => ({ type: i % 5 === 0 ? 'h' : 'p', md: '本文'.repeat(len) }));
const model = (cap = true) => ({ issue, credits: {}, imageMeta: {}, captions: cap ? { 'a.jpg': { caption: 'c' } } : {} });
const full = { issue, title: 'タイトル', kicker: 'K', deck: 'D', intro: 'I', author: 'A', author_role: 'R', interviewee: 'X', interviewee_role: 'Y', hero_image: 'a.jpg', portrait: 'a.jpg', image: 'a.jpg', images: ['a.jpg', 'a.jpg', 'a.jpg', 'a.jpg'], pull_quote: 'Q', pull_quotes: ['Q'], cover_lines: ['x'], toc: [], facts: [] };
const scenarios = {
  'required-only': (c, v) => { const i = { issue, toc: [], pull_quotes: [], images: [], cover_lines: [] }; for (const k of c.required(v)) i[k] = full[k]; return { inputs: i, text: [], model: model() }; },
  'no-optional-no-caption': (c, v) => ({ inputs: { ...full, kicker: undefined, deck: undefined, intro: undefined, author: undefined, cover_lines: [] }, text: [], model: model(false) }),
  'very-long-strings': (c, v) => ({ inputs: { ...full, title: longT, deck: longT, intro: longT, kicker: longT, author: longT, interviewee: longT, pull_quote: longT, cover_lines: [longT, longT, longT, longT] }, text: [], model: model() }),
  'huge-text': (c, v) => ({ inputs: full, text: blocks(60, 200), model: model() }),
  'empty-text': (c, v) => ({ inputs: full, text: [], model: model() }),
  'toc-100-entries': (c, v) => ({ inputs: { ...full, toc: Array.from({ length: 100 }, (_, i) => ({ page: i, title: longT, deck: longT, kicker: 'K' })) }, text: [], model: model() }),
  'html-in-strings': (c, v) => ({ inputs: { ...full, title: '<b>&"\'</b>', deck: '<script>1</script>', pull_quote: '"><img src=x>' }, text: [], model: model() }),
};
const bad = [];
let n = 0;
for (const c of Object.values(reg.components)) for (const v of Object.keys(c.variants)) for (const [sn, mk] of Object.entries(scenarios)) {
  n++;
  try {
    const a = mk(c, v);
    const out = c.render({ ...a, variant: v, entry: {}, pages: [] });
    if (out.length !== variantPages(c, v)) bad.push(`${c.name}/${v} [${sn}]: wrong page count`);
    const html = out.map((p) => (typeof p === 'string' ? p : p.html)).join('');
    if (/undefined|NaN|\[object/.test(html)) bad.push(`${c.name}/${v} [${sn}]: leaked ${html.match(/undefined|NaN|\[object/)[0]}`);
    if (sn === 'html-in-strings' && /<script>1|<img src=x>/.test(html.replace(/&lt;/g, ''))) bad.push(`${c.name}/${v} [${sn}]: UNESCAPED html in a metadata field`);
  } catch (e) { bad.push(`${c.name}/${v} [${sn}]: THROWS ${e.message.slice(0, 80)}`); }
}
console.log(`${n} renders (${Object.keys(reg.components).length} components, ${Object.values(reg.components).reduce((a, c) => a + Object.keys(c.variants).length, 0)} variants x ${Object.keys(scenarios).length} scenarios); problems: ${bad.length}`);
console.log(bad.join('\n'));

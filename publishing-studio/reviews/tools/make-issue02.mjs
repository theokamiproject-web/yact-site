// RC1: builds issues/test-issue-02 (B5, 24p, photo-led, short pieces). Sample DATA only; uses existing components as-is.
import fs from 'node:fs';
import path from 'node:path';
import sharp from 'sharp';
import * as yaml from 'js-yaml';

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '../../issues/test-issue-02');
fs.rmSync(root, { recursive: true, force: true });
for (const d of ['articles', 'images', 'captions', 'notes']) fs.mkdirSync(path.join(root, d), { recursive: true });
const w = (f, s) => fs.writeFileSync(path.join(root, f), s);
const Y = (o) => yaml.dump(o, { lineWidth: 200 });

// ---- images: procedural city/street "photographs" (different look from issue 01)
function rng(seed) { let s = seed; return () => ((s = (s * 1103515245 + 12345) % 2147483648) / 2147483648); }
function city(wpx, hpx, seed, pal) {
  const r = rng(seed);
  let bld = '';
  const n = 14;
  for (let i = 0; i < n; i++) {
    const bw = wpx / n * (0.9 + r() * 0.7), bx = i * (wpx / n) - 10, bh = hpx * (0.18 + r() * 0.42);
    bld += `<rect x="${bx}" y="${hpx * 0.78 - bh}" width="${bw}" height="${bh + hpx}" fill="${pal.b[i % pal.b.length]}"/>`;
    for (let k = 0; k < 6; k++) bld += `<rect x="${bx + bw * (0.15 + r() * 0.6)}" y="${hpx * 0.78 - bh + bh * r() * 0.9}" width="${bw * 0.08}" height="${bh * 0.05}" fill="${pal.w}" opacity="${0.4 + r() * 0.5}"/>`;
  }
  return Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="${wpx}" height="${hpx}"><defs><linearGradient id="s" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${pal.s[0]}"/><stop offset="1" stop-color="${pal.s[1]}"/></linearGradient></defs><rect width="${wpx}" height="${hpx}" fill="url(#s)"/>${bld}<rect y="${hpx * 0.78}" width="${wpx}" height="${hpx * 0.22}" fill="${pal.g}" opacity="0.85"/></svg>`);
}
const P = {
  a: { s: ['#f3d9b1', '#e98f6b'], b: ['#3b2f3a', '#2a2330', '#4a3a45'], w: '#ffe9a8', g: '#2a2330' },
  b: { s: ['#9fc5d6', '#e8f1f2'], b: ['#35505c', '#27424e', '#486572'], w: '#ffffff', g: '#27424e' },
  c: { s: ['#2a2d4a', '#7a5c8c'], b: ['#14152a', '#1d1f3a', '#101126'], w: '#ffd36b', g: '#101126' },
  d: { s: ['#d9e6c3', '#a8c58a'], b: ['#40523a', '#2f3f2b', '#546a4b'], w: '#f5f5dc', g: '#2f3f2b' },
};
const imgs = [
  ['cover.jpg', 1500, 2100, 1, 'c'], ['street-spread.jpg', 2950, 2100, 2, 'a'], ['shore.jpg', 2950, 1500, 3, 'b'],
  ['seq-1.jpg', 1400, 1000, 4, 'a'], ['seq-2.jpg', 1000, 1000, 5, 'd'], ['seq-3.jpg', 1000, 1000, 6, 'b'], ['seq-4.jpg', 1500, 1000, 7, 'c'],
  ['full-single.jpg', 1500, 2100, 8, 'd'], ['grid-1.jpg', 1500, 2100, 9, 'b'], ['grid-2.jpg', 1400, 1000, 10, 'a'], ['grid-3.jpg', 1400, 1000, 11, 'c'],
  ['person-a.jpg', 900, 1200, 12, 'a'], ['person-b.jpg', 1400, 900, 13, 'd'], ['person-c.jpg', 900, 900, 14, 'b'],
];
for (const [f, wpx, hpx, seed, p] of imgs) await sharp(city(wpx, hpx, seed, P[p])).blur(0.5).jpeg({ quality: 76, mozjpeg: true }).withMetadata({ density: 300 }).toFile(path.join(root, 'images', f));
w('images/images.yaml', Y(Object.fromEntries(imgs.map(([f, wpx, hpx]) => [f, { orientation: wpx > hpx ? 'landscape' : wpx < hpx ? 'portrait' : 'square' }]))));
const cap = (t) => ({ caption: t, credit: '写真＝サンプル画像' });
w('captions/captions.yaml', Y({
  'street-spread.jpg': cap('朝の商店街。シャッターが上がる前の静けさ。'), 'shore.jpg': cap('河口の護岸から見た街並み。'),
  'seq-1.jpg': cap('駅前、午前七時。'), 'seq-2.jpg': cap('路地の角。'), 'seq-3.jpg': cap('橋の下の光。'), 'seq-4.jpg': cap('夜の窓。'),
  'full-single.jpg': cap('丘の上から。'), 'grid-1.jpg': cap('川沿いの夕暮れ。'), 'grid-2.jpg': cap('屋根の連なり。'), 'grid-3.jpg': cap('夜の始まり。'),
  'person-a.jpg': cap('パン屋の店主・七海さん。'), 'person-b.jpg': cap('古書店の店主・松原さん。'), 'person-c.jpg': cap('写真館三代目・河野さん。'),
}));

w('issue.yaml', Y({ id: 'test-issue-02', title: 'TEST ISSUE 02', subtitle: '朝と夜のあいだ', issue_number: 2, date: '2026年11月', publisher: '架空の編集室', theme: 'base', theme_overrides: { '--color-accent': '#2f6f5e', '--color-accent-2': '#3a2f4a' }, format: 'B5', width: 182, height: 257, pages: 24, binding: 'saddle-stitch', bleed: 3, language: 'ja', running_header: 'TEST ISSUE 02' }));
w('editorial.yaml', Y({ concept: '街の一日を、短い断片と写真で並べる写真主導のZINE。長い文章は置かない。', audience: '通勤・通学の合間に開く20〜40代。', editorial_voice: '短く、断定しすぎない。', mood: '朝の光、乾いた空気、夜の窓', pacing: 'fast', density: 'low', keywords: ['街', '朝', '夜', '断片'], fingerprint_target: { max_same_layout_run: 2, max_consecutive_image_heavy: 3, min_intensity_range: 40, max_opener_repeat: 3, min_quiet_pages: 2 } }));
w('credits.yaml', Y({ credits: [{ role: '編集', names: ['架空 太郎'] }, { role: '写真', names: ['サンプル画像（SVG生成）'] }, { role: '協力', names: ['七海', '松原', '河野'] }], colophon: { published: '2026年11月1日', publisher: '架空の編集室', editor: '架空 太郎', printer: 'テスト印刷所（架空）', price: '非売品' } }));
w('notes/README.md', 'TEST ISSUE 02: 構造の異なる第二サンプル（B5/24p/写真主導/短文）。Publishing Studio の汎用性検証用。\n');

const art = (id, meta, body = '') => w(`articles/${id}.md`, `---\n${Y({ id, status: 'ready', priority: 3, target_pages: 1, ...meta })}---\n${body}`);
art('cover', { title: '表紙', type: 'cover', priority: 1, in_contents: false, assets: [{ image: 'cover.jpg', role: 'hero' }], cover_lines: ['朝と夜のあいだ', '七つの短い断片'] });
art('contents', { title: '目次', type: 'contents', in_contents: false });
art('preface', { title: 'はじめに', kicker: 'PREFACE', type: 'column', author: '架空 太郎', section: 'はじめに' }, '朝の駅前と、夜の窓。そのあいだにある街の時間を、写真と短い言葉で並べました。\n\nどこから開いても読めます。\n');
art('street-spread', { title: '朝の商店街', type: 'photo-essay', priority: 1, target_pages: 2, section: '朝の商店街', assets: [{ image: 'street-spread.jpg', role: 'hero' }] });
art('divider-1', { title: '朝', kicker: 'CHAPTER 1', deck: '開店前の街。', type: 'divider', in_contents: false });
art('quote-a', { title: '引用A', type: 'quote', in_contents: false, author: '七海', pull_quotes: ['朝いちばんに焼けるのは、いつも同じパン。'] });
art('shore', { title: '河口', kicker: 'PHOTO', type: 'photo-essay', target_pages: 2, section: '河口', assets: [{ image: 'shore.jpg', role: 'sequence' }] });
art('profile-a', { title: '七海 ひな', deck: 'パン屋の店主', type: 'profile', section: '人物', author_role: '店主', assets: [{ image: 'person-a.jpg', role: 'portrait' }] }, '朝四時に店を開ける。常連は十二人。最初のお客は、いつも同じ新聞配達の青年だという。\n');
art('quote-b', { title: '引用B', type: 'quote', in_contents: false, author: '松原', pull_quotes: ['古い本は、前の持ち主の時間も連れてくる。'] });
art('sequence', { title: '路地と橋', kicker: 'PHOTO', type: 'photo-essay', target_pages: 2, section: '路地と橋', assets: ['seq-1.jpg', 'seq-2.jpg', 'seq-3.jpg', 'seq-4.jpg'].map((image) => ({ image, role: 'sequence' })) });
art('note-a', { title: '路地メモ', kicker: 'NOTE', type: 'column', author: '架空 太郎', section: 'メモ' }, '路地は、地図に載らない近道。\n\n歩くと七分、走ると三分。自転車は押す。\n');
art('full-single', { title: '丘の上', type: 'photo-essay', section: '丘の上', assets: [{ image: 'full-single.jpg', role: 'hero' }] });
art('divider-2', { title: '夜', kicker: 'CHAPTER 2', deck: '窓の明かりが増える頃。', type: 'divider', in_contents: false });
art('profile-b', { title: '松原 悟', deck: '古書店の店主', type: 'profile', section: '人物', assets: [{ image: 'person-b.jpg', role: 'portrait' }] }, '駅裏の古書店を三十一年。店の奥には、売らない本だけの棚がある。\n');
art('grid-set', { title: '夕暮れから夜へ', kicker: 'PHOTO', type: 'photo-essay', target_pages: 2, section: '夕暮れから夜へ', assets: ['grid-1.jpg', 'grid-2.jpg', 'grid-3.jpg'].map((image) => ({ image, role: 'sequence' })) });
art('mini-interview', { title: '三代目は急がない', kicker: 'INTERVIEW', deck: '河野写真館', type: 'interview', author: '架空 太郎', interviewee: '河野 あき', interviewee_role: '写真館三代目', section: 'ひと言インタビュー', assets: [{ image: 'person-c.jpg', role: 'portrait' }] }, 'Q: 一日に何枚撮りますか。\n\nA: 多い日で三枚。少ない日はゼロです。\n\nQ: 続ける理由は。\n\nA: 夜に窓の明かりがついているのを見ると、まだ撮れる気がします。\n');
art('quote-c', { title: '引用C', type: 'quote', in_contents: false, author: '河野', pull_quotes: ['急がないと、街が見えてくる。'] });
art('note-b', { title: 'あとがき', kicker: 'AFTERWORD', type: 'column', author: '架空 太郎', section: 'あとがき' }, '読み終えたら、いつもの道を一本だけ違う道で帰ってみてください。\n');
art('credits', { title: 'クレジット', type: 'credits', in_contents: false, status: 'spiked' });
art('colophon', { title: '奥付', type: 'colophon', in_contents: false });
art('back-cover', { title: '裏表紙', type: 'back-cover', in_contents: false, deck: '朝と夜のあいだ' });

const E = (pages, article, layout, variant, v, t, i, extra = {}) => ({ pages, article, layout, variant, visual_intensity: v, text_density: t, image_density: i, ...extra });
w('flatplan.yaml', Y({ pages: [
  E([1], 'cover', 'cover', 'split', 5, 1, 4), E([2], 'contents', 'contents', 'large', 2, 3, 1), E([3], 'preface', 'column', 'plain', 2, 2, 1),
  E([4, 5], 'street-spread', 'full-bleed-photo', 'spread', 5, 1, 5, { slots: {} }), E([6], 'divider-1', 'divider', 'ink', 4, 1, 1), E([7], 'quote-a', 'quote-page', 'center', 2, 1, 1),
  E([8, 9], 'shore', 'photo-essay', 'wide-single', 4, 1, 4), E([10], 'profile-a', 'profile', 'card', 2, 3, 3), E([11], 'quote-b', 'quote-page', 'left-rule', 2, 1, 1),
  E([12, 13], 'sequence', 'photo-essay', 'sequence-4', 4, 1, 5), E([14], 'note-a', 'column', 'box', 2, 2, 1), E([15], 'full-single', 'full-bleed-photo', 'single', 5, 1, 5),
  E([16], 'divider-2', 'divider', 'accent', 4, 1, 1), E([17], 'profile-b', 'profile', 'wide', 3, 3, 3), E([18, 19], 'grid-set', 'photo-essay', 'grid-3', 5, 1, 5),
  E([20], 'mini-interview', 'interview-opener', 'big-quote', 3, 3, 2), E([21], 'quote-c', 'quote-page', 'color-block', 4, 1, 1), E([22], 'note-b', 'column', 'plain', 1, 2, 1),
  E([23], 'colophon', 'colophon', 'with-credits', 1, 3, 1), E([24], 'back-cover', 'cover', 'back', 3, 1, 1),
] }));
console.log('wrote', root);

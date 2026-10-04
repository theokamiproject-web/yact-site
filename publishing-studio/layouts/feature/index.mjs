import { esc, img, fig, captionHtml, body, byline, when, has, frameChars, liveBox } from '../_shared.mjs';

const head = (i, cls = '') => `${when(i.kicker, `<p class="kicker">${esc(i.kicker)}</p>`)}<h1 class="fo-title ${cls}">${esc(i.title)}</h1>${when(i.deck, `<p class="deck fo-deck">${esc(i.deck)}</p>`)}`;

export default {
  family: 'feature',
  components: {
    'feature-opener': {
      variants: { 'hero-top': { pages: 1 }, 'title-over': { pages: 1 }, 'spread-bleed': { pages: 2 } },
      defaultVariant: 'hero-top',
      required: () => ['title', 'deck', 'hero_image'],
      optional: ['kicker', 'author', 'intro'],
      captions: true,
      render({ inputs: i, variant, model }) {
        if (variant === 'hero-top') {
          return [{ html: `<div class="fo-hero">${img(model, i.hero_image)}</div><div class="fo-herocap">${captionHtml(model, i.hero_image)}</div>
<div class="live fo-ht"><div class="c-all">${head(i)}</div>${when(i.intro, `<p class="lead c-1-4 fo-intro">${esc(i.intro)}</p>`)}<div class="c-all">${byline(i)}</div></div>` }];
        }
        if (variant === 'title-over') {
          return [{ dark: true, html: `<div class="bleed">${img(model, i.hero_image)}</div><div class="bleed fo-shade"></div>
<div class="live fo-to on-dark"><div class="c-all">${head(i)}</div><div class="c-all">${byline(i)}</div></div>
<div class="fo-vcap on-dark">${captionHtml(model, i.hero_image)}</div>` }];
        }
        const half = (side) => `<div class="fo-sp fo-sp-${side}">${img(model, i.hero_image, '', '')}</div>`;
        return [
          { dark: false, html: `${half('l')}<div class="live fo-spl"><div class="c-all">${head(i, 'fo-title-sp')}</div></div>` },
          { html: `${half('r')}<div class="live fo-spr">${when(i.intro, `<p class="lead c-all fo-intro">${esc(i.intro)}</p>`)}<div class="c-all">${byline(i)}</div><div class="c-all fo-spcap">${captionHtml(model, i.hero_image)}</div></div>` },
        ];
      },
    },

    'feature-body': {
      variants: { 'two-col': { pages: 1 }, 'two-col-image': { pages: 1 }, pullquote: { pages: 1 } },
      defaultVariant: 'two-col',
      required: (v) => (v === 'two-col-image' ? ['image'] : v === 'pullquote' ? ['pull_quote'] : []),
      optional: ['image', 'pull_quote'],
      captions: true,
      text: { capacity: (v, i) => { const b = liveBox(i); return frameChars({ w: b.w, h: { 'two-col': b.h, 'two-col-image': b.h - 77, pullquote: b.h - 36 }[v], cols: 2 }); } },
      render({ inputs: i, variant, text, model }) {
        if (variant === 'two-col') return [{ html: `<div class="live fb"><div class="fb-text c-all fit cols-2">${body(text)}</div></div>` }];
        if (variant === 'two-col-image') {
          return [{ html: `<div class="live fb fb-img-rows"><div class="c-all">${fig(model, i.image, { imgStyle: 'height:62mm' })}</div><div class="fb-text c-all fit cols-2">${body(text)}</div></div>` }];
        }
        return [{ html: `<div class="live fb fb-pq-rows"><p class="pullquote c-all fb-pq">${esc(i.pull_quote)}</p><div class="fb-text c-all fit cols-2">${body(text)}</div></div>` }];
      },
    },
  },
};

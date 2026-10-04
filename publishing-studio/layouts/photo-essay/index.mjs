import { esc, img, captionHtml, when, has } from '../_shared.mjs';

const fig = (model, f, cls = '') => `<figure class="fig pe-fig ${cls}">${img(model, f)}${captionHtml(model, f)}</figure>`;

export default {
  family: 'photo-essay',
  components: {
    'photo-essay': {
      variants: { 'grid-3': { pages: 2 }, 'sequence-4': { pages: 2 }, 'wide-single': { pages: 2 } },
      defaultVariant: 'grid-3',
      required: (v) => ['images', ...(v === 'grid-3' ? [] : [])],
      optional: ['title', 'kicker'],
      minImages: { 'grid-3': 3, 'sequence-4': 4, 'wide-single': 1 },
      captions: true,
      render({ inputs: i, variant, model }) {
        const [a, b, c, d] = i.images;
        const head = `<div class="pe-head c-all">${when(i.kicker, `<span class="kicker">${esc(i.kicker)}</span>`)}<h2>${esc(i.title)}</h2></div>`;
        if (variant === 'grid-3') {
          return [
            { chrome: 'folio', html: `<div class="pe-bleed-l">${img(model, a)}</div><div class="pe-capl">${captionHtml(model, a)}</div>` },
            { html: `<div class="live pe-r">${head}<div class="c-all pe-r1">${fig(model, b)}</div><div class="c-all pe-r2">${fig(model, c)}</div></div>` },
          ];
        }
        if (variant === 'sequence-4') {
          return [
            { html: `<div class="live pe-seq"><div class="c-all">${fig(model, a, 'pe-tall')}</div><div class="c-1-3">${fig(model, b, 'pe-sq')}</div><div class="c-4-6">${fig(model, c, 'pe-sq')}</div></div>` },
            { html: `<div class="live pe-seq">${head}<div class="c-all">${fig(model, d, 'pe-tall')}</div></div>` },
          ];
        }
        return [
          { chrome: 'folio', html: `<div class="pe-wide">${img(model, a)}</div><div class="live pe-widecap"><div class="c-all">${captionHtml(model, a)}</div></div>` },
          { html: `<div class="pe-wide-r">${img(model, a)}</div><div class="live pe-wide-head"><div class="c-all">${head}</div></div>` },
        ];
      },
    },
    'full-bleed-photo': {
      variants: { single: { pages: 1 }, spread: { pages: 2 } },
      defaultVariant: 'single',
      required: () => ['hero_image'],
      optional: [],
      captions: true,
      render({ inputs: i, variant, model }) {
        if (variant === 'single') return [{ chrome: 'folio', dark: true, html: `<div class="bleed">${img(model, i.hero_image)}</div><div class="fp-cap on-dark">${captionHtml(model, i.hero_image)}</div>` }];
        return [
          { chrome: 'folio', dark: true, html: `<div class="fp-sp fp-sp-l">${img(model, i.hero_image)}</div>` },
          { chrome: 'folio', dark: true, html: `<div class="fp-sp fp-sp-r">${img(model, i.hero_image)}</div><div class="fp-cap on-dark">${captionHtml(model, i.hero_image)}</div>` },
        ];
      },
    },
  },
};

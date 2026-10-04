import { esc, fig, img, captionHtml, body, byline, when, has } from '../_shared.mjs';

export default {
  family: 'column',
  components: {
    column: {
      variants: { box: { pages: 1 }, plain: { pages: 1 } },
      defaultVariant: 'box',
      required: () => ['title'],
      optional: ['kicker', 'author', 'image'],
      captions: true,
      text: true,
      render({ inputs: i, variant, text, model }) {
        const head = `<div class="c-all">${when(i.kicker, `<p class="kicker">${esc(i.kicker)}</p>`)}<h2 class="cl-title">${esc(i.title)}</h2>${byline(i)}</div>`;
        const im = when(has(i.image), `<div class="c-all">${fig(model, i.image, { imgStyle: 'height:var(--column-img-h)' })}</div>`);
        const inner = `${head}${im}<div class="c-all cl-text fit fit-auto">${body(text)}</div>`;
        return [{ html: `<div class="live cl cl-${variant}">${variant === 'box' ? `<div class="tint-box c-all cl-box"><div class="cl-grid">${inner}</div></div>` : inner}</div>` }];
      },
    },
    profile: {
      variants: { card: { pages: 1 }, wide: { pages: 1 } },
      defaultVariant: 'card',
      required: () => ['title'],
      optional: ['portrait', 'deck', 'facts'],
      captions: true,
      text: true,
      render({ inputs: i, variant, text, model }) {
        const facts = (i.facts ?? []).map((f) => `<div class="pf-row"><dt>${esc(f.label)}</dt><dd>${esc(f.value)}</dd></div>`).join('');
        return [{ html: `<div class="live pf pf-${variant}"><p class="label c-all">PROFILE</p>
${when(i.portrait, `<div class="${variant === 'card' ? 'c-1-3' : 'c-all'} pf-img">${fig(model, i.portrait, { imgStyle: variant === 'card' ? 'height:var(--profile-img-h)' : 'height:var(--profile-img-wide-h)' })}</div>`)}
<div class="${variant === 'card' && i.portrait ? 'c-4-6' : 'c-all'} pf-name"><h2>${esc(i.title)}</h2>${when(i.deck, `<p class="deck">${esc(i.deck)}</p>`)}</div>
<div class="c-all pf-text fit fit-auto">${body(text)}</div>${when(facts, `<dl class="c-all pf-facts">${facts}</dl>`)}</div>` }];
      },
    },
  },
};

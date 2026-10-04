import { esc, img, fig, captionHtml, body, when, frameChars, liveBox } from '../_shared.mjs';

const who = (i) => `<p class="iv-who"><b>${esc(i.interviewee ?? '')}</b>${i.interviewee_role ? `<span>${esc(i.interviewee_role)}</span>` : ''}</p>`;

export default {
  family: 'interview',
  components: {
    'interview-opener': {
      variants: { 'portrait-left': { pages: 1 }, 'big-quote': { pages: 1 } },
      defaultVariant: 'portrait-left',
      required: (v) => (v === 'portrait-left' ? ['title', 'portrait', 'interviewee'] : ['title', 'interviewee']),
      optional: ['kicker', 'deck', 'portrait', 'interviewee_role', 'author'],
      captions: true,
      text: { capacity: (v, i) => frameChars({ w: liveBox(i).w, h: v === 'portrait-left' ? 46 : 88 }) },
      render({ inputs: i, variant, text, model }) {
        if (variant === 'portrait-left') {
          return [{ html: `<div class="iv-portrait">${img(model, i.portrait)}</div>
<div class="live iv-o"><div class="c-4-6 iv-side"><div><p class="kicker">${esc(i.kicker ?? 'INTERVIEW')}</p>${who(i)}</div>${captionHtml(model, i.portrait)}</div>
<h1 class="iv-title c-all">${esc(i.title)}</h1>${when(i.deck, `<p class="deck c-all iv-deck">${esc(i.deck)}</p>`)}<div class="iv-text c-all fit">${body(text)}</div></div>` }];
        }
        return [{ html: `<div class="live iv-o iv-bq"><p class="kicker c-all">${esc(i.kicker ?? 'INTERVIEW')}</p><h1 class="iv-title iv-title-xl c-all">${esc(i.title)}</h1>
<div class="c-1-4">${who(i)}</div>${when(i.portrait, `<div class="c-5-6 iv-thumb">${img(model, i.portrait)}</div>`)}<div class="iv-text c-all fit">${body(text)}</div></div>` }];
      },
    },
    'interview-body': {
      variants: { qa: { pages: 1 }, 'qa-portrait': { pages: 1 } },
      defaultVariant: 'qa',
      required: (v) => (v === 'qa-portrait' ? ['image'] : []),
      optional: ['image'],
      captions: true,
      text: { capacity: (v, i) => { const b = liveBox(i); return frameChars({ w: b.w, h: v === 'qa' ? b.h : b.h - 62, cols: 2 }); } },
      render({ inputs: i, variant, text, model }) {
        if (variant === 'qa') return [{ html: `<div class="live ib"><div class="ib-text c-all fit cols-2">${body(text)}</div></div>` }];
        return [{ html: `<div class="live ib ib-rows"><div class="c-1-3">${fig(model, i.image, { imgStyle: 'height:52mm' })}</div><div class="ib-text c-all fit cols-2">${body(text)}</div></div>` }];
      },
    },
  },
};

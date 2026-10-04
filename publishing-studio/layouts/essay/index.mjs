import { esc, body, byline, when, frameChars, liveBox } from '../_shared.mjs';

export default {
  family: 'essay',
  components: {
    essay: {
      variants: { opener: { pages: 1 }, body: { pages: 1 }, end: { pages: 1 } },
      defaultVariant: 'body',
      required: (v) => (v === 'opener' ? ['title'] : []),
      optional: ['kicker', 'deck', 'author'],
      captions: false,
      text: { capacity: (v, i) => { const b = liveBox(i); const w = ((b.w - 5 * 4) / 6) * 5 + 16; return frameChars({ w, h: v === 'opener' ? b.h - 48 : b.h - (v === 'end' ? 6 : 0) }); } },
      render({ inputs: i, variant, text }) {
        const endMark = variant === 'end' ? '<span class="end-mark"></span>' : '';
        const txt = `<div class="es-text fit">${body(text)}${endMark}</div>`;
        if (variant === 'opener') {
          return [{ html: `<div class="live es es-o"><div class="es-head c-all">${when(i.kicker, `<p class="kicker">${esc(i.kicker)}</p>`)}<h1 class="es-title">${esc(i.title)}</h1>${when(i.deck, `<p class="deck">${esc(i.deck)}</p>`)}${byline(i)}</div><div class="c-1-5 es-col"><div class="es-text es-text-o fit">${body(text)}</div></div></div>` }];
        }
        return [{ html: `<div class="live es"><div class="c-1-5 es-col">${txt}</div></div>` }];
      },
    },
  },
};

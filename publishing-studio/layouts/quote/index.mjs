import { esc, when } from '../_shared.mjs';

export default {
  family: 'quote',
  components: {
    'quote-page': {
      variants: { center: { pages: 1 }, 'color-block': { pages: 1 }, 'left-rule': { pages: 1 } },
      defaultVariant: 'center',
      required: () => ['pull_quote'],
      optional: ['author', 'quote_source'],
      captions: false,
      render({ inputs: i, variant }) {
        const who = i.quote_source ?? i.author;
        const attr = when(who, `<p class="qp-who">— ${esc(who)}</p>`);
        const q = `<blockquote class="qp-text">${esc(i.pull_quote)}</blockquote>${attr}`;
        if (variant === 'color-block') return [{ chrome: 'folio', bg: 'accent', dark: true, html: `<div class="live qp qp-cb">${q}</div>` }];
        if (variant === 'left-rule') return [{ chrome: 'folio', html: `<div class="live qp qp-lr">${q}</div>` }];
        return [{ chrome: 'folio', html: `<div class="live qp qp-c">${q}</div>` }];
      },
    },
  },
};

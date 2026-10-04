import { esc, when } from '../_shared.mjs';

export default {
  family: 'divider',
  components: {
    divider: {
      variants: { ink: { pages: 1 }, paper: { pages: 1 }, accent: { pages: 1 } },
      defaultVariant: 'ink',
      required: () => ['title'],
      optional: ['kicker', 'deck'],
      captions: false,
      render({ inputs: i, variant }) {
        const bg = variant === 'ink' ? 'ink' : variant === 'accent' ? 'accent' : undefined;
        return [{ chrome: 'none', bg, dark: !!bg, html: `<div class="live dv"><p class="label c-all">${esc(i.kicker ?? 'SECTION')}</p><h1 class="dv-title c-all">${esc(i.title)}</h1>${when(i.deck, `<p class="deck c-1-5">${esc(i.deck)}</p>`)}</div>` }];
      },
    },
  },
};

import { esc, when } from '../_shared.mjs';

export default {
  family: 'toc',
  components: {
    contents: {
      variants: { list: { pages: 1 }, large: { pages: 1 } },
      defaultVariant: 'list',
      required: () => ['toc'],
      optional: [],
      captions: false,
      render({ inputs: i, variant }) {
        const items = i.toc.map((t, k) => `<li class="toc-item"><span class="toc-p num">${String(t.page).padStart(2, '0')}</span><div class="toc-t">${when(t.kicker, `<span class="kicker">${esc(t.kicker)}</span>`)}<h2>${esc(t.title)}</h2>${when(t.deck && variant === 'list', `<p class="toc-d">${esc(t.deck)}</p>`)}</div></li>`).join('');
        return [{ html: `<div class="live toc toc-${variant}"><div class="toc-head c-all"><p class="label">CONTENTS</p><h1>${esc(i.title ?? '目次')}</h1></div><ol class="toc-list c-all">${items}</ol></div>` }];
      },
    },
  },
};

import { esc, img, when, has } from '../_shared.mjs';

const lines = (i) => when(has(i.cover_lines), `<ul class="cv-lines">${i.cover_lines.map((l) => `<li>${esc(l)}</li>`).join('')}</ul>`);
const meta = (i) => `<div class="cv-meta"><span class="cv-no num">No.${esc(i.issue.issue_number)}</span><span class="cv-date num">${esc(i.issue.date ?? '')}</span></div>`;

export default {
  family: 'cover',
  components: {
    cover: {
      variants: { full: { pages: 1 }, typo: { pages: 1 }, split: { pages: 1 }, back: { pages: 1 } },
      defaultVariant: 'full',
      required: (v) => (v === 'full' || v === 'split' ? ['hero_image'] : []),
      optional: ['cover_lines', 'hero_image'],
      captions: false,
      render({ inputs: i, variant, model }) {
        const title = `<h1 class="cv-title">${esc(i.issue.title)}</h1>${when(i.issue.subtitle, `<p class="cv-sub">${esc(i.issue.subtitle)}</p>`)}`;
        if (variant === 'full') {
          return [{ chrome: 'none', dark: true, html: `<div class="bleed">${img(model, i.hero_image)}</div><div class="bleed cv-shade"></div>
<div class="live cv-live on-dark">${meta(i)}<div class="cv-head c-all">${title}</div><div class="cv-foot c-all">${lines(i)}</div></div>` }];
        }
        if (variant === 'typo') {
          return [{ chrome: 'none', html: `<div class="live cv-live cv-typo">${meta(i)}<div class="cv-head c-all">${title}</div>
${when(i.hero_image, `<div class="cv-small c-3-6">${img(model, i.hero_image)}</div>`)}<div class="cv-foot c-all">${lines(i)}</div></div>` }];
        }
        if (variant === 'split') {
          return [{ chrome: 'none', html: `<div class="cv-split-img">${img(model, i.hero_image)}</div>
<div class="live cv-live cv-split">${meta(i)}<div class="cv-head c-all">${title}</div><div class="cv-foot c-all">${lines(i)}</div></div>` }];
        }
        return [{ chrome: 'none', bg: 'accent-2', dark: true, html: `<div class="live cv-back on-dark"><div class="c-all"><p class="cv-back-title">${esc(i.issue.title)}</p><p class="cv-back-line">${esc(i.deck ?? i.issue.subtitle ?? '')}</p></div>
<p class="cv-back-pub c-all">${esc(i.issue.publisher ?? '')}</p></div>` }];
      },
    },
  },
};

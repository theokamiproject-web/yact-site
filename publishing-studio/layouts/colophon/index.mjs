import { esc, when, has } from '../_shared.mjs';

const credits = (model) => (model.credits?.credits ?? []).map((g) => `<div class="co-row"><dt>${esc(g.role)}</dt><dd>${(g.names ?? []).map(esc).join('、')}</dd></div>`).join('');
const info = (model, { withCredits }) => {
  const c = model.credits?.colophon ?? {};
  // a role already printed in the credits table is not repeated in the colophon table
  const printed = new Set(withCredits ? (model.credits?.credits ?? []).map((g) => g.role) : []);
  const rows = [['発行日', c.published ?? model.issue.date], ['発行', c.publisher ?? model.issue.publisher], ['編集', c.editor], ['印刷・製本', c.printer], ['連絡先', c.contact], ['価格', c.price]].filter(([k, v]) => has(v) && !printed.has(k));
  return rows.map(([k, v]) => `<div class="co-row"><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('');
};

export default {
  family: 'colophon',
  components: {
    credits: {
      variants: { columns: { pages: 1 } },
      defaultVariant: 'columns',
      required: () => [],
      optional: [],
      captions: false,
      render({ model, inputs: i }) {
        return [{ html: `<div class="live co"><p class="label c-all">CREDITS</p><h2 class="c-all">${esc(i.title ?? 'クレジット')}</h2><dl class="co-list c-all">${credits(model)}</dl></div>` }];
      },
    },
    colophon: {
      variants: { standard: { pages: 1 }, 'with-credits': { pages: 1 } },
      defaultVariant: 'standard',
      required: () => [],
      optional: [],
      captions: false,
      render({ model, inputs: i, variant }) {
        const copy = model.credits?.colophon?.copyright;
        return [{ html: `<div class="live co co-end"><div class="co-main c-all"><p class="label">COLOPHON</p><h2>${esc(i.issue.title)}</h2><p class="co-no num">No.${esc(i.issue.issue_number)}${i.issue.subtitle ? `　${esc(i.issue.subtitle)}` : ''}</p></div>
${when(variant === 'with-credits', `<dl class="co-list c-all">${credits(model)}</dl>`)}<dl class="co-list c-all">${info(model, { withCredits: variant === 'with-credits' })}</dl>${when(copy, `<p class="co-copy caption c-all">${esc(copy)}</p>`)}</div>` }];
      },
    },
  },
};

// DOM/CSS-derived per-page metrics. Runs in Chromium against output/<id>/web/index.html (screen media, fixed-size sheets).
import path from 'node:path';
import { pathToFileURL } from 'node:url';

export async function collectMetrics(browser, webDir, issue) {
  const page = await browser.newPage({ viewport: { width: 1000, height: 1400 }, deviceScaleFactor: 1 });
  await page.goto(pathToFileURL(path.join(webDir, 'index.html')).href, { waitUntil: 'load' });
  await page.evaluate(() => document.fonts.ready);
  const result = await page.evaluate(({ widthMm, heightMm, bleedMm, safeMm }) => {
    const GW = 60, GH = 84;
    const out = [];
    for (const pg of document.querySelectorAll('.page')) {
      const pr = pg.getBoundingClientRect();
      const k = pr.width / widthMm; // px per mm
      const rel = (r) => ({ x: (r.left - pr.left) / k, y: (r.top - pr.top) / k, w: r.width / k, h: r.height / k });
      const inChrome = (n) => !!(n.parentElement && n.parentElement.closest('.folio, .runhead'));
      const m = { n: Number(pg.dataset.page), layout: pg.dataset.layout, variant: pg.dataset.variant, article: pg.dataset.article, chrome: pg.dataset.chrome, spread: pg.dataset.spread ?? null, intentional_blank: pg.dataset.intentionalBlank === 'true', declared_intensity: pg.dataset.intensity ? Number(pg.dataset.intensity) : null };

      // text
      let chars = 0;
      const textRects = [];
      const fonts = new Set();
      const walker = document.createTreeWalker(pg, NodeFilter.SHOW_TEXT);
      for (let n = walker.nextNode(); n; n = walker.nextNode()) {
        const t = n.textContent.replace(/\s+/g, '');
        if (!t || inChrome(n)) continue;
        const el = n.parentElement;
        const cs = getComputedStyle(el);
        if (cs.visibility === 'hidden' || cs.display === 'none') continue;
        chars += [...t].length;
        fonts.add(cs.fontFamily.split(',')[0].replace(/["']/g, '').trim());
        const range = document.createRange();
        range.selectNodeContents(n);
        for (const r of range.getClientRects()) if (r.width > 0 && r.height > 0) textRects.push({ ...rel(r), fs: parseFloat(cs.fontSize) / k });
      }
      m.text_chars = chars;
      m.fonts = [...fonts];

      // images
      const images = [];
      for (const img of pg.querySelectorAll('img')) {
        const r = img.getBoundingClientRect();
        const rr = rel(r);
        const nw = img.naturalWidth, nh = img.naturalHeight;
        const scale = nw ? Math.max(r.width / nw, r.height / nh) : 0; // object-fit: cover
        images.push({ file: img.dataset.image ?? img.getAttribute('src'), ok: img.complete && nw > 0, natural: [nw, nh], rect_mm: rr, ppi: scale ? Math.round((k * 25.4) / scale) : 0 });
      }
      m.images = images;

      // ink grid (whitespace estimate)
      const cells = new Uint8Array(GW * GH);
      const mark = (x, y, w, h, padX = 0, padY = 0) => {
        const x0 = Math.max(0, Math.floor(((x - padX) / widthMm) * GW)), x1 = Math.min(GW - 1, Math.floor(((x + w + padX) / widthMm) * GW));
        const y0 = Math.max(0, Math.floor(((y - padY) / heightMm) * GH)), y1 = Math.min(GH - 1, Math.floor(((y + h + padY) / heightMm) * GH));
        for (let j = y0; j <= y1; j++) for (let i = x0; i <= x1; i++) cells[j * GW + i] = 1;
      };
      for (const t of textRects) mark(t.x, t.y, t.w, t.h, 0.3, 1.2);
      for (const im of images) mark(im.rect_mm.x, im.rect_mm.y, im.rect_mm.w, im.rect_mm.h);
      let shapes = 0;
      for (const el of pg.querySelectorAll('*')) {
        if (el.closest('.folio, .runhead')) continue;
        const cs = getComputedStyle(el);
        const bg = cs.backgroundColor;
        const a = bg.startsWith('rgba') ? parseFloat(bg.split(',')[3]) : bg === 'transparent' ? 0 : 1;
        const hasGrad = cs.backgroundImage !== 'none';
        if ((a > 0.05 || hasGrad) && !el.classList.contains('live')) {
          const rr = rel(el.getBoundingClientRect());
          if (rr.w * rr.h > 4) { mark(rr.x, rr.y, rr.w, rr.h); shapes++; }
        }
        if (parseFloat(cs.borderTopWidth) > 0 && cs.borderTopStyle !== 'none') shapes++;
      }
      if (pg.dataset.bg) cells.fill(1);
      let covered = 0;
      for (const c of cells) covered += c;
      m.ink_ratio = +(covered / cells.length).toFixed(3);
      m.whitespace_ratio = +(1 - covered / cells.length).toFixed(3);

      // image ratio (clipped to the trim box)
      let imgArea = 0;
      for (const im of images) {
        const x0 = Math.max(0, im.rect_mm.x), y0 = Math.max(0, im.rect_mm.y);
        const x1 = Math.min(widthMm, im.rect_mm.x + im.rect_mm.w), y1 = Math.min(heightMm, im.rect_mm.y + im.rect_mm.h);
        if (x1 > x0 && y1 > y0) imgArea += (x1 - x0) * (y1 - y0);
      }
      m.image_ratio = +Math.min(1, imgArea / (widthMm * heightMm)).toFixed(3);
      m.bg_fill = pg.dataset.bg ?? null;

      // element counts & type scale
      m.text_blocks = pg.querySelectorAll('p, h1, h2, h3, blockquote, li, dt, dd').length;
      m.visual_elements = images.length + shapes + pg.querySelectorAll('h1, h2, h3, blockquote, .pullquote').length;
      let headPx = 0, bodyPx = 0;
      for (const el of pg.querySelectorAll('h1, h2, h3, .pullquote, .qp-text, .cv-title, .dv-title')) headPx = Math.max(headPx, parseFloat(getComputedStyle(el).fontSize));
      const bp = pg.querySelector('.body p, .body, p');
      bodyPx = bp ? parseFloat(getComputedStyle(bp).fontSize) : 0;
      m.headline_pt = +(headPx * 0.75).toFixed(1);
      m.body_pt = +(bodyPx * 0.75).toFixed(1);

      // overflow / clipping
      const overflow = [];
      const fills = [];
      for (const el of pg.querySelectorAll('.fit')) {
        const cs = getComputedStyle(el);
        const cc = parseInt(cs.columnCount, 10) || 1;
        const auto = el.classList.contains('fit-auto'); // content-sized frame: fill is trivially 1
        const er = el.getBoundingClientRect();
        let lines = 0;
        const w2 = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
        for (let n = w2.nextNode(); n; n = w2.nextNode()) {
          if (!n.textContent.trim() || n.parentElement.closest('.qm')) continue;
          const range = document.createRange();
          range.selectNodeContents(n);
          lines += [...range.getClientRects()].filter((r) => r.width > 0).length;
        }
        const baseline = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--baseline')) || 5.5;
        if (!auto) fills.push(+((lines * baseline * k) / (er.height * cc)).toFixed(2));
      }
      m.fit_fill = fills.length ? Math.max(...fills) : null;
      for (const el of pg.querySelectorAll('.fit')) {
        if (el.scrollHeight > el.clientHeight + 1 || el.scrollWidth > el.clientWidth + 1) {
          overflow.push({ el: el.className, kind: 'content-clipped', scroll: [el.scrollWidth, el.scrollHeight], client: [el.clientWidth, el.clientHeight] });
        }
      }
      const lim = bleedMm + 0.5;
      const outside = [];
      for (const t of textRects) {
        if (t.x < -0.5 || t.y < -0.5 || t.x + t.w > widthMm + 0.5 || t.y + t.h > heightMm + 0.5) outside.push({ kind: 'text-outside-trim', rect: [t.x, t.y, t.w, t.h].map((v) => +v.toFixed(1)) });
      }
      for (const im of images) {
        const r = im.rect_mm;
        if (r.x < -lim || r.y < -lim || r.x + r.w > widthMm + lim + 0.01 && !pg.dataset.spread || r.y + r.h > heightMm + lim) outside.push({ kind: 'image-beyond-bleed', file: im.file });
      }
      m.overflow = overflow;
      m.outside = outside;
      // safe area: text closer than safeMm to the trim edge (folio/runhead excluded by construction)
      m.safe_violations = textRects.filter((t) => t.x < safeMm - 0.2 || t.y < safeMm - 0.2 || t.x + t.w > widthMm - safeMm + 0.2 || t.y + t.h > heightMm - safeMm + 0.2).length;

      // folio
      const f = pg.querySelector('.folio');
      m.folio = f ? { text: f.textContent.trim(), expected: String(m.n) } : null;
      m.has_runhead = !!pg.querySelector('.runhead');
      out.push(m);
    }
    return out;
  }, { widthMm: issue.width, heightMm: issue.height, bleedMm: issue.bleed, safeMm: 5 });
  await page.close();
  return result;
}

/** Composite 0..100 "visual intensity" from measured values (not from the flatplan). */
export function measuredIntensity(m) {
  const imageScore = Math.min(1, m.image_ratio / 0.6) * 55;
  const headScore = Math.min(1, Math.max(0, (m.headline_pt - 8.5) / 40)) * 25;
  const fillScore = m.bg_fill ? 20 : 0;
  const densityPenalty = Math.min(1, m.text_chars / 1500) * 8;
  return Math.round(Math.max(0, Math.min(100, imageScore + headScore + fillScore - densityPenalty + 6)));
}

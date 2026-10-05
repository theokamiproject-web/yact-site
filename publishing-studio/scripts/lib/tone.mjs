// Tone of the image area behind running heads / folios / captions, so page chrome picks a readable colour.
// Measured from the pixels (top and bottom strips, optionally one half of a spread image); images.yaml `tone: dark|light` overrides.
import sharp from 'sharp';

const DARK_BELOW = 118; // mean luminance (0-255); paper-coloured text (#6d6a62-ish) needs a light ground
const STRIP = 0.14;

async function strips(file) {
  const { data, info } = await sharp(file).removeAlpha().greyscale().resize(96, 96, { fit: 'fill' }).raw().toBuffer({ resolveWithObject: true });
  const mean = (y0, y1, x0, x1) => { let s = 0, n = 0; for (let y = y0; y < y1; y++) for (let x = x0; x < x1; x++) { s += data[y * info.width + x]; n++; } return s / n; };
  const h = Math.max(1, Math.round(info.height * STRIP)), w = info.width, half = Math.floor(w / 2);
  const t = (x0, x1) => ({ top: mean(0, h, x0, x1), bottom: mean(info.height - h, info.height, x0, x1) });
  return { all: t(0, w), left: t(0, half), right: t(half, w) };
}

/** @returns {Promise<Record<string, {all:{top,bottom},left:{top,bottom},right:{top,bottom}}>>} 'dark' | 'light' per region */
export async function imageTones(model, files) {
  const out = {};
  for (const f of new Set(files)) {
    const path = model.images[f];
    if (!path) continue;
    const forced = model.imageMeta?.[f]?.tone;
    const m = await strips(path);
    const cls = (v) => (forced ?? (v < DARK_BELOW ? 'dark' : 'light'));
    out[f] = Object.fromEntries(Object.entries(m).map(([k, v]) => [k, { top: cls(v.top), bottom: cls(v.bottom) }]));
  }
  return out;
}

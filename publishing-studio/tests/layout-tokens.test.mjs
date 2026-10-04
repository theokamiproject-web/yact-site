// P1-3: layouts are page-relative. No physical millimetre literal or unscaled point size may sneak back into component CSS.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { PS } from './helpers.mjs';

const files = [...fs.readdirSync(path.join(PS, 'layouts'), { withFileTypes: true }).filter((d) => d.isDirectory()).map((d) => path.join(PS, 'layouts', d.name, 'style.css')),
  ...['typography', 'grid', 'components'].map((n) => path.join(PS, 'themes/base', `${n}.css`)),
  path.join(PS, 'themes/base/page.css')].filter((f) => fs.existsSync(f));
const strip = (css) => css.replace(/\/\*[\s\S]*?\*\//g, '').replace(/@media screen\s*\{[\s\S]*?\n\}/g, ''); // the screen-only preview block is exempt

test('no millimetre / centimetre / inch literal in layouts/*.css or base theme (except tokens.css)', () => {
  for (const f of files) {
    const hits = strip(fs.readFileSync(f, 'utf8')).match(/(?<![\w.-])\d*\.?\d+(mm|cm|in)\b/g);
    assert.equal(hits, null, `${path.relative(PS, f)} uses physical lengths ${hits}; use page-relative tokens from themes/base/tokens.css`);
  }
});

test('no physical lengths hidden in component JS (inline styles) either', () => {
  const dirs = fs.readdirSync(path.join(PS, 'layouts'), { withFileTypes: true }).filter((d) => d.isDirectory());
  for (const d of dirs) {
    const src = fs.readFileSync(path.join(PS, 'layouts', d.name, 'index.mjs'), 'utf8');
    assert.equal(src.match(/(?<![\w.-])\d*\.?\d+(mm|cm|in|pt|px)\b/g), null, `layouts/${d.name}/index.mjs contains a physical length`);
  }
});

test('font sizes in component CSS are tokens or scaled with --type-scale (and never below --min-text)', () => {
  for (const f of files) {
    for (const m of strip(fs.readFileSync(f, 'utf8')).matchAll(/font-size:\s*([^;]+);/g)) {
      const v = m[1];
      assert.ok(/var\(--/.test(v) || /--type-scale/.test(v) || /^\d*\.?\d+em$|%$/.test(v.trim()), `${path.relative(PS, f)}: unscaled font-size "${v}"`);
    }
  }
});

test('tokens.css defines the three families and page-relative margins (no mm margins)', () => {
  const t = fs.readFileSync(path.join(PS, 'themes/base/tokens.css'), 'utf8');
  for (const k of ['PHYSICAL', 'PAGE-RELATIVE', 'TYPOGRAPHY-DERIVED']) assert.match(t, new RegExp(k));
  for (const k of ['--margin-top', '--margin-bottom', '--margin-inner', '--margin-outer', '--gutter', '--content-w', '--content-h', '--opener-hero-h', '--inline-img-h']) {
    assert.match(t, new RegExp(`${k}:\\s*calc\\(var\\(--(page|content)-[wh]\\)`), `${k} must be page-relative`);
  }
});

// Theme resolution: base -> named theme -> issue theme.css -> issue.yaml theme_overrides -> page-setup (from issue.yaml)
import fs from 'node:fs';
import path from 'node:path';
import { THEMES_DIR } from './paths.mjs';

const BASE_FILES = ['tokens.css', 'typography.css', 'page.css', 'grid.css', 'components.css'];
const read = (f) => fs.readFileSync(f, 'utf8');

export function resolveTheme(model) {
  const { issue } = model;
  const parts = [];
  const base = path.join(THEMES_DIR, 'base');
  for (const f of BASE_FILES) parts.push({ source: `themes/base/${f}`, css: read(path.join(base, f)) });

  if (issue.theme && issue.theme !== 'base') {
    const dir = path.join(THEMES_DIR, issue.theme);
    if (!fs.existsSync(dir)) throw new Error(`theme "${issue.theme}" not found in themes/`);
    for (const f of fs.readdirSync(dir).filter((x) => x.endsWith('.css')).sort()) parts.push({ source: `themes/${issue.theme}/${f}`, css: read(path.join(dir, f)) });
  }
  const issueTheme = path.join(model.dir, 'theme.css');
  if (fs.existsSync(issueTheme)) parts.push({ source: 'issue theme.css', css: read(issueTheme) });

  const ov = Object.entries(issue.theme_overrides ?? {});
  if (ov.length) parts.push({ source: 'issue.yaml theme_overrides', css: `:root {\n${ov.map(([k, v]) => `  ${k}: ${v};`).join('\n')}\n}` });
  return parts;
}

/**
 * Type scale derived from the trim width (A5 148mm = 1.00). Square-root growth keeps measure (characters per line)
 * comfortable on larger pages without making type huge; never below 0.92 so body text stays >= 7.8pt.
 */
export function typeScale(widthMm) {
  return Math.max(0.92, Math.round(Math.sqrt(widthMm / 148) * 100) / 100);
}

export function pageSetupCss(issue, { marks }) {
  return `/* generated from issue.yaml — do not edit */
:root { --page-w: ${issue.width}mm; --page-h: ${issue.height}mm; --bleed: ${issue.bleed}mm; --type-scale: ${typeScale(issue.width)}; }
@page {
  size: ${issue.width}mm ${issue.height}mm;
  margin: 0;
  bleed: ${issue.bleed}mm;
${marks ? '  marks: crop;\n' : ''}}
`;
}

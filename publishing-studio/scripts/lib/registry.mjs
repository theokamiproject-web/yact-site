// Layout component registry. Each layouts/<family>/index.mjs exports {family, components}.
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { LAYOUTS_DIR } from './paths.mjs';

const { DENSITY } = await import(pathToFileURL(path.join(LAYOUTS_DIR, '_contracts.mjs')).href);

let cache;

export async function loadRegistry() {
  if (cache) return cache;
  const components = {};
  const styles = [];
  for (const family of fs.readdirSync(LAYOUTS_DIR).sort()) {
    const dir = path.join(LAYOUTS_DIR, family);
    const entry = path.join(dir, 'index.mjs');
    if (!fs.statSync(dir).isDirectory() || !fs.existsSync(entry)) continue;
    const mod = (await import(pathToFileURL(entry).href)).default;
    for (const [name, c] of Object.entries(mod.components)) {
      if (components[name]) throw new Error(`duplicate layout component: ${name}`);
      components[name] = { name, family, ...c, density: DENSITY[name] };
    }
    const css = path.join(dir, 'style.css');
    if (fs.existsSync(css)) styles.push({ family, file: css, css: fs.readFileSync(css, 'utf8') });
  }
  cache = { components, styles };
  return cache;
}

export const variantPages = (c, variant) => c.variants[variant ?? c.defaultVariant]?.pages;

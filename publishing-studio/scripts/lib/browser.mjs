import fs from 'node:fs';
import path from 'node:path';
import { chromium } from 'playwright-core';

export function findChromium() {
  if (process.env.PS_BROWSER && fs.existsSync(process.env.PS_BROWSER)) return process.env.PS_BROWSER;
  const roots = [process.env.PLAYWRIGHT_BROWSERS_PATH, '/opt/pw-browsers', path.join(process.env.HOME ?? '', '.cache/ms-playwright')].filter(Boolean);
  for (const root of roots) {
    if (!fs.existsSync(root)) continue;
    const dirs = fs.readdirSync(root).filter((d) => /^chromium-\d+$/.test(d)).sort().reverse();
    for (const d of dirs) {
      for (const rel of ['chrome-linux/chrome', 'chrome-mac/Chromium.app/Contents/MacOS/Chromium', 'chrome-win/chrome.exe']) {
        const p = path.join(root, d, rel);
        if (fs.existsSync(p)) return p;
      }
    }
  }
  try {
    const p = chromium.executablePath();
    if (p && fs.existsSync(p)) return p;
  } catch { /* fall through */ }
  return undefined;
}

export async function launch() {
  const executablePath = findChromium();
  if (!executablePath) throw new Error('no Chromium found. Set PS_BROWSER=/path/to/chrome or install Playwright Chromium.');
  return chromium.launch({ executablePath, args: ['--no-sandbox', '--font-render-hinting=none'] });
}

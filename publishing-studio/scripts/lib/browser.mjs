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

/**
 * Chromium sandbox policy. The sandbox is ON by default.
 * It is only switched off when it cannot work: PS_NO_SANDBOX=1 (explicit), or automatically inside the managed remote
 * container (CLAUDE_CODE_REMOTE=true) when running as root. In every such case manuscripts are already sanitised
 * (raw HTML escaped, no network access from the measurement browser). PS_NO_SANDBOX=0 forces the sandbox on.
 */
export function sandboxPolicy(env = process.env, uid = process.getuid?.()) {
  if (env.PS_NO_SANDBOX === '1') return { noSandbox: true, reason: 'PS_NO_SANDBOX=1 (explicit)' };
  if (env.PS_NO_SANDBOX === '0') return { noSandbox: false };
  if (env.CLAUDE_CODE_REMOTE === 'true' && uid === 0) return { noSandbox: true, reason: 'isolated remote container running as root (CLAUDE_CODE_REMOTE=true)' };
  return { noSandbox: false };
}

let noticed = false;
export async function launch() {
  const executablePath = findChromium();
  if (!executablePath) throw new Error('no Chromium found. Set PS_BROWSER=/path/to/chrome or install Playwright Chromium.');
  const pol = sandboxPolicy();
  if (pol.noSandbox && !noticed) { noticed = true; console.error(`  NOTE: Chromium sandbox disabled: ${pol.reason}. Only use this in an isolated environment.`); }
  try {
    return await chromium.launch({ executablePath, args: ['--font-render-hinting=none', ...(pol.noSandbox ? ['--no-sandbox'] : [])] });
  } catch (e) {
    if (!pol.noSandbox && /sandbox/i.test(String(e.message))) throw new Error(`Chromium could not start with its sandbox (${e.message.split('\n')[0]}). If this is an isolated container (e.g. running as root) set PS_NO_SANDBOX=1; otherwise fix the sandbox. The sandbox is never disabled automatically outside the managed remote container.`);
    throw e;
  }
}

/** A page that cannot reach the network: only file:/data:/about: requests are allowed. */
export async function safePage(browser, options) {
  const page = await browser.newPage(options);
  await page.route('**/*', (route) => (/^(file|data|about|blob):/.test(route.request().url()) ? route.continue() : route.abort()));
  return page;
}

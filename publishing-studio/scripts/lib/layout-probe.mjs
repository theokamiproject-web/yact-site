// Pass A of every build/validate: compose the book WITHOUT body text, load it in Chromium and measure.
//  - text frames (.fit): real width/height/columns/font size/leading -> body capacity (no constants duplicated in JS)
//  - content that already overflows with no body text (long headline/caption, too many contents entries) -> structural errors
import path from 'node:path';
import { outDir } from './paths.mjs';
import { compose } from './compose.mjs';
import { writeWeb } from './web.mjs';
import { launch } from './browser.mjs';
import { collectMetrics } from './metrics.mjs';

export async function probeLayout(model) {
  const dir = path.join(outDir(model.id), '.probe');
  const composed = await compose(model, { plan: new Map() });
  await writeWeb(model, composed, dir);
  const browser = await launch();
  try {
    const { pages: metrics, tokens } = await collectMetrics(browser, dir, model.issue);
    const frames = new Map(metrics.filter((m) => m.fit_frames.length).map((m) => [m.n, m.fit_frames[0]]));
    return { frames, metrics, tokens };
  } finally {
    await browser.close();
  }
}

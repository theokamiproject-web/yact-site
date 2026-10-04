import { launch } from '../../scripts/lib/browser.mjs';
import { pathToFileURL } from 'node:url';
const b = await launch(); const p = await b.newPage();
await p.goto(pathToFileURL(process.argv[2]).href);
console.log(JSON.stringify(await p.evaluate(() => {
  const cs = (sel) => getComputedStyle(document.querySelector(sel));
  return {
    'cv-title color (issue theme says lime, no !important)': cs('.cv-title').color,
    'cv-title font-size (issue theme says 20pt !important)': cs('.cv-title').fontSize,
    'kicker color (issue theme says blue)': cs('.page[data-page="4"] .kicker').color,
    'folio right (issue theme says .folio{right:40mm}) on p5': cs('.page[data-page="5"] .folio').right,
    'h1 letter-spacing (issue theme .page h1 = 1em)': cs('.fo-title').letterSpacing,
  };
}), null, 1));
await b.close();

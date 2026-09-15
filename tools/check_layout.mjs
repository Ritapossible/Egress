/* Measure every generated page at every width. Fails the build on overflow.
 *
 * Screenshots crop and a headless window is not the viewport, so neither is
 * evidence. This reads getBoundingClientRect() on every element instead - the
 * check that found a <details> menu painting out of a zero-width box while a
 * page-level scrollWidth comparison reported everything fine.
 *
 *   node tools/check_layout.mjs [--pages docs]
 */
import { chromium } from 'playwright';
import { readdirSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';

const dir = resolve(process.argv.includes('--pages')
  ? process.argv[process.argv.indexOf('--pages') + 1] : 'docs');
const pages = readdirSync(dir).filter(f => f.endsWith('.html')).sort();
const widths = [320, 360, 390, 430, 768, 900, 1024, 1440];

if (!pages.length) {
  console.error(`no pages in ${dir} - run "python -m egress.page" first`);
  process.exit(1);
}

const browser = await chromium.launch();
let failures = 0;

for (const width of widths) {
  const context = await browser.newContext({
    viewport: { width, height: 900 }, deviceScaleFactor: 1, isMobile: width < 700,
  });
  const page = await context.newPage();

  for (const file of pages) {
    await page.goto(pathToFileURL(resolve(dir, file)).href);
    const result = await page.evaluate(() => {
      const doc = document.documentElement;
      const scrolls = (el) => {
        for (let n = el.parentElement; n && n !== document.body; n = n.parentElement) {
          const ox = getComputedStyle(n).overflowX;
          if (ox === 'auto' || ox === 'scroll' || ox === 'hidden') return true;
        }
        return false;
      };
      const over = [];
      for (const el of document.querySelectorAll('body *')) {
        const r = el.getBoundingClientRect();
        if (r.width === 0 && r.height === 0) continue;
        if (r.right > doc.clientWidth + 1 || r.left < -1) {
          if (scrolls(el)) continue;      // clipped by a scroller on purpose
          over.push(`${el.tagName.toLowerCase()}${el.className ? '.' + el.className : ''}`
                    + ` [${Math.round(r.left)},${Math.round(r.right)}]`);
        }
      }
      // A menu that cannot be opened is broken even when nothing overflows.
      const menu = document.querySelector('details.menu');
      let menuOk = true;
      if (menu) {
        menu.open = true;
        const ul = menu.querySelector('ul').getBoundingClientRect();
        menuOk = ul.width > 0 && ul.right <= doc.clientWidth + 1 && ul.left >= -1;
        menu.open = false;
      }
      return { client: doc.clientWidth, scroll: doc.scrollWidth,
               over: over.slice(0, 5), menuOk };
    });

    const ok = result.scroll <= result.client + 1 && !result.over.length && result.menuOk;
    if (!ok) {
      failures++;
      console.error(`FAIL ${String(width).padEnd(5)} ${file}`
        + ` scroll=${result.scroll}/${result.client}`
        + (result.menuOk ? '' : ' menu=OFFSCREEN')
        + (result.over.length ? ` overflow=${JSON.stringify(result.over)}` : ''));
    }
  }
  await context.close();
}

await browser.close();
const checks = widths.length * pages.length;
if (failures) {
  console.error(`\n${failures} of ${checks} page/width combinations failed`);
  process.exit(1);
}
console.log(`OK: ${checks} checks (${pages.length} pages x ${widths.length} widths)`
  + ' - no horizontal overflow, menu reachable at every width');

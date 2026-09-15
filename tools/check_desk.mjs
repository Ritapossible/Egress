/* Drive the desk's client script in a real browser against real answer shapes.
 *
 * The gap this closes: a syntax check is not enough. `var inFlight` was deleted
 * during a refactor, every Python test stayed green, ruff stayed green, and the
 * desk threw a ReferenceError on the first click. Nothing executed the script.
 *
 *   node tools/check_desk.mjs
 */
import { chromium } from 'playwright';
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';

const answers = JSON.parse(readFileSync('tools/fixtures/answers.json', 'utf8'));
const page_url = pathToFileURL(resolve('docs/index.html')).href;

// What a reader must be able to see for each kind of answer.
const expect = {
  priced:     ['.verdict', '.ctx', 'details.working'],
  floor:      ['.verdict', '.warn', 'details.working'],
  unquotable: ['.verdict'],
  error:      ['.verdict.bad'],
};

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 390, height: 844 },
                                           isMobile: true });
const page = await context.newPage();

const problems = [];
page.on('pageerror', (e) => problems.push(`uncaught: ${e.message}`));
page.on('console', (m) => {
  if (m.type() === 'error' && !m.text().includes('ERR_FILE_NOT_FOUND')) {
    problems.push(`console: ${m.text()}`);
  }
});

for (const [name, answer] of Object.entries(answers)) {
  await page.goto(page_url);
  await page.evaluate((a) => {
    window.fetch = () => Promise.resolve({
      ok: true, status: 200, text: () => Promise.resolve(JSON.stringify(a)) });
    document.getElementById('q').value = 'cost to exit 40000 USDT of TSLA';
    document.getElementById('go').click();
  }, answer);

  try {
    await page.waitForSelector('#out .ans', { timeout: 5000 });
  } catch {
    problems.push(`${name}: the panel never rendered`);
    continue;
  }

  const found = await page.evaluate((sels) => sels.map(
    (s) => [s, document.querySelector(s) !== null]), expect[name]);
  for (const [sel, ok] of found) {
    if (!ok) problems.push(`${name}: expected ${sel} in the panel`);
  }

  // A disabled button after the answer means the form is stuck.
  const stuck = await page.evaluate(() => document.getElementById('go').disabled);
  if (stuck) problems.push(`${name}: the Ask button stayed disabled`);

  // Nothing user-supplied may reach the page as markup.
  const raw = await page.evaluate(() => document.getElementById('out').innerHTML);
  if (raw.includes('<script')) problems.push(`${name}: script tag in the panel`);
}

// The escaper must actually escape.
await page.goto(page_url);
await page.evaluate(() => {
  window.fetch = () => Promise.resolve({ ok: true, status: 200,
    text: () => Promise.resolve(JSON.stringify(
      { error: '<img src=x onerror=alert(1)>' })) });
  document.getElementById('q').value = 'x';
  document.getElementById('go').click();
});
try {
  await page.waitForSelector('#out .ans', { timeout: 5000 });
  const escaped = await page.evaluate(() =>
    document.querySelector('#out').innerHTML.includes('&lt;img'));
  if (!escaped) problems.push('an error message was not HTML-escaped');
} catch {
  problems.push('the panel never rendered for the escaping check');
}

await browser.close();

if (problems.length) {
  for (const p of problems) console.error(`FAIL ${p}`);
  console.error(`\n${problems.length} problem(s) in the desk client`);
  process.exit(1);
}
console.log(`OK: the desk client renders ${Object.keys(answers).length}`
  + ' answer shapes with no uncaught errors, and escapes its input');

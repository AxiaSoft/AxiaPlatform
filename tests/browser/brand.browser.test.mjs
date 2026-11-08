/* Brand lockup proportions, run in a real Chromium.

   The header lockup is a symbol plus a wordmark image, and the two have to read
   as one object: if the wordmark grows relative to the symbol, or the gap opens
   up, the brand looks like two unrelated items and starts competing with the
   navigation for attention.

   The failure this guards against is not a crash but a slow drift — the wordmark
   width was declared in six different rules across media queries, so raising one
   silently changed only some viewports. Measured before the fix: the wordmark
   was 2.3x the symbol width with a 10px gap; the footer was still 1.89x after
   the header had been corrected, because it uses the same base rule.

   Asserts, at every breakpoint, that:
     * the wordmark is between 1.2x and 2.0x the symbol width,
     * the gap between them stays small (<= 8px),
     * the wordmark never exceeds the symbol height,
     * header and footer lockups agree within 0.25x.

   Needs npm, so run it on demand:

     npm install --no-save --prefix /tmp/pup puppeteer-core@23
     CHROME=/path/to/chrome SITE=http://127.0.0.1:8000/AxiaPlatform/ \
       node tests/browser/brand.browser.test.mjs
*/

import puppeteer from 'puppeteer-core';

const BASE = process.env.SITE || 'http://127.0.0.1:8000/AxiaPlatform/';
const EXEC = process.env.CHROME || '/tmp/chromium';

const VIEWPORTS = [
  ['wide 1920', 1920, 1000, false],
  ['desktop 1440', 1440, 900, false],
  ['laptop 1024', 1024, 800, false],
  ['tablet 768', 768, 1024, true],
  ['phone 390', 390, 844, true],
  ['small 320', 320, 700, true],
];

const MIN_RATIO = 1.2;
const MAX_RATIO = 2.0;
const MAX_GAP = 8;

const browser = await puppeteer.launch({
  executablePath: EXEC,
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
});

const problems = [];
let checks = 0;

function measure(page, scope) {
  return page.evaluate((sel) => {
    const brand = document.querySelector(sel);
    if (!brand) return null;
    const mark = brand.querySelector('.brand-mark');
    const word = brand.querySelector('.brand-wordmark');
    if (!mark || !word) return null;
    const mb = mark.getBoundingClientRect();
    const wb = word.getBoundingClientRect();
    const visible = getComputedStyle(brand).display !== 'none' &&
                    getComputedStyle(brand).visibility !== 'hidden';
    return {
      visible,
      markW: mb.width, markH: mb.height,
      wordW: wb.width, wordH: wb.height,
      gap: wb.left - mb.right,
      ratio: wb.width / mb.width,
    };
  }, scope);
}

function check(label, where, m) {
  checks++;
  if (!m || !m.visible) return;
  if (m.ratio < MIN_RATIO || m.ratio > MAX_RATIO) {
    problems.push(
      `${label} ${where}: wordmark is ${m.ratio.toFixed(2)}x the symbol width ` +
      `(allowed ${MIN_RATIO}-${MAX_RATIO}x) - mark ${Math.round(m.markW)}px, word ${Math.round(m.wordW)}px`);
  }
  if (m.gap > MAX_GAP) {
    problems.push(`${label} ${where}: gap between symbol and text is ${Math.round(m.gap)}px (max ${MAX_GAP}px)`);
  }
  if (m.wordH > m.markH) {
    problems.push(
      `${label} ${where}: wordmark is taller than the symbol ` +
      `(${Math.round(m.wordH)}px vs ${Math.round(m.markH)}px)`);
  }
}

for (const [label, width, height, touch] of VIEWPORTS) {
  const page = await browser.newPage();
  await page.setViewport({ width, height, isMobile: touch, hasTouch: touch });
  await page.goto(BASE + '#/contact', { waitUntil: 'networkidle0', timeout: 30000 });
  await new Promise((resolve) => setTimeout(resolve, 500));

  const header = await measure(page, '.topbar .brand');
  check(label, 'header', header);

  // Footer lockup uses the same classes, so it must stay in the same family.
  await page.evaluate(() => document.querySelector('.footer .brand')?.scrollIntoView({ block: 'center' }));
  await new Promise((resolve) => setTimeout(resolve, 350));
  const footer = await measure(page, '.footer .brand');
  check(label, 'footer', footer);

  if (header?.visible && footer?.visible) {
    checks++;
    if (Math.abs(header.ratio - footer.ratio) > 0.25) {
      problems.push(
        `${label}: header and footer lockups disagree ` +
        `(header ${header.ratio.toFixed(2)}x, footer ${footer.ratio.toFixed(2)}x)`);
    }
  }
  await page.close();
}

await browser.close();

for (const problem of problems) console.log('FAIL  ' + problem);
console.log(`\n== ${checks - problems.length}/${checks} brand lockup checks passed ==`);
process.exit(problems.length ? 1 : 0);

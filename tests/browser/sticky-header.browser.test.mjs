/* Sticky header regression test, run in a real Chromium.

   The header is meant to travel with the page: it stays pinned to the top while
   the content scrolls under it. It silently stopped doing that when
   horizontal-overflow containment was added as `html { overflow-x: clip }` —
   any overflow value other than `visible` on the root element turns the root
   into the scroll container, so `position: sticky` children track that box
   instead of the viewport and scroll out of sight with the content.

   Containment therefore belongs on body (with `clip`, which — unlike `hidden`
   — does not create a scroll container that traps the header).

   This test scrolls each route and asserts the header stays at the top, keeps
   its height, and stays above the content. It also re-checks that the page
   still has no horizontal scroll, because that is what the containment is for
   and the two requirements pull in opposite directions.

   Needs npm, so run it on demand:

     npm install --no-save --prefix /tmp/pup puppeteer-core@23
     CHROME=/path/to/chrome SITE=http://127.0.0.1:8000/AxiaPlatform/ \
       node tests/browser/sticky-header.browser.test.mjs
*/

import puppeteer from 'puppeteer-core';

const BASE = process.env.SITE || 'http://127.0.0.1:8000/AxiaPlatform/';
const EXEC = process.env.CHROME || '/tmp/chromium';

const ROUTES = ['#/', '#/products', '#/services', '#/aurion', '#/about', '#/contact',
                '#/products/tutorial-product'];
// tutorial-product is planted by plantProduct() below, so the product-detail
// layout keeps its sticky-header coverage even though the shipped catalog is empty.
const VIEWPORTS = [
  ['desktop 1440', 1440, 900, false],
  ['desktop 1024', 1024, 800, false],
  ['tablet 820', 820, 1180, true],
  ['phone 390', 390, 844, true],
  ['small phone 320', 320, 700, true],
];

/* The catalog ships empty (products are created in the admin console), but these
   checks need real product cards to exercise. Planting one through the demo
   store makes the run cover the same UI regardless of the shipped catalog. */
const TUTORIAL_PRODUCT = {
  id: 1, slug: 'tutorial-product', title: 'Tutorial Product', category: 'Websites',
  summary: 'A representative product used by the browser test suite.',
  description: 'A representative product used by the browser test suite.',
  cover: 'web', features: ['One', 'Two'], technologies: ['Python'],
  status: 'available', price_label: 'Request a quote',
  github_url: 'https://github.com/AxiaSoft/tutorial-product', published: 1,
};

async function plantProduct(page) {
  await page.evaluateOnNewDocument((product) => {
    try {
      localStorage.setItem('axia-demo-products-v1', JSON.stringify([product]));
    } catch (err) { /* storage blocked: the catalog simply stays empty */ }
  }, TUTORIAL_PRODUCT);
}

const browser = await puppeteer.launch({
  executablePath: EXEC,
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
});

const problems = [];
let checks = 0;

for (const [label, width, height, touch] of VIEWPORTS) {
  const page = await browser.newPage();
  await plantProduct(page);
  await page.setViewport({ width, height, isMobile: touch, hasTouch: touch });

  for (const route of ROUTES) {
    await page.goto(BASE + route, { waitUntil: 'networkidle0', timeout: 30000 });
    await new Promise((resolve) => setTimeout(resolve, 400));

    const metrics = await page.evaluate(() => {
      const bar = document.querySelector('.topbar');
      if (!bar) return null;
      const start = bar.getBoundingClientRect();
      return {
        position: getComputedStyle(bar).position,
        height: Math.round(start.height),
        htmlOverflow: getComputedStyle(document.documentElement).overflowX,
        bodyOverflow: getComputedStyle(document.body).overflowX,
        maxScroll: document.documentElement.scrollHeight - window.innerHeight,
      };
    });
    checks++;

    if (!metrics) {
      problems.push(`${label} ${route}: no .topbar in the document`);
      continue;
    }
    if (metrics.position !== 'sticky' && metrics.position !== 'fixed') {
      problems.push(`${label} ${route}: header is ${metrics.position}, not sticky/fixed`);
    }
    if (metrics.htmlOverflow !== 'visible') {
      // The precise cause of the regression; name it so it cannot be vague.
      problems.push(
        `${label} ${route}: html has overflow-x:${metrics.htmlOverflow}, ` +
        `which makes the root a scroll container and disables sticky`);
    }

    // Scroll down the page and check the header is still pinned.
    for (const ratio of [0.25, 0.6, 1]) {
      if (metrics.maxScroll < 80) break;
      const target = Math.round(metrics.maxScroll * ratio);
      const result = await page.evaluate((y) => {
        window.scrollTo(0, y);
        return new Promise((resolve) => requestAnimationFrame(() => {
          const bar = document.querySelector('.topbar');
          const rect = bar.getBoundingClientRect();
          const de = document.documentElement;
          resolve({
            scrolledTo: Math.round(window.scrollY),
            top: Math.round(rect.top),
            height: Math.round(rect.height),
            zIndex: getComputedStyle(bar).zIndex,
            hScroll: de.scrollWidth > de.clientWidth + 1,
            scrollWidth: de.scrollWidth,
            clientWidth: de.clientWidth,
          });
        }));
      }, target);
      checks++;

      if (result.top !== 0) {
        problems.push(
          `${label} ${route}: scrolled to ${result.scrolledTo}px but the header is at ` +
          `top=${result.top}px instead of 0 (it scrolled away)`);
      }
      if (Math.abs(result.height - metrics.height) > 1) {
        problems.push(
          `${label} ${route}: header changed height while scrolling ` +
          `(${metrics.height} -> ${result.height}px)`);
      }
      if (result.zIndex === 'auto') {
        problems.push(`${label} ${route}: header has no z-index, content will paint over it`);
      }
      if (result.hScroll) {
        problems.push(
          `${label} ${route}: page scrolls horizontally at scrollY=${result.scrolledTo} ` +
          `(${result.scrollWidth} > ${result.clientWidth})`);
      }
    }
  }
  await page.close();
}

await browser.close();

for (const problem of problems.slice(0, 25)) console.log('FAIL  ' + problem);
if (problems.length > 25) console.log(`... and ${problems.length - 25} more`);
console.log(`\n== ${checks - problems.length}/${checks} sticky-header checks passed ==`);
process.exit(problems.length ? 1 : 0);

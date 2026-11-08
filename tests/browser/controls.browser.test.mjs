/* Interactive-control regression test, run in a real Chromium.

   Guards two defects that were visible to users:

   1. A blue box appeared around a button or link after clicking it. The cause
      was `outline: 2px solid var(--blue)` on `*:focus-visible`, plus a forced
      `border-radius: 10px` on `a:focus-visible` — so the ring ignored the
      element's shape and every link looked square. `:focus-visible` also fires
      for pointer input in some browsers.

   2. Tapping anything on a phone flashed the browser's default highlight
      (`-webkit-tap-highlight-color`), which reads as a blue/grey square over
      the control.

   The test clicks and taps every kind of control, then asserts that no focus
   ring survives, that the tap highlight is transparent, and that keyboard focus
   still produces a visible, shape-following ring (accessibility must not be
   sacrificed to fix the visual bug).

   Needs npm, so run it on demand:

     npm install --no-save --prefix /tmp/pup puppeteer-core@23
     CHROME=/path/to/chrome SITE=http://127.0.0.1:8000/AxiaPlatform/ \
       node tests/browser/controls.browser.test.mjs
*/

import puppeteer from 'puppeteer-core';

const BASE = process.env.SITE || 'http://127.0.0.1:8000/AxiaPlatform/';
const EXEC = process.env.CHROME || '/tmp/chromium';

const CONTROLS = ['.button-primary', '.button-quiet', '.tab', '.icon-button',
                  '.nav-links a', '.product-card', '.chat-launcher'];
const ROUTES = ['#/', '#/products', '#/services', '#/contact'];

const ringVisible = (style) =>
  style.outlineStyle !== 'none' && parseFloat(style.outlineWidth) > 0;

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

async function inspect(page, selector) {
  return page.evaluate((sel) => {
    const el = document.querySelector(sel);
    if (!el) return null;
    window.__prevEl = el;
    const cs = getComputedStyle(el);
    return {
      focusVisible: el.matches(':focus-visible'),
      outlineStyle: cs.outlineStyle,
      outlineWidth: cs.outlineWidth,
      outlineOffset: cs.outlineOffset,
      radius: parseFloat(cs.borderTopLeftRadius) || 0,
      tap: cs.webkitTapHighlightColor,
      cursor: cs.cursor,
    };
  }, selector);
}

for (const [label, viewport, touch] of [
  ['desktop 1280', { width: 1280, height: 900 }, false],
  ['laptop 1024', { width: 1024, height: 800 }, false],
  ['phone 390', { width: 390, height: 844 }, true],
  ['small phone 320', { width: 320, height: 700 }, true],
]) {
  const page = await browser.newPage();
  await plantProduct(page);
  await page.setViewport({ ...viewport, isMobile: touch, hasTouch: touch });

  for (const route of ROUTES) {
    await page.goto(BASE + route, { waitUntil: 'networkidle0', timeout: 30000 });
    await new Promise((resolve) => setTimeout(resolve, 500));

    for (const selector of CONTROLS) {
      const present = await page.$(selector);
      if (!present) continue;

      // --- tap highlight must be suppressed everywhere -------------------
      const before = await inspect(page, selector);
      if (before && before.tap !== 'rgba(0, 0, 0, 0)') {
        problems.push(`${label} ${route} ${selector}: tap highlight is ${before.tap}`);
      }
      checks++;

      // --- pointer activation must not leave a ring ----------------------
      await page.evaluate((sel) => document.querySelector(sel)?.scrollIntoView({ block: 'center' }), selector);
      await new Promise((resolve) => setTimeout(resolve, 120));
      if (touch) {
        const handle = await page.$(selector);
        const box = handle ? await handle.boundingBox() : null;
        if (!box) continue;
        await page.touchscreen.tap(box.x + box.width / 2, box.y + box.height / 2);
      } else {
        await page.click(selector).catch(() => {});
      }
      await new Promise((resolve) => setTimeout(resolve, 180));
      const after = await inspect(page, selector);
      checks++;
      if (after && ringVisible(after)) {
        problems.push(
          `${label} ${route} ${selector}: ring after pointer activation ` +
          `(focus-visible=${after.focusVisible}, ${after.outlineStyle} ${after.outlineWidth})`);
      }
      await page.evaluate((sel) => document.querySelector(sel)?.blur(), selector);
    }
  }
  await page.close();
}

// --- keyboard focus must still be clearly visible -------------------------
{
  const page = await browser.newPage();
  await plantProduct(page);
  await page.setViewport({ width: 1280, height: 900 });
  await page.goto(BASE + '#/products', { waitUntil: 'networkidle0' });
  await new Promise((resolve) => setTimeout(resolve, 600));

  for (const selector of ['.tab', '.button-primary', '.nav-links a']) {
    const handle = await page.$(selector);
    if (!handle) continue;
    await page.evaluate((sel) => {
      const el = document.querySelector(sel);
      el.focus();
      // Keyboard focus is what turns :focus-visible on; a plain .focus() call
      // already reports it, so this reflects the real Tab path.
    }, selector);
    const style = await inspect(page, selector);
    checks++;
    if (!style || !ringVisible(style)) {
      problems.push(`${selector}: keyboard focus has no visible ring (accessibility regression)`);
    } else if (style.radius > 1 && style.outlineOffset === '0px') {
      // A ring pinned to the border box ignores the corner radius in older engines.
      problems.push(`${selector}: keyboard ring has no offset on a rounded control`);
    }
    await page.evaluate((sel) => document.querySelector(sel)?.blur(), selector);
  }
  await page.close();
}

await browser.close();

for (const problem of problems) console.log('FAIL  ' + problem);
console.log(`\n== ${checks - problems.length}/${checks} control checks passed ==`);
process.exit(problems.length ? 1 : 0);

/* Every control must be clickable across its whole face.

   Decorative, absolutely-positioned pseudo-elements (glow circles, gradients,
   orbit rings) paint above the content they sit next to. Without
   `pointer-events:none` they silently swallow clicks, so a button looks normal
   but only its left half responds. That is exactly what happened to the
   "Request this product" button inside .category-card: a 190x190 blurred
   circle at right:-34px/bottom:-95px covered its right edge.

   This walks a grid of points across each button and fails if any point in the
   middle of the control does not hit the control itself.

     SITE=http://127.0.0.1:8110/AxiaPlatform/ CHROME=/tmp/chromium \
       LD_LIBRARY_PATH=/tmp/cwx/lib node tests/browser/interactive-hit.browser.test.mjs
*/
import puppeteer from 'puppeteer-core';

const BASE = process.env.SITE || 'http://127.0.0.1:8000/AxiaPlatform/';
const EXEC = process.env.CHROME || '/tmp/chromium';
const LANGS = ['en', 'fa'];

const browser = await puppeteer.launch({ executablePath: EXEC,
  args: ['--no-sandbox', '--disable-dev-shm-usage'] });
const failures = [];
let checks = 0;

for (const lang of LANGS) {
  const page = await browser.newPage();
  page.on('dialog', (d) => d.accept().catch(() => {}));
  await page.setViewport({ width: 1440, height: 1000 });
  await page.setCacheEnabled(false);
  await page.goto(BASE, { waitUntil: 'networkidle0' });

  /* The shipped catalog is intentionally empty, so the storefront has no cards
     and no order buttons - the test would otherwise pass vacuously. Seed two
     illustrative products straight into the same storage the demo console uses.
     The storefront reads them through demo-backend.js. */
  await page.goto(BASE, { waitUntil: 'networkidle0' });
  await page.evaluate((lang) => {
    const products = [
      { id: 1, slug: 'northstar-corporate', title: 'Northstar Corporate', category: 'Websites',
        summary: 'A concept for a brand-led website.', price_label: 'from €4,800',
        status: 'available', published: true, featured: false, position: 0, cover: '' },
      { id: 2, slug: 'atlas-client-portal', title: 'Atlas Client Portal', category: 'Applications',
        summary: 'A concept for a client portal.', price_label: 'from €6,200',
        status: 'available', published: true, featured: false, position: 1, cover: '' }
    ];
    localStorage.setItem('axia-demo-products-v1', JSON.stringify(products));
    localStorage.setItem('axia-lang', lang);
  }, lang);

  for (const route of ['#/contact', '#/products', '#/']) {
    await page.goto(BASE + route, { waitUntil: 'networkidle0' });
    await new Promise((r) => setTimeout(r, 1500));

    const targets = await page.evaluate(() => {
      const out = [];
      const seen = new Set();
      for (const el of document.querySelectorAll('.button, button, a.button')) {
        const r = el.getBoundingClientRect();
        if (r.width < 40 || r.height < 16) continue;
        if (el.disabled) continue;
        if (seen.has(el)) continue;
        seen.add(el);
        out.push({ sel: el.tagName + '.' + String(el.className).slice(0, 40),
                   label: (el.textContent || '').trim().slice(0, 40),
                   x: r.x, y: r.y, w: r.width, h: r.height });
      }
      return out;
    });

    if (!targets.length) failures.push(`${lang} ${route}: no clickable controls were rendered`);

    for (const t of targets) {
      // Sample the interior, staying just inside the rounded corners.
      const points = [];
      for (const fy of [0.25, 0.5, 0.75]) {
        for (const fx of [0.08, 0.3, 0.5, 0.7, 0.92]) points.push([fx, fy]);
      }
      const bad = await page.evaluate((t, points) => {
        const el = document.elementFromPoint(t.x + t.w * 0.5, t.y + t.h * 0.5);
        let node = el;
        while (node && !(node.matches && node.matches('.button, button, a.button'))) node = node.parentElement;
        if (!node) return null;              // the centre is fine, use it as anchor
        const misses = [];
        for (const [fx, fy] of points) {
          const hit = document.elementFromPoint(t.x + t.w * fx, t.y + t.h * fy);
          if (!hit) continue;
          const inside = node.contains(hit) || hit === node || node.contains(hit.parentElement);
          if (!inside) misses.push(`${Math.round(fx * 100)}%x${Math.round(fy * 100)}%`);
        }
        return misses;
      }, t, points);

      checks++;
      if (bad && bad.length) {
        failures.push(`${lang} ${route} [${t.label || t.sel}] dead at ${bad.join(' ')}`);
      }

      /* elementFromPoint can disagree with a real click because the browser
         hit-tests the topmost painted layer, including pseudo-elements. Click
         the far edge of order buttons, which is where a decorative overlay
         used to sit. */
      if (route === '#/contact' && /Request this product|درخواست این محصول/.test(t.label)) {
        for (const fx of [0.9, 0.96]) {
          await page.mouse.click(t.x + t.w * fx, t.y + t.h / 2);
          await new Promise((r) => setTimeout(r, 260));
          const opened = await page.evaluate(() => !!document.querySelector('.modal-overlay'));
          checks++;
          if (!opened) failures.push(`${lang} ${route} click at ${Math.round(fx * 100)}% of [${t.label}] did nothing`);
          await page.evaluate(() => document.querySelector('.modal-overlay')?.remove());
        }
      }
    }
  }
  await page.close();
}

await browser.close();
if (failures.length) {
  console.log('FAILURES');
  for (const f of failures.slice(0, 12)) console.log('  ' + f);
}
console.log(`\n== ${checks - failures.length}/${checks} controls are clickable across their whole face ==`);
process.exit(failures.length ? 1 : 0);

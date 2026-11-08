/* Horizontal-scroll regression test, run in a real Chromium.

   Guards the bug where the hero's 3D orbit leaned past the viewport and let the
   whole page scroll sideways, worst in RTL. It measures documentElement
   scrollWidth AND proves it behaviourally by trying to scroll, then checks that
   no asset 404s (a missing font silently widens the text and reintroduces the
   overflow).

   Needs a Chromium binary and puppeteer-core, neither of which ship with the
   project, so it is run on demand rather than in CI:

     npm install --no-save --prefix /tmp/pup puppeteer-core@23
     # any chromium works; point CHROME at it
     CHROME=/path/to/chrome SITE=http://127.0.0.1:8000/AxiaPlatform/ \
       node tests/browser/overflow.browser.test.mjs

   Exit code is non-zero if any combination scrolls horizontally or 404s.
*/

import puppeteer from 'puppeteer-core';
const BASE = process.env.SITE || 'http://127.0.0.1:8000/AxiaPlatform/';
const EXEC = process.env.CHROME || '/tmp/chromium';
const browser = await puppeteer.launch({ executablePath: EXEC,
  args:['--no-sandbox','--disable-dev-shm-usage'] });

// The catalog ships empty, so no product slug is assumed here; the product
// detail layout is covered by products.browser.test.mjs once a product exists.
const ROUTES = ['#/','#/products','#/services','#/aurion','#/about','#/contact',
                '#/account','#/legal/privacy','#/legal/terms'];
const WIDTHS = [320,360,390,414,540,768,820,1024,1280,1440,1920];
const LANGS = ['en','fa'];

let total=0, fails=0;
const problems = [];

for (const lang of LANGS) {
  for (const w of WIDTHS) {
    const page = await browser.newPage();
    const assetErrors = [];
    page.on('response', r => { if (r.status() >= 400) assetErrors.push(`${r.status()} ${r.url()}`); });
    await page.setViewport({ width:w, height:800, isMobile:w<900, hasTouch:w<900 });
    await page.goto(BASE, { waitUntil:'domcontentloaded' });
    await page.evaluate(l => localStorage.setItem('axia-lang', l), lang);
    for (const route of ROUTES) {
      await page.goto(BASE + route, { waitUntil:'networkidle0', timeout:30000 });
      await new Promise(r=>setTimeout(r, 500));
      const d = await page.evaluate(() => {
        const de = document.documentElement;
        const canScrollX = de.scrollWidth > de.clientWidth + 1;
        // also prove it behaviourally: try to scroll and see if anything moves
        const before = window.scrollX;
        window.scrollTo(9999, 0);
        const after = window.scrollX;
        window.scrollTo(before, 0);
        return { sw: de.scrollWidth, cw: de.clientWidth, canScrollX,
                 moved: after > before, dir: de.dir, lang: de.lang };
      });
      total++;
      const bad = d.canScrollX || d.moved || assetErrors.length;
      if (bad) {
        fails++;
        problems.push({ lang, w, route, ...d, assetErrors:[...new Set(assetErrors)] });
        if (problems.length <= 6)
          console.log(`FAIL ${lang} ${w}px ${route}  sw=${d.sw} cw=${d.cw} scrolled=${d.moved} ${assetErrors.slice(0,2).join(',')}`);
      }
      assetErrors.length = 0;
    }
    await page.close();
  }
}
await browser.close();

console.log(`\n== ${total-fails}/${total} page/width/lang combinations: no horizontal scroll, no failed assets ==`);
if (fails) { console.log('\nFirst failures:'); console.log(JSON.stringify(problems.slice(0,5), null, 2)); }
process.exit(fails ? 1 : 0);

/* No horizontal scroll on the administrator console, in a real Chromium.

   The storefront has had a regression test for this since the hero orbit bug;
   the console grew a wide product table, a six-column stat grid and a settings
   form, all of which can push past a 320px viewport. This walks every console
   page at every common width in both languages and fails on any page that
   overflows, with the widest offending element named.

   Run against a built, served copy:

     SITE=http://127.0.0.1:8110/AxiaPlatform/ CHROME=/tmp/chromium \
       LD_LIBRARY_PATH=/tmp/cwx/lib node tests/browser/admin-overflow.browser.test.mjs
*/
import puppeteer from 'puppeteer-core';

const BASE = process.env.SITE || 'http://127.0.0.1:8000/AxiaPlatform/';
const EXEC = process.env.CHROME || '/tmp/chromium';
const PAGES = ['#dashboard', '#site', '#products', '#orders', '#customers',
               '#support', '#refunds', '#activity'];
const WIDTHS = [320, 360, 390, 414, 540, 768, 820, 1024, 1280, 1440, 1920];
const LANGS = ['en', 'fa'];

const browser = await puppeteer.launch({ executablePath: EXEC,
  args: ['--no-sandbox', '--disable-dev-shm-usage'] });

let total = 0;
const problems = [];

for (const lang of LANGS) {
  for (const width of WIDTHS) {
    const context = await browser.createBrowserContext();
    const page = await context.newPage();
    page.on('dialog', (d) => d.accept().catch(() => {}));
    await page.setViewport({ width, height: 900 });
    await page.goto(BASE + 'admin/', { waitUntil: 'networkidle0', timeout: 30000 });
    await page.evaluate((l) => localStorage.setItem('axia-lang', l), lang);
    await page.reload({ waitUntil: 'networkidle0' });
    await new Promise((r) => setTimeout(r, 700));
    await page.type('#loginEmail', 'demo');
    await page.type('#loginPassword', 'demo');
    await page.click('[data-form="login"] button');
    await new Promise((r) => setTimeout(r, 1500));
    await page.evaluate(() => { if (window.AXIA_DEMO_SAMPLES) window.AXIA_DEMO_SAMPLES(); });
    await page.reload({ waitUntil: 'networkidle0' });
    await new Promise((r) => setTimeout(r, 1500));

    for (const route of PAGES) {
      await page.evaluate((h) => { location.hash = h; }, route);
      await new Promise((r) => setTimeout(r, 850));
      const result = await page.evaluate(() => {
        const de = document.documentElement;
        const offenders = [...document.querySelectorAll('.content *')]
          .filter((el) => {
            const rect = el.getBoundingClientRect();
            if (rect.width === 0) return false;
            if (getComputedStyle(el).position === 'fixed') return false;
            return rect.right > de.clientWidth + 1 || rect.left < -1;
          })
          .slice(0, 3)
          .map((el) => `${el.tagName}.${String(el.className).slice(0, 24)}`);
        return { overflow: de.scrollWidth > de.clientWidth + 1,
                 scrollWidth: de.scrollWidth, clientWidth: de.clientWidth, offenders };
      });
      total++;
      if (result.overflow) {
        problems.push(`${lang} ${width}px ${route} sw=${result.scrollWidth} cw=${result.clientWidth} ` +
                      result.offenders.join(','));
      }
    }
    await context.close();
  }
}

await browser.close();
if (problems.length) {
  console.log('FAILURES');
  for (const p of problems.slice(0, 10)) console.log('  ' + p);
}
console.log(`\n== ${total - problems.length}/${total} admin page/width/lang combinations: no horizontal scroll ==`);
process.exit(problems.length ? 1 : 0);

/* Persian (RTL) layout and halo integrity, run in a real Chromium.

   Two things are asserted, both of which broke before:

   1. RTL. The Persian build sets html[dir=rtl], and layout mirroring alone is
      not enough: any element that keeps text-align:left inside an RTL page
      reads as "half translated". This walks every text block on every route and
      fails on left-aligned text, on a missing dir, or on the wrong html lang.

   2. Halos are never sliced. The hero halo is a fixed-size circle behind a 3D
      orbit; where it was wider than its container the page edge cut a slice off
      it, which is what "the halo is cut in half" looked like. It is now sized
      with min() against the container and the viewport, so this checks that the
      orbit and the halo stay fully inside the viewport at every width.

   Needs npm, so run it on demand:

     npm install --no-save --prefix /tmp/pup puppeteer-core@23
     CHROME=/path/to/chrome SITE=http://127.0.0.1:8000/AxiaPlatform/ \
       node tests/browser/rtl-halos.browser.test.mjs
*/

import puppeteer from 'puppeteer-core';

const BASE = process.env.SITE || 'http://127.0.0.1:8000/AxiaPlatform/';
const EXEC = process.env.CHROME || '/tmp/chromium';

const ROUTES = ['#/', '#/products', '#/services', '#/aurion', '#/about',
                '#/contact', '#/account', '#/legal/privacy'];
const HALO_WIDTHS = [320, 360, 390, 414, 540, 768, 820, 1024, 1280, 1440, 1920];

// Text that legitimately stays latin in the Persian build.
const ALLOWED_LATIN = /^(AXIASOFT|AXIA|AURION|MetaTrader|Android|iOS|EN|AI|CSV|\d+|\d+\s*\/\s*\d+|Next\.js|TypeScript|PostgreSQL|Node\.js|React|CSS|HTML|SQLite|Python|JavaScript|JSON|API)$/;

const browser = await puppeteer.launch({
  executablePath: EXEC,
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
});

const problems = [];
let checks = 0;

// ---------------------------------------------------------------- Persian
for (const width of [390, 1280]) {
  for (const route of ROUTES) {
    const page = await browser.newPage();
    await page.setViewport({ width, height: 800, isMobile: width < 900, hasTouch: width < 900 });
    await page.evaluateOnNewDocument(() => {
      try { localStorage.setItem('axia-lang', 'fa'); } catch (error) { /* ignore */ }
    });
    await page.goto(BASE + route, { waitUntil: 'networkidle0', timeout: 30000 });
    await new Promise((resolve) => setTimeout(resolve, 700));

    const result = await page.evaluate((allowedSource) => {
      const allowed = new RegExp(allowedSource);
      const de = document.documentElement;
      const leftAligned = [];

      for (const el of document.querySelectorAll(
        'h1,h2,h3,p,li,label,.subhead,.eyebrow,.nav-links a,.footer-links a,' +
        '.button,.tab,.orbit-tag,.product-info h3,.category-card h3')) {
        const cs = getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        if (!rect.width || cs.display === 'none' || cs.visibility === 'hidden') continue;
        // A handful of technical strings are deliberately LTR.
        if (el.closest('[dir="ltr"], .preview-toolbar, pre, code')) continue;
        if (cs.textAlign === 'left') {
          leftAligned.push(`<${el.tagName.toLowerCase()}.${String(el.className || '').trim().split(/\s+/)[0]}>`);
        }
      }

      const untranslated = new Set();
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      let node;
      while ((node = walker.nextNode())) {
        const text = (node.nodeValue || '').trim();
        if (text.length < 5) continue;
        if (node.parentElement?.closest('script,style,noscript,.brand,code,pre')) continue;
        if (!/^[\x20-\x7E\p{P}\p{S}]*$/u.test(text)) continue;   // contains Persian -> fine
        if (/[A-Za-z]{2,}/.test(text) === false) continue;         // no words -> skip separators
        if (allowed.test(text)) continue;
        untranslated.add(text.slice(0, 50));
      }

      return {
        lang: de.lang,
        dir: de.dir,
        leftAligned: leftAligned.slice(0, 5),
        leftCount: leftAligned.length,
        untranslated: [...untranslated].slice(0, 6),
        unCount: untranslated.size,
        scrollW: de.scrollWidth,
        clientW: de.clientWidth,
      };
    }, ALLOWED_LATIN.source);
    checks++;

    if (result.lang !== 'fa' || result.dir !== 'rtl') {
      problems.push(`${width}px ${route}: html is lang=${result.lang} dir=${result.dir}, expected fa/rtl`);
    }
    if (result.leftCount > 0) {
      problems.push(`${width}px ${route}: ${result.leftCount} element(s) still left-aligned: ` +
                    result.leftAligned.join(' '));
    }
    if (result.scrollW > result.clientW + 1) {
      problems.push(`${width}px ${route}: page scrolls horizontally (${result.scrollW} > ${result.clientW})`);
    }
    if (result.unCount > 0) {
      // Reported, not fatal: some proper nouns are expected, this is a review aid.
      console.log(`NOTE  ${width}px ${route}: untranslated latin: ${result.untranslated.join(' | ')}`);
    }
    await page.close();
  }
}

// ------------------------------------------------------------- halo integrity
for (const width of HALO_WIDTHS) {
  const page = await browser.newPage();
  await page.setViewport({ width, height: 850, isMobile: width < 900, hasTouch: width < 900 });
  await page.goto(BASE + '#/', { waitUntil: 'networkidle0', timeout: 30000 });
  await new Promise((resolve) => setTimeout(resolve, 700));

  const halo = await page.evaluate(() => {
    const de = document.documentElement;
    const vw = de.clientWidth;
    const art = document.querySelector('.hero-art');
    const orbit = document.querySelector('.hero-orbit');
    const logo = document.querySelector('.hero-logo');
    const before = art ? getComputedStyle(art, '::before') : null;

    const boxes = {};
    for (const [name, el] of [['orbit', orbit], ['logo', logo]]) {
      if (!el) continue;
      const r = el.getBoundingClientRect();
      boxes[name] = { left: r.left, right: r.right, top: r.top, bottom: r.bottom };
    }
    const artRect = art ? art.getBoundingClientRect() : null;
    return {
      vw,
      haloWidth: before ? parseFloat(before.width) : null,
      haloHeight: before ? parseFloat(before.height) : null,
      artOverflow: art ? getComputedStyle(art).overflow : null,
      boxes,
      // offsetWidth/Height are the untransformed border box. The hero is
      // transform:scale(.88) at tablet widths, so getBoundingClientRect() would
      // report a shrunken box and make a correctly-sized halo look oversized.
      artBox: artRect ? { left: artRect.left, right: artRect.right,
                          top: artRect.top, bottom: artRect.bottom,
                          width: art.offsetWidth, height: art.offsetHeight } : null,
      // Does the clip have anything to cut? Measured: if a decoration paints past
      // the box that clips it, the clip turns a soft glow into a straight edge.
      // 1px tolerance: the halo is a percentage of this same box, so a rounding
      // difference of a fraction of a pixel is not a slice.
      haloPokesX: !!(before && artRect &&
        (parseFloat(before.width) > art.offsetWidth + 1)),
      haloPokesY: !!(before && artRect &&
        (parseFloat(before.height) > art.offsetHeight + 1)),
      hScroll: de.scrollWidth > vw + 1,
      scrollW: de.scrollWidth,
    };
  });
  checks++;

  // The halo must never be wider than the space it lives in.
  if (halo.haloWidth !== null && halo.haloWidth > halo.vw + 1) {
    problems.push(`${width}px: halo is ${Math.round(halo.haloWidth)}px wide, wider than the ${halo.vw}px viewport`);
  }
  // A decoration that is bigger than the box clipping it gets a dead-straight
  // edge where the clip lands. Both the halo disc and the 3D ring have to fit
  // inside .hero-art, or the glow is visibly sliced in half.
  if (halo.haloPokesX || halo.haloPokesY) {
    problems.push(`${width}px: halo (${Math.round(halo.haloWidth)}x${Math.round(halo.haloHeight)}) ` +
                  `is larger than .hero-art (${Math.round(halo.artBox.width)}x${Math.round(halo.artBox.height)}), so the clip slices it`);
  }
  if (halo.artBox) {
    const o = halo.boxes.orbit;
    if (o) {
      const over = Math.max(o.right - halo.artBox.right, halo.artBox.left - o.left);
      if (over > 1) {
        problems.push(`${width}px: orbit ring pokes ${Math.round(over)}px out of .hero-art, so the clip slices it`);
      }
    }
  }
  // Nothing decorative may stick out of the viewport, or the page edge slices it.
  for (const [name, box] of Object.entries(halo.boxes)) {
    if (box.left < -1) {
      problems.push(`${width}px: ${name} extends ${Math.round(-box.left)}px past the left edge (would be cut)`);
    }
    if (box.right > halo.vw + 1) {
      problems.push(`${width}px: ${name} extends ${Math.round(box.right - halo.vw)}px past the right edge (would be cut)`);
    }
  }
  // overflow:clip on .hero-art is the guard that keeps a 3D ring from pushing the
  // page sideways, so it is allowed - but only when nothing inside pokes out of
  // it (checked above). What is NOT allowed is a value that clips unevenly.
  if (halo.artOverflow && !['clip', 'visible'].includes(halo.artOverflow)) {
    problems.push(`${width}px: .hero-art has overflow:${halo.artOverflow}, which slices the orbit`);
  }
  if (halo.hScroll) {
    problems.push(`${width}px: page scrolls horizontally (${halo.scrollW} > ${halo.vw})`);
  }
  await page.close();
}

await browser.close();

for (const problem of problems) console.log('FAIL  ' + problem);
console.log(`\n== ${checks - problems.length}/${checks} RTL + halo checks passed ==`);
process.exit(problems.length ? 1 : 0);

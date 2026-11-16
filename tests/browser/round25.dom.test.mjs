// Round 25: the brand logos, and the category rules around them.
//
// Two reports from the operator:
//
//   1. "put the category logos in the demo" — Arya, Homa, Ersha and Mino each
//      arrived as a picture and the storefront drew a monogram from the initial
//      instead, because a brand shipped no artwork.
//   2. "don't show the site's categories in the app" — the website brands were
//      offered on every catalog tab, including Applications, where choosing one
//      emptied the grid; and a product's own page led with its category instead
//      of with the product.
//
// This drives the real storefront with the committed settings and catalog, so a
// regression in either shows up as a missing image or a stray category label.
import { JSDOM, VirtualConsole } from 'jsdom';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const R = process.env.STATIC_DIST || fileURLToPath(new URL('../../public/', import.meta.url));
const ROOT = process.env.STATIC_DIST
  ? path.dirname(process.env.STATIC_DIST.replace(/\/$/, ''))
  : fileURLToPath(new URL('../../', import.meta.url));
const out = [];
const ck = (n, ok, x = '') => out.push(`${ok ? 'PASS' : 'FAIL'}  ${n}${x ? '  (' + x + ')' : ''}`);

const read = (p) => { try { return fs.readFileSync(p, 'utf8'); } catch { return ''; } };
const settings = JSON.parse(read(ROOT + 'data/settings.json') || '{}');
const products = JSON.parse(read(ROOT + 'data/products.json') || '[]');
const BRANDS = settings.brands || [];

function boot() {
  const vc = new VirtualConsole();
  vc.on('jsdomError', () => {});
  const dom = new JSDOM(read(R + 'index.html'), {
    runScripts: 'outside-only', pretendToBeVisual: true,
    url: 'http://localhost:8000/', virtualConsole: vc,
    beforeParse(w) {
      w.matchMedia = (q) => ({
        matches: /hover: hover/.test(q) || !/reduce/.test(q), media: q,
        addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
        dispatchEvent() { return false; },
      });
      w.IntersectionObserver = class {
        constructor(cb) { this.cb = cb; }
        observe(el) { this.cb([{ isIntersecting: true, target: el }], this); }
        unobserve() {} disconnect() {}
      };
      w.requestAnimationFrame = (fn) => setTimeout(() => fn(0), 0);
      w.scrollTo = () => {};
      w.fetch = async (u) => {
        const s = String(u);
        const body = /\/api\/site/.test(s) ? { settings } : (/products/.test(s) ? products : {});
        return { ok: true, json: async () => body, headers: { get: () => null } };
      };
    },
  });
  const w = dom.window;
  w.AXIA_STATIC = { products: [], articles: [], pages: [], pairs: [], settings };
  for (const f of ['i18n.js', 'data/settings.js', 'brands.js']) {
    try { w.eval(read(R + f)); } catch { /* the settings snapshot is also fetched */ }
  }
  w.eval(read(R + 'app.js'));
  return w;
}

const go = async (w, hash, wait = 600) => {
  w.location.hash = hash;
  w.dispatchEvent(new w.Event('hashchange'));
  await new Promise((r) => setTimeout(r, wait));
  return w.document.querySelector('#app');
};

const brandFiles = BRANDS.map((b) => b.logo || b.mark).filter(Boolean);

// ---- the artwork is really shipped ------------------------------------- //
ck('every brand names an image', brandFiles.length === BRANDS.length,
  `${brandFiles.length}/${BRANDS.length}`);
for (const file of brandFiles) {
  const full = R + file.replace(/^\//, '');
  ck(`the file exists: ${file}`, fs.existsSync(full));
}
// The supplied marks are blue artwork on white; PNG was 3-5x heavier.
ck('the marks ship as WebP, not PNG', brandFiles.every((f) => /\.webp$/.test(f)),
  brandFiles.join(' '));

const win = boot();
await new Promise((r) => setTimeout(r, 1200));

// ---- the catalog shows them ------------------------------------------- //
const catalog = await go(win, '#/products');
const pickerLogos = [...catalog.querySelectorAll('.brand-pick-logo img')]
  .map((i) => i.getAttribute('src').split('/').pop());
ck('the brand strip is on the websites tab', catalog.querySelectorAll('.brand-pick').length === BRANDS.length,
  `${catalog.querySelectorAll('.brand-pick').length} cards`);
ck('every brand picker card shows its logo',
  brandFiles.every((f) => pickerLogos.includes(f.split('/').pop())),
  pickerLogos.join(' '));

const covers = [...catalog.querySelectorAll('.product-cover img')].map((i) => i.getAttribute('src'));
ck('the product cards show the brand marks',
  covers.length >= 4 && covers.every((c) => /-logo\.webp$/.test(c)),
  covers.join(' '));

// ---- the categories stay in the grid ---------------------------------- //
const tabs = [...catalog.querySelectorAll('.tab')].map((t) => t.textContent.trim());
ck('the tab row does not offer an empty category',
  !tabs.some((t) => /^Applications$|اپلیکیشن/.test(t)), tabs.join(' | '));

// ---- a brand never leaks into another tab ----------------------------- //
const apps = await go(win, '#/products?category=applications');
ck('the applications tab offers no website brands',
  !apps.querySelector('.brand-picker'),
  `${apps.querySelectorAll('.brand-pick').length} cards`);

// ---- a product's own page is about the product ------------------------ //
const detail = await go(win, '#/products/arya');
const eyebrow = (detail.querySelector('.eyebrow') || {}).textContent || '';
const badges = [...detail.querySelectorAll('.detail-meta .badge')].map((b) => b.textContent);
ck('the product page does not lead with the category',
  !/websites|وب‌سایت/i.test(eyebrow), eyebrow.trim());
ck('the category is not among the product badges',
  !badges.some((b) => /^websites$|^وب‌سایت‌ها$/.test(b.trim())), badges.join(' | '));
ck('the cover caption does not print the category',
  !/websites/i.test((detail.querySelector('.cover-label') || {}).textContent || ''));
ck('the product page still shows the brand logo',
  /-logo\.webp$/.test((detail.querySelector('.product-cover img') || {}).src || ''),
  (detail.querySelector('.product-cover img') || {}).src || 'none');

console.log(out.join('\n'));
const failed = out.filter((l) => l.startsWith('FAIL')).length;
console.log(`\n${out.length - failed}/${out.length} checks passed`);
process.exit(failed ? 1 : 0);

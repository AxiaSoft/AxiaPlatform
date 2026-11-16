// Round 26: the demo catalog is not empty.
//
// The operator asked for two things that pull in opposite directions: "add a few
// products to the demo so it is not empty, but only the server site must stay
// clean." The demo shipped four products, all of them website brands, so the
// Applications tab opened an empty grid and the filter row offered a tab that
// led nowhere.
//
// This boots the real storefront with the built snapshot and counts what a
// visitor sees on each tab. The server side of the same guarantee is asserted in
// tests/test_static_build.py (the server shell carries no catalog snapshot).
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

// Load the Persian dictionary so the titles are checked in the language the
// default visitor reads.
function translator() {
  const sandbox = {
    window: {},
    document: { documentElement: { dataset: {}, lang: '', dir: '' }, querySelector: () => null,
      addEventListener() {}, body: {}, createTreeWalker: () => ({ nextNode: () => null }) },
    localStorage: { getItem: () => 'fa', setItem() {} },
    location: { search: '', reload() {} },
    URLSearchParams, MutationObserver: class { observe() {} },
    NodeFilter: { SHOW_TEXT: 4 }, Node: { TEXT_NODE: 3, ELEMENT_NODE: 1 },
    console,
  };
  // eslint-disable-next-line no-new-func
  new Function('window', 'document', 'localStorage', 'location', 'URLSearchParams',
    'MutationObserver', 'NodeFilter', 'Node', 'console', read(R + 'i18n.js'))(
    sandbox.window, sandbox.document, sandbox.localStorage, sandbox.location,
    URLSearchParams, sandbox.MutationObserver, sandbox.NodeFilter, sandbox.Node, console);
  return sandbox.window.AXIA_T || ((x) => x);
}

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

const go = async (w, hash, wait = 650) => {
  w.location.hash = hash;
  w.dispatchEvent(new w.Event('hashchange'));
  await new Promise((r) => setTimeout(r, wait));
  return w.document.querySelector('#app');
};

// ---- the build really ships a catalog ---------------------------------- //
ck('the demo snapshot is populated', products.length >= 10, `${products.length} products`);

const byCat = {};
for (const p of products) (byCat[p.category] = byCat[p.category] || []).push(p);
const demoCats = (settings.categories || []).map((c) => c.id);
for (const id of demoCats) {
  ck(`the demo has products in ${id}`, (byCat[id] || []).length > 0,
    `${(byCat[id] || []).length}`);
}
ck('the catalog is more than one row of cards', products.length > 4);

// ---- every row is translated ------------------------------------------- //
const T = translator();
const untranslated = [];
for (const p of products) {
  for (const k of ['title', 'summary', 'description']) {
    const v = p[k] || '';
    if (v && T(v) === v) untranslated.push(`${p.slug}.${k}`);
  }
}
ck('every product reads in Persian', untranslated.length === 0, untranslated.join(' '));

// ---- what a visitor actually sees -------------------------------------- //
const win = boot();
await new Promise((r) => setTimeout(r, 1200));

const all = await go(win, '#/products');
const cards = all.querySelectorAll('.product-card');
ck('the catalog renders every product', cards.length === products.length,
  `${cards.length} cards`);

const tabs = [...all.querySelectorAll('.tab')].map((t) => t.textContent.trim());
ck('the tab row offers both categories', tabs.length >= 3, tabs.join(' | '));

for (const id of demoCats) {
  const view = await go(win, `#/products?category=${id}`);
  const n = view.querySelectorAll('.product-card').length;
  ck(`the ${id} tab is not empty`, n > 0, `${n} cards`);
  ck(`the ${id} tab shows no empty state`, !view.querySelector('.catalog-empty'));
}

// ---- and a concept product opens ------------------------------------- //
const first = (byCat.applications || [])[0];
if (first) {
  const detail = await go(win, `#/products/${first.slug}`);
  ck('an application product has its own page',
    (detail.querySelector('h1') || {}).textContent?.trim().length > 0,
    ((detail.querySelector('h1') || {}).textContent || '').slice(0, 40));
}

console.log(out.join('\n'));
const failed = out.filter((l) => l.startsWith('FAIL')).length;
console.log(`\n${out.length - failed}/${out.length} checks passed`);
process.exit(failed ? 1 : 0);

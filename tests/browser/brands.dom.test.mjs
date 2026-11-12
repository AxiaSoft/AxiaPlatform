// Storefront brand picker and the admin cover uploader, driven through the real
// app code in jsdom. No browser binary is needed, so this runs anywhere the
// other .dom suites do.
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const DIST = process.env.STATIC_DIST || '/tmp/site2/AxiaPlatform/';
const read = (p) => readFileSync(DIST + p, 'utf8');
const products = JSON.parse(read('data/products.json'));
const settings = JSON.parse(read('data/settings.json'));

let pass = 0, fail = 0;
const ck = (name, ok, detail = '') => {
  ok ? pass++ : fail++;
  console.log(`${ok ? '  ok  ' : '  FAIL'}  ${name}${!ok && detail ? '  ' + detail : ''}`);
};

// A tiny stand-in for the network: the app must not reach the real server.
function fetchStub(url) {
  const u = String(url);
  let body = {};
  if (u.includes('/api/products')) body = products;
  else if (u.includes('/api/me')) body = { user: null, csrf: null };
  else if (u.includes('/api/site') || u.includes('/api/settings')) body = settings;
  return { ok: true, status: 200, headers: { get: () => null }, json: async () => body };
}

async function boot(hash = '#/products', lang = 'fa', storedBrand = null) {
  const dom = new JSDOM(read('index.html'), {
    runScripts: 'outside-only', url: 'https://x.test/AxiaPlatform/' + hash, pretendToBeVisual: true,
  });
  const w = dom.window;
  const errors = [];
  w.addEventListener('error', (e) => errors.push(String(e.message)));
  w.localStorage.setItem('axia-lang', lang);
  if (storedBrand) w.localStorage.setItem('axia-brand', storedBrand);
  w.fetch = fetchStub;
  w.matchMedia = w.matchMedia || (() => ({
    matches: false, addEventListener() {}, removeEventListener() {},
    addListener() {}, removeListener() {},
  }));
  w.scrollTo = () => {};
  for (const file of ['brands.js', 'i18n.js', 'app.js']) w.eval(read(file));
  await new Promise((r) => setTimeout(r, 1300));
  return { w, doc: w.document, errors };
}

const click = (w, el) => el.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));

/* ------------------------------------------------ the brand catalog ---- */
const { w, doc, errors } = await boot('#/products');
ck('the page boots without a script error', errors.length === 0, errors.slice(0, 2).join('|'));
ck('the brand picker renders', !!doc.querySelector('.brand-picker'));
ck('four brand buttons are offered', doc.querySelectorAll('[data-brand-pick]').length === 4);
ck('brand names are shown in Persian by default',
   [...doc.querySelectorAll('.brand-pick strong')].map((x) => x.textContent).join('·') === 'آریا·ارشا·مینو·هما',
   [...doc.querySelectorAll('.brand-pick strong')].map((x) => x.textContent).join('·'));
ck('each button names a product count', doc.querySelectorAll('.brand-pick-count').length === 4);
// The static build rebases every root-relative URL onto the Pages sub-path, so
// the assertion is about the file being a brand logo, not about its prefix.
ck('every brand logo is an image in the build',
   [...doc.querySelectorAll('.brand-pick-logo img')].every((img) =>
     /\/brand\/[a-z]+-logo\.png$/.test(img.getAttribute('src') || '')),
   [...doc.querySelectorAll('.brand-pick-logo img')].map((i) => i.getAttribute('src')).join(','));
ck('no brand is active before one is chosen', !doc.documentElement.hasAttribute('data-brand'));
ck('the catalog lists all four products', doc.querySelectorAll('.product-card').length === 4);
ck('each card shows its own uploaded cover', doc.querySelectorAll('.product-cover.has-image img').length === 4);

/* ------------------------------------------------ choosing a brand ----- */
click(w, doc.querySelector('[data-brand-pick="homa"]'));
await new Promise((r) => setTimeout(r, 500));
ck('the choice is remembered', w.localStorage.getItem('axia-brand') === 'homa');
ck('the header mark becomes that brand', doc.querySelector('#brand-mark img').getAttribute('src') === '/brand/homa-mark.png');
ck('the accent colour changes',
   doc.documentElement.style.getPropertyValue('--brand-accent') === '#1e5fa6',
   doc.documentElement.style.getPropertyValue('--brand-accent'));
ck('the page title carries the brand name', doc.title.startsWith('هما'), doc.title);
ck('the AXIASOFT wordmark steps aside', doc.querySelector('#brand-wordmark').hidden === true);
ck('the chosen brand is marked active', !!doc.querySelector('[data-brand-pick="homa"].is-active'));
ck('the active button reports itself pressed',
   doc.querySelector('[data-brand-pick="homa"]').getAttribute('aria-pressed') === 'true');
ck('the catalog narrows to that brand', doc.querySelectorAll('.product-card').length === 1);
ck('the remaining card is the chosen brand',
   doc.querySelector('.product-card h3').textContent.includes('Homa'));
ck('a "show all" escape is offered', !!doc.querySelector('[data-brand-clear]'));

/* ------------------------------------------------ clearing the brand --- */
click(w, doc.querySelector('[data-brand-pick="homa"]'));
await new Promise((r) => setTimeout(r, 500));
ck('pressing the active brand returns to the full catalog', doc.querySelectorAll('.product-card').length === 4);
ck('the preference is cleared', w.localStorage.getItem('axia-brand') === null);
ck('the AXIASOFT mark is restored',
   doc.querySelector('#brand-mark img').getAttribute('src') === '/brand/axiasoft-original.png');
ck('the wordmark returns', doc.querySelector('#brand-wordmark').hidden === false);
ck('the brand attribute is removed', !doc.documentElement.hasAttribute('data-brand'));

/* --------------------------------------- the header logo goes home -------
   A visitor who picks Homa and then presses the header logo expects the
   AXIASOFT mark back. The link points at '#/' and nothing ever cleared the
   brand on that route, so the hash changed, the home page rendered, and the
   Homa logo simply stayed in the header.

   Two ways in are covered because they fail for different reasons: choosing
   the brand from the catalog, and arriving with one already stored.
   ------------------------------------------------------------------------ */
const picked = await boot('#/products');
click(picked.w, picked.doc.querySelector('[data-brand-pick="homa"]'));
await new Promise((r) => setTimeout(r, 400));
ck('the brand is running before the logo is pressed',
   picked.doc.querySelector('#brand-mark img').getAttribute('src') === '/brand/homa-mark.png');

click(picked.w, picked.doc.querySelector('#brand-link'));
await new Promise((r) => setTimeout(r, 500));
ck('pressing the header logo restores the AXIASOFT mark',
   picked.doc.querySelector('#brand-mark img').getAttribute('src') === '/brand/axiasoft-original.png',
   picked.doc.querySelector('#brand-mark img').getAttribute('src'));
ck('the brand attribute is gone', !picked.doc.documentElement.hasAttribute('data-brand'),
   picked.doc.documentElement.getAttribute('data-brand'));
ck('the stored choice is dropped, so a reload stays AXIASOFT',
   picked.w.localStorage.getItem('axia-brand') === null,
   picked.w.localStorage.getItem('axia-brand'));
ck('the AXIASOFT wordmark comes back',
   picked.doc.querySelector('#brand-wordmark').hidden === false);
ck('the title stops naming the brand', picked.doc.title.startsWith('AXIASOFT'), picked.doc.title);
ck('pressing the logo still lands on the home page',
   picked.w.location.hash === '#/' || picked.w.location.hash === '',
   picked.w.location.hash);

/* A returning visitor: the choice was stored on an earlier visit, so the very
   first render already shows that brand. */
const returning = await boot('#/products', 'fa', 'mino');
ck('a stored brand is running on arrival',
   returning.doc.querySelector('#brand-mark img').getAttribute('src') === '/brand/mino-mark.png',
   returning.doc.querySelector('#brand-mark img').getAttribute('src'));
click(returning.w, returning.doc.querySelector('#brand-link'));
await new Promise((r) => setTimeout(r, 500));
ck('a returning visitor can also press the logo to get AXIASOFT back',
   returning.doc.querySelector('#brand-mark img').getAttribute('src') === '/brand/axiasoft-original.png');

/* The home page is the AXIASOFT studio page, so arriving there drops a product
   brand. Without this the header could show Homa above AXIASOFT's own hero. */
const homeWithBrand = await boot('#/', 'fa', 'homa');
ck('the home page does not wear a product brand',
   homeWithBrand.doc.querySelector('#brand-mark img').getAttribute('src') === '/brand/axiasoft-original.png',
   homeWithBrand.doc.querySelector('#brand-mark img').getAttribute('src'));

/* With no brand running the link must keep doing its ordinary job. */
const plain = await boot('#/products');
click(plain.w, plain.doc.querySelector('#brand-link'));
await new Promise((r) => setTimeout(r, 400));
ck('with no brand active the header logo still navigates home',
   plain.w.location.hash === '#/', plain.w.location.hash);

/* ------------------------------------------------ a second language ----- */
const english = await boot('#/products', 'en');
ck('the english page still offers four brands',
   english.doc.querySelectorAll('[data-brand-pick]').length === 4);
ck('brand names switch to English',
   [...english.doc.querySelectorAll('.brand-pick strong')].map((x) => x.textContent).join('·') === 'Arya·Ersha·Mino·Homa',
   [...english.doc.querySelectorAll('.brand-pick strong')].map((x) => x.textContent).join('·'));
click(english.w, english.doc.querySelector('[data-brand-pick="mino"]'));
await new Promise((r) => setTimeout(r, 400));
ck('an English visitor gets the English brand name in the title',
   english.doc.title.startsWith('Mino'), english.doc.title);

/* ------------------------------------------------ the admin uploader --- */
const adminHtml = read('admin/index.html');
const adminDom = new JSDOM(adminHtml, {
  runScripts: 'outside-only', url: 'https://x.test/AxiaPlatform/admin/', pretendToBeVisual: true,
});
const aw = adminDom.window;
const adminErrors = [];
aw.addEventListener('error', (e) => adminErrors.push(String(e.message)));
aw.localStorage.setItem('axia-lang', 'en');
aw.fetch = async (url) => {
  const u = String(url);
  let body = {};
  if (u.includes('/api/me')) body = { user: { id: 1, name: 'Admin', email: 'a@b.test', role: 'admin' }, csrf: 'tok' };
  else if (u.includes('/api/admin/overview')) body = { orders: [], products: [], tickets: [], refunds: [], users: [] };
  else if (u.includes('/api/admin/products')) body = { products: [] };
  else if (u.includes('/api/admin/articles')) body = { articles: [] };
  return { ok: true, status: 200, headers: { get: () => null }, json: async () => body };
};
aw.matchMedia = aw.matchMedia || (() => ({ matches: false, addEventListener() {}, removeEventListener() {} }));
aw.eval(read('admin/admin.js'));
await new Promise((r) => setTimeout(r, 900));
ck('the admin console boots', adminErrors.length === 0, adminErrors.slice(0, 2).join('|'));
const addBtn = adminDom.window.document.querySelector('[data-act="new-product"]');
ck('the add-product action is available', !!addBtn);
click(aw, addBtn);
await new Promise((r) => setTimeout(r, 400));
const adoc = aw.document;
const uploader = adoc.querySelector('[data-cover-uploader]');
ck('the product form has a cover uploader', !!uploader);
ck('the file picker accepts image types only',
   (uploader?.querySelector('[data-cover-file]')?.getAttribute('accept') || '').includes('image/png'),
   uploader?.querySelector('[data-cover-file]')?.getAttribute('accept'));
ck('the uploader keeps a hidden field the form can read',
   !!uploader?.querySelector('input[name="cover_image"]'));
// The note that camera metadata is stripped sits under the field, which is a
// sibling of the uploader rather than part of it.
ck('it explains that metadata is stripped',
   /metadata/i.test(adoc.querySelector('[data-form="product"]')?.textContent || ''));
ck('no cover is shown before one is chosen',
   /No cover image/i.test(uploader?.querySelector('.cover-empty')?.textContent || ''));
ck('the remove action starts hidden',
   uploader?.querySelector('[data-cover-clear]')?.hasAttribute('hidden') === true);

console.log(`\n== ${pass}/${pass + fail} brand and upload checks passed ==`);
process.exit(fail ? 1 : 0);

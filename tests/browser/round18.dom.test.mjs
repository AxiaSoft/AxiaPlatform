// Round 18: the contact form, the FAQ console, the AURION plan page, the
// WebP logos, and Xiona preferring the model. Runs against the built tree.
import { JSDOM } from 'jsdom';
import fs from 'fs';
import { fileURLToPath } from 'url';

const D = process.env.STATIC_DIST || fileURLToPath(new URL('../../dist/', import.meta.url));
const read = (p) => fs.readFileSync(D + p, 'utf8');
const out = [];
const ck = (n, ok, x = '') => out.push(`${ok ? 'PASS' : 'FAIL'}  ${n}${x ? '  (' + x + ')' : ''}`);

/* ---- 1. no PNG logo is reachable, in the build or in the repo ---- */
for (const name of ['axiasoft-original.png', 'axiasoft-wordmark.png', 'aurion-original.png']) {
  ck(`${name} is not built`, !fs.existsSync(D + 'brand/' + name));
  ck(`${name} is not referenced`, !read('index.html').includes(name) && !read('app.js').includes(name));
}
ck('the WebP logos are built', ['axiasoft-original.webp', 'axiasoft-wordmark.webp', 'aurion-original.webp']
  .every((n) => fs.existsSync(D + 'brand/' + n)));
ck('the header uses the WebP mark', read('index.html').includes('src="/AxiaPlatform/brand/axiasoft-original.webp"')
  || read('index.html').includes('src="/brand/axiasoft-original.webp"'));

/* ---- 2. the blog shell matches the storefront ---- */
const blog = read('blog/index.html');
ck('the blog does not force a dark theme', !/<html[^>]*data-theme="dark"/.test(blog));
ck('the blog reads the saved theme', blog.includes("localStorage.getItem('axia-theme')"));
ck('the blog has a theme switch', blog.includes('id="theme-toggle"'));
ck('the blog has the mobile drawer', blog.includes('id="blog-mobile-nav"'));
ck('the blog drawer is initially hidden', /id="blog-mobile-nav"[^>]*hidden/.test(blog));
for (const route of ['#/products', '#/services', '#/aurion', '#/about', '#/contact']) {
  ck(`the blog drawer links to ${route}`, blog.includes(`/AxiaPlatform/${route}"`) || blog.includes(`/${route}"`));
}

/* ---- 3. body text is black or white, never taupe ---- */
const css = read('styles.css');
ck('light theme text is black', /:root|\[data-theme=?"?light"?\]/.test(css) && css.includes('--text:#000000'));
ck('dark theme text is white', css.includes('--text:#ffffff'));
for (const taupe of ['#57677e', '#9aa9bf', '#6c7b92', '#8290a4']) {
  ck(`${taupe} is gone`, !css.includes(taupe));
}

/* ---- 4. the contact page has a form, driven by the app ---- */
const productRows = (() => {
  const src = read('data/products.js');
  const from = src.indexOf('[');
  let depth = 0, end = -1;
  for (let i = from; i < src.length; i++) {
    if (src[i] === '[') depth++;
    else if (src[i] === ']') { depth--; if (depth === 0) { end = i; break; } }
  }
  return JSON.parse(src.slice(from, end + 1));
})();
/* settings.js is `window.AXIA_STATIC.settings = {...};`. Reading from the
   first `{` lands inside the `|| {}` guard at the top of the file and parses
   an empty object, which is how this test first "passed" with 0 vs 0. The
   assignment is the only reliable anchor. */
const settings = (() => {
  const src = read('data/settings.js');
  return JSON.parse(src.slice(src.indexOf('settings = ') + 11).replace(/;\s*$/, ''));
})();

function fetchStub(url, opts = {}) {
  const u = String(url);
  let body = {};
  let status = 200;
  if (u.includes('/api/contact')) { body = { ref: 'AXC-TEST' }; status = 201; }
  else if (u.includes('/api/products')) body = productRows;
  else if (u.includes('/api/me')) body = { user: null, csrf: null };
  // /api/site returns { settings }; the app reads site.faq from it. Getting
  // this shape wrong is what made an earlier version of this test assert 0 === 0
  // and pass while the page rendered nothing.
  else if (u.includes('/api/site')) body = { settings };
  else if (u.includes('/api/settings')) body = settings;
  return Promise.resolve({ ok: status < 400, status, headers: { get: () => null }, json: async () => body });
}

async function boot(hash, lang = 'en') {
  const dom = new JSDOM(read('index.html'), {
    runScripts: 'outside-only', url: 'https://x.test/AxiaPlatform/' + hash, pretendToBeVisual: true,
  });
  const w = dom.window;
  const errors = [];
  w.addEventListener('error', (e) => errors.push(String(e.message)));
  w.localStorage.setItem('axia-lang', lang);
  w.fetch = fetchStub;
  w.matchMedia = w.matchMedia || (() => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  }));
  w.scrollTo = () => {};
  for (const file of ['data/settings.js', 'data/products.js', 'brands.js', 'i18n.js', 'app.js']) {
    w.eval(read(file));
  }
  await new Promise((r) => setTimeout(r, 1300));
  return { w, doc: w.document, errors };
}

const { w, doc, errors } = await boot('#/contact');
ck('the contact page boots cleanly', errors.length === 0, errors.slice(0, 2).join(' | '));
ck('the contact form is present', !!doc.querySelector('#contact-form'));
ck('the form has name, email and message', !!doc.querySelector('#contact-form [name="name"]')
  && !!doc.querySelector('#contact-form [name="email"]')
  && !!doc.querySelector('#contact-form [name="message"]'));
ck('every field explains what to write', doc.querySelectorAll('#contact-form .field-help').length === 3,
  `${doc.querySelectorAll('#contact-form .field-help').length}`);
ck('the vague old sentence is gone', !doc.body.textContent.includes('Choose a development starting point'));
ck('the page says what happens next', !!doc.querySelector('.contact-steps'));

/* The form really posts, and shows the reference the server returned. */
const form = doc.querySelector('#contact-form');
form.querySelector('[name="name"]').value = 'Sara Ahmadi';
form.querySelector('[name="email"]').value = 'sara@example.com';
form.querySelector('[name="message"]').value = 'The checkout on our shop is slow on phones and I want it to feel instant.';
form.dispatchEvent(new w.Event('submit', { bubbles: true, cancelable: true }));
await new Promise((r) => setTimeout(r, 200));
ck('sending shows the reference', doc.querySelector('#contact-feedback').textContent.includes('AXC-TEST'),
  doc.querySelector('#contact-feedback').textContent.trim().slice(0, 60));

/* A short message is refused before it reaches the network. */
const form2 = doc.querySelector('#contact-form');
form2.querySelector('[name="name"]').value = 'Sara';
form2.querySelector('[name="email"]').value = 'sara@example.com';
form2.querySelector('[name="message"]').value = 'too short';
form2.dispatchEvent(new w.Event('submit', { bubbles: true, cancelable: true }));
await new Promise((r) => setTimeout(r, 120));
ck('a short message is refused locally',
  doc.querySelector('#contact-feedback').textContent.includes('20 characters'),
  doc.querySelector('#contact-feedback').textContent.trim().slice(0, 60));

/* ---- 5. the AURION button opens a plan page ---- */
const aurion = await boot('#/aurion');
const aurionText = aurion.doc.body.textContent;
ck('the AURION page boots cleanly', aurion.errors.length === 0, aurion.errors.slice(0, 2).join(' | '));
ck('the button reads "View the AURION plans"', aurionText.includes('View the AURION plans'));
ck('the button no longer says "Explore packages"', !aurionText.includes('Explore packages'));
const planLink = [...aurion.doc.querySelectorAll('a')].find((a) => a.getAttribute('href') === '#/aurion/plans');
ck('the button links to the plan route', !!planLink);

const plans = await boot('#/aurion/plans');
ck('the plan page boots cleanly', plans.errors.length === 0, plans.errors.slice(0, 2).join(' | '));
const planText = plans.doc.body.textContent;
ck('the plan page lists all four durations', ['1', '3', '6', '12'].every((n) => planText.includes(n)));
ck('the plan page says nothing is for sale', planText.includes('No live trading'));
ck('the plan page has the comparison table', !!plans.doc.querySelector('.plan-table'));

/* ---- 6. the FAQ comes from settings, not the source ---- */
ck('the build ships the console questions', (settings.faq || []).length === 3,
   `${(settings.faq || []).length}`);
ck('the AURION page renders the console questions',
   aurion.doc.querySelectorAll('.faq').length === (settings.faq || []).length &&
   aurion.doc.querySelectorAll('.faq').length > 0,
   `${aurion.doc.querySelectorAll('.faq').length} vs ${(settings.faq || []).length}`);
/* The question is a button now, not a <details><summary>. A summary's marker
   is drawn by the browser in the browser's own style, which is the thing this
   round removed; the site draws its own. Same text, same toggle, own control. */
ck('the first question is the one the console ships',
   (aurion.doc.querySelector('.faq-q')?.textContent || '').includes('Does AURION place trades?'),
   aurion.doc.querySelector('.faq-q')?.textContent.trim() || '(no question rendered)');
ck('the question opens its own answer',
   aurion.doc.querySelector('.faq-q')?.getAttribute('aria-expanded') === 'false' &&
   !!aurion.doc.querySelector('.faq-a[hidden]'));
ck('the plan page renders the same questions',
   plans.doc.querySelectorAll('.faq').length === aurion.doc.querySelectorAll('.faq').length);

console.log(out.join('\n'));
const failures = out.filter((l) => l.startsWith('FAIL')).length;
console.log(`\n${failures ? failures + ' FAILURES' : 'ALL PASS'}`);
process.exit(failures ? 1 : 0);

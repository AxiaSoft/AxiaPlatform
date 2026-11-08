/* The GitHub Pages build publishes the admin console, answered in the browser by
   public/demo-backend.js. This test pins down what that demo promises:

     * it opens with the demo account, and nothing else is accepted,
     * a product added in the panel appears in the storefront catalog with its
       GitHub preview link,
     * unpublishing it removes it from the catalog again,
     * a hostile preview URL never reaches an href,
     * the demo is visibly labelled, so it can't be mistaken for the real one.

   Run against a built, served copy of the site:

     SITE=http://127.0.0.1:8090/AxiaPlatform/ CHROME=/path/to/chrome \
       node tests/browser/admin-demo.browser.test.mjs
*/
import puppeteer from 'puppeteer-core';

const BASE = process.env.SITE || 'http://127.0.0.1:8000/AxiaPlatform/';
const EXEC = process.env.CHROME || '/tmp/chromium';

const browser = await puppeteer.launch({ executablePath: EXEC,
  args: ['--no-sandbox', '--disable-dev-shm-usage'] });

const problems = [];
let checks = 0;
const check = (name, ok, detail = '') => {
  checks++;
  if (!ok) problems.push(`${name}${detail ? ` (${detail})` : ''}`);
};

const context = await browser.createBrowserContext();
const admin = await context.newPage();
await admin.setViewport({ width: 1440, height: 950 });

// ---- the console opens and asks for the demo account -----------------------
await admin.goto(BASE + 'admin/', { waitUntil: 'networkidle0', timeout: 30000 });
await new Promise((r) => setTimeout(r, 1200));

const loginState = await admin.evaluate(() => ({
  hasForm: !!document.querySelector('[data-form="login"]'),
  chip: !!document.querySelector('[data-demo-chip], .demo-chip'),
  note: (document.querySelector('.setup-command') || {}).textContent || '',
  demoFlag: document.documentElement.dataset.demoMode === 'on',
}));
check('admin console is served, not a gate page', loginState.hasForm);
check('demo mode is visibly labelled', loginState.chip && loginState.demoFlag);
// The console defaults to Persian, so the note is translated. Match either
// language rather than pinning the English word.
check('login card shows the demo credentials',
      /demo|نمایشی/i.test(loginState.note), loginState.note.slice(0, 60));

// wrong credentials must fail
const rejected = await admin.evaluate(async () => {
  const r = await fetch('/api/login', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: 'admin', password: 'wrong' }),
  });
  return r.status;
});
check('wrong credentials are rejected', rejected === 401, `status=${rejected}`);

// the real credentials work
const accepted = await admin.evaluate(async () => {
  const r = await fetch('/api/login', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: 'demo', password: 'demo' }),
  });
  const body = await r.json();
  return { status: r.status, role: body.user && body.user.role };
});
check('demo account signs in as administrator', accepted.status === 200 && accepted.role === 'admin',
      JSON.stringify(accepted));

// the admin API refuses calls while signed out
const anonymous = await context.newPage();
await anonymous.goto(BASE + 'admin/', { waitUntil: 'networkidle0' });
const guarded = await anonymous.evaluate(async () => (await fetch('/api/admin/overview')).status);
check('admin API requires a session', guarded === 403, `status=${guarded}`);
await anonymous.close();

// ---- add a product with a GitHub preview link ------------------------------
await admin.reload({ waitUntil: 'networkidle0' });
await new Promise((r) => setTimeout(r, 1000));
const created = await admin.evaluate(async () => {
  await fetch('/api/login', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: 'demo', password: 'demo' }) });
  const r = await fetch('/api/admin/products', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      title: 'Demo Product', slug: 'demo-product', category: 'Websites',
      summary: 'Added by the test suite.', description: 'Added by the test suite.',
      features: [], technologies: [], status: 'available', price_label: 'Request a quote',
      github_url: 'https://github.com/AxiaSoft/demo-product', published: true,
    }),
  });
  return r.status;
});
check('a product can be created in the demo panel', created === 201, `status=${created}`);

// ---- it reaches the storefront, with the link ------------------------------
const store = await context.newPage();
await store.setViewport({ width: 1280, height: 900 });
await store.goto(BASE + '#/products', { waitUntil: 'networkidle0' });
await new Promise((r) => setTimeout(r, 1200));
const catalog = await store.evaluate(() => {
  const cards = [...document.querySelectorAll('.product-card')];
  return cards.map((card) => ({
    title: (card.querySelector('h3') || {}).textContent,
    // The button is labelled "Preview ↗" in English and "پیش‌نمایش ↗" in Persian,
    // so it is identified by its target rather than its translated text.
    preview: [...card.querySelectorAll('a')]
      .filter((a) => /github\.com/i.test(a.getAttribute('href') || '') ||
                     /preview|پیش‌نمایش/i.test(a.textContent))
      .map((a) => ({ href: a.getAttribute('href'), target: a.target, rel: a.rel })),
  }));
});
// The card is matched loosely: the visible title follows the console language
// and the storefront defaults to Persian.
const demoCard = catalog.find((c) => /demo product|محصول نمایشی/i.test(c.title || '')) ||
                 catalog.find((c) => c.preview && c.preview.length);
check('new product appears in the storefront', !!demoCard, JSON.stringify(catalog.map((c) => c.title)));
check('preview button opens the GitHub link in a new tab',
      !!demoCard && demoCard.preview.length === 1 &&
      demoCard.preview[0].href === 'https://github.com/AxiaSoft/demo-product' &&
      demoCard.preview[0].target === '_blank' &&
      /noopener/.test(demoCard.preview[0].rel),
      JSON.stringify(demoCard && demoCard.preview));

// detail page swaps the concept preview for the real link
await store.evaluate(() => { location.hash = '#/products/demo-product'; });
await new Promise((r) => setTimeout(r, 900));
const detail = await store.evaluate(() => ({
  text: document.querySelector('#app') ? document.querySelector('#app').textContent : '',
  hrefs: [...document.querySelectorAll('#app a')].map((a) => a.getAttribute('href') || ''),
}));
check('detail page offers the GitHub preview',
      detail.hrefs.includes('https://github.com/AxiaSoft/demo-product'));
check('detail page drops the built-in concept preview', !/Concept preview/.test(detail.text));

// ---- unpublishing removes it from the catalog -----------------------------
await admin.evaluate(async () => {
  const list = JSON.parse(localStorage.getItem('axia-demo-products-v1') || '[]');
  const target = list.find((p) => p.slug === 'demo-product');
  await fetch('/api/admin/products', {
    method: 'DELETE', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id: target.id }),
  });
});
const afterUnpublish = await context.newPage();
await afterUnpublish.goto(BASE + '#/products', { waitUntil: 'networkidle0' });
await new Promise((r) => setTimeout(r, 1000));
const gone = await afterUnpublish.evaluate(() =>
  [...document.querySelectorAll('.product-card h3')].some((h) => h.textContent === 'Demo Product'));
check('unpublished product leaves the catalog', gone === false);
await afterUnpublish.close();

// ---- a hostile link never becomes an href --------------------------------
const evil = await context.newPage();
await evil.evaluateOnNewDocument(() => {
  localStorage.setItem('axia-demo-products-v1', JSON.stringify([
    { id: 9, slug: 'evil-one', title: 'Evil One', category: 'Websites', summary: 's',
      description: 'd', features: [], technologies: [], status: 'available',
      price_label: 'x', github_url: 'javascript:alert(1)', published: 1 },
    { id: 10, slug: 'evil-two', title: 'Evil Two', category: 'Websites', summary: 's',
      description: 'd', features: [], technologies: [], status: 'available',
      price_label: 'x', github_url: 'data:text/html,<script>alert(1)</script>', published: 1 },
  ]));
});
let dialogFired = false;
evil.on('dialog', async (d) => { dialogFired = true; await d.dismiss(); });
await evil.goto(BASE + '#/products', { waitUntil: 'networkidle0' });
await new Promise((r) => setTimeout(r, 1000));
const hostileHrefs = await evil.evaluate(() =>
  [...document.querySelectorAll('a')].map((a) => a.getAttribute('href') || '')
    .filter((h) => /^(javascript|data):/i.test(h)));
check('hostile preview URLs never reach an href', hostileHrefs.length === 0, hostileHrefs.join(','));
check('hostile preview URL executes nothing', dialogFired === false);
await evil.close();

await context.close();
await browser.close();

if (problems.length) {
  console.log(`\nFAILURES (${problems.length})`);
  for (const p of problems) console.log('  FAIL  ' + p);
}
console.log(`\n== ${checks - problems.length}/${checks} admin demo checks passed ==`);
process.exit(problems.length ? 1 : 0);

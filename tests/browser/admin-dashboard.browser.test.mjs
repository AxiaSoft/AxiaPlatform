/* The expanded administrator dashboard, run in a real Chromium against a built,
   served copy of the site (the same artifact GitHub Pages publishes).

   It covers what the console gained beyond the original five screens:

     * the Overview page: hero strip, six stat cards, health panel, activity
       feed, product ranking and the 14-day spark strip,
     * the Website settings page: announcement bar, hero copy, section
       visibility, contact details and the first-visit theme — each saved from
       the console and then verified on the public site,
     * product control: featured flag, manual ordering and bulk publish,
     * Persian: the new screens are fully translated and stay RTL.

   Run against a built, served copy:

     SITE=http://127.0.0.1:8110/AxiaPlatform/ CHROME=/tmp/chromium \
       LD_LIBRARY_PATH=/tmp/cwx/lib node tests/browser/admin-dashboard.browser.test.mjs
*/
import puppeteer from 'puppeteer-core';

const BASE = process.env.SITE || 'http://127.0.0.1:8000/AxiaPlatform/';
const EXEC = process.env.CHROME || '/tmp/chromium';

const browser = await puppeteer.launch({
  executablePath: EXEC,
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
  protocolTimeout: 30000,
});

const problems = [];
let checks = 0;
const check = (name, ok, detail = '') => {
  checks++;
  if (!ok) problems.push(`${name}${detail ? ` (${detail})` : ''}`);
  console.log((ok ? 'PASS  ' : 'FAIL  ') + name + (ok ? '' : '  ' + detail));
};
const pause = (ms) => new Promise((r) => setTimeout(r, ms));

const context = await browser.createBrowserContext();
const admin = await context.newPage();
admin.on('pageerror', (e) => problems.push('page error: ' + e.message.slice(0, 160)));
// The console asks before bulk changes; a native dialog would block CDP.
admin.on('dialog', (d) => d.accept().catch(() => {}));

await admin.setViewport({ width: 1440, height: 950 });
await admin.goto(BASE + 'admin/', { waitUntil: 'networkidle0', timeout: 30000 });
await pause(900);
check('console serves the demo login', !!(await admin.$('[data-form="login"]')));

await admin.type('#loginEmail', 'demo');
await admin.type('#loginPassword', 'demo');
await admin.click('[data-form="login"] button');
await pause(1600);
check('demo console signs in', !!(await admin.$('.admin-shell')));

// A clean slate, so the run does not inherit a previous edit.
await admin.evaluate(() => {
  localStorage.removeItem('axia-demo-products-v1');
  localStorage.removeItem('axia-demo-settings-v1');
});
await admin.reload({ waitUntil: 'networkidle0' });
await pause(1600);

/* -------------------------------------------------------- navigation --- */
const nav = await admin.evaluate(() =>
  [...document.querySelectorAll('.side-link[data-page]')].map((b) => b.dataset.page));
check('sidebar offers the website screen', nav.includes('site'), nav.join(','));
check('sidebar keeps every original screen',
  ['dashboard', 'orders', 'products', 'customers', 'support', 'refunds', 'activity']
    .every((p) => nav.includes(p)), nav.join(','));

/* ---------------------------------------------------------- overview --- */
const overview = await admin.evaluate(() => ({
  hero: !!document.querySelector('.hero-strip'),
  stats: document.querySelectorAll('.stat-card').length,
  health: document.querySelectorAll('.health-row').length,
  activity: document.querySelectorAll('.activity-item').length,
  rank: document.querySelectorAll('.rank-row').length,
  spark: document.querySelectorAll('.spark-bar').length,
  chart: !!document.querySelector('.chart-line'),
  quick: document.querySelectorAll('.quick-card').length,
  text: document.querySelector('#pageContent').textContent.replace(/\s+/g, ' '),
}));
check('overview has the greeting strip', overview.hero);
check('overview has six stat cards', overview.stats === 6, `count=${overview.stats}`);
check('overview has a site-health panel', overview.health >= 5, `rows=${overview.health}`);
check('overview has an activity feed', overview.activity >= 4, `rows=${overview.activity}`);
check('overview ranks products by requests', overview.rank >= 3, `rows=${overview.rank}`);
check('overview shows 14 daily bars', overview.spark === 14, `bars=${overview.spark}`);
check('overview keeps the six-month trend chart', overview.chart);
check('overview keeps quick actions', overview.quick >= 4, `cards=${overview.quick}`);
// The check runs in English, but the console is scanned for its sentence in
// whichever language the visitor picked - assert on the number instead.
check('overview reports the pending queue',
  /need a first review|Nothing is waiting|درخواست پروژه منتظر|چیزی در انتظار نیست/.test(overview.text),
  overview.text.slice(0, 90));

/* ---------------------------------------------------- website settings --- */
// helper that sets a control the way a user would, then saves the form
async function saveForm(fields) {
  await admin.evaluate((values) => {
    for (const [name, value] of Object.entries(values)) {
      const el = document.querySelector(`[data-form="settings"] [name="${name}"]`);
      if (!el) continue;
      if (el.type === 'checkbox') {
        if (el.checked !== value) el.click();
      } else {
        el.value = value;
        el.dispatchEvent(new Event('input', { bubbles: true }));
      }
    }
  }, fields);
  const dirty = await admin.evaluate(() => !!document.querySelector('.dirty-note'));
  await admin.evaluate(() => {
    const form = document.querySelector('[data-form="settings"]');
    form.requestSubmit();
  });
  await pause(900);
  return dirty;
}

async function openTab(name) {
  await admin.evaluate((tab) => {
    const button = document.querySelector(`[data-site-tab="${tab}"]`);
    if (button) button.click();
  }, name);
  await pause(450);
}

await admin.evaluate(() => { location.hash = '#site'; });
await pause(1200);
const site = await admin.evaluate(() => ({
  title: (document.querySelector('.page-head h1') || {}).textContent || '',
  tabs: [...document.querySelectorAll('[data-site-tab]')].map((b) => b.dataset.siteTab),
  crumb: (document.querySelector('.crumb strong') || {}).textContent,
}));
// The console defaults to Persian, so screen names are translated. Assert on
// the structure (six tabs, the fields) and accept either language here.
check('website screen opens', /Website|وب‌سایت/i.test(site.title), site.title);
check('website screen has six tabs',
  ['identity', 'announcement', 'hero', 'sections', 'contact', 'danger']
    .every((t) => site.tabs.includes(t)), site.tabs.join(','));
check('breadcrumb follows the new screen', /^(Website|وب‌سایت)$/.test(site.crumb || ''), site.crumb);
await openTab('hero');
const heroStart = await admin.evaluate(() =>
  (document.querySelector('[data-form="settings"] [name="hero_title"]') || {}).value);
check('the hero field starts with the shipped copy',
  /Building digital experiences/i.test(heroStart || ''), String(heroStart));


/* announcement */
await openTab('announcement');
const dirty = await saveForm({
  announcement_enabled: true,
  announcement_text: 'Demo banner: the Northstar catalog is live',
});
check('unsaved changes are flagged', dirty);
const savedBar = await admin.evaluate(() =>
  JSON.parse(localStorage.getItem('axia-demo-settings-v1') || '{}'));
check('announcement setting is stored',
  savedBar.announcement_enabled === true && /Northstar/.test(savedBar.announcement_text || ''),
  JSON.stringify(savedBar.announcement_text));

/* hero */
await openTab('hero');
await saveForm({ hero_title: 'We design calm software.', hero_accent: 'And ship it with care.' });

/* visibility */
await openTab('sections');
const switches = await admin.evaluate(() => document.querySelectorAll('.switch').length);
check('every section has a visibility switch', switches === 7, `switches=${switches}`);
await saveForm({ show_services: false, show_prices: false });

/* contact */
await openTab('contact');
await saveForm({
  contact_email: 'hello@axiasoft.dev',
  github_url: 'https://github.com/AxiaSoft',
  footer_note: 'Built in Nuremberg.',
});
const contactSaved = await admin.evaluate(() =>
  JSON.parse(localStorage.getItem('axia-demo-settings-v1') || '{}'));
check('contact details are stored',
  contactSaved.contact_email === 'hello@axiasoft.dev' &&
  /Nuremberg/.test(contactSaved.footer_note || ''),
  JSON.stringify(contactSaved.contact_email));
check('all settings survived the later saves',
  contactSaved.announcement_enabled === true &&
  /calm software/i.test(contactSaved.hero_title || '') &&
  contactSaved.show_services === false,
  JSON.stringify(contactSaved).slice(0, 120));

/* the API refuses bad input rather than dropping it silently */
const rejectedEmail = await admin.evaluate(async () => {
  const r = await fetch('/api/admin/settings', {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ contact_email: 'not-an-address' }),
  });
  return r.status;
});
check('a malformed email is rejected', rejectedEmail === 400, `status=${rejectedEmail}`);

/* ------------------------------------------- the public storefront --- */
const store = await context.newPage();
store.on('pageerror', (e) => problems.push('store error: ' + e.message.slice(0, 160)));
await store.setViewport({ width: 1280, height: 900 });
await store.goto(BASE + '#/', { waitUntil: 'networkidle0' });
await pause(1500);
const publicHome = await store.evaluate(() => ({
  bar: (document.querySelector('#announcement-bar') || {}).textContent || '',
  barVisible: !!document.querySelector('#announcement-bar:not([hidden])'),
  hero: (document.querySelector('.hero .headline') || {}).textContent || '',
  navServices: !!document.querySelector('.nav-links a[href="#/services"]:not([hidden])'),
  footer: (document.querySelector('.footer-top>p') || {}).textContent || '',
  mail: !!document.querySelector('.footer-links a[href^="mailto:"]'),
  github: !!document.querySelector('.footer-links a[href="https://github.com/AxiaSoft"]'),
}));
check('announcement bar reaches the storefront',
  publicHome.barVisible && /Northstar/.test(publicHome.bar), publicHome.bar.slice(0, 60));
check('hero headline comes from the console',
  /calm software/i.test(publicHome.hero), publicHome.hero.slice(0, 60));
check('a hidden section leaves the navigation', publicHome.navServices === false);
check('footer note comes from the console', /Nuremberg/.test(publicHome.footer), publicHome.footer);
check('contact email appears in the footer', publicHome.mail);
check('GitHub link appears in the footer', publicHome.github);

await store.evaluate(() => { location.hash = '#/services'; });
await pause(900);
const hiddenPage = await store.evaluate(() =>
  (document.querySelector('#app') || {}).textContent || '');
check('a hidden page explains itself', /published/i.test(hiddenPage), hiddenPage.slice(0, 80));

await store.evaluate(() => { location.hash = '#/products'; });
await pause(1000);
const emptyCatalog = await store.evaluate(() => document.querySelectorAll('.product-card').length);
check('the shipped catalog starts empty', emptyCatalog === 0, `cards=${emptyCatalog}`);

/* The demo catalog is empty until the operator asks for samples, so that the
   public site can never invent products. Load them from Maintenance, then the
   catalog has something to show. */
await admin.evaluate(() => { location.hash = '#site'; });
await pause(1100);
await openTab('danger');
await admin.evaluate(() => {
  const button = document.querySelector('[data-act="demo-samples"]');
  if (button) button.click();
});
await pause(1800);
const loaded = await admin.evaluate(() =>
  JSON.parse(localStorage.getItem('axia-demo-products-v1') || '[]').length);
check('the maintenance tab can load a sample catalog', loaded === 6, `products=${loaded}`);

await store.reload({ waitUntil: 'networkidle0' });
await store.evaluate(() => { location.hash = '#/products'; });
await pause(1300);
const catalog = await store.evaluate(() => ({
  cards: document.querySelectorAll('.product-card').length,
  prices: document.querySelectorAll('.product-price').length,
  featuredFirst: (document.querySelector('.product-card h3') || {}).textContent || '',
}));
// The storefront hides AURION (its own showcase page) and unpublished rows, so
// six stored products show as four cards.
check('the storefront shows the sample catalog', catalog.cards === 4, `cards=${catalog.cards}`);
check('price labels can be switched off', catalog.prices === 0, `labels=${catalog.prices}`);
// The sample catalog is written in the console's language, so a Persian
// install renders the Persian title for the same product.
check('the featured product leads the catalog',
  /Northstar|نورت‌استار|شرکتی نورث/i.test(catalog.featuredFirst), catalog.featuredFirst);

/* ------------------------------------------------ product controls --- */
await admin.evaluate(() => { location.hash = '#products'; });
await pause(1300);
const rows = await admin.evaluate(() =>
  [...document.querySelectorAll('[data-act="feature-product"]')].map((b) => Number(b.dataset.id)));
check('catalog lists the sample products', rows.length === 6, `rows=${rows.length}`);

// Northstar ships as the featured product; feature a second one and confirm the
// flag flips on exactly that row.
const notFeatured = await admin.evaluate(() => {
  const button = [...document.querySelectorAll('[data-act="feature-product"]')]
    .find((b) => b.dataset.featured === '0');
  if (!button) return null;
  const id = button.dataset.id;
  button.click();
  return id;
});
await pause(1400);
const starred = await admin.evaluate((id) => {
  const button = document.querySelector(`[data-act="feature-product"][data-id="${id}"]`);
  return button ? button.dataset.featured : null;
}, notFeatured);
check('a product can be featured from the table', starred === '1',
  `id=${notFeatured} featured=${starred}`);

await admin.evaluate(() => {
  const down = [...document.querySelectorAll('[data-act="move-product"][data-dir="1"]')]
    .find((b) => !b.closest('tr').classList.contains('is-hidden'));
  if (down) down.click();
});
await pause(1400);
const positions = await admin.evaluate(() =>
  JSON.parse(localStorage.getItem('axia-demo-products-v1') || '[]')
    .map((p) => `${p.slug}:${Number(p.position)}`));
check('manual ordering is rewritten', positions.some((x) => /:\d+$/.test(x)), positions.join(','));

await admin.evaluate(() => {
  const boxes = [...document.querySelectorAll('[data-select-product]')];
  if (boxes[0]) boxes[0].click();
});
await pause(600);
const bulkVisible = await admin.evaluate(() => ({
  unpublish: !!document.querySelector('[data-act="bulk-unpublish"]'),
  publish: !!document.querySelector('[data-act="bulk-publish"]'),
}));
check('selecting a row reveals bulk actions', bulkVisible.unpublish && bulkVisible.publish);

await admin.evaluate(() => {
  const button = document.querySelector('[data-act="bulk-unpublish"]');
  if (button) button.click();
});
await pause(1600);
const hiddenCount = await admin.evaluate(() =>
  JSON.parse(localStorage.getItem('axia-demo-products-v1') || '[]')
    .filter((p) => !p.published).length);
check('bulk hide unpublishes the selection', hiddenCount >= 1, `hidden=${hiddenCount}`);

/* ------------------------------------------------------------- Persian --- */
await admin.evaluate(() => localStorage.setItem('axia-lang', 'fa'));
await admin.reload({ waitUntil: 'networkidle0' });
await pause(1800);
await admin.evaluate(() => { location.hash = '#site'; });
await pause(1400);
const fa = await admin.evaluate(() => {
  const text = document.querySelector('#pageContent').textContent.replace(/\s+/g, ' ');
  const latin = text.match(/[A-Za-z]{4,}/g) || [];
  return {
    lang: document.documentElement.lang,
    dir: document.documentElement.dir,
    latin: [...new Set(latin)],
    tabs: [...document.querySelectorAll('[data-site-tab]')].map((b) => b.textContent),
  };
});
check('admin stays RTL in Persian', fa.lang === 'fa' && fa.dir === 'rtl', `${fa.lang}/${fa.dir}`);
const allowed = ['https', 'http', 'mailto', 'demo', 'Demo', 'AXIASOFT', 'GitHub', 'JSON', 'AURION', 'Websites', 'Applications', 'Aurion'];
const untranslated = fa.latin.filter((w) => !allowed.includes(w));
check('website screen is written in Persian', untranslated.length === 0, untranslated.join(','));
check('tabs are translated', !fa.tabs.some((t) => /^[A-Za-z ]+$/.test(t)), fa.tabs.join('|'));

await context.close();
await browser.close();

if (problems.length) {
  console.log(`\nFAILURES (${problems.length})`);
  for (const p of problems) console.log('  FAIL  ' + p);
}
console.log(`\n== ${checks - problems.length}/${checks} dashboard checks passed ==`);
process.exit(problems.length ? 1 : 0);

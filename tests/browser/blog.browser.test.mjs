// The blog is server-rendered, so these checks load real HTML from the static
// build rather than exercising the single-page app.
import puppeteer from 'puppeteer-core';

const BASE = process.env.SITE || 'http://127.0.0.1:8110/AxiaPlatform/';
const CHROME = process.env.CHROME || '/tmp/chromium';

let pass = 0, fail = 0;
const check = (name, ok, detail = '') => {
  if (ok) { pass++; } else { fail++; console.log(`  FAIL  ${name} ${detail}`); }
};

const browser = await puppeteer.launch({ executablePath: CHROME, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
const page = await browser.newPage();
await page.setCacheEnabled(false);
await page.setViewport({ width: 1200, height: 900 });
const errors = [];
page.on('pageerror', (e) => errors.push(String(e)));

const open = async (url) => {
  await page.goto(BASE + url, { waitUntil: 'networkidle0' });
  await new Promise((r) => setTimeout(r, 250));
};

// ---- the Persian blog ---------------------------------------------------- //
await open('blog/');
const fa = await page.evaluate(() => ({
  lang: document.documentElement.lang,
  dir: document.documentElement.dir,
  h1: (document.querySelector('h1') || {}).textContent || '',
  nav: [...document.querySelectorAll('.nav-links a')].map((a) => a.textContent.trim()),
  cards: document.querySelectorAll('.blog-card').length,
  switchHref: (document.querySelector('.blog-lang') || {}).getAttribute?.('href'),
  scroll: document.documentElement.scrollWidth,
  client: document.documentElement.clientWidth,
  css: [...document.styleSheets].some((s) => (s.href || '').includes('blog.css')),
}));
check('persian blog is RTL and in Persian', fa.lang === 'fa' && fa.dir === 'rtl', `${fa.lang}/${fa.dir}`);
check('persian blog has a Persian heading', /یادداشت|مقال/.test(fa.h1), fa.h1.slice(0, 40));
check('blog navigation is translated', fa.nav.includes('وبلاگ'), fa.nav.join(','));
check('blog.css loads', fa.css);
check('no horizontal scroll on the blog', fa.scroll <= fa.client + 1, `${fa.scroll}/${fa.client}`);
check('the language switch points at the English mirror',
      /en\/blog\/?$/.test(fa.switchHref || ''), String(fa.switchHref));

// A skip link must not be visible until it is focused.
const skip = await page.evaluate(() => {
  const el = document.querySelector('.skip-link');
  if (!el) return null;
  return Math.round(el.getBoundingClientRect().top);
});
check('the skip link is off-screen until focused', skip === null || skip < 0, String(skip));

// ---- the English mirror -------------------------------------------------- //
await open('en/blog/');
const en = await page.evaluate(() => ({
  lang: document.documentElement.lang,
  dir: document.documentElement.dir,
  h1: (document.querySelector('h1') || {}).textContent || '',
  nav: [...document.querySelectorAll('.nav-links a')].map((a) => a.textContent.trim()),
  switchHref: (document.querySelector('.blog-lang') || {}).getAttribute?.('href'),
  alternate: document.querySelector('link[hreflang="fa-IR"]')?.getAttribute('href') || '',
  canonical: document.querySelector('link[rel="canonical"]')?.getAttribute('href') || '',
  scroll: document.documentElement.scrollWidth,
  client: document.documentElement.clientWidth,
}));
check('english blog is LTR', en.lang === 'en' && en.dir === 'ltr', `${en.lang}/${en.dir}`);
check('english blog has an English heading', /Notes on building/i.test(en.h1), en.h1.slice(0, 40));
check('english navigation is translated', en.nav.includes('Blog'), en.nav.join(','));
check('the english switch points back to Persian', /\/blog\/$/.test(en.switchHref || ''), String(en.switchHref));
check('the english page names its Persian alternate', /\/blog\/$/.test(en.alternate), en.alternate);
check('the english page is canonical to itself', /en\/blog\/$/.test(en.canonical), en.canonical);
check('no horizontal scroll on the english blog', en.scroll <= en.client + 1, `${en.scroll}/${en.client}`);

// ---- an article ---------------------------------------------------------- //
const slug = await page.evaluate(() => {
  const link = document.querySelector('.blog-card-link');
  return link ? link.getAttribute('href') : null;
});
if (slug) {
  await open(slug.replace(/^\/AxiaPlatform\//, ''));
  const post = await page.evaluate(() => ({
    h1: (document.querySelector('h1') || {}).textContent || '',
    // The page owns the single <h1>, so body headings start at <h2>.
    bodyHeadings: [...document.querySelectorAll('.blog-prose h2, .blog-prose h3')].map((h) => h.tagName),
    jsonld: [...document.querySelectorAll('script[type="application/ld+json"]')].map((s) => s.textContent),
    robots: document.querySelector('meta[name="robots"]')?.getAttribute('content') || '',
    og: document.querySelector('meta[property="og:title"]')?.getAttribute('content') || '',
    canonical: document.querySelector('link[rel="canonical"]')?.getAttribute('href') || '',
  }));
  check('the article renders a title', (post.h1 || '').length > 4, post.h1.slice(0, 40));
  check('article headings never compete with the page title',
        post.bodyHeadings.every((tag) => tag !== 'H1'), post.bodyHeadings.join(','));
  check('the article carries BlogPosting structured data',
        post.jsonld.some((s) => /"BlogPosting"/.test(s)));
  check('the article is indexable', /index/.test(post.robots), post.robots);
  check('the article has an Open Graph title', post.og.length > 4, post.og.slice(0, 40));
  check('the article is canonical to itself', post.canonical.includes(encodeURI(slug)), post.canonical);

  // The English version of the same article must exist and say what it is.
  await open(slug.replace(/^\/AxiaPlatform\//, '').replace(/^blog\//, 'en/blog/'));
  const mirror = await page.evaluate(() => ({
    lang: document.documentElement.lang,
    notice: !!document.querySelector('.blog-notice'),
    dir: document.querySelector('.blog-prose')?.getAttribute('dir'),
    canonical: document.querySelector('link[rel="canonical"]')?.getAttribute('href') || '',
  }));
  check('the english article is LTR', mirror.lang === 'en', mirror.lang);
  check('an untranslated article says so plainly', mirror.notice);
  check('the untranslated body keeps its own direction', mirror.dir === 'rtl', String(mirror.dir));
  check('the english article is canonical to itself', /en\/blog\//.test(mirror.canonical), mirror.canonical);
}

check('no uncaught errors on any blog page', errors.length === 0, errors.slice(0, 2).join('|'));

console.log(`\n== ${pass}/${pass + fail} blog checks passed ==`);
await browser.close();
process.exit(fail ? 1 : 0);

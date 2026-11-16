// Round 22: the blog's theme must agree with the site's, and the demo article
// comparing WordPress with hand-coding must be reachable — on the blog, in the
// English mirror, and in the browser-only console.
//
// Runs against the built tree. The theme checks execute the script the server
// actually ships, rather than a copy of it, so a change to the resolver is
// caught here instead of only in a browser.
import { JSDOM } from 'jsdom';
import fs from 'fs';
import { fileURLToPath } from 'url';

const D = process.env.STATIC_DIST || fileURLToPath(new URL('../../dist/', import.meta.url));
const read = (p) => fs.readFileSync(D + p, 'utf8');
// Hand-edited sources, as opposed to build output: read from the repository so
// a check never passes just because a stale copy happens to sit in the build.
const REPO = fileURLToPath(new URL('../../', import.meta.url));
const source = (p) => fs.readFileSync(REPO + p, 'utf8');
const exists = (p) => fs.existsSync(D + p);
const out = [];
const ck = (n, ok, x = '') => out.push(`${ok ? 'PASS' : 'FAIL'}  ${n}${x ? '  (' + x + ')' : ''}`);

/* ---- 1. the blog reads the administrator's default theme ---------------- */

const blogIndex = read('blog/index.html');

// Render a page with `fallback` as the admin default, `os` as the system
// preference and `saved` as any earlier choice, then report the theme applied.
function themeFor({ fallback, os = 'dark', saved = null }) {
  let page = blogIndex.replace(/var fallback = "[^"]*";/, `var fallback = ${JSON.stringify(fallback)};`);
  const dom = new JSDOM(page, {
    runScripts: 'dangerously',
    url: 'https://axiasoft.github.io/AxiaPlatform/blog/',
    beforeParse(w) {
      w.matchMedia = (q) => ({
        matches: q.includes('light') ? os === 'light' : os === 'dark',
        media: q,
        addListener() {}, removeListener() {},
        addEventListener() {}, removeEventListener() {},
      });
      if (saved) w.localStorage.setItem('axia-theme', saved);
    },
  });
  return dom.window.document.documentElement.dataset.theme;
}

ck('the blog ships a theme fallback at all', /var fallback = "/.test(blogIndex));
ck('admin light + OS dark => light', themeFor({ fallback: 'light', os: 'dark' }) === 'light');
ck('admin light + OS light => light', themeFor({ fallback: 'light', os: 'light' }) === 'light');
ck('admin dark + OS light => dark', themeFor({ fallback: 'dark', os: 'light' }) === 'dark');
ck('admin system + OS light => light', themeFor({ fallback: 'system', os: 'light' }) === 'light');
ck('admin system + OS dark => dark', themeFor({ fallback: 'system', os: 'dark' }) === 'dark');
ck('a saved choice beats the admin default', themeFor({ fallback: 'light', os: 'light', saved: 'dark' }) === 'dark');
ck('a saved choice beats system', themeFor({ fallback: 'system', os: 'dark', saved: 'light' }) === 'light');
ck('no setting follows the OS (light)', themeFor({ fallback: '', os: 'light' }) === 'light');
ck('no setting follows the OS (dark)', themeFor({ fallback: '', os: 'dark' }) === 'dark');

/* ---- 2. the same knob drives both pages -------------------------------- */

// The storefront resolves theme from the same three sources; the blog must
// agree, which is only true if both read the same setting and the same key.
const appJs = read('app.js');
ck('the storefront reads site.default_theme', appJs.includes('site.default_theme'));
ck('the storefront honours a saved choice', appJs.includes("localStorage.getItem('axia-theme')"));
ck('the blog writes the same storage key the site reads', read('blog/index.html').includes("localStorage.getItem('axia-theme')"));
ck('the blog toolbar saves a choice too', blogIndex.includes("localStorage.setItem('axia-theme'"));

/* ---- 3. the theme setting actually used is one the console allows ------ */

const serverBlog = source('server/blog.py').includes('default_theme');
ck('the server passes the setting to the shell', serverBlog);
ck('only the three known values survive', source('server/blog.py').includes("('dark', 'light', 'system')"));

/* ---- 4. the colours adapt instead of being pinned to dark -------------- */

const blogCss = read('blog.css');
ck('no hardcoded notice colour remains', !blogCss.includes('#f0cd98'));
// The amber marks the notice; the words are --text, which is black in light
// mode and white in dark. Colouring the copy amber failed AA in light mode.
ck('the notice text uses the theme text colour', /\.blog-notice\s*\{[\s\S]*?color:\s*var\(--text\)/.test(blogCss));
ck('the notice accent comes from the palette', /\.blog-notice\s*\{[\s\S]*?var\(--amber\)/.test(blogCss));
ck('no hardcoded skip-link colour remains', !blogCss.includes('#eaf0fa') || blogCss.includes('var(--text, #eaf0fa)'));
ck('the comparison table has a style', /\.blog-prose table\s*\{/.test(blogCss));
ck('the table uses tokens, not fixed colours',
  /\.blog-prose th\s*\{[^}]*var\(--surface2\)/.test(blogCss)
  && !/#[0-9a-f]{3,6}\s*;/i.test(blogCss.slice(blogCss.indexOf('.blog-prose table'), blogCss.indexOf('.blog-cta'))));

/* ---- 5. the demo article exists on every surface ---------------------- */

const faPost = 'blog/wordpress-vs-code/index.html';
const enPost = 'en/blog/wordpress-vs-code/index.html';
ck('the Persian article page is built', exists(faPost));
ck('the English article page is built', exists(enPost));
ck('the blog index links to it', read('blog/index.html').includes('blog/wordpress-vs-code/'));
ck('the English index links to it', read('en/blog/index.html').includes('blog/wordpress-vs-code/'));

if (exists(faPost) && exists(enPost)) {
  const fa = read(faPost);
  const en = read(enPost);
  ck('the Persian page shows its title', fa.includes('وردپرس یا کدنویسی'));
  ck('the Persian page renders the comparison table', fa.includes('<table>'));
  ck('the Persian page names both subjects', fa.includes('وردپرس') && fa.includes('کدنویسی'));
  ck('the English page is really translated', en.includes('WordPress or hand-coded'));
  ck('the English page renders the comparison table', en.includes('<table>'));
  const prose = en.slice(en.indexOf('<div class="blog-prose"'));
  ck('the English page has a body, not an empty block', prose.slice(0, prose.indexOf('</div>')).length > 500);
  ck('neither page doubles the base path',
    !fa.includes('/AxiaPlatform/AxiaPlatform') && !en.includes('/AxiaPlatform/AxiaPlatform'));
  ck('the canonical points at the right page',
    fa.includes('href="https://axiasoft.github.io/AxiaPlatform/blog/wordpress-vs-code/"'));
  ck('the English canonical points at the English page',
    en.includes('href="https://axiasoft.github.io/AxiaPlatform/en/blog/wordpress-vs-code/"'));
}

/* ---- 6. the feed and sitemap carry it --------------------------------- */

const feed = read('blog/feed.xml');
const sitemap = read('sitemap.xml');
ck('the feed lists the article', feed.includes('wordpress-vs-code'));
ck('the feed has no doubled slash', !feed.includes('AxiaPlatform//'));
ck('the sitemap lists the article', sitemap.includes('wordpress-vs-code'));
ck('the sitemap has no doubled slash', !sitemap.includes('AxiaPlatform//'));

/* ---- 7. the browser-only console can see it --------------------------- */

const productData = read('data/products.js');
ck('the snapshot carries the articles', /AXIA_STATIC\.articles = \[\{/.test(productData));
ck('the snapshot carries the new article', productData.includes('wordpress-vs-code'));

const dom = new JSDOM('<!doctype html><html><body></body></html>', {
  url: 'https://axiasoft.github.io/AxiaPlatform/admin/',
  runScripts: 'outside-only',
});
const w = dom.window;
w.AXIA_STATIC = { base: '/AxiaPlatform/' };
// demo-backend.js only installs its handlers over an existing fetch.
w.fetch = async () => { throw new Error('no network in this suite'); };
w.eval(productData);
w.eval(read('demo-backend.js'));

const publicList = await (await w.fetch('/api/articles')).json();
ck('the demo serves the articles without signing in', (publicList.articles || []).length >= 2,
  `${(publicList.articles || []).length} article(s)`);
ck('the demo article is published there', (publicList.articles || []).some((a) => a.slug === 'wordpress-vs-code'));

const single = await w.fetch('/api/articles/wordpress-vs-code');
const one = await single.json();
ck('the demo returns the article by slug', single.status === 200 && one.slug === 'wordpress-vs-code');
ck('it carries the real body', (one.body || '').length > 1500);

await w.fetch('/api/login', { method: 'POST', body: JSON.stringify({ email: 'demo', password: 'demo' }) });
const adminList = await (await w.fetch('/api/admin/articles')).json();
ck('the console lists it after sign-in', (adminList.articles || []).some((a) => a.slug === 'wordpress-vs-code'));

const missing = await w.fetch('/api/articles/no-such-article');
ck('an unknown slug is a 404', missing.status === 404);

console.log(out.join('\n'));
const failed = out.filter((line) => line.startsWith('FAIL'));
console.log(`\n${out.length - failed.length}/${out.length} checks passed`);
if (failed.length) process.exit(1);

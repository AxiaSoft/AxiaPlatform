// The footer on the bottom edge, the About page without its approach card, and
// the blog in the hamburger menu. Runs against the built tree.
import { JSDOM } from 'jsdom';
import fs from 'fs';
import { fileURLToPath } from 'url';
const D = process.env.STATIC_DIST || fileURLToPath(new URL('../../dist/', import.meta.url));
const read = (p) => fs.readFileSync(D + p, 'utf8');
const out = [];
const ck = (n, ok, x = '') => out.push(`${ok ? 'PASS' : 'FAIL'}  ${n}${x ? '  (' + x + ')' : ''}`);

// ---- 1. footer pinned ----------------------------------------------------
const css = read('styles.css');
/* One body rule, not two: the column was folded into the block that already
   set the background, colour and min-height. */
ck('body is a full-height column',
   /body\{[^}]*display:flex[^}]*flex-direction:column[^}]*\}/.test(css) &&
   /body\{[^}]*min-height:100vh/.test(css));
// The rule is preceded by a comment rather than a closing brace, so the match
// cannot anchor on what comes before it.
ck('there is exactly one body rule', (css.match(/[\n;}]body\{/g) || []).length === 1,
   String((css.match(/[\n;}]body\{/g) || []).length));
ck('main takes the slack', /main\{position:relative;flex:1 0 auto\}/.test(css));
ck('the footer does not stretch', /\.footer\{flex:none\}/.test(css));
ck('the footer is not fixed (it must scroll away)', !/\.footer\{[^}]*position:fixed/.test(css));

// ---- 2. About page has no approach card ----------------------------------
const app = read('app.js');
const about = (() => { const i = app.indexOf('function about('); return app.slice(i, app.indexOf('\nfunction ', i + 10)); })();
ck('the approach card is gone', !/feature-panel/.test(about));
ck('its heading is gone', !/Less noise/.test(about));
ck('the values column survives', /Our values/.test(about) && /Built to be clear/.test(about));
ck('the About route still renders', /function about\(/.test(app));

// ---- 3. blog in the mobile menu (checked on the rendered drawer, below) ---

// ---- the About page actually renders without the card --------------------
const dom = new JSDOM(read('index.html'), { runScripts: 'outside-only', url: 'http://localhost/AxiaPlatform/' });
const w = dom.window;
w.AXIA_STATIC = { base: '/AxiaPlatform/', settings: {}, products: [], articles: [], pages: [], pairs: [] };
w.fetch = async (u) => { const s = String(u);
  const b = s.includes('/api/products') ? [] : s.includes('/api/site') ? { settings: {} } : s.includes('/api/me') ? { user: null } : {};
  return { ok: true, status: 200, headers: { get: () => null }, json: async () => b }; };
w.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });
// static-config.js is what tells the page where it is deployed, and it is the
// first script in index.html. Without it assetUrl() cannot prefix the blog
// link with /AxiaPlatform/, and the drawer is tested in a state no visitor sees.
try { w.eval(read('static-config.js')); } catch (e) { /* older builds ship none */ }
try { w.eval(read('i18n.js')); w.eval(read('brands.js')); w.eval(read('app.js')); }
catch (e) { ck('scripts evaluate', false, e.message); }
w.location.hash = '#/about';
/* The drawer is built at runtime, so its links are read from the DOM rather
   than from the source text. The blog entry goes through assetUrl('blog/'),
   because the site is served from /AxiaPlatform/ on GitHub Pages and a raw
   "/blog/" 404s there — the reason a freshly published post looked missing. */
const drawer = (() => {
  const button = w.document.querySelector('.mobile-menu');
  button?.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  return w.document.querySelector('.mobile-nav');
})();
const drawerLinks = drawer ? [...drawer.querySelectorAll('a')] : [];
const drawerText = drawerLinks.map((a) => a.textContent.trim()).join(' · ');
const blogLink = drawerLinks.find((a) => a.textContent.trim() === 'Blog');
ck('the hamburger has a blog entry', !!blogLink, drawerText);
ck('the blog entry carries the deploy base',
   !!blogLink && blogLink.getAttribute('href') === '/AxiaPlatform/blog/',
   blogLink ? blogLink.getAttribute('href') : 'no link');
/* The drawer lists the site in the same order the top bar has always used:
   Products · Services · Blog · AURION · About. */
ck('blog sits between Services and AURION',
   drawerText.indexOf('Services') < drawerText.indexOf('Blog') &&
   drawerText.indexOf('Blog') < drawerText.indexOf('AURION'), drawerText);
ck('the menu keeps its other entries',
   ['Products', 'Services', 'AURION', 'About', 'Start a project']
     .every((l) => drawerText.includes(l)), drawerText);

await new Promise((r) => setTimeout(r, 700));
const doc = w.document;
ck('the rendered About page has no approach panel', !doc.querySelector('.feature-panel'));
ck('the rendered About page shows its values', /Out values|Our values|ارزش/i.test(doc.getElementById('app').textContent));
ck('the About page still has its heading', doc.querySelector('.page-head h1')?.textContent.length > 10);

console.log(out.join('\n'));
const bad = out.filter((l) => l.startsWith('FAIL'));
console.log(bad.length ? `\n${bad.length} FAILURES` : '\nALL PASS');
process.exit(bad.length ? 1 : 0);

// The marquee, the English blog mirror and the brand monogram — the three
// things round 16 changed. Runs against the built tree, like every other DOM
// test here.
import { JSDOM } from 'jsdom';
import fs from 'fs';
import { fileURLToPath } from 'url';
const D = process.env.STATIC_DIST || fileURLToPath(new URL('../../dist/', import.meta.url));
const read = (p) => fs.readFileSync(D + p, 'utf8');
const out = [];
const ck = (n, ok, x = '') => out.push(`${ok ? 'PASS' : 'FAIL'}  ${n}${x ? '  (' + x + ')' : ''}`);

// ---- 1. marquee: CSS must not pause on hover ------------------------------
const css = read('styles.css');
const stripRule = css.match(/\.trust-strip:hover[^{]*\{[^}]*\}/)?.[0] || '';
ck('the strip does not pause on hover', !/paused/.test(stripRule), stripRule || 'no rule');
ck('the strip is inert to the pointer', /\.trust-strip\{pointer-events:none\}/.test(css));
ck('the animation still loops', /animation:trustScroll 38s linear infinite/.test(css));
ck('the track is still doubled by the script', read('app.js').includes('${items}${items}'));

// ---- 2. blog: the English mirror is real English --------------------------
const en = read('en/blog/fast-website/index.html');
const fa = read('blog/fast-website/index.html');
ck('the English article is in English', /How to build a fast website/.test(en) && !/چطور یک وب‌سایت/.test(en));
ck('the Persian article is unchanged', /چطور یک وب‌سایت سریع بسازیم/.test(fa));
ck('no "untranslated" notice on the English page', !/has not been translated/.test(en));
ck('the English index lists the post', /fast-website/.test(read('en/blog/index.html')));
ck('the language switch pairs the two', /hreflang="fa"/.test(en) && /hreflang="en"/.test(fa));
ck('translations.json ships with the build', fs.existsSync(D + 'data/translations.json'));

// ---- 3. brands: no shipped artwork, monogram instead ----------------------
for (const n of ['arya', 'ersha', 'mino', 'homa'])
  for (const k of ['mark', 'logo'])
    ck(`${n}-${k}.png is gone`, !fs.existsSync(D + `brand/${n}-${k}.png`));
const settings = JSON.parse(read('data/settings.json'));
ck('no brand points at deleted artwork',
   settings.brands.every((b) => !b.mark && !b.logo),
   JSON.stringify(settings.brands.map((b) => [b.id, b.mark, b.logo])));
const app = read('app.js');
ck('the storefront draws a monogram', /function brandGlyph\(/.test(app) && /cover-glyph/.test(app));
const admin = read('admin/admin.js');
ck('the console has an uploader per brand image', /data-brand-asset-file/.test(admin));
ck('the console falls back to an initial', /brand-swatch-glyph/.test(admin));

// ---- the brand strip renders a monogram, not a broken image ---------------
// The fixture is the built page with the built snapshots behind fetch, which is
// what the static site actually serves. It is deliberately close to dbg6.mjs,
// the script that proved the behaviour before this check was written.
const dom = new JSDOM(read('index.html'), { runScripts: 'outside-only', url: 'http://localhost/AxiaPlatform/' });
const w = dom.window;
const _settings = JSON.parse(read('data/settings.json'));
const _products = ['arya', 'ersha', 'mino', 'homa'].map((id, n) => ({
  id: n + 1, slug: id + '-app', title: id, category: 'websites', summary: 's',
  description: 'd', features: [], technologies: [], status: 'available',
  price_label: 'x', published: true, position: n, featured: false,
  github_url: '', cover: '',
}));
w.AXIA_STATIC = { base: '/AxiaPlatform/', settings: _settings, products: _products,
                  articles: [], pages: [], pairs: [] };
w.fetch = async (u) => {
  const url = String(u);
  const body = url.includes('/api/site') ? { settings: _settings }
    : url.includes('/api/products') ? _products
    : url.includes('/api/me') ? { user: null }
    : {};
  return { ok: true, status: 200, headers: { get: () => null }, json: async () => body };
};
w.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });
try {
  w.eval(read('i18n.js'));
  w.eval(read('brands.js'));
  w.eval(read('app.js'));
} catch (e) { ck('scripts evaluate', false, e.message); }
/* The brand row lives on the catalog screen, so the fixture has to be there
   before it can assert anything about it. */
w.location.hash = '#/products';
await new Promise((r) => setTimeout(r, 700));
const strip = w.document.querySelector('.brand-pick-logo');
ck('a brand tile renders without an <img>', !!strip && !strip.querySelector('img'),
   strip ? strip.innerHTML.slice(0, 60) : 'no tile');
ck('the monogram carries its letter', !!strip?.querySelector('.brand-glyph'),
   strip?.textContent?.trim());
ck('the catalog drew real cards', w.document.querySelectorAll('.product-card').length > 0,
   `cards=${w.document.querySelectorAll('.product-card').length}`);
ck('a brand with no image is still offered', w.document.querySelectorAll('.brand-pick').length > 0,
   `tiles=${w.document.querySelectorAll('.brand-pick').length}`);

console.log(out.join('\n'));
const bad = out.filter((l) => l.startsWith('FAIL'));
console.log(bad.length ? `\n${bad.length} FAILURES` : '\nALL PASS');
process.exit(bad.length ? 1 : 0);

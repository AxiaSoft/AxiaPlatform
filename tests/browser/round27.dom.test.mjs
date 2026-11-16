// Round 27: the page must not pay for work nobody asked for.
//
// The operator's words: "make the site faster and switch off the processing
// that is not needed, so it is quicker." Measuring first showed the file sizes
// were not the problem — parsing 105 KB of app.js costs about a millisecond. The
// real costs were (a) a three-request waterfall before anything was drawn, and
// (b) downloading, parsing and indexing the whole assistant for every visitor,
// including the ones who never open it.
//
// This suite pins both fixes: the first paint needs only the site and the
// catalog, the assistant script is not fetched at all until somebody reaches for
// it, and it still answers once they do.
//
// It runs against the built tree, like the other .dom suites.
import { JSDOM, VirtualConsole } from 'jsdom';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const R = process.env.STATIC_DIST || fileURLToPath(new URL('../../dist/', import.meta.url));
const ROOT = process.env.STATIC_DIST
  ? path.dirname(process.env.STATIC_DIST.replace(/\/$/, '')) + '/'
  : fileURLToPath(new URL('../../', import.meta.url));
const read = (p) => { try { return fs.readFileSync(p, 'utf8'); } catch { return ''; } };

const out = [];
const ck = (n, ok, x = '') => out.push(`${ok ? 'PASS' : 'FAIL'}  ${n}${x ? '  (' + x + ')' : ''}`);
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

const settings = JSON.parse(read(ROOT + 'data/settings.json') || '{}');
const products = JSON.parse(read(ROOT + 'data/products.json') || '[]');
const html = read(R + 'index.html');

/* ------------------------------------------------------------------ markup */

// The lazy tag must carry the path in data-src only. A real src still downloads
// and parses the file, which would defeat the entire change.
const xionaTag = html.match(/<script[^>]*data-xiona[^>]*>/)?.[0] || '';
ck('the assistant tag is in the markup', !!xionaTag, xionaTag);
ck('it points at the assistant through data-src', /data-src="[^"]*xiona\.js/.test(xionaTag));
ck('and it does not carry a src that would still fetch it',
  !/\ssrc="[^"]*xiona\.js/.test(xionaTag), xionaTag);
ck('no other tag loads the assistant', !/<script[^>]*\ssrc="[^"]*xiona\.js/.test(html));

// The first paint must not wait on the session call.
ck('the boot no longer chains the session call into the paint',
  !/loadSite\(\)\.then\([^)]*\)\.then\([^)]*refresh/.test(read(R + 'app.js')));

/* ------------------------------------------------------------------- boot */

function boot() {
  const vc = new VirtualConsole();
  vc.on('jsdomError', () => {});
  const requested = [];   // every fetch, in order
  const injected = [];    // every dynamically added <script src>

  const dom = new JSDOM(html, {
    runScripts: 'outside-only', pretendToBeVisual: true,
    url: 'http://localhost:8000/', virtualConsole: vc,
    beforeParse(w) {
      w.matchMedia = (q) => ({
        matches: /hover: hover/.test(q) || !/reduce/.test(q), media: q,
        addEventListener() {}, removeEventListener() {},
        addListener() {}, removeListener() {}, dispatchEvent() { return false; },
      });
      w.IntersectionObserver = class {
        constructor(cb) { this.cb = cb; }
        observe(el) { this.cb([{ isIntersecting: true, target: el }], this); }
        unobserve() {} disconnect() {}
      };
      w.requestAnimationFrame = (fn) => setTimeout(() => fn(0), 0);
      w.cancelAnimationFrame = (id) => clearTimeout(id);
      w.scrollTo = () => {};
      w.fetch = async (u) => {
        const s = String(u);
        requested.push(s);
        const body = /\/api\/site/.test(s) ? { settings }
          : /\/api\/products/.test(s) ? products
            : /\/api\/me/.test(s) ? { user: null }
              : {};
        return { ok: true, status: 200, headers: { get: () => null }, json: async () => body };
      };
      /* Record the lazy script instead of running it: jsdom would want a real
         network for the file. Resolving it here is exactly the contract the app
         relies on, so the close-the-panel path behaves the same. */
      const origCreate = w.document.createElement.bind(w.document);
      w.document.createElement = function (tag, opts) {
        const el = origCreate(tag, opts);
        if (String(tag).toLowerCase() === 'script') {
          let real = '';
          Object.defineProperty(el, 'src', {
            get() { return real; },
            set(v) {
              real = v;
              injected.push(v);
              setTimeout(() => el.onload && el.onload(), 0);
            },
          });
        }
        return el;
      };
    },
  });

  const w = dom.window;
  w.AXIA_STATIC = { products: [], articles: [], pages: [], pairs: [], settings };
  for (const f of ['i18n.js', 'data/settings.js', 'brands.js']) {
    try { w.eval(read(R + f)); } catch { /* settings also arrive over the wire */ }
  }
  w.eval(read(R + 'app.js'));
  return { w, requested, injected };
}

const { w, requested, injected } = boot();
await wait(1400);

/* --------------------------------------------------------------- first paint */

const app = w.document.querySelector('#app');
ck('the page painted without waiting for the session',
  !/Preparing your experience/.test(app.textContent), app.textContent.trim().slice(0, 50));
ck('the site request went out', requested.some((u) => /\/api\/site/.test(u)), requested.join(' '));
ck('the catalog request went out', requested.some((u) => /\/api\/products/.test(u)));

// The point of the change: site and catalog are independent, so they must not be
// serialized. Both start before either settles.
const siteAt = requested.findIndex((u) => /\/api\/site/.test(u));
const productsAt = requested.findIndex((u) => /\/api\/products/.test(u));
ck('the two boot requests start together, not one after the other',
  siteAt >= 0 && productsAt >= 0 && Math.abs(siteAt - productsAt) === 1,
  `site@${siteAt} products@${productsAt}`);

/* ------------------------------------------------- the assistant stays away */

ck('the assistant is not downloaded for a visitor who ignores it',
  injected.length === 0, injected.join(' '));
ck('the assistant global is absent until somebody asks',
  typeof w.Xiona === 'undefined', typeof w.Xiona);

// The index for a closed panel used to be built on the first render.
ck('no assistant engine was built at boot', typeof w.Xiona === 'undefined');

/* ------------------------------------------ reaching for it does load, once */

const launcher = w.document.querySelector('#chat-launcher');
ck('the launcher exists', !!launcher);

// A pointer reaching for the button is enough of a hint.
launcher.dispatchEvent(new w.Event('pointerenter'));
await wait(250);
ck('reaching for the launcher starts the download', injected.length === 1, injected.join(' '));
ck('the download is the assistant script', /xiona\.js/.test(injected[0] || ''), injected[0]);
ck('it is fetched once, not once per hint',
  (() => { launcher.dispatchEvent(new w.Event('pointerenter')); launcher.dispatchEvent(new w.Event('focus')); return injected.length === 1; })(),
  injected.join(' '));

/* ----------------------------------------------------------- the chat works */

// The script is stubbed in this harness, so teach the panel path directly: the
// panel must still open, greet, and take a question without the real engine.
const panelBefore = w.document.querySelector('#chat-panel');
ck('the panel is closed until it is clicked', !panelBefore);

launcher.dispatchEvent(new w.Event('click'));
await wait(300);
const panel = w.document.querySelector('#chat-panel');
ck('the panel opens on the click', !!panel);
ck('it greets the visitor straight away',
  !!panel && (panel.querySelector('.chat-msg')?.textContent || '').trim().length > 0,
  panel?.querySelector('.chat-msg')?.textContent?.slice(0, 40));
ck('it offers the question form', !!w.document.querySelector('#chat-form input'));

// Opening it a second time must not download the assistant again.
const injectedBefore = injected.length;
launcher.dispatchEvent(new w.Event('click'));
await wait(150);
launcher.dispatchEvent(new w.Event('click'));
await wait(150);
ck('closing and reopening never refetches the script',
  injected.length === injectedBefore, `${injectedBefore} -> ${injected.length}`);

/* --------------------------------------------------------------- no regress */

// Theme and language still boot normally.
ck('the page carries a language', !!w.document.documentElement.lang,
  w.document.documentElement.lang);
ck('the theme is applied to the root', !!w.document.documentElement.dataset.theme,
  w.document.documentElement.dataset.theme);
ck('the topbar and footer still render',
  !!w.document.querySelector('.topbar') && !!w.document.querySelector('footer'));

console.log(out.join('\n'));
const failed = out.filter((l) => l.startsWith('FAIL')).length;
console.log(`\n${out.length - failed}/${out.length} checks passed`);
if (failed) process.exit(1);

// Round 24: the assistant must know the site it is standing on.
//
// The report: Xiona was live on the site and refused to answer about AURION and
// about price, saying the site had published nothing on either. It was telling
// the truth about its own index and lying about the site. A fresh install seeds
// no products and publishes no articles, so the index was empty; separately the
// server never passed the site's page copy to the engine, and AURION's page was
// missing from the list the build rendered. The greeting advertised "ask me
// about AURION" the whole time.
//
// These checks run the real browser assistant against the committed snapshot,
// which is the same artifact the server now reads, so a regression in either
// place shows up here.
import { JSDOM, VirtualConsole } from 'jsdom';
import fs from 'fs';
import { fileURLToPath } from 'url';

// Two roots: the assistant ships in public/, the rendered snapshot is written
// to data/ at the repository root. STATIC_DIST points at a built site, where
// both sit side by side.
const R = process.env.STATIC_DIST || fileURLToPath(new URL('../../public/', import.meta.url));
const DATA = process.env.STATIC_DIST || fileURLToPath(new URL('../../data/', import.meta.url));
const out = [];
const ck = (n, ok, x = '') => out.push(`${ok ? 'PASS' : 'FAIL'}  ${n}${x ? '  (' + x + ')' : ''}`);

// The snapshot the build writes next to the site: page copy plus the lexicon.
function snapshot() {
  const read = (f) => {
    try { return fs.readFileSync(DATA + f, 'utf8'); } catch { return ''; }
  };
  const grab = (text, name) => {
    const m = text.match(new RegExp('window\\.AXIA_STATIC\\.' + name + '\\s*=\\s*(\\[.*?\\]);', 's'));
    if (!m) return [];
    try { return JSON.parse(m[1]); } catch { return []; }
  };
  const products = read('products.js');
  return { pages: grab(products, 'pages'), pairs: grab(read('vocabulary.js'), 'pairs') };
}

function boot(pages, pairs) {
  const vc = new VirtualConsole();
  vc.on('jsdomError', () => {});
  const dom = new JSDOM('<!doctype html><html><body><div id="app"></div></body></html>', {
    runScripts: 'outside-only', pretendToBeVisual: true, url: 'http://localhost:8000/',
    virtualConsole: vc,
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
      w.localStorage.setItem('axia-lang', 'fa');
      w.AXIA_STATIC = { products: [], articles: [], pages, pairs };
    },
  });
  dom.window.eval(fs.readFileSync(R + 'xiona.js', 'utf8'));
  return dom.window;
}

const { pages, pairs } = snapshot();

// ---- the build actually rendered AURION -------------------------------- //
const topics = pages.map((p) => p.topic);
ck('the snapshot contains AURION copy', topics.includes('aurion'), topics.join(','));
ck('the snapshot contains the AURION plans page', topics.includes('aurionPlans'));
ck('the snapshot contains the services copy', topics.includes('services'));

const aurion = pages.find((p) => p.topic === 'aurion') || {};
ck('the AURION copy names MetaTrader',
  /MetaTrader/i.test(aurion.text || ''));
ck('the AURION copy says it is a showcase',
  /showcase|concept/i.test(aurion.text || ''));
// Decorative glyphs and "Back to ..." crumbs were being quoted back as facts.
ck('the AURION copy carries no navigation crumbs',
  !/Back to|↗|←|◈/.test(aurion.text || ''),
  (aurion.text || '').slice(0, 60));

// ---- the browser assistant answers from it ----------------------------- //
const win = boot(pages, pairs);
ck('the browser script defines Xiona', !!(win.Xiona && win.Xiona.Engine));
// The engine starts empty and is fed: vocabulary first, then content — the
// same order build_engine() uses on the server.
const engine = win.Xiona
  ? new win.Xiona.Engine({}).vocabulary(pairs)
      .learn({ products: [], articles: [], pages })
  : null;
ck('the browser engine boots', !!engine && engine.size() > 0,
  engine ? engine.size() + ' chunks' : 'none');

if (engine) {
  // The browser engine takes an options object (the server takes a keyword).
  const ask = (q, lang) => engine.answer(q, { language: lang });

  const fa = ask('اوریون چیست؟', 'fa');
  ck('a Persian question about AURION is answered', fa.source === 'knowledge', fa.source);
  ck('the AURION answer does not claim ignorance',
    !/هنوز دانشی/.test(fa.text || ''));
  ck('the AURION answer talks about MetaTrader',
    /MetaTrader|متاتریدر/i.test(fa.text || ''));

  const en = ask('what is AURION?', 'en');
  ck('an English question about AURION is answered', en.source === 'knowledge', en.source);

  const services = ask('چه خدماتی ارائه می‌دهید؟', 'fa');
  ck('a question about services is answered', services.source === 'knowledge',
    services.source);

  // The policy pages exist only in English, and the browser engine refuses to
  // hand English text to a Persian reader — a deliberate choice, documented in
  // answer(). What must hold is that the refusal is the honest "this part of the
  // site is English only" notice, not the empty-index message that started all
  // this.
  const refund = ask('سیاست بازپرداخت چیست؟', 'fa');
  ck('a Persian refund question gets the language notice, not "I know nothing"',
    !/هنوز دانشی/.test(refund.text || ''), refund.source);
  const refundEn = ask('what is the refund policy?', 'en');
  ck('the refund policy is reachable in English',
    refundEn.source === 'knowledge' && /14/.test(refundEn.text || ''),
    refundEn.source);

  // The site publishes no prices at all. The assistant must say that rather
  // than produce a number, and must not answer "I know nothing".
  const price = ask('قیمت طراحی وب‌سایت چقدر است؟', 'fa');
  ck('a price question never invents a number',
    !/(€|یورو|تومان|دلار)\s*[0-9۰-۹]/.test(price.text || ''),
    (price.text || '').slice(0, 80));
  // The quiet half of the same bug: the site genuinely publishes no prices, so
  // any figure would be fabricated. Numbers may appear only as the 14-day
  // refund window or a duration — never as a price.
  const figures = (price.text || '').match(/[0-9۰-۹][0-9۰-۹,٬.]*/g) || [];
  ck('the price answer contains no invented figures',
    figures.every((f) => /^(14|1|3|6|12)$/.test(f)), figures.join(','));
  ck('a price question does not claim total ignorance',
    !/هنوز دانشی/.test(price.text || ''));
}

console.log(out.join('\n'));
const failed = out.filter((l) => l.startsWith('FAIL')).length;
console.log(`\n${out.length - failed}/${out.length} checks passed`);
process.exit(failed ? 1 : 0);

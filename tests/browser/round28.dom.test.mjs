// Round 28: the assistant must have the site's knowledge in the browser.
//
// The report was "I can't chat with the AI, and it seems the AI does not answer
// correctly". Reproduced exactly: on the server build, public/index.html carries
// no snapshot (that is deliberate - the server catalog stays empty), so
// window.AXIA_STATIC is undefined in the browser and learnSite() was handed
// nothing but the footer and the panel text. The whole index was two chunks, and
// the refusal said so out loud:
//
//   "This site does not publish anything about 'aurion', so I have no answer for
//    it. What it does publish: AXIASOFT, Xiona."
//
// Meanwhile /api/agent on the same server answered AURION correctly, because the
// server has the index and the browser did not.
//
// Three separate faults were behind this, and each has its own checks below:
//
//   1. the browser was never given the page copy   (/api/xiona/knowledge)
//   2. 'چیه' was tokenized with its question mark  ('چیه؟' is not the stopword)
//   3. every question ending in 'چیه' was read as "who are you"
//
// Tests run against the built tree, like the other .dom suites.
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

/* ------------------------------------------------------------- the engine */

// xiona.js exports tokenize/fold for exactly this kind of check.
const xionaSrc = read(R + 'xiona.js');
const xmod = { exports: {} };
new Function('module', xionaSrc)(xmod);
const { Engine, tokenize } = xmod.exports;

/* --------------------------------------------------- 1. the question mark */

// The Arabic question mark, comma and semicolon live inside \u0600-\u06FF, which
// is the range the token regex accepts, so a word followed by one of them was
// captured WITH it: 'چیه؟' became the token 'چیه؟', which is not the stopword
// 'چیه'. The commonest way a Persian speaker asks a question therefore read as a
// content word and wrecked the score.
const punct = [
  ['چیه؟', 'اوریون چیه؟'],
  ['چیست؟', 'AURION چیست؟'],
  ['چیه،', 'محصولات چیه،'],
  ['چیه؛', 'هزینه چیه؛'],
];
for (const [word, q] of punct) {
  ck(`'${word}' leaves no punctuation on the tokens`,
    !tokenize(q).some((t) => /[؟،؛]/.test(t)), tokenize(q).join(','));
}
ck('the question mark is gone but the subject survives',
  tokenize('اوریون چیه؟').join(',') === 'اوریون', tokenize('اوریون چیه؟').join(','));
ck("'چیه' is still a stopword once the mark is off", tokenize('چیه').length === 0);

// The Python twin folds the same characters; the two engines must agree.
const pyEngine = read(fileURLToPath(new URL('../../server/xiona_engine.py', import.meta.url)));
ck('the Python twin folds the same punctuation',
  /u061F/u.test(pyEngine) && /u060C/u.test(pyEngine) && /u061B/u.test(pyEngine));

/* ------------------------------------------------ 3. "who are you" hijack */

// The identity pattern treated the SUBJECT as optional and accepted a bare 'ه',
// so the 'چی' inside 'چیه' plus its final 'ه' matched: every question ending in
// 'چیه' got the introduction instead of an answer.
const identSrc = xionaSrc.match(/var IDENTITY = (\/[\s\S]*?\/i);/);
ck('the identity pattern is still in the engine', !!identSrc);
const IDENTITY = identSrc ? eval(identSrc[1]) : /$^/;

const notIdentity = ['اوریون چیه؟', 'محصولات چیه؟', 'هزینه بازپرداخت چیه؟', 'AURION چیه؟', 'ساعت کاری چیه؟'];
const isIdentity = ['شما کی هستید؟', 'تو کی هستی', 'شما چی هستید؟', 'who are you', 'what are you', 'are you a bot'];
for (const q of notIdentity) ck(`'${q}' is a question about its subject`, !IDENTITY.test(q));
for (const q of isIdentity) ck(`'${q}' still asks who the assistant is`, IDENTITY.test(q));

/* ------------------------------------- 2. the browser is given the copy */

// The route must exist in api_get - a read, not api_write. The first attempt at
// this fix was inserted into the POST handler by accident and answered 404 to
// every GET, which is exactly the kind of mistake a test should catch.
const appPy = read(fileURLToPath(new URL('../../server/app.py', import.meta.url)));
ck('the server exposes the page copy for the browser', /['"]\/api\/xiona\/knowledge['"]/.test(appPy));
const apiGet = appPy.slice(appPy.indexOf('def api_get'), appPy.indexOf('def api_write'));
ck('it is registered as a read route', /api\/xiona\/knowledge/.test(apiGet));
ck('the browser fetches that route', /api\/xiona\/knowledge/.test(read(R + 'app.js')));

/* ------------------------------------------------------ answers for real */

const settings = JSON.parse(read(ROOT + 'data/settings.json') || '{}');
const products = JSON.parse(read(ROOT + 'data/products.json') || '[]');

// learnSite reads pages, products and pairs from window.AXIA_STATIC. Build the
// same object the browser ends up with once the snapshot and the lazily fetched
// vocabulary have both landed.
const snapshot = { AXIA_STATIC: {} };
new Function('window', read(ROOT + 'data/products.js'))(snapshot);
new Function('window', read(ROOT + 'data/vocabulary.js'))(snapshot);

function engineFor(pages) {
  const w = { AXIA_STATIC: { products, articles: snapshot.AXIA_STATIC.articles || [], pages, pairs: snapshot.AXIA_STATIC.pairs || [] } };
  const doc = {
    documentElement: { lang: 'fa', dataset: {}, dir: 'rtl' },
    querySelector: () => null, querySelectorAll: () => [],
  };
  global.document = doc; global.window = w; w.document = doc;
  return new Engine().learnSite({ window: w, document: doc });
}

const pages = snapshot.AXIA_STATIC.pages || [];
ck('the built snapshot ships page copy to index', pages.length >= 8, `${pages.length} pages`);

const engine = engineFor(pages);

// The four ways of asking the same thing must all reach the AURION page, and
// none of them may be answered with a Terms excerpt.
for (const q of ['AURION چیست؟', 'اوریون چیه؟', 'AURION چیه؟', 'اوریون چیست؟']) {
  const r = engine.answer(q);
  const topics = (r.citations || []).map((c) => c.topic);
  ck(`'${q}' reaches the AURION page`, topics.includes('aurion') || topics.includes('aurionPlans'),
    topics.join(',') || r.source);
  ck(`'${q}' is not answered with the terms page`, !topics.includes('terms'), topics.join(','));
}

const aurion = engine.answer('اوریون چیه؟');
ck('and the answer actually names AURION', /aurion/i.test(aurion.text || ''),
  (aurion.text || '').slice(0, 60));

// A question about the assistant itself still gets the introduction.
const self = engine.answer('شما کی هستید؟');
ck('an identity question introduces the assistant', /Xiona/.test(self.text || ''), self.text.slice(0, 50));

// A question the site genuinely does not cover still says so, honestly.
const absent = engine.answer('قیمت سهام بورس چیه؟');
ck('an unknown subject is still declined', absent.source === 'uncovered' || absent.source === 'no-match',
  `${absent.source}: ${(absent.text || '').slice(0, 50)}`);

/* --------------------------- the empty-index refusal must not fire wrongly */

// The whole point: with the copy present the index is not two chunks, so the
// "I have no knowledge yet" answer cannot appear for ordinary questions.
const stats = engine.stats();
ck('the index carries the catalog and the pages, not two shell chunks',
  stats.chunks > 40, `${stats.chunks} chunks`);
ck('it knows the products', (stats.topics.product || 0) + (stats.topics.products || 0) > 0,
  JSON.stringify(stats.topics).slice(0, 80));

console.log(out.join('\n'));
const failed = out.filter((l) => l.startsWith('FAIL')).length;
console.log(`\n${out.length - failed}/${out.length} checks passed`);
if (failed) process.exit(1);

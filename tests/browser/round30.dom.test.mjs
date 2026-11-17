// Round 30: the assistant answers in the language it was spoken to in.
//
// The operator: "the chatbot speaks English; make it answer in English when I
// speak English and in Persian when I speak Persian." The browser engine took
// its language from `document.documentElement.lang`, so a Persian question on
// an English page was answered in English by design. This pins the reversal and
// the greeting guard that the reversal exposed.
import fs from 'fs';
import { fileURLToPath } from 'url';

const SRC = fileURLToPath(new URL('../../public/xiona.js', import.meta.url));
const src = fs.readFileSync(SRC, 'utf8');

const out = [];
const ck = (n, ok, x = '') => out.push(`${ok ? 'PASS' : 'FAIL'}  ${n}${x ? '  (' + x + ')' : ''}`);

// The engine reads `document.documentElement.lang` only through uiLanguage(),
// and only when nothing else decides. Stub it at the opposite value to what the
// question is, so a passing check proves the question won.
function load(siteLanguage) {
  const mod = { exports: {} };
  const doc = { documentElement: { lang: siteLanguage } };
  global.document = doc;
  global.window = { document: doc };
  new Function('module', 'window', 'document', src)(mod, global.window, doc);
  return mod.exports;
}

const X = load('en');           // the site is open in English
const e = new X.Engine();
e.add({ id: 'a', title: 'About', topic: 'about', route: '#/about', language: 'en',
  text: 'AXIASOFT is an independent software studio in Nuremberg. We build websites, ' +
        'mobile applications and custom software for teams of any size.', keywords: 'about studio' });

/* ---------------------------------- the question decides the reply language */

const fa = e.answer('محصولاتتون چیه؟');
ck('a Persian question on the English site is answered in Persian',
  fa.language === 'fa', `got ${fa.language}`);

const en = e.answer('what do you build?');
ck('an English question is answered in English', en.language === 'en', `got ${en.language}`);

// Same engine, opposite site language: the answer must not move.
const X2 = load('fa');
const e2 = new X2.Engine();
e2.add({ id: 'a', title: 'About', topic: 'about', route: '#/about', language: 'fa',
  text: 'AXIASOFT یک استودیوی مستقل نرم‌افزار در نورنبرگ است.', keywords: 'about' });
ck('the site language no longer decides it',
  e2.answer('what do you build?').language === 'en',
  `got ${e2.answer('what do you build?').language}`);

/* ------------------------------- an explicit language still overrides it */

const forced = e.answer('محصولاتتون چیه؟', { language: 'en' });
ck('an explicit language still wins', forced.language === 'en', `got ${forced.language}`);

/* -------------------------------------------------------- greeting guard */

// A greeting that opens a real question is a question. The old guard counted
// the tokens left after stopword removal, so once 'چطوری' became a function
// word "چطوری سایت بسازیم" had two left and was answered "Hello, I am Xiona".
for (const q of ['چطوری سایت بسازیم', 'سلام، قیمت چنده؟', 'hello, how much does a site cost']) {
  ck(`'${q}' is not treated as a greeting`, e.answer(q).source !== 'greeting',
    e.answer(q).source);
}
for (const q of ['سلام', 'چطوری', 'hi', 'hello there', 'how are you doing today']) {
  ck(`'${q}' is a greeting`, e.answer(q).source === 'greeting', e.answer(q).source);
}

/* ------------------------------------------- the widened search runs empty */

// Round 29 gated the cross-language search on `hits.length`, so when the
// Persian search found nothing at all — the common case for catalog subjects —
// the widening never ran and the question was refused while Python answered it.
const X3 = load('fa');
const e3 = new X3.Engine();
e3.vocabulary([['refund', 'بازپرداخت']]);   // pairs are [english, persian]
// Enough English chunks that BM25 behaves: the score depends on how many
// documents share a term, so a one-document corpus gives every query a near-zero
// score and the minimum-score guard fires before the widening is reached.
const padding = [
  'We build websites and mobile applications for teams of every size.',
  'Our studio works from first idea to a released product.',
  'Custom software, integrations and long-running maintenance plans.',
  'The team is small, senior and based in Nuremberg, Germany.',
  'Every project starts with a short discovery conversation.',
];
padding.forEach((text, i) => e3.add({ id: 'p' + i, title: 'Page ' + i, topic: 'page' + i,
  route: '#/p' + i, language: 'en', text: text, keywords: 'page ' + i }));
e3.add({ id: 'r', title: 'Refund policy', topic: 'refunds-policy', route: '#/refunds',
  language: 'en', keywords: 'refund policy terms',
  text: 'A refund is available within thirty days of purchase. Contact support to start one.' });
const refund = e3.answer('بازپرداخت');
ck('a Persian word with no Persian chunk reaches the English one',
  refund.source === 'knowledge', refund.source);
ck('and the answer names the refund policy',
  (refund.citations[0] || {}).topic === 'refunds-policy',
  (refund.citations[0] || {}).topic);

/* -------------------------------------------------- the browser side */

const appJs = fs.readFileSync(fileURLToPath(new URL('../../public/app.js', import.meta.url)), 'utf8');
const call = appJs.slice(appJs.indexOf("fetch('/api/agent'"), appJs.indexOf("fetch('/api/agent'") + 300);
ck('the browser no longer dictates the language', !/\blanguage\s*:/.test(call),
  call.replace(/\s+/g, ' ').slice(0, 90));

console.log(out.join('\n'));
const failed = out.filter((l) => l.startsWith('FAIL')).length;
console.log(`\n${out.length - failed}/${out.length} checks passed`);
if (failed) process.exit(1);

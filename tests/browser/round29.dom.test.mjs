// Round 29: the assistant must be able to reach the site's words.
//
// The operator's log showed `GET /data/vocabulary.js 404` on every page load,
// and the complaint behind it: "I still did not get a correct answer from the
// AI." The 404 was real and permanent on a server install - loadVocabulary()
// asks for data/vocabulary.js, which only the static build writes, and the
// server serves public/ and nothing else (it must not serve data/: the SQLite
// database lives there).
//
// Without the dictionary the engine cannot cross languages, so a Persian
// question about the catalog read as a word the site never publishes:
//
//   'محصولات چیه؟'   -> "this site publishes nothing about 'محصولات'"
//
// Three more faults sat behind that one:
//
//   1. the dictionary was unreachable on the server            (/api route)
//   2. 'تون' was not a suffix, so 'خدماتتون' never became 'خدمات'
//   3. spoken question words ('چنده', 'چطوره', 'کدومه') were content
//
// and two on the ranking side, both older than this round:
//
//   4. the catalog is indexed as English, so a Persian search never saw it
//   5. "what is X" was answered from a closing legal paragraph
//
// Runs against the built tree, like the other .dom suites.
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

const xionaSrc = read(R + 'xiona.js');
const xmod = { exports: {} };
new Function('module', xionaSrc)(xmod);
const { Engine, tokenize } = xmod.exports;

/* ------------------------------------------- 1. the dictionary is reachable */

const appPy = read(fileURLToPath(new URL('../../server/app.py', import.meta.url)));
const appJs = read(R + 'app.js');

ck('the server exposes the dictionary', /['"]\/api\/xiona\/vocabulary['"]/.test(appPy));
const apiGet = appPy.slice(appPy.indexOf('def api_get'), appPy.indexOf('def api_write'));
ck('it is a read route, not a write one', /api\/xiona\/vocabulary/.test(apiGet));
ck('the browser falls back to it when the static file is missing',
  /api\/xiona\/vocabulary/.test(appJs), 'loadVocabulary()');
ck('and it still tries the static file first, so the demo pays nothing',
  appJs.indexOf('data/vocabulary.js') < appJs.indexOf('api/xiona/vocabulary'));

/* --------------------------------------------- 2. spoken suffixes are stems */

// 'خدماتتون' is 'خدمات' + 'تون' (the spoken form of 'تان'). It was missing from
// the suffix list, so a question written the way people talk kept a word the
// site never publishes and was refused.
const stems = [
  ['خدماتتون چیه؟', 'خدمات'],
  ['محصولاتتون کدومه؟', 'محصولات'],
  ['ساعت کارتون چطوره؟', 'کار'],
];
for (const [question, expected] of stems) {
  ck(`'${question}' stems to include '${expected}'`,
    tokenize(question).includes(expected), tokenize(question).join(','));
}

/* ------------------------------------- 3. spoken question words are dropped */

for (const word of ['چنده', 'چطوره', 'کدومه', 'کدام', 'کجاست', 'چطوری']) {
  ck(`'${word}' is a function word, not a subject`, tokenize(word).length === 0,
    tokenize(word).join(','));
}
ck("'قیمت چنده؟' is a question about price only",
  tokenize('قیمت چنده؟').join(',') === 'قیمت', tokenize('قیمت چنده؟').join(','));

/* ------------------------------- 4+5. the catalog is reachable and defined */

const settings = JSON.parse(read(ROOT + 'data/settings.json') || '{}');
const products = JSON.parse(read(ROOT + 'data/products.json') || '[]');
const snapshot = { AXIA_STATIC: {} };
new Function('window', read(ROOT + 'data/products.js'))(snapshot);
new Function('window', read(ROOT + 'data/vocabulary.js'))(snapshot);

// Load the site dictionary so AXIA_T exists, exactly as the page does.
const i18nSrc = read(R + 'i18n.js');
const fakeDoc = {
  documentElement: { lang: 'fa', dataset: {}, dir: 'rtl' },
  querySelector: () => null, querySelectorAll: () => [],
  addEventListener() {}, body: {}, createTreeWalker: () => ({ nextNode: () => null }),
};
const shell = {};
global.document = fakeDoc;
global.localStorage = { getItem: () => 'fa', setItem() {} };
global.location = { search: '', reload() {} };
global.MutationObserver = class { observe() {} };
global.NodeFilter = { SHOW_TEXT: 4 };
global.Node = { TEXT_NODE: 3, ELEMENT_NODE: 1 };
new Function('window', 'document', 'localStorage', 'location', 'MutationObserver',
  'NodeFilter', 'Node', i18nSrc)(shell, fakeDoc, localStorage, location,
  MutationObserver, NodeFilter, Node);

const w = { AXIA_STATIC: { products, articles: snapshot.AXIA_STATIC.articles || [],
  pages: snapshot.AXIA_STATIC.pages || [], pairs: snapshot.AXIA_STATIC.pairs || [] } };
if (shell.AXIA_T) w.AXIA_T = shell.AXIA_T;
global.window = w;
w.document = fakeDoc;

const engine = new Engine().learnSite({ window: w, document: fakeDoc });

ck('the dictionary reached the engine', (snapshot.AXIA_STATIC.pairs || []).length > 500,
  `${(snapshot.AXIA_STATIC.pairs || []).length} pairs`);

// The fault the operator hit: the catalog is indexed as English, so a Persian
// search never reached it and the contact page's incidental 'price' won.
for (const q of ['محصولات چیه؟', 'چه محصولاتی دارید؟', 'محصولاتتون کدومه؟']) {
  const r = engine.answer(q);
  ck(`'${q}' is answered, not refused`, r.source === 'knowledge',
    `${r.source}: ${(r.text || '').slice(0, 40)}`);
}

// And the refusal must not come back for the spoken forms of a question.
for (const q of ['قیمت چنده؟', 'خدماتتون چیه؟']) {
  const r = engine.answer(q);
  ck(`'${q}' is not a refusal`, r.source === 'knowledge',
    `${r.source}: ${(r.text || '').slice(0, 40)}`);
}

// "What is X" must be answered from the sentence that says what X is, not from
// a closing legal paragraph that merely shares the page's vocabulary.
const aurion = engine.answer('اوریون چیست؟');
ck('AURION is answered from the sentence that defines it',
  /product by AXIASOFT/i.test(aurion.text || '') || /MetaTrader/i.test(aurion.text || ''),
  (aurion.text || '').slice(0, 70));

// A question about the assistant itself, with no content words at all.
const self = engine.answer('شما کی هستید؟');
ck('an identity question is answered about the assistant',
  /Xiona/.test(self.text || ''), (self.text || '').slice(0, 60));

/* --------------------------------------- the server answers the same way */

const enginePy = read(fileURLToPath(new URL('../../server/xiona_engine.py', import.meta.url)));
ck('the Python twin knows the spoken suffixes',
  /'تون'/.test(enginePy) && /'مون'/.test(enginePy) && /'شون'/.test(enginePy));
ck('the Python twin knows the spoken question words',
  /'چنده'/.test(enginePy) && /'چطوره'/.test(enginePy) && /'کدومه'/.test(enginePy));
ck('the Python twin tests the stem against the stopword list',
  /stem != word and stem in stops/.test(enginePy));

const agentPy = read(fileURLToPath(new URL('../../server/agent.py', import.meta.url)));
ck('the server teaches the engine what the assistant is',
  /ASSISTANT_SELF/.test(agentPy) && /topic': 'assistant'/.test(agentPy));

console.log(out.join('\n'));
const failed = out.filter((l) => l.startsWith('FAIL')).length;
console.log(`\n${out.length - failed}/${out.length} checks passed`);
if (failed) process.exit(1);

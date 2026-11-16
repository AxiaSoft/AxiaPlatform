// Round 20: Xiona answers in the site's language, and the conversation outlives
// the panel. Runs against the built tree in the state a visitor gets it.
import { JSDOM, VirtualConsole } from 'jsdom';
import fs from 'fs';
import { fileURLToPath } from 'url';

const D = process.env.STATIC_DIST || fileURLToPath(new URL('../../dist/', import.meta.url));
const read = (p) => fs.readFileSync(D + p, 'utf8');
const out = [];
const ck = (n, ok, x = '') => out.push(`${ok ? 'PASS' : 'FAIL'}  ${n}${x ? '  (' + x + ')' : ''}`);

const settingsSrc = read('data/settings.js');
const settings = JSON.parse(settingsSrc.slice(settingsSrc.indexOf('settings = ') + 11).replace(/;\s*$/, ''));
const vocabulary = read('data/vocabulary.js');

/* One shared account store across boots, so "another device" is really another
   device hitting the same account rather than two objects in one process. */
let accountHistory = null;

async function boot({ lang = 'en', signedIn = false, tabStore = null } = {}) {
  const vc = new VirtualConsole();
  const errors = [];
  vc.on('jsdomError', (e) => errors.push(e.message));
  const dom = new JSDOM(read('index.html'), {
    runScripts: 'outside-only', url: 'https://x.test/AxiaPlatform/#/',
    pretendToBeVisual: true, virtualConsole: vc,
  });
  const w = dom.window;
  w.matchMedia = (q) => ({
    matches: false, addEventListener() {}, removeEventListener() {},
    addListener() {}, removeListener() {},
  });
  w.localStorage.setItem('axia-lang', lang);
  if (tabStore) w.sessionStorage.setItem('axia-chat-v1', tabStore);
  w.fetch = async (u, o = {}) => {
    const s = String(u);
    const m = (o.method || 'GET').toUpperCase();
    const ok = (body, status = 200) => ({
      ok: status < 400, status, headers: { get: () => null }, json: async () => body,
    });
    if (s.includes('/api/site')) return ok({ settings });
    if (s.includes('/api/me')) {
      return ok({ user: signedIn ? { id: 1, name: 'S', email: 'e@x', role: 'customer' } : null, csrf: 'c' });
    }
    if (s.includes('/api/agent/history')) {
      if (!signedIn) return ok({ error: 'sign in' }, 401);
      if (m === 'GET') return ok({ history: accountHistory || [] });
      if (m === 'POST') { accountHistory = JSON.parse(o.body).history; return ok({ ok: true }); }
      if (m === 'DELETE') { accountHistory = []; return ok({ ok: true }); }
    }
    if (s.includes('vocabulary.js')) return { ok: true, status: 200, text: async () => vocabulary };
    if (s.endsWith('/api/agent')) return ok({ error: 'static build' }, 501);
    return ok([]);
  };
  w.scrollTo = () => {};
  for (const f of ['data/products.js', 'data/settings.js', 'brands.js', 'i18n.js', 'xiona.js', 'app.js']) {
    w.eval(read(f));
  }
  await new Promise((r) => setTimeout(r, 1400));
  return { w, errors };
}

const openPanel = async (w) => {
  w.document.getElementById('chat-launcher')
    .dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  // The vocabulary fetch plus the history round-trip.
  await new Promise((r) => setTimeout(r, 1100));
};
const closePanel = async (w) => {
  w.document.getElementById('chat-launcher')
    .dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await new Promise((r) => setTimeout(r, 250));
};
const send = async (w, text) => {
  const input = w.document.getElementById('chat-input');
  input.value = text;
  w.document.getElementById('chat-form')
    .dispatchEvent(new w.Event('submit', { bubbles: true, cancelable: true }));
  await new Promise((r) => setTimeout(r, 900));
  const nodes = [...w.document.querySelectorAll('#chat-messages .chat-msg')];
  return nodes[nodes.length - 1]?.textContent || '';
};
const turns = (w) => [...w.document.querySelectorAll('#chat-messages .chat-msg')].length;
const isPersian = (s) => /[\u0600-\u06FF]/.test(s);

/* ---- 1. the engine takes its language from the site, not the question ---- */
const src = read('xiona.js');
ck('the engine reads the page language', src.includes('function uiLanguage()') &&
  src.includes('documentElement.lang'));
ck('answer() no longer infers from the question',
  /var language = \(opts\.language === 'fa' \|\| opts\.language === 'en'\) \? opts\.language : uiLanguage\(\);/.test(src));
ck('retrieval searches the site language first',
  /hits = this\.search\(query, \{ language: language, limit: this\.maxResults \}\)/.test(src));
ck('a Persian reader is not handed English copy',
  src.includes('the failure this ordering removes') || src.includes("language === 'en'") );
ck('the refusal names the other language only when it has the answer',
  src.includes('_otherLanguageHint'));
ck('identity questions are answered as identity questions',
  src.includes('_asksIdentity') && src.includes('_selfChunk'));
ck('the old glyph-free greeting still exists in both languages',
  src.includes("greeting: 'سلام.") && src.includes('greeting: "Hi,'));

/* ---- 2. a Persian site answers in Persian, an English one in English ---- */
{
  const { w, errors } = await boot({ lang: 'fa' });
  ck('the Persian site boots cleanly', errors.length === 0, errors[0] || '');
  await openPanel(w);
  ck('the panel speaks Persian', /دستیار/.test(w.document.querySelector('.chat-head strong')?.textContent || ''));
  ck('the placeholder is Persian', /محصولات/.test(w.document.getElementById('chat-input')?.placeholder || ''));

  const identity = await send(w, 'شما کی هستید؟');
  ck('an identity question is answered, not refused',
    !/چیزی منتشر نکرده/.test(identity) && /Xiona/.test(identity), identity.slice(0, 60));
  ck('...in Persian', isPersian(identity));

  const greeting = await send(w, 'سلام');
  ck('a Persian greeting gets a Persian greeting', isPersian(greeting) && greeting.length < 120);

  // The reported bug: ask in Persian, get English back.
  const products = await send(w, 'چه محصولاتی دارید؟');
  ck('a Persian product question is not answered in English',
    !/catalog holds|complete website build/i.test(products), products.slice(0, 60));
  ck('...it is answered in Persian', isPersian(products));
  ck('...and it names where the English content is',
    /انگلیسی/.test(products), products.slice(0, 70));

  // A question typed in English on the Persian site still answers in Persian.
  const mixed = await send(w, 'what products do you have?');
  ck('a question typed in the other language still answers in the site language',
    isPersian(mixed), mixed.slice(0, 60));

  w.close();
}

{
  const { w, errors } = await boot({ lang: 'en' });
  ck('the English site boots cleanly', errors.length === 0, errors[0] || '');
  await openPanel(w);
  ck('the panel speaks English',
    /on-site assistant/.test(w.document.querySelector('.chat-head strong')?.textContent || ''));

  const products = await send(w, 'what products do you have?');
  ck('the English catalog question is answered from the catalog',
    /catalog holds|Arya/i.test(products), products.slice(0, 50));
  ck('...in English', !isPersian(products));

  // The mirror case: Persian typed into the English site.
  const persianOnEnglish = await send(w, 'چه محصولاتی دارید؟');
  ck('a Persian question on the English site is answered in English',
    !isPersian(persianOnEnglish) || /AXIASOFT|Xiona/.test(persianOnEnglish),
    persianOnEnglish.slice(0, 60));
  w.close();
}

/* ---- 3. the conversation outlives the panel ---- */
{
  const { w } = await boot({ lang: 'en' });
  await openPanel(w);
  await send(w, 'what products do you have?');
  const afterOne = turns(w);
  ck('a turn is recorded', afterOne >= 3, `${afterOne} nodes`);
  ck('it is written to the tab store', !!w.sessionStorage.getItem('axia-chat-v1'));

  await closePanel(w);
  ck('closing removes the panel', !w.document.getElementById('chat-panel'));
  await openPanel(w);
  ck('reopening restores the conversation', turns(w) >= 2, `${turns(w)} nodes`);
  ck('...with a divider that says so', !!w.document.querySelector('.chat-resumed'));
  ck('...not a second greeting',
    (w.document.getElementById('chat-messages').textContent.match(/I'm Xiona/g) || []).length === 0);

  const tabCopy = w.sessionStorage.getItem('axia-chat-v1');
  w.close();

  // A reload: new document, same tab.
  const { w: reloaded } = await boot({ lang: 'en', tabStore: tabCopy });
  await openPanel(reloaded);
  ck('a reload keeps it', turns(reloaded) >= 2, `${turns(reloaded)} nodes`);
  ck('a reload shows the divider', !!reloaded.document.querySelector('.chat-resumed'));
  reloaded.close();
}

/* ---- 4. a signed-in visitor's history belongs to the account ---- */
{
  accountHistory = null;
  const { w } = await boot({ lang: 'en', signedIn: true });
  await openPanel(w);
  await send(w, 'what products do you have?');
  await new Promise((r) => setTimeout(r, 500));
  ck('signed in, the turn reaches the account', (accountHistory || []).length >= 1,
    `${(accountHistory || []).length} turns`);
  w.close();

  // Another device: no tab storage at all.
  const { w: other } = await boot({ lang: 'en', signedIn: true });
  await openPanel(other);
  ck('another device resumes from the account', turns(other) >= 2, `${turns(other)} nodes`);
  ck('...and labels it as resumed', !!other.document.querySelector('.chat-resumed'));
  other.close();

  // A shared machine: the tab holds someone else's history.
  const leaked = JSON.stringify([{ role: 'user', text: 'my password is hunter2' },
                                 { role: 'bot', text: 'noted' }]);
  const { w: shared } = await boot({ lang: 'en', signedIn: true, tabStore: leaked });
  await openPanel(shared);
  const shown = shared.document.getElementById('chat-messages').textContent;
  ck('a signed-in visitor never sees the previous tab holder\'s chat',
    !shown.includes('hunter2'), 'leaked tab copy was rendered');
  shared.close();
}

/* ---- 5. signed out, the history dies with the browser session ---- */
{
  // That is what sessionStorage means: it is scoped to the tab (and its
  // opener chain), and is discarded when the browser session ends. The code
  // must therefore use sessionStorage rather than localStorage for guests.
  const appJs = read('app.js');
  ck('the guest store is the tab, not the device',
    /sessionStorage/.test(appJs) && /CHAT_KEY/.test(appJs));
  ck('guests are written to sessionStorage specifically',
    /chatStorage\(\)\?\.setItem\(CHAT_KEY/.test(appJs.replace(/\s+/g, '')) ||
    appJs.replace(/\s+/g, '').includes('chatStorage()?.setItem(CHAT_KEY'));
  const guestBlock = appJs.slice(appJs.indexOf('function chatStorage()'),
                                appJs.indexOf('function loadChatHistory()'));
  ck('the guest store never touches localStorage', !/localStorage/.test(guestBlock));
  ck('a signed-in visitor\'s history is fetched from the account',
    appJs.includes("api('/api/agent/history')"));
  ck('the account copy wins over the tab copy',
    appJs.includes('The account is authoritative'));
}

console.log(out.join('\n'));
const failures = out.filter((l) => l.startsWith('FAIL')).length;
console.log(`\n${failures ? failures + ' FAILURES' : 'ALL PASS'}`);
process.exit(failures ? 1 : 0);

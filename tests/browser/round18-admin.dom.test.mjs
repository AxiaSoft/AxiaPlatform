// The FAQ editor in the console: the tab renders, the inputs edit the draft,
// the add/remove/reorder actions work, and a save sends the list.
import { JSDOM } from 'jsdom';
import fs from 'fs';

const D = process.env.STATIC_DIST || '/home/user/AxiaPlatform/';
const read = (p) => fs.readFileSync(D + p, 'utf8');
const out = [];
const ck = (n, ok, x = '') => out.push(`${ok ? 'PASS' : 'FAIL'}  ${n}${x ? '  (' + x + ')' : ''}`);

const settings = (() => {
  const src = read('data/settings.js');
  return JSON.parse(src.slice(src.indexOf('settings = ') + 11).replace(/;\s*$/, ''));
})();
let cart = [];
const dom = new JSDOM(read('admin/index.html'), {
  runScripts: 'outside-only', url: 'https://x.test/AxiaPlatform/admin/', pretendToBeVisual: true,
});
const w = dom.window;
const errors = [];
w.addEventListener('error', (e) => errors.push(String(e.message)));
w.matchMedia = w.matchMedia || (() => ({
  matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
}));
w.fetch = (url, opts = {}) => {
  const u = String(url);
  let body = {}, status = 200;
  if (u.includes('/api/me')) body = { user: { id: 1, name: 'Admin', email: 'a@b.c', role: 'admin' }, csrf: 'tok' };
  else if (u.includes('/api/admin/settings')) {
    if (opts.method === 'PUT') {
      cart = JSON.parse(opts.body || '{}');
      body = { settings: { ...settings, ...JSON.parse(opts.body || '{}') } };
    } else body = { settings };
  } else if (u.includes('/api/admin/stats') || u.includes('/api/admin/')) body = {};
  else body = {};
  return Promise.resolve({ ok: status < 400, status, headers: { get: () => null }, json: async () => body });
};
for (const f of ['data/settings.js', 'brands.js', 'i18n.js', 'admin/admin.js']) {
  try { w.eval(read(f)); } catch (e) { errors.push('load ' + f + ': ' + e.message); }
}
await new Promise((r) => setTimeout(r, 900));

ck('the console boots without an error', errors.length === 0, errors.slice(0, 2).join(' | '));

const doc = w.document;
ck('the console is signed in', !!doc.querySelector('#pageContent'), 'no pageContent');

// Reach the settings screen and the FAQ tab.
const siteLink = [...doc.querySelectorAll('[data-page]')].find((b) => b.dataset.page === 'site')
  || [...doc.querySelectorAll('button')].find((b) => /site/i.test(b.textContent));
ck('the Site settings entry exists', !!siteLink);
if (siteLink) {
  siteLink.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await new Promise((r) => setTimeout(r, 400));
}

const faqTab = [...doc.querySelectorAll('[data-site-tab]')].find((b) => b.dataset.siteTab === 'faq');
ck('the Questions tab exists', !!faqTab, [...doc.querySelectorAll('[data-site-tab]')].map((b) => b.dataset.siteTab).join(','));
if (faqTab) {
  faqTab.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await new Promise((r) => setTimeout(r, 400));
}

ck('the editor lists the three shipped questions',
   doc.querySelectorAll('[data-faq-row]').length === 3,
   `${doc.querySelectorAll('[data-faq-row]').length}`);
ck('each row has both languages',
   doc.querySelectorAll('[data-field="q"]').length === 3 &&
   doc.querySelectorAll('[data-field="qFa"]').length === 3 &&
   doc.querySelectorAll('[data-field="a"]').length === 3 &&
   doc.querySelectorAll('[data-field="aFa"]').length === 3);
ck('the Persian inputs are right-to-left',
   doc.querySelector('[data-field="qFa"]').getAttribute('dir') === 'rtl');

// Typing reaches the draft.
const firstQ = doc.querySelector('[data-field="q"]');
firstQ.value = 'A changed question';
firstQ.dispatchEvent(new w.Event('input', { bubbles: true }));
await new Promise((r) => setTimeout(r, 120));
ck('typing updates the row heading',
   (doc.querySelector('[data-faq-row] strong')?.textContent || '').includes('A changed question'),
   doc.querySelector('[data-faq-row] strong')?.textContent);

// Add a row.
const add = [...doc.querySelectorAll('[data-act="faq-add"]')][0];
ck('the Add question button exists', !!add);
if (add) {
  add.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await new Promise((r) => setTimeout(r, 400));
}
ck('adding appends a row', doc.querySelectorAll('[data-faq-row]').length === 4,
   `${doc.querySelectorAll('[data-faq-row]').length}`);

// Remove the row we added (the last one, which is blank).
const removes = [...doc.querySelectorAll('[data-act="faq-remove"]')];
if (removes.length === 4) {
  removes[3].dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await new Promise((r) => setTimeout(r, 400));
}
ck('removing takes it back out', doc.querySelectorAll('[data-faq-row]').length === 3,
   `${doc.querySelectorAll('[data-faq-row]').length}`);

// A row with a question but no answer is refused; a wholly blank row is
// simply dropped, which is the documented behaviour of "Add question".
const form = doc.querySelector('[data-form="faq"]');
ck('the editor has a save form', !!form);
if (form) {
  const add2 = doc.querySelector('[data-act="faq-add"]');
  add2.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await new Promise((r) => setTimeout(r, 350));
  // Fill in a question but leave its answer empty: that is a half-written row,
  // not an abandoned one, and it must not be saved silently.
  const rows = doc.querySelectorAll('[data-faq-row]');
  const last = rows[rows.length - 1];
  const q = last.querySelector('[data-field="q"]');
  q.value = 'A question with no answer';
  q.dispatchEvent(new w.Event('input', { bubbles: true }));
  await new Promise((r) => setTimeout(r, 200));

  let puts = 0;
  const original = w.fetch;
  w.fetch = (u, o) => { if (o && o.method === 'PUT') puts++; return original(u, o); };
  const form2 = doc.querySelector('[data-form="faq"]');
  form2.dispatchEvent(new w.Event('submit', { bubbles: true, cancelable: true }));
  await new Promise((r) => setTimeout(r, 500));
  w.fetch = original;

  ck('a question with no answer is refused', puts === 0, `${puts} save(s) went out`);
  // The note must carry a sentence, not a swallowed error: a crashed handler
  // leaves the message empty and the operator with no idea what went wrong.
  const note = doc.querySelector('.error-note')?.textContent || '';
  ck('the refusal is explained on the form', note.length > 20 && !/is not a function/.test(note),
     note.slice(0, 70));
}

// A fully-written list saves, and the PUT carries exactly what is on screen.
{
  const rows = doc.querySelectorAll('[data-faq-row]');
  const last = rows[rows.length - 1];
  const a = last.querySelector('[data-field="a"]');
  a.value = 'It is on its way in the next release.';
  a.dispatchEvent(new w.Event('input', { bubbles: true }));
  await new Promise((r) => setTimeout(r, 200));

  let body = null;
  const original = w.fetch;
  w.fetch = (u, o) => { if (o && o.method === 'PUT') body = JSON.parse(o.body || '{}'); return original(u, o); };
  doc.querySelector('[data-form="faq"]').dispatchEvent(new w.Event('submit', { bubbles: true, cancelable: true }));
  await new Promise((r) => setTimeout(r, 700));
  w.fetch = original;

  ck('a complete list saves', Array.isArray(body?.faq), body ? JSON.stringify(body).slice(0, 60) : 'no PUT');
  ck('the save carries the edited question',
     (body?.faq || []).some((x) => x.q === 'A changed question'),
     (body?.faq || []).map((x) => x.q).join(' | ').slice(0, 80));
  ck('the save carries four questions now', (body?.faq || []).length === 4,
     `${(body?.faq || []).length}`);
}

console.log(out.join('\n'));
const failures = out.filter((l) => l.startsWith('FAIL')).length;
console.log(`\n${failures ? failures + ' FAILURES' : 'ALL PASS'}`);
process.exit(failures ? 1 : 0);

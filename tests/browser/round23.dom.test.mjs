// Round 23: the console must tell the truth about the model.
//
// A key in the environment and a model that answers are different things, and
// the assistant falls back to the on-site answer silently on purpose. That is
// right for a visitor and dangerous for an operator: a revoked key, or a model
// ID Google has shut down, produces a site that looks perfectly healthy while
// no visitor ever reaches the model. The console used to say "A live model is
// answering" whenever a key existed.
//
// This drives the real admin app with a stubbed /api/admin/agent and reads the
// sentence it actually renders for each of the four states.
import { JSDOM, VirtualConsole } from 'jsdom';
import fs from 'fs';
import { fileURLToPath } from 'url';

const R = process.env.STATIC_DIST || fileURLToPath(new URL('../../public/', import.meta.url));
const out = [];
const ck = (n, ok, x = '') => out.push(`${ok ? 'PASS' : 'FAIL'}  ${n}${x ? '  (' + x + ')' : ''}`);

async function renderMaintenanceCard(agentDoc) {
  const vc = new VirtualConsole();
  vc.on('jsdomError', () => {});
  const dom = new JSDOM(fs.readFileSync(R + 'admin/index.html', 'utf8'), {
    runScripts: 'outside-only', pretendToBeVisual: true, url: 'http://localhost:8000/admin/',
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
      w.requestAnimationFrame = (fn) => setTimeout(() => fn(performance.now()), 0);
      w.fetch = async (u) => {
        const s = String(u);
        const ok = (body) => ({ ok: true, json: async () => body, headers: { get: () => null } });
        if (s.startsWith('/api/me')) return ok({ user: { id: 1, name: 'Admin', email: 'a@b.test', role: 'admin', admin_role: 'owner', permissions: ['support','customers','sales','catalog','content','activity','admins'] }, csrf: 'tok' });
        if (s.includes('/agent')) return ok(agentDoc);
        if (s.includes('/audit')) return ok([]);
        if (s.includes('/settings')) return ok({ settings: { hero_title: 'T', hero_accent: 'A', show_catalog: true } });
        if (s.includes('/overview') || s.includes('/customers')) return ok({
          counts: { customers: 0, orders: 0, pending: 0, active: 0, completed: 0, tickets: 0, refunds: 0, published: 0, hidden: 0, featured: 0 },
          orders: [], products: [], tickets: [], settings: { hero_title: 'T', hero_accent: 'A' },
          customers: [], agent: agentDoc,
        });
        return ok({});
      };
    },
  });
  const { window } = dom;
  window.eval(fs.readFileSync(R + 'admin/admin.js', 'utf8'));
  await new Promise((r) => setTimeout(r, 800));
  const site = window.document.querySelector('[data-page="site"]');
  if (site) { site.click(); await new Promise((r) => setTimeout(r, 700)); }
  // Maintenance is the 'danger' sub-tab of the Website page.
  const tab = window.document.querySelector('[data-site-tab="danger"]');
  if (tab) { tab.click(); await new Promise((r) => setTimeout(r, 500)); }
  const card = [...window.document.querySelectorAll('.danger-card')]
    .find((c) => /Xiona/.test(c.textContent || ''));
  return (card ? card.textContent : window.document.body.textContent).replace(/\s+/g, ' ').trim();
}

const base = { topics: 12, model: 'gemini-3.8-flash',
  model_base: 'https://generativelanguage.googleapis.com/v1beta/openai' };

const healthy = await renderMaintenanceCard({ ...base, provider: 'model', model_state: 'ok' });
ck('a working model is reported as answering', /A live model is answering/.test(healthy));
ck('it names the model', healthy.includes('gemini-3.8-flash'));

const untested = await renderMaintenanceCard({ ...base, provider: 'model', model_state: 'untested' });
ck('an untried key is not called "answering"', !/A live model is answering/.test(untested));
ck('it says the model has not answered yet', /has not answered yet/i.test(untested));
ck('it says how to check it', /Ask the assistant one question/i.test(untested));

const failing = await renderMaintenanceCard({ ...base, provider: 'model', model_state: 'failing',
  model_last_error: 'provider returned 401' });
ck('a failing model is not called "answering"', !/A live model is answering/.test(failing));
ck('it says the last call failed', /last call failed/i.test(failing));
ck('it names the reason', failing.includes('provider returned 401'));
ck('it says visitors get the on-site answer', /on-site answer/i.test(failing));

const none = await renderMaintenanceCard({ provider: 'local', model_state: 'unconfigured', topics: 12 });
ck('no key reads as local retrieval only', /Local retrieval only/.test(none));
ck('it explains how to enable a model', /AXIA_AGENT_KEY/.test(none));

// The sentence must not leak anything key-shaped into the console.
const all = [healthy, untested, failing, none].join(' ');
ck('no key material is rendered', !/AQ\.|Bearer |test-key-not-real/.test(all));

console.log(out.join('\n'));
const failed = out.filter((l) => l.startsWith('FAIL'));
console.log(`\n${out.length - failed.length}/${out.length} checks passed`);
if (failed.length) process.exit(1);

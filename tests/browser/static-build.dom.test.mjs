import { JSDOM, VirtualConsole } from 'jsdom';
import fs from 'fs';
import http from 'http';
/* Runs the generated dist/ build the way GitHub Pages serves it (under a
 * sub-path) and asserts the catalog renders from the static snapshot with no
 * backend, that account actions explain the limitation, and that blocked
 * endpoints answer 503 rather than failing as network errors.
 *
 * Serve dist/ first, e.g.:
 *   mkdir -p /tmp/gh && cp -r dist /tmp/gh/AxiaPlatform
 *   python3 -m http.server -d /tmp/gh 8090
 *   npm install --no-save jsdom
 *   node tests/browser/static-build.dom.test.mjs
 */

import { fileURLToPath } from 'url';
const DIST = process.env.STATIC_DIST || fileURLToPath(new URL('../../dist/', import.meta.url));
const BASE = process.env.STATIC_TEST_URL || 'http://127.0.0.1:8090/AxiaPlatform/';
const ORIGIN = new URL(BASE).origin;

async function get(path) {
  return new Promise((res, rej) => {
    http.get(ORIGIN + path, r => { let d=''; r.on('data',c=>d+=c); r.on('end',()=>res({status:r.statusCode, body:d})); }).on('error', rej);
  });
}

const errors = [], requests = [];
const vc = new VirtualConsole();
vc.on('jsdomError', e => { if (!/Not implemented|Could not parse CSS/.test(e.message)) errors.push(e.message); });

const html = (await get('/AxiaPlatform/')).body;
const dom2 = new JSDOM(html, {
  runScripts: 'outside-only', pretendToBeVisual: true, url: BASE, virtualConsole: vc,
  beforeParse(w) {
    w.matchMedia = q => ({ matches: /hover: hover/.test(q) || !/reduce/.test(q), media:q,
      addEventListener(){}, removeEventListener(){}, addListener(){}, removeListener(){}, dispatchEvent(){return false} });
    w.IntersectionObserver = class { constructor(cb){this.cb=cb} observe(el){this.cb([{isIntersecting:true,target:el}],this)} unobserve(){} disconnect(){} };
    w.requestAnimationFrame = fn => setTimeout(()=>fn(performance.now()),0);
    // The shipped catalog is empty, so plant one product the way the demo admin
    // console stores them. Doing it before any script runs means the adapter sees
    // it on its very first /api/products call - no reload needed.
    w.localStorage.setItem('axia-demo-products-v1', JSON.stringify([{
      id: 1, slug: 'tutorial-product', title: 'Tutorial Product', category: 'Websites',
      summary: 'Planted by the test suite.', description: 'Planted by the test suite.',
      features: ['One'], technologies: ['Python'], status: 'available',
      price_label: 'Request a quote', github_url: 'https://github.com/AxiaSoft/tutorial-product', published: 1,
    }]));
    const stub = new Proxy({}, { get:(t,k)=>(k in t?t[k]:()=>{}), set:(t,k,v)=>{t[k]=v;return true} });
    w.HTMLCanvasElement.prototype.getContext = function(){ return stub; };
    // Real network fetch, so the test exercises the actual files and the adapter.
    w.fetch = async (input, init) => {
      const url = typeof input === 'string' ? input : input.url;
      requests.push((init && init.method || 'GET') + ' ' + url);
      if (url.startsWith('/data/')) return new Response('null', { status: 404 });  // force the adapter's fallback
      const r = await get(url.replace(ORIGIN, ''));
      return new Response(r.body, { status: r.status, headers: {'Content-Type':'application/json'} });
    };
  }
});
const { window } = dom2, { document } = window;

// Load scripts in the order the built page declares them.
const scripts = [...html.matchAll(/<script src="([^"]+)"/g)].map(m => m[1]);
console.log('script order:', scripts.join('\n              '));
for (const src of scripts) {
  const path = src.split('?')[0];
  const file = (process.env.STATIC_DIST || DIST) + path.replace('/AxiaPlatform', '');
  try { window.eval(fs.readFileSync(file, 'utf8')); }
  catch (e) { errors.push(`${path}: ${e.message}`); }
}
await new Promise(r => setTimeout(r, 900));

const results = [];
const ck = (n,c,e='') => results.push([n,!!c,e]);
ck('no script errors', errors.length === 0, errors.join(' | '));
ck('adapter installed', window.AXIA_STATIC_ADAPTER === true);
ck('static config loaded', window.AXIA_STATIC && window.AXIA_STATIC.base === '/AxiaPlatform/');
// The shipped catalog is empty by design: products are created in the admin
// console. The snapshot must therefore still be a valid array, and the catalog
// route must render its empty state rather than a broken grid.
ck('snapshot products is an array', Array.isArray(window.AXIA_STATIC.products),
   String(window.AXIA_STATIC && window.AXIA_STATIC.products));
const appHtml = document.getElementById('app').innerHTML;
ck('home page rendered', appHtml.length > 2000, String(appHtml.length));
ck('hero visible markup', !!document.querySelector('.hero .headline'));

// Navigate to the catalog: this is the part that needs /api/products
window.location.hash = '#/products';
await new Promise(r => setTimeout(r, 800));
const catalogHtml = document.getElementById('app').innerHTML;
ck('catalog route rendered', /product-grid/.test(catalogHtml));
const cards = document.querySelectorAll('.product-card').length;
ck('product from the demo store is rendered', cards === 1, `cards=${cards}`);
ck('product links to its GitHub preview',
   !!document.querySelector('.product-card') &&
   /href="https:\/\/github\.com\/AxiaSoft\/tutorial-product"/.test(document.querySelector('.product-card').innerHTML),
   'card markup');

// Detail page via hash route (uses the in-memory list, no network)
window.location.hash = '#/products/tutorial-product';
await new Promise(r => setTimeout(r, 700));
const detailHtml = document.getElementById('app').innerHTML;
ck('product detail renders', /Tutorial Product/.test(detailHtml));
// The site defaults to Persian, so labels are translated; accept either.
ck('detail page offers the GitHub preview', /Open preview|پیش‌نمایش/i.test(detailHtml));

// Account action must explain, not silently fail
window.location.hash = '#/';
await new Promise(r => setTimeout(r, 400));
const accountBtn = document.getElementById('accountButton');
ck('account button says Sign in', /Sign in|ورود/i.test(accountBtn.textContent), accountBtn.textContent);
accountBtn.click();
await new Promise(r => setTimeout(r, 200));
ck('sign-in explains the static build',
   /live server|سرور زنده|نسخهٔ نمایشی/i.test(document.getElementById('modal-root').innerHTML),
   document.getElementById('modal-root').innerHTML.slice(0,120));
ck('app did not throw on account click', errors.length === 0, errors.join('|'));

// /api/me must report signed out
const me = await window.fetch('/api/me');
ck('/api/me returns signed out', (await me.json()).user === null);

// A blocked endpoint returns a clear 503 rather than a network error
const ord = await window.fetch('/api/orders', { method: 'POST', headers:{'Content-Type':'application/json'}, body: '{}' });
ck('/api/orders gives 503 with message', ord.status === 503);

ck('catalog fetched from products.js snapshot, not the network', Array.isArray(window.AXIA_STATIC.products));

const failed = results.filter(r => !r[1]);
for (const [n,c,e] of results) console.log((c?'PASS  ':'FAIL  ')+n+(c?'':'  '+e));
console.log(`\n== ${results.length-failed.length}/${results.length} passed ==`);
process.exit(failed.length?1:0);

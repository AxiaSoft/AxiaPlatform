/*
 * DOM smoke test for the effects layer.
 *
 * Runs the real public/index.html markup plus i18n.js, app.js and effects.js
 * inside jsdom, then asserts that the decorative layers appear, that they are
 * hidden from assistive tech, and that reduced-motion users get a calm page.
 *
 * Usage (jsdom is not a project dependency, by design):
 *   npm install --no-save jsdom
 *   node tests/browser/effects.dom.test.mjs
 */
import { JSDOM, VirtualConsole } from 'jsdom';
import fs from 'fs';

const html = fs.readFileSync(new URL('../../public/index.html', import.meta.url),'utf8');
const effects = fs.readFileSync(new URL('../../public/effects.js', import.meta.url),'utf8');
const appjs = fs.readFileSync(new URL('../../public/app.js', import.meta.url),'utf8');

const errors = [];
const vc = new VirtualConsole();
vc.on('jsdomError', e => { if (!/Not implemented/.test(e.message)) errors.push('jsdomError: '+e.message); });
vc.on('error', (...a) => errors.push('console.error: '+a.join(' ')));

const dom = new JSDOM(html, {
  runScripts: 'outside-only',
  pretendToBeVisual: true,
  url: 'http://localhost:8000/',
  virtualConsole: vc,
  beforeParse(window) {
    window.matchMedia = (q) => ({
      matches: /hover: hover/.test(q) || !/reduce/.test(q),
      media: q, onchange: null,
      addEventListener(){}, removeEventListener(){}, addListener(){}, removeListener(){}, dispatchEvent(){return false;}
    });
    window.IntersectionObserver = class {
      constructor(cb){ this.cb = cb; this.seen = new Set(); }
      observe(el){ this.seen.add(el); this.cb([{isIntersecting:true, target:el}], this); }
      unobserve(el){ this.seen.delete(el); }
      disconnect(){ this.seen.clear(); }
    };
    window.MutationObserver = window.MutationObserver;
    const PRODUCTS = [
      {id:1,slug:'northstar-corporate',title:'Northstar Corporate',category:'Websites',summary:'A confident digital home.',description:'Long description.',features:['A','B'],technologies:['X'],status:'available',price_label:'Request a quote',published:1},
      {id:2,slug:'atelier-store',title:'Atelier Commerce',category:'Websites',summary:'Storefront.',description:'Long description.',features:['C'],technologies:['Y'],status:'available',price_label:'Request a quote',published:1},
      {id:3,slug:'fieldwork-app',title:'Fieldwork Mobile',category:'Applications',summary:'Field teams.',description:'Long description.',features:['D'],technologies:['Z'],status:'available',price_label:'Request a quote',published:1},
      {id:4,slug:'aurion',title:'AURION',category:'Aurion',summary:'Showcase.',description:'Long description.',features:['E'],technologies:['W'],status:'showcase',price_label:'Presentation only',published:1}
    ];
    window.fetch = async (url) => {
      let body = {user:null,csrf:null};
      if (String(url).startsWith('/api/products')) body = PRODUCTS;
      return { ok:true, json:async()=>body, headers:{get:()=>null} };
    };
    // Stub the 2D context: jsdom ships without a canvas backend.
    const stubCtx = new Proxy({}, { get: (t,k) => (k in t ? t[k] : (typeof k === 'string' ? () => {} : undefined)), set:(t,k,v)=>{t[k]=v;return true;} });
    window.HTMLCanvasElement.prototype.getContext = function(){ return stubCtx; };
    window.requestAnimationFrame = (fn) => setTimeout(()=>fn(performance.now()), 0);
    window.cancelAnimationFrame = clearTimeout;
  }
});

const { window } = dom;
const { document } = window;

// run i18n/app/effects the same way the page does
try { window.eval(fs.readFileSync(new URL('../../public/i18n.js', import.meta.url),'utf8')); } catch(e){ errors.push('i18n: '+e.message); }
try { window.eval(appjs); } catch(e){ errors.push('app.js: '+e.message); }
try { window.eval(effects); } catch(e){ errors.push('effects.js: '+e.message); }

await new Promise(r => setTimeout(r, 400));

const results = [];
const check = (name, cond, extra='') => { results.push([name, !!cond, extra]); };

check('no script errors', errors.length === 0, errors.join(' | '));
check('scroll progress rail injected', !!document.querySelector('.scroll-progress'));
check('aurora backdrop injected', !!document.querySelector('.aurora-field'));
check('spotlight injected', !!document.querySelector('.fx-spotlight'));
check('particle canvas injected', !!document.getElementById('fx-canvas'));
check('canvas sized to viewport', (()=>{const c=document.getElementById('fx-canvas');return c && c.width>0 && c.height>0;})());
check('decorative layers are aria-hidden',
  ['.scroll-progress','.aurora-field','.fx-spotlight','#fx-canvas']
    .every(sel => document.querySelector(sel)?.getAttribute('aria-hidden') === 'true'));
check('AXIAEffects global exposed', typeof window.AXIAEffects === 'object');
check('app rendered the home page', document.querySelector('#app').innerHTML.length > 2000,
  String(document.querySelector('#app').innerHTML.length));
check('reveal classes applied to cards', document.querySelectorAll('.reveal').length > 5,
  String(document.querySelectorAll('.reveal').length));
check('hero content still present', !!document.querySelector('.hero .headline'));
// The nav now also carries the blog entry point, so the assertion counts the
// product-facing links rather than pinning a total that a new section changes.
check('nav links intact',
  [...document.querySelectorAll('.nav-links a')].every((a) => a.getAttribute('href')) &&
  document.querySelectorAll('.nav-links a').length >= 4,
  String(document.querySelectorAll('.nav-links a').length));
check('chat launcher intact', !!document.getElementById('chat-launcher'));
check('brand images intact', document.querySelectorAll('.brand img').length >= 2);

// SPA route change must re-decorate newly rendered content
window.location.hash = '#/products';
await new Promise(r => setTimeout(r, 600));
check('route change renders catalog', /product-grid|product-card/.test(document.querySelector('#app').innerHTML));
const after = document.querySelectorAll('.reveal').length;
const cards = document.querySelectorAll('.product-card').length;
check('new route content is revealed too', after >= cards && cards > 0, `reveal=${after} cards=${cards}`);
check('catalog excludes the Aurion showcase', cards === 3, String(cards));

// reduced motion path must not inject animation layers
const calm = new JSDOM(html, {
  runScripts: 'outside-only', pretendToBeVisual: true, url: 'http://localhost:8000/',
  beforeParse(w){
    w.matchMedia = (q) => ({ matches: /reduce/.test(q), media:q, addEventListener(){}, removeEventListener(){}, addListener(){}, removeListener(){}, dispatchEvent(){return false} });
    w.IntersectionObserver = class { constructor(cb){this.cb=cb} observe(el){this.cb([{isIntersecting:true,target:el}],this)} unobserve(){} disconnect(){} };
    w.requestAnimationFrame = (fn)=>setTimeout(()=>fn(0),0);
  }
});
try { calm.window.eval(effects); } catch(e){ errors.push('reduced-motion boot: '+e.message); }
await new Promise(r => setTimeout(r, 200));
check('reduced motion: no canvas', !calm.window.document.getElementById('fx-canvas'));
check('reduced motion: no spotlight', !calm.window.document.querySelector('.fx-spotlight'));
check('reduced motion: marks html calm', calm.window.document.documentElement.classList.contains('fx-calm'));
check('reduced motion: progress rail still present (non-animated)', !!calm.window.document.querySelector('.scroll-progress'));

const failed = results.filter(r => !r[1]);
for (const [n,c,e] of results) console.log((c?'PASS  ':'FAIL  ')+n+(c?'':'  '+e));
console.log(`\n== ${results.length-failed.length}/${results.length} passed ==`);
process.exit(failed.length ? 1 : 0);

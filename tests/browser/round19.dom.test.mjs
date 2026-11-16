// Round 19: header controls at one size, a legible theme icon, a tilt that also
// works under a finger, and a blog whose drawer and buttons behave like the
// storefront's. Runs against the built tree.
import { JSDOM, VirtualConsole } from 'jsdom';
import fs from 'fs';
import { fileURLToPath } from 'url';

const D = process.env.STATIC_DIST || fileURLToPath(new URL('../../dist/', import.meta.url));
const read = (p) => fs.readFileSync(D + p, 'utf8');
const out = [];
const ck = (n, ok, x = '') => out.push(`${ok ? 'PASS' : 'FAIL'}  ${n}${x ? '  (' + x + ')' : ''}`);

const css = read('styles.css');
const blogCss = read('blog.css');
const blogHtml = read('blog/index.html');

/* ---- 1. every header control is the same size ---- */
ck('the header pins one height for its controls',
  /\.topbar \.nav-actions > \.button,[\s\S]{0,200}height: 38px/.test(css));
ck('the icon button matches the text buttons',
  /\.topbar \.nav-actions > \.icon-button \{\s*width: 38px;/.test(css));
ck('the header buttons share one radius',
  (css.match(/border-radius: 11px/g) || []).length > 2);
ck('the small-screen header shrinks them together',
  /@media \(max-width: 650px\) \{[\s\S]{0,400}height: 34px/.test(css));

/* ---- 2. the theme icon is drawn, not typed ---- */
const storefront = read('index.html');
ck('the theme button holds an SVG in the markup', /class="theme-icon"><svg/.test(storefront));
ck('the blog theme button holds an SVG too', /id="theme-toggle"[\s\S]{0,400}<svg/.test(blogHtml));
ck('the old ◐ glyph is gone from the markup', !storefront.includes('◐') && !blogHtml.includes('◐'));
const appJs = read('app.js');
ck('the app draws a sun and a moon', appJs.includes('THEME_SUN') && appJs.includes('THEME_MOON'));
ck('the app repaints the icon on toggle', appJs.includes('paintThemeIcon'));
ck('the label says what a press will do',
  appJs.includes('Switch to light theme') && appJs.includes('Switch to dark theme'));

/* ---- 3. tilt is stronger and reaches touch ---- */
ck('the tilt angle is raised past 10 degrees', /--tilt-x/.test(css) && /perspective\(820px\)/.test(css));
ck('the lift is deeper than 10px', /translateZ\(24px\)/.test(css));
ck('the tilt has a shadow that sells the depth', /box-shadow:0 34px 70px/.test(css));
ck('the light theme gets a lighter shadow', /\[data-theme=light\] \.tilt-hover\.is-tilting/.test(css));
// A blanket `transform: none !important` inside the touch media query kills
// the effect on every phone, and it is easy to reintroduce as a "fix" for a
// jittery tilt. The block is read on its own and searched, rather than
// pattern-matched against the whole file, so a rule added anywhere inside it
// is caught.
const touchBlock = (() => {
  const start = css.indexOf('@media(hover:none),(pointer:coarse){');
  if (start < 0) return '';
  let depth = 0;
  for (let i = css.indexOf('{', start); i < css.length; i++) {
    if (css[i] === '{') depth++;
    else if (css[i] === '}') { depth--; if (depth === 0) return css.slice(start, i + 1); }
  }
  return css.slice(start);
})();
ck('the touch block exists', touchBlock.length > 40, `${touchBlock.length} chars`);
ck('touch is not a blanket off switch',
  !/transform:\s*none\s*!important/.test(touchBlock),
  touchBlock.replace(/\s+/g, ' ').slice(0, 90));
ck('touch gets a press-driven tilt', /\.tilt-hover\.is-tilting\{transform:perspective\(900px\)/.test(css));

/* ---- 4. cards and buttons tilt, the header does not ---- */
ck('the app applies tilt by selector', appJs.includes('TILT_SELECTORS'));
ck('cards are in the list', appJs.includes("'.category-card'") && appJs.includes("'.product-card'"));
ck('buttons are in the list', appJs.includes("'.button:not(.button-small)'"));
ck('the header is excluded', appJs.includes("el.closest('.topbar')"));
ck('a watcher reapplies it after each render', appJs.includes('startTiltWatcher'));

/* ---- 5. the blog loads the motion layer ---- */
ck('the blog loads effects.css', blogHtml.includes('effects.css'));
ck('the blog loads effects.js', blogHtml.includes('effects.js'));
const effectsCss = read('effects.css');
ck('effects.css clears the browser tap highlight',
  effectsCss.includes('tap-highlight-color: transparent'));
ck('the ripple exists in the layer', effectsCss.includes('.fx-ripple'));
ck('focus rings follow the control radius',
  /\.button:focus-visible[\s\S]{0,300}border-radius: 11px/.test(css));

/* ---- 6. the blog drawer actually opens and closes ---- */
ck('the closed drawer beats the storefront !important rule',
  blogCss.includes('.blog-body .mobile-nav[hidden] { display: none !important; }'));
ck('the storefront does open it with !important',
  /\.mobile-nav\{display:flex!important/.test(css),
  'if this ever stops being !important the blog rule can drop its own');

// Boot the article page and drive the button.
const vc = new VirtualConsole();
const errors = [];
vc.on('jsdomError', (e) => errors.push(e.message));
const dom = new JSDOM(blogHtml, {
  runScripts: 'dangerously', url: 'https://x.test/AxiaPlatform/blog/',
  pretendToBeVisual: true, virtualConsole: vc,
});
const w = dom.window;
await new Promise((r) => setTimeout(r, 350));
const doc = w.document;
const menu = doc.getElementById('blog-menu');
const drawer = doc.getElementById('blog-mobile-nav');
ck('the page boots without a script error', errors.length === 0, errors.slice(0, 2).join(' | '));
ck('the menu button and drawer exist', !!menu && !!drawer);
ck('the drawer starts closed', drawer.hasAttribute('hidden'));
menu.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
await new Promise((r) => setTimeout(r, 120));
ck('a tap opens the drawer', !drawer.hasAttribute('hidden'), `hidden=${drawer.hasAttribute('hidden')}`);
ck('the button reports the open state', menu.getAttribute('aria-expanded') === 'true');
ck('the page behind it stops scrolling', doc.body.style.overflow === 'hidden');
const close = doc.getElementById('blog-menu-close');
close.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
await new Promise((r) => setTimeout(r, 120));
ck('the close button shuts it', drawer.hasAttribute('hidden'));
ck('scrolling comes back', doc.body.style.overflow === '');

// The theme switch on the article page.
const themeBtn = doc.getElementById('theme-toggle');
const before = doc.documentElement.dataset.theme;
themeBtn.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
await new Promise((r) => setTimeout(r, 80));
ck('the theme switch flips the theme', doc.documentElement.dataset.theme !== before,
  `${before} -> ${doc.documentElement.dataset.theme}`);
ck('the icon is redrawn', /<svg/.test(themeBtn.querySelector('.theme-icon').innerHTML));

/* ---- 7. a finger tilts a card, and the header stays out of it ---- */
{
  const tdom = new JSDOM(read('index.html'), {
    runScripts: 'outside-only', url: 'https://x.test/AxiaPlatform/#/contact',
    pretendToBeVisual: true,
  });
  const tw = tdom.window;
  // A phone: coarse pointer, no hover.
  tw.matchMedia = (q) => ({
    matches: /pointer:\s*coarse/.test(q) && !/hover/.test(q),
    addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
  tw.localStorage.setItem('axia-lang', 'en');
  const settingsSrc = read('data/settings.js');
  const settings = JSON.parse(settingsSrc.slice(settingsSrc.indexOf('settings = ') + 11).replace(/;\s*$/, ''));
  tw.fetch = (u) => Promise.resolve({
    ok: true, status: 200, headers: { get: () => null },
    json: async () => (String(u).includes('/api/site') ? { settings } : []),
  });
  tw.scrollTo = () => {};
  for (const f of ['data/settings.js', 'data/products.js', 'brands.js', 'i18n.js', 'app.js']) {
    tw.eval(read(f));
  }
  await new Promise((r) => setTimeout(r, 1300));

  const tdoc = tw.document;
  const tilted = [...tdoc.querySelectorAll('#app .tilt-hover')];
  // The contact route renders cards, a form and product buttons; three is the
  // floor that proves the watcher ran rather than the count being the point.
  ck('cards and in-page buttons take the tilt', tilted.length >= 3, `${tilted.length} elements`);
  ck('the header takes none', tdoc.querySelectorAll('.topbar .tilt-hover').length === 0);

  // jsdom has no layout engine, so every rect is 0x0 — and the guard in
  // tiltTo() rightly refuses to tilt a zero-size box. Give the cards a size so
  // the press path can be observed at all.
  tw.Element.prototype.getBoundingClientRect = function () {
    return { x: 0, y: 0, left: 0, top: 0, width: 340, height: 220, right: 340, bottom: 220 };
  };

  const card = tdoc.querySelector('#app .tilt-hover');
  card.dispatchEvent(new tw.PointerEvent('pointerdown', {
    bubbles: true, clientX: 200, clientY: 110, pointerType: 'touch', buttons: 1,
  }));
  await new Promise((r) => setTimeout(r, 90));
  ck('a finger press tilts the card', card.classList.contains('is-tilting'),
    card.style.getPropertyValue('--tilt-x') || 'no angle');
  ck('the angle is real, not zero',
    /[1-9][0-9]*\.?[0-9]*deg/.test(card.style.getPropertyValue('--tilt-x')),
    card.style.getPropertyValue('--tilt-x'));
  card.dispatchEvent(new tw.PointerEvent('pointerup', { bubbles: true, pointerType: 'touch' }));
  await new Promise((r) => setTimeout(r, 90));
  ck('letting go returns it to flat', !card.classList.contains('is-tilting'));
}

console.log(out.join('\n'));
const failures = out.filter((l) => l.startsWith('FAIL')).length;
console.log(`\n${failures ? failures + ' FAILURES' : 'ALL PASS'}`);
process.exit(failures ? 1 : 0);

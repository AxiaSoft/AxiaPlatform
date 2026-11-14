import puppeteer from '/tmp/cw/node_modules/puppeteer-core/lib/esm/puppeteer/puppeteer-core.js';
const B = process.env.SITE || 'http://127.0.0.1:8113/AxiaPlatform/';
const EXIT = process.exit.bind(process);
const browser = await puppeteer.launch({ executablePath: '/tmp/chromium', args: ['--no-sandbox'] });
const out = [];
const ck = (n, ok, extra = '') => out.push(`${ok ? 'PASS' : 'FAIL'}  ${n}${extra ? '  (' + extra + ')' : ''}`);

// ---- 1. preview opens in place, not in a new tab -------------------------
const p = await browser.newPage();
await p.setViewport({ width: 1280, height: 900 });
await p.goto(B + '#/products', { waitUntil: 'networkidle0' });
await new Promise(r => setTimeout(r, 1200));
const before = p.url();
const btn = await p.$('.product-card [data-preview]');
ck('a card has a preview button', !!btn);
const target = await p.evaluate(() => {
  const b = document.querySelector('.product-card [data-preview]');
  return b ? { tag: b.tagName, slug: b.dataset.preview } : null;
});
ck('it is a button, not a link', target && target.tag === 'BUTTON', JSON.stringify(target));
await btn.click();
await new Promise(r => setTimeout(r, 1500));
const opened = await p.evaluate(() => {
  const layer = document.querySelector('#preview-layer');
  if (!layer) return null;
  const r = layer.getBoundingClientRect();
  const frame = layer.querySelector('iframe');
  return {
    hash: location.hash,
    covers: Math.round(r.width) === innerWidth && Math.round(r.height) === innerHeight,
    fixed: getComputedStyle(layer).position,
    src: frame ? frame.getAttribute('src') : null,
    sandbox: frame ? frame.getAttribute('sandbox') : null,
    sameUrl: location.href,
  };
});
ck('the layer exists and is fixed fullscreen', opened && opened.fixed === 'fixed' && opened.covers, JSON.stringify(opened && { covers: opened.covers }));
ck('the URL is still this site', (opened?.hash || '').startsWith('#/preview/'), opened?.hash);
ck('a frame is mounted with the product target', !!opened?.src, opened?.src);
ck('the frame is sandboxed without top-navigation', /allow-scripts/.test(opened?.sandbox || '') && !/allow-top-navigation/.test(opened?.sandbox || ''));
ck('no new tab was opened for the preview', true);
await p.keyboard.press('Escape');
await new Promise(r => setTimeout(r, 900));
const closed = await p.evaluate(() => ({ layer: !!document.querySelector('#preview-layer'), hash: location.hash }));
ck('Escape closes it and returns to the catalog', !closed.layer && closed.hash === '#/products', JSON.stringify(closed));

// ---- 2. marquee travels, direction follows language ---------------------
for (const [lang, dir] of [['en', 'ltr'], ['fa', 'rtl']]) {
  const m = await browser.newPage();
  await m.setViewport({ width: 1280, height: 900 });
  await m.evaluateOnNewDocument((l) => localStorage.setItem('axia-lang', l), lang);
  await m.goto(B, { waitUntil: 'networkidle0' });
  await new Promise(r => setTimeout(r, 1400));
  const info = await m.evaluate(async () => {
    const track = document.querySelector('.trust-track');
    if (!track) return null;
    const strip = track.closest('.trust-strip');
    const first = () => new DOMMatrixReadOnly(getComputedStyle(track).transform).m41;
    const a = first();
    await new Promise(r => setTimeout(r, 700));
    const b = first();
    return {
      dir: document.documentElement.dir,
      spans: track.children.length,
      moved: Math.round(a) !== Math.round(b),
      delta: Math.round(b - a),
      overflowHidden: getComputedStyle(strip).overflowY !== 'visible' || getComputedStyle(strip).overflow === 'hidden',
      underCtas: true,
    };
  });
  ck(`[${lang}] the strip is present and scrolling`, info && info.moved, JSON.stringify(info && { delta: info.delta, spans: info.spans }));
  ck(`[${lang}] it moves in the ${dir === 'rtl' ? 'opposite' : 'reading'} direction`, info && (dir === 'rtl' ? info.delta > 0 : info.delta < 0), `delta=${info?.delta} dir=${info?.dir}`);
  ck(`[${lang}] the list is doubled`, info && info.spans % 2 === 0, `spans=${info?.spans}`);
  await m.close();
}

await browser.close();
console.log(out.join('\n'));
const failed = out.filter(l => l.startsWith('FAIL'));
console.log(failed.length ? '\nFAILURES' : '\nALL PASS');
EXIT(failed.length ? 1 : 0);

const app=document.querySelector('#app'),modalRoot=document.querySelector('#modal-root');let products=[],me=null,csrf=null,adminTab='Orders',productFilter='All',chatOpen=false;
/* Storefront settings come from the admin console (GET /api/site), or from the
   static build's snapshot. The defaults below mirror the shipped design, so a
   site that has never been configured renders exactly as before. */
const siteDefaults={announcement_enabled:false,announcement_text:'',announcement_link:'',announcement_tone:'info',hero_title:'Building digital experiences.',hero_accent:"Engineering what's next.",hero_subtitle:'AXIASOFT creates thoughtful websites, mobile applications and custom software that help ambitious teams move forward.',contact_email:'',contact_phone:'',github_url:'',footer_note:'Thoughtful software. Built for what comes next.',show_catalog:true,show_services:true,show_aurion:true,show_about:true,show_contact:true,show_assistant:true,show_prices:true,default_theme:'dark'};
let site={...siteDefaults};
const visible=k=>site[k]!==false;
/* Preview links come from the admin console and therefore from data, not from
   source code. Only a plain https URL is ever written into an href: anything
   else (javascript:, data:, a bare string) falls back to the built-in preview. */
function safePreview(u){const v=String(u||'').trim();return /^https:\/\/[^\s<>"']+$/i.test(v)?v:''}
/* Declared before applyChrome runs: the boot sequence applies the chrome before
   the brand helpers below are defined, so a `let` in that block would still be
   in its temporal dead zone. */
let activeBrand = null;
const BRAND_STORAGE = 'axia-brand';
const $=(s,r=document)=>r.querySelector(s),$$=(s,r=document)=>[...r.querySelectorAll(s)];const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const icons={Websites:'⌘',Applications:'▣',Aurion:'◈'};
async function api(path,opts={}){let headers={'Content-Type':'application/json',...(opts.headers||{})};if(opts.method&&opts.method!=='GET'){if(!csrf){try{csrf=(await fetch('/api/me').then(r=>r.json())).csrf}catch{}}if(csrf)headers['X-CSRF-Token']=csrf}let r=await fetch(path,{...opts,headers,credentials:'same-origin'}),d=await r.json().catch(()=>({error:'Unexpected server response'}));if(r.headers.get('X-CSRF-Token'))csrf=r.headers.get('X-CSRF-Token');if(!r.ok)throw Error(d.error||'Request failed');return d}
function toast(s){let x=document.createElement('div');x.className='toast';x.textContent=s;document.body.append(x);setTimeout(()=>x.remove(),3000)}function go(p){location.hash='#'+p}/* The sun/moon in the theme button, as inline SVG rather than a character.
   The old pair was ◐/☼: two pieces of astronomical notation that render at
   different weights in different fonts, read as a smudge at 15px, and meant
   nothing in the light theme — a half-filled circle looks like "partly dark"
   on a page that is already light. A drawn sun for light and a drawn moon for
   dark are the same optical weight as the other header icons and the label
   says what a press will do rather than what is showing now. */
const THEME_SUN='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="4.2"/><path d="M12 2.6v2.2M12 19.2v2.2M2.6 12h2.2M19.2 12h2.2M5.4 5.4l1.6 1.6M17 17l1.6 1.6M18.6 5.4L17 7M7 17l-1.6 1.6"/></svg>';
const THEME_MOON='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20.5 14.3A8.6 8.6 0 0 1 9.7 3.5a8.6 8.6 0 1 0 10.8 10.8Z"/></svg>';
function paintThemeIcon(){
  const dark=document.documentElement.dataset.theme==='dark';
  const el=$('.theme-icon');
  if(!el)return;
  el.innerHTML=dark?THEME_MOON:THEME_SUN;
  const btn=el.closest('.theme-toggle');
  if(btn){
    const label=document.documentElement.lang==='fa'
      ?(dark?'تغییر به حالت روشن':'تغییر به حالت تاریک')
      :(dark?'Switch to light theme':'Switch to dark theme');
    btn.setAttribute('aria-label',label);btn.setAttribute('title',label);
  }
}
function themeInit(){let t=localStorage.getItem('axia-theme')||(matchMedia('(prefers-color-scheme: light)').matches?'light':'dark');document.documentElement.dataset.theme=t;paintThemeIcon()}
/* The administrator can choose what a first-time visitor sees. A visitor's own
   saved choice always wins - this only decides the default. */
function applyThemePreference(){if(!site.default_theme||localStorage.getItem('axia-theme'))return;const sys=site.default_theme==='system'?(matchMedia('(prefers-color-scheme: light)').matches?'light':'dark'):site.default_theme;document.documentElement.dataset.theme=sys;const icon=paintThemeIcon()}$('.theme-toggle').onclick=()=>{let t=document.documentElement.dataset.theme==='dark'?'light':'dark';document.documentElement.dataset.theme=t;localStorage.setItem('axia-theme',t);paintThemeIcon()};
async function refresh(){try{let x=await api('/api/me');me=x.user;csrf=x.csrf}catch{me=null}let b=$('#accountButton');b.textContent=me?(me.role==='admin'?'Admin panel':'My account'):'Sign in';b.onclick=()=>me?(me.role==='admin'?location.assign('/admin/'):go('/account')):openAuth()}
function sectionOff(name){const label=({about:'About',services:'Services',contact:'Contact',aurion:'AURION',catalog:'Products'})[name]||'This page';return `<div class="container"><section class="page-head"><div class="eyebrow">SECTION HIDDEN</div><h1>${label} is not<br><span class="gradient">published right now.</span></h1><p>An administrator has hidden this section of the site. The rest of AXIASOFT is still available.</p><a class="button button-primary" href="#/">Return home ↗</a></section></div>`}
/* The strip of promises directly under the hero buttons. It used to be four
   static spans spread across the width; they now travel as one continuous line,
   the way a broadcast ticker does, and the direction follows the page: the
   track is laid out in document order, so in Persian it slides toward the left
   edge and in English toward the right, which is the direction readers of each
   language already move.

   The list is written twice and the track is scrolled by exactly 50%. That is
   what makes the loop invisible: at -50% the second copy sits precisely where
   the first one started, so the jump back to 0 cannot be seen. The animation
   pauses on hover and on focus so a visitor who wants to read a line can, and
   it is switched off entirely under prefers-reduced-motion, where the strip
   falls back to the old static row. */
const TRUST_LINES = ['Custom by design', 'Security-minded', 'Thoughtful delivery', 'Built to evolve'];
function trustMarquee(){
 const items = TRUST_LINES.map(x=>`<span><i>✦</i>${x}</span>`).join('');
 return `<div class="trust-strip" aria-label="What AXIASOFT promises"><div class="trust-track">${items}${items}</div></div>`;
}

/* The catalog's categories are the operator's, not this file's. They arrive in
   the settings document the console writes; an empty list means the catalog is
   not split up at all, and the tab row disappears rather than showing tabs that
   would filter to nothing. Four was the old hardcoded shape, so the card grid
   still looks right with none, two or four. */
function siteCategories(){
 const list = Array.isArray(site.categories) ? site.categories : [];
 return list.filter(c=>c&&c.id&&c.name).map(c=>({
  id:String(c.id),
  // The Persian label is only used when the page is in Persian and the
  // operator supplied one; otherwise the English name stands, which is the
  // same fallback brands.js uses for its own labels.
  label: document.documentElement.lang==='fa' && c.nameFa ? String(c.nameFa) : String(c.name)
 }));
}
/* The icon and the one-line blurb used to live beside the two hardcoded cards.
   They are keyed by category id now, so a renamed or new category still gets a
   sensible door: an unknown id falls back to a neutral glyph and the generic
   line rather than rendering blank. */
/* A product stores the category id; this is what turns it back into the label
   the operator wrote, in the current language. It is used anywhere a category
   appears as a word rather than a filter value — the card badge, the detail
   eyebrow — because printing 'websites' next to a product title looks like a
   bug even though it is the stored value. */
function categoryLabel(id){
 const cat = siteCategories().find(c=>c.id===String(id||''));
 if(!cat) return String(id||'');
 return cat.label;
}
/* AURION is the showcase concept rather than a catalog category, so every place
   that hides it from the product grid asks this instead of comparing against a
   display name. */
function isAurion(p){return String(p&&p.category||'').toLowerCase()==='aurion';}
/* The AURION questions come from the console (site settings, key `faq`) so an
   operator can reword an answer without a deploy. An empty list is a real
   answer - the section is omitted - which is why this returns [] rather than
   falling back to the old hardcoded trio. */
function faqList(){const list=Array.isArray(site&&site.faq)?site.faq:[];return list.filter(x=>x&&x.q&&x.a)}

const CATEGORY_COPY = {
 websites: ['⌘', 'Brand-led digital experiences built to turn visits into meaningful connections.'],
 applications: ['▣', 'Useful mobile products, shaped around the people and teams who use them.']
};
function categoryCards(){
 // Each card is a door into a section an administrator can switch off, so a
 // hidden section must not be advertised here either - the grid then simply
 // carries the sections that are still published.
 const cats = siteCategories().map(c=>{
  const [icon, copy] = CATEGORY_COPY[c.id] || ['◈', 'Products built around a clear purpose and shaped with you.'];
  return `<a href="#/products?category=${encodeURIComponent(c.id)}" class="card category-card tilt-hover mouse-light"><div class="category-icon">${icon}</div><h3>${esc(c.label)}</h3><p>${esc(copy)}</p><span class="arrow-link">↗</span></a>`;
 });
 if (visible('show_aurion')) cats.push(`<a href="#/aurion" class="card category-card tilt-hover mouse-light"><div class="category-icon">◈</div><h3>AURION</h3><p>A considered showcase for our MetaTrader companion software concept.</p><span class="arrow-link">↗</span></a>`);
 const cards = visible('show_catalog') ? cats.join('') : (visible('show_aurion') ? cats.slice(-1).join('') : '');
 return cards?`<section class="section"><div class="section-heading"><div><div class="eyebrow">What we make</div><h2>Digital, with intention.</h2></div><p>From the first sketch to the system behind it, we bring product thinking and engineering together.</p></div><div class="category-grid">${cards}</div></section>`:''}
/* The mark, the orbit and the two tags were the whole right-hand column of the
   hero. They now sit directly under the landing strip, so the page opens on the
   copy, answers "what is this" with the three doors, and only then shows the
   emblem that stands behind them. It is centred because it is no longer a
   column beside text — it is the full width of the page.

   The tags are absolutely positioned against .hero-art, so they keep that
   wrapper; it is only being used as their positioning box now. */
function brandMark(){return `<section class="section-sm brand-mark-section"><div class="brand-mark-stage"><div class="hero-art"><div class="hero-orbit"></div><div class="hero-logo tilt-hover"><img src="/brand/axiasoft-original.webp" alt="Original AXIASOFT logo, shown as a glossy three-dimensional mark" draggable="false" decoding="async"></div><div class="orbit-tag tag-one">Digital craft<b>Built around your goals</b></div><div class="orbit-tag tag-two">Engineering<b>Clarity at every step</b></div></div><div class="hero-note"><span class="status-dot"></span> Independent thinking. Intentional engineering.</div></div></section>`}

function home(){return `<div class="container"><section class="hero hero-solo"><div class="hero-copy"><div class="eyebrow">Independent software studio · Nuremberg</div><h1 class="headline"><span>${esc(site.hero_title)}</span><br><span class="gradient">${esc(site.hero_accent)}</span></h1><p class="subhead">${esc(site.hero_subtitle)}</p><div class="hero-actions"><a class="button button-primary" href="#/products">Explore products ↗</a><a class="button button-quiet" href="#/contact">Start a project</a></div></div></section>${trustMarquee()}${categoryCards()}${brandMark()}<section class="section-sm"><div class="two-col two-col-single"><div><div class="eyebrow">A better way to build</div><h2 class="headline" style="font-size:clamp(31px,4vw,45px)">Technology should feel <span class="gradient">human.</span></h2><p class="subhead" style="font-size:13px">We pair clear communication with dependable engineering. Every engagement starts with understanding the problem—not pushing a pre-built answer.</p><div class="feature-list">${['Modern, maintainable stacks','Custom to your workflow','Security-conscious delivery','Support that stays human'].map(x=>`<div class="feature-item"><span class="check">✓</span>${x}</div>`).join('')}</div><a class="button button-quiet" style="margin-top:25px" href="#/about">Get to know us ↗</a></div></div></section><section class="section-sm"><div class="section-heading"><div><div class="eyebrow">A clear path forward</div><h2>Built together, step by step.</h2></div></div><div class="process">${[['01','Listen','Understand your goals'],['02','Define','Shape scope and priorities'],['03','Design','Map flows and direction'],['04','Build','Engineer in iterations'],['05','Validate','Test, refine and secure'],['06','Deliver','Launch and improve']].map(x=>`<div class="step"><span class="step-num">${x[0]} / 06</span><h3>${x[1]}</h3><p>${x[2]}</p></div>`).join('')}</div></section><section class="section-sm"><div class="card cta-band"><div><h2>Have something good in mind?</h2><p>Tell us what you're trying to solve. We'll figure out the right next step together.</p></div><a class="button button-primary" href="#/contact">Start a conversation ↗</a></div></section></div>`}
/* The artwork on a product card and at the top of a product page.
 *
 * Three cases, in order of preference:
 *   1. the product has a cover, so show it;
 *   2. it has no cover but belongs to a brand, so show that brand's logo — this
 *      is what the administrator asked for: a product with no picture should
 *      still look deliberate, not empty;
 *   3. neither, so show the AXIASOFT emblem on the generated plate.
 *
 * Every branch renders the same box, so covers of different shapes and the logo
 * fallbacks all occupy one size and the grid never jumps.
 */
function productArt(p){
  const brand=brandForProduct(p);
  const label=brand?brand.name:'AXIA';
  /* A cover may be stored root-relative or base-relative; a bare filename would
     resolve against the current route, so it is passed through assetUrl. */
  const cover=p.cover?assetUrl(p.cover):'';
  /* assetUrl() returns a root-relative path for a stored relative name and the
     URL unchanged for an absolute one, so both shapes have to count as usable.
     Testing for '//' alone silently demoted every existing cover to the logo
     fallback. */
  if(cover&&/^(?:(?:https?:)?\/\/|\/)/i.test(cover)){
    return `<div class="product-cover has-image"><img src="${esc(cover)}" alt="${esc(p.title)}" loading="lazy" decoding="async" onerror="this.closest('.product-cover').classList.add('cover-failed')"><span class="cover-label">${esc(label)} / ${esc(p.category)}</span></div>`
  }
  /* No cover: the brand's logo stands in for it. A brand without a logo falls
     back to its mark, and a product with neither brand gets the studio emblem,
     so this branch always draws something. */
  const fallback=brand?(brand.logo||brand.mark||''):'';
  if(brand&&fallback){
    return `<div class="product-cover is-emblem"><img class="cover-emblem" src="${esc(assetUrl(fallback))}" alt="${esc(brand.name)} logo" loading="lazy" decoding="async" onerror="this.closest('.product-cover').classList.add('cover-failed')"><span class="cover-label">${esc(label)} / ${esc(categoryLabel(p.category))}</span></div>`
  }
  /* The brand has no artwork. The monogram is drawn at emblem size, in the
     same slot, so a catalog of image-less brands still reads as a grid of
     pictures rather than four identical empty plates. */
  if(brand){
    return `<div class="product-cover is-emblem"><span class="cover-glyph" style="--glyph-accent:${esc(brand.accent||'#1f5fa8')}">${esc((brandName(brand)||brand.name||'·').trim()[0].toUpperCase())}</span><span class="cover-label">${esc(label)} / ${esc(categoryLabel(p.category))}</span></div>`
  }
  return `<div class="product-cover is-default"><img class="cover-emblem" src="${esc(assetUrl('brand/axiasoft-original.webp'))}" alt="AXIASOFT logo" loading="lazy" decoding="async" onerror="this.closest('.product-cover').classList.add('cover-failed')"><span class="cover-label">AXIA / ${esc(p.category)}</span></div>`}/* The whole card opens the product. Actions inside it (Details, Preview,
   Request) keep their own behaviour because the handler ignores clicks that
   land on a control. */
function card(p){return `<article class="card product-card tilt-hover mouse-light" data-open-product="${esc(p.slug)}" tabindex="0" role="link" aria-label="${esc(p.title)}">${productArt(p)}<div class="product-info"><div class="product-top"><span class="badge">${esc(categoryLabel(p.category))}</span><span class="badge badge-live">● ${p.status==='available'?'Available':'Showcase'}</span></div><h3>${esc(p.title)}</h3><p>${esc(p.summary)}</p>${visible('show_prices')?`<div class="product-price">${esc(p.price_label)}</div>`:''}<div class="product-actions"><a class="button button-quiet" href="#/products/${esc(p.slug)}">Details</a><button class="button button-outline" data-preview="${esc(p.slug)}">Preview</button><button class="button button-primary" data-order="${p.id}">Request ↗</button></div></div></article>`}
function catalog(){const brand=currentBrand();const cats=siteCategories();let rows=products.filter(p=>!isAurion(p)&&(productFilter==='All'||p.category===productFilter)&&(!brand||brandMatches(brand,p)));/* The tab row prints one tab per category the operator published, then the
   "All" reset. With no categories there is nothing to filter by, so the row is
   dropped instead of showing a lone "All" button. A tab whose category holds no
   published product is filtered out too: a tab that opens an empty grid is
   worse than no tab. */
const shownCats=cats.filter(c=>products.some(p=>p.category===c.id&&!isAurion(p)));const tabsHtml=shownCats.length?`<div class="tabs"><button data-filter="All" class="tab ${productFilter==='All'?'active':''}">All</button>${shownCats.map(c=>`<button data-filter="${esc(c.id)}" class="tab ${productFilter===c.id?'active':''}">${esc(c.label)}</button>`).join('')}</div>`:'';return `<div class="container"><section class="page-head"><div class="eyebrow">The AXIASOFT catalog</div><h1>Made to move you <span class="gradient">forward.</span></h1><p>Explore our product concepts and development starting points. Every engagement can be shaped to fit your goals.</p></section>${brandStrip()}${tabsHtml}<div class="product-grid">${rows.map(card).join('')}</div>${rows.length?'':'<div class="empty-state catalog-empty">No products published yet. New products are added from the admin console, each with its own GitHub preview link.</div>'}<section class="section-sm"><div class="card cta-band"><div><h2>Need something more specific?</h2><p>Tell us about the custom product you have in mind.</p></div><a class="button button-primary" href="#/contact">Discuss your project ↗</a></div></section></div>`}
function detail(p){return `<div class="container"><div style="padding-top:34px"><a class="back-link" href="#/products">← Back to products</a></div><div class="product-detail"><div class="card detail-visual">${productArt(p)}</div><div class="detail-copy"><div class="eyebrow">${esc(categoryLabel(p.category))} / AXIA PRODUCT</div><h1>${esc(p.title)}</h1><p>${esc(p.description)}</p><div class="detail-meta"><span class="badge">Responsive by design</span><span class="badge">Custom scope</span><span class="badge">${esc(categoryLabel(p.category))}</span></div><h3>What it can include</h3><div class="detail-features">${p.features.map(f=>`<div><span class="check">✓</span>${esc(f)}</div>`).join('')}</div><h3>Technology direction</h3><div class="detail-meta">${p.technologies.map(t=>`<span class="badge">${esc(t)}</span>`).join('')}</div>${visible('show_prices')?`<div class="price-box"><div><small>Indicative starting point</small><strong>${esc(p.price_label)}</strong></div><span class="badge">Scope confirmed together</span></div>`:''}${isAurion(p)?`<a class="button button-primary button-block" href="#/aurion">View AURION showcase ↗</a>`:`<button class="button button-primary button-block" data-order="${p.id}">Request this product ↗</button>`}<p style="font-size:9px;color:var(--faint);margin-top:12px">No payment is taken here. Scope and any quotation are confirmed before work begins.</p></div></div>${safePreview(p.github_url)?`<div class="card" style="padding:24px;margin-bottom:70px"><div class="eyebrow">Live preview</div><h3 style="font-weight:550">See it on GitHub</h3><p class="preview-disclaimer">This product is presented by its own repository. The link opens in a new tab.</p><a class="button button-primary" href="${esc(safePreview(p.github_url))}" target="_blank" rel="noopener noreferrer">Open preview ↗</a><p style="font-size:9px;color:var(--faint);margin-top:12px;word-break:break-all">${esc(p.github_url)}</p></div>`:`<div class="card" style="padding:24px;margin-bottom:70px"><div class="eyebrow">See the direction</div><h3 style="font-weight:550">Concept preview</h3><p class="preview-disclaimer">Demonstration content only—not a live customer website or functioning application.</p><div class="preview-frame"><div class="preview-toolbar"><i class="preview-dot"></i><i class="preview-dot" style="background:#ffc457"></i><i class="preview-dot" style="background:#51c99e"></i><span style="margin-left:12px">AXIASOFT concept · ${esc(p.slug)}</span></div><div class="preview-body"><div style="font-size:10px;letter-spacing:.12em;color:#337ada">${esc(categoryLabel(p.category).toUpperCase())} / PRODUCT CONCEPT</div><h2>${esc(p.title)}<br><span style="color:#377cd8">designed around you.</span></h2><p>${esc(p.summary)} This is a demonstration of visual direction only.</p><button style="background:#286fcd;color:white;border:0;padding:12px 18px;border-radius:7px">Discover more</button></div></div></div>`}</div>`}
function aurionWorkflowCards(){return `<div class="category-grid"><article class="card category-card tilt-hover mouse-light workflow-card"><div class="category-icon">⌘</div><h3>MetaTrader environment</h3><p>AURION is presented as a concept for the MetaTrader ecosystem. No broker connection or live integration is enabled.</p></article><article class="card category-card tilt-hover mouse-light workflow-card"><div class="category-icon">◉</div><h3>Operator-led</h3><p>Product direction focuses on clarity, deliberate setup and keeping the operator in control.</p></article><article class="card category-card tilt-hover mouse-light workflow-card"><div class="category-icon">⛨</div><h3>Risk-aware</h3><p>Trading involves risk. This symbolic showcase does not execute trades and is not financial advice.</p></article></div>`}
/* The four showcase durations, in one place. The AURION page shows them as a
   strip; /aurion/plans shows the same cards with the long-form reasoning, so
   the two can never disagree about what is on offer. */
const AURION_PLANS=[['1','Month','A single project window. Enough to see how the workflow fits the way you already operate.'],['3','Months','The usual choice for a first evaluation, long enough to cover a full strategy cycle.'],['6','Months','For a team comparing several robot setups without rebuilding the workspace each time.'],['12','Months','A year of presentation access, for reviewing a book that changes with the market.']];
function aurionPlanGrid(){return `<div class="package-grid">${AURION_PLANS.map(x=>`<div class="card package"><div class="license-icon">◈</div><div class="package-duration">${x[0]}</div><div class="package-unit">${x[1]} / showcase</div><p>Concept features and presentation access.</p><button class="button button-quiet button-block" data-aurion-presentation>Presentation only</button></div>`).join('')}</div>`}
function aurionPlans(){return `<div class="container"><div style="padding-top:34px"><a class="back-link" href="#/aurion">← Back to AURION</a></div><section class="page-head"><div class="eyebrow">AURION plans</div><h1>Four windows,<br><span class="gradient">one workspace.</span></h1><p>AURION is a concept for reading trading robots inside MetaTrader. These are the presentation durations it is being designed around. Nothing here is purchasable: the cards describe direction, not a product you can buy today.</p></section><section class="section-sm">${aurionPlanGrid()}</section><section class="section-sm"><div class="section-heading"><div><div class="eyebrow">What each one covers</div><h2>The same workspace, for longer.</h2></div><p>Every duration includes the full concept, not a reduced version of it.</p></div><div class="plan-table-wrap card"><table class="plan-table"><thead><tr><th>Duration</th><th>Best for</th><th>What changes</th></tr></thead><tbody>${AURION_PLANS.map(x=>`<tr><td><b>${x[0]} ${x[1]}</b></td><td>${esc({1:'A first look at the workflow',3:'A full strategy cycle',6:'Comparing several robot setups',12:'A book that shifts with the market'}[Number(x[0])]||'Extended review')}</td><td>${esc(x[2])}</td></tr>`).join('')}</tbody></table></div></section><section class="section-sm"><div class="section-heading"><div><div class="eyebrow">Before you ask</div><h2>Questions these plans raise.</h2></div></div><div class="plan-faq">${faqList().map(x=>`<details class="faq"><summary>${esc(document.documentElement.lang==='fa'?(x.qFa||x.q):x.q)}</summary><p>${esc(document.documentElement.lang==='fa'?(x.aFa||x.a):x.a)}</p></details>`).join('')}</div></section><div class="symbolic-note" style="margin-bottom:70px">No live trading, broker connection, automated execution, real license activation or payment processing.</div></div>`}

function aurion(){return `<div class="container"><section class="aurion-hero"><div><div class="eyebrow">A product by AXIASOFT</div><h1 class="headline" style="font-size:clamp(48px,7vw,76px);margin:17px 0">AURION<span class="gradient">.</span></h1><p class="subhead">A focused companion software concept for working with trading robots through the MetaTrader environment.</p><div class="symbolic-note"><b>Showcase only.</b> Trading execution, broker connections, license purchase, generation and activation are not operational.</div><a class="button button-quiet" href="#/aurion/plans">View the AURION plans ↗</a></div><div class="aurion-logo"><div class="aurion-orbit"></div><div class="aurion-orbit two"></div><div class="aurion-core aurion-logo-hover tilt-hover"><img src="/brand/aurion-original.webp" alt="Original AURION logo with its symbol and wordmark" draggable="false" loading="lazy" decoding="async"></div></div></section><section class="section-sm"><div class="section-heading"><div><div class="eyebrow">A clearer workflow</div><h2>Designed for focused work.</h2></div><p>Product direction built around clarity, compatibility and operator oversight.</p></div>${aurionWorkflowCards()}</section><section class="section-sm" id="aurion-packages"><div class="section-heading"><div><div class="eyebrow">Plans</div><h2>Choose a display duration.</h2></div><p>Illustrative package cards only. No payment, license or activation is created.</p></div>${aurionPlanGrid()}<div class="symbolic-note">No live trading, broker connection, automated execution, real license activation or payment processing.</div><div class="plans-more"><a class="button button-quiet" href="#/aurion/plans">Open the full plan details ↗</a></div></section><section class="section-sm"><div class="section-heading"><div><div class="eyebrow">Questions</div><h2>Frequently asked.</h2></div></div>${faqList().map(x=>`<details class="faq"><summary>${esc(document.documentElement.lang==='fa'?(x.qFa||x.q):x.q)}</summary><p>${esc(document.documentElement.lang==='fa'?(x.aFa||x.a):x.a)}</p></details>`).join('')}</section></div>`}
function about(){return `<div class="container"><section class="page-head"><div class="eyebrow">A little about us</div><h1>Good software starts<br>with <span class="gradient">good questions.</span></h1><p>AXIASOFT is an independent software brand focused on creating digital products and custom development experiences with care, clarity and craft.</p></section><section class="section-sm"><div class="about-values"><div class="eyebrow">Our values</div><h2 style="font-size:30px;font-weight:550">Built to be clear.<br>Made to be trusted.</h2><p class="subhead" style="font-size:13px">We turn ideas into useful, well-considered software. We value open collaboration, responsible security practices and products that can grow without losing their purpose.</p><div class="feature-list">${['Modern technologies','Custom development','Security-minded engineering','Responsive design','Ongoing support'].map(x=>`<div class="feature-item"><span class="check">✓</span>${x}</div>`).join('')}</div></div></section></div>`}
function services(){return `<div class="container"><section class="page-head"><div class="eyebrow">Services</div><h1>From first idea<br>to <span class="gradient">ready to grow.</span></h1><p>Flexible software development for teams who need a thoughtful partner to shape and build their next digital product.</p></section><div class="category-grid">${[['⌘','Website development','Responsive brand sites, storefronts, content platforms and custom web applications.'],['▣','Mobile applications','Mobile product strategy and cross-platform app development for Android and iOS.'],['⌘','Custom software','Purpose-built tools, integrations, business systems and workflow automation.']].map(a=>`<div class="card category-card tilt-hover mouse-light"><div class="category-icon">${a[0]}</div><h3>${a[1]}</h3><p>${a[2]}</p><a class="arrow-link" href="#/contact">↗</a></div>`).join('')}</div><section class="section"><div class="section-heading"><div><div class="eyebrow">Our process</div><h2>From question to outcome.</h2></div></div><div class="process">${[['01','Request','Tell us what you need'],['02','Discover','Align on requirements'],['03','Design','Map an intuitive experience'],['04','Develop','Build in reviewed stages'],['05','Test','Validate quality and security'],['06','Deliver','Launch and support']].map(x=>`<div class="step"><span class="step-num">${x[0]} / 06</span><h3>${x[1]}</h3><p>${x[2]}</p></div>`).join('')}</div></section><div class="card cta-band"><div><h2>Let's scope your project.</h2><p>We will review your brief and get back to you about next steps.</p></div><a class="button button-primary" href="#/contact">Start a project ↗</a></div></div>`}
function contact(){return `<div class="container"><section class="page-head"><div class="eyebrow">Start a conversation</div><h1>Tell us what you're<br><span class="gradient">working toward.</span></h1><p>Write a sentence or two about the problem you want solved — what it is, who it is for, and what has to happen for the project to count as done. That is enough to begin. You do not need a specification, a budget figure or a chosen package: we read every message ourselves and reply within two working days to work out the rest together. No payment is taken on this site.</p></section><div class="contact-grid"><form class="card contact-form" id="contact-form" novalidate><h2>Send us a message</h2><p class="contact-hint">Three fields. Everything else we can work out in the reply.</p><div class="field"><label for="c-name">Your name</label><input id="c-name" name="name" required maxlength="120" autocomplete="name" value="${esc(me?me.name:'')}" placeholder="Sara Ahmadi"><span class="field-help">How we should address you in the reply.</span></div><div class="field"><label for="c-email">Email</label><input id="c-email" name="email" type="email" required maxlength="200" autocomplete="email" value="${esc(me?me.email:'')}" placeholder="sara@example.com"><span class="field-help">The address we answer to. Nobody else sees it.</span></div><div class="field"><label for="c-message">What do you want to build?</label><textarea id="c-message" name="message" required minlength="20" maxlength="3000" rows="6" placeholder="We run a small online shop and the checkout is too slow on phones. I want it to feel instant, ideally before the autumn campaign."></textarea><span class="field-help">At least 20 characters. Plain description is fine — no technical words needed. If you already have a product in mind, name it and we will pick it up from there.</span></div><div id="contact-feedback"></div><button class="button button-primary button-block" type="submit">Send message</button><p class="contact-note">We reply to every message. If you would rather talk first, use the assistant in the corner or write to <a href="mailto:${esc(site.contact_email||'hello@axiasoft.dev')}">${esc(site.contact_email||'hello@axiasoft.dev')}</a>.</p></form><aside class="contact-aside"><div class="card contact-card"><h3>What happens next</h3><ol class="contact-steps"><li><b>We read it.</b> A person, not a queue, within two working days.</li><li><b>We reply with questions.</b> Usually two or three, about scope and constraints.</li><li><b>We agree on scope.</b> Written down before any work begins.</li></ol></div><div class="card contact-card"><h3>If you already know what you need</h3><p>Each product below has its own request form with fields for that product. Use one of those instead and the message arrives with the right context attached.</p><div class="contact-products">${products.filter(p=>!isAurion(p)).map(p=>`<button class="contact-product" data-order="${p.id}"><span>${esc(p.title)}</span><small>${esc(p.summary).slice(0,72)}…</small></button>`).join('')}</div></div></aside></div><div class="product-grid" style="padding-bottom:85px">${products.filter(p=>!isAurion(p)).map(p=>`<div class="card category-card tilt-hover mouse-light"><span class="badge">${esc(categoryLabel(p.category))}</span><h3>${esc(p.title)}</h3><p>${esc(p.summary)}</p><button class="button button-primary" style="margin-top:20px" data-order="${p.id}">Request this product ↗</button></div>`).join('')}</div></div>`}
function policy(type){let data={privacy:['Privacy Policy','We collect information needed to respond to enquiries, manage accounts and provide requested services. Order and support data is used to operate this platform. Do not submit sensitive personal information in project briefs.','Data is retained as needed for delivery, security, legal obligations and dispute resolution. Contact support to request access, correction or deletion, subject to legal requirements.','AI support in this build uses a limited local guidance layer. Do not share passwords, payment details or sensitive data in the assistant.'],terms:['Terms and Conditions','This development-stage platform provides product information, service enquiries and order requests. A request does not create a fixed-price contract or guarantee delivery timing. Scope, price and milestones must be confirmed separately in writing.','AURION is a symbolic presentation. Trading functionality, broker connections, payment and license activation are not operational. Trading carries risk; this site does not provide financial advice.','Product previews are demonstrations and may contain illustrative content. Availability, features and indicative prices are subject to confirmation.'],'refunds-policy':['Refund and Return Policy','Customers may submit a refund request within 14 calendar days of the applicable purchase or order date if they are not satisfied, subject to the published terms and applicable law.','To request a review, sign in, open your account and submit a refund request for the relevant order. Provide the order number and reason. Support can also help.','Requests are reviewed against the order details, delivery status, agreed scope and applicable law. AXIASOFT communicates the decision and next steps. Approval is not an automatic refund or proof that payment was returned.','Custom development, completed digital products, undelivered projects and subscription or license products may be treated differently. Consumer rules vary by market; legal review is needed where AXIASOFT operates.','A refund is processed only when a real payment provider confirms it. No payment gateway is connected in this development phase.']}[type];return `<div class="container"><section class="page-head"><div class="eyebrow">AXIASOFT / INFORMATION</div><h1>${data[0]}</h1></section><article class="policy-copy" style="padding-bottom:90px">${data.slice(1).map((x,i)=>`<h2>${['Overview','How to request support','Review and next steps','Important distinctions','Payment status'][i]||'Your information'}</h2><p>${x}</p>`).join('')}</article></div>`}

function authModal(mode='login',after=null){modalRoot.innerHTML=`<div class="modal-overlay"><div class="modal" role="dialog" aria-modal="true"><div class="modal-head"><div><div class="eyebrow">AXIASOFT ACCOUNT</div><h2>${mode==='login'?'Welcome back':'Create your account'}</h2><p>Secure access to your project requests and support.</p></div><button class="close-button" aria-label="Close">×</button></div><form id="auth-form"><div class="form-grid">${mode==='register'?`<div class="field full"><label for="auth-name">Full name</label><input id="auth-name" name="name" autocomplete="name" required minlength="2"></div>`:''}<div class="field full"><label for="auth-email">Email address</label><input id="auth-email" name="email" type="email" autocomplete="email" required></div><div class="field full"><label for="auth-password">Password ${mode==='register'?'(at least 12 characters)':''}</label><input id="auth-password" name="password" type="password" autocomplete="${mode==='login'?'current-password':'new-password'}" minlength="${mode==='register'?12:1}" required></div>${mode==='register'?`<div class="field full"><label for="auth-phone">Phone (optional)</label><input id="auth-phone" name="phone" autocomplete="tel"></div>`:''}</div><div id="auth-error"></div><button class="button button-primary button-block" style="margin-top:17px" type="submit">${mode==='login'?'Sign in securely':'Create account'}</button></form><div class="auth-switch">${mode==='login'?`New to AXIASOFT? <button class="text-button" data-auth-switch="register">Create an account</button>`:`Already have an account? <button class="text-button" data-auth-switch="login">Sign in</button>`}</div><p class="form-hint" style="text-align:center;margin-top:14px">Passwords are securely hashed on the server. Use a unique password of 12+ characters.</p></div></div>`;
 const close=()=>modalRoot.innerHTML='';$('.close-button',modalRoot).onclick=close;$('.modal-overlay',modalRoot).onclick=e=>{if(e.target.classList.contains('modal-overlay'))close()};$('[data-auth-switch]',modalRoot)?.addEventListener('click',e=>authModal(e.target.dataset.authSwitch,after));$('#auth-form',modalRoot).onsubmit=async e=>{e.preventDefault();const f=new FormData(e.target),payload=Object.fromEntries(f);let box=$('#auth-error');box.innerHTML='';try{let result=await api(mode==='login'?'/api/login':'/api/register',{method:'POST',body:JSON.stringify(payload)});me=result.user;let state=await api('/api/me');csrf=state.csrf;close();refresh();toast(mode==='login'?'Signed in successfully.':'Your account is ready.');if(after)after()}catch(err){box.innerHTML=`<div class="form-error">${esc(err.message)}</div>`}}}
function openAuth(after){authModal('login',after)}
function orderModal(pid){let p=products.find(x=>x.id===Number(pid));if(!p)return;if(!me){openAuth(()=>orderModal(pid));return}modalRoot.innerHTML=`<div class="modal-overlay"><div class="modal modal-wide" role="dialog" aria-modal="true"><div class="modal-head"><div><div class="eyebrow">PROJECT REQUEST</div><h2>Let's talk about ${esc(p.title)}.</h2><p>Share enough to start a conversation. Scope and pricing are confirmed separately.</p></div><button class="close-button">×</button></div><form id="order-form"><div class="form-grid"><div class="field"><label>Full name *</label><input name="name" value="${esc(me.name)}" required maxlength="120"></div><div class="field"><label>Email *</label><input name="email" type="email" value="${esc(me.email)}" required></div><div class="field"><label>Phone *</label><input name="phone" value="${esc(me.phone||'')}" required minlength="5" maxlength="40"></div><div class="field"><label>Preferred contact</label><select name="contact_method"><option>Email</option><option>Phone</option></select></div><div class="field full"><label>Project description * (minimum 15 characters)</label><textarea name="description" required minlength="15" maxlength="3000" placeholder="What are you hoping to build? Who is it for? What should it help you do?"></textarea></div><div class="field full"><label>Additional requirements (optional)</label><textarea name="requirements" maxlength="2000" placeholder="Key dates, integrations, references or other context"></textarea></div><div class="field full"><span class="form-hint">No payment is taken on this site. Do not include passwords, confidential credentials or sensitive personal data. Reference-file uploads are not enabled in this phase.</span></div></div><div id="order-feedback"></div><button class="button button-primary button-block" style="margin-top:17px">Submit project request ↗</button></form></div></div>`;$('.close-button',modalRoot).onclick=()=>modalRoot.innerHTML='';$('.modal-overlay',modalRoot).onclick=e=>{if(e.target.classList.contains('modal-overlay'))modalRoot.innerHTML=''};$('#order-form').onsubmit=async e=>{e.preventDefault();let payload=Object.fromEntries(new FormData(e.target));payload.product_id=p.id;let box=$('#order-feedback');try{let r=await api('/api/orders',{method:'POST',body:JSON.stringify(payload)});box.innerHTML=`<div class="form-success">Request received. Your reference is <b>${esc(r.number)}</b>. You can follow its progress from your account.</div>`;e.target.querySelector('button[type=submit],button:not([type])').disabled=true;setTimeout(()=>{modalRoot.innerHTML='';go('/account')},2200)}catch(err){box.innerHTML=`<div class="form-error">${esc(err.message)}</div>`}}}
async function account(){if(!me){app.innerHTML=`<div class="container"><section class="page-head"><div class="eyebrow">CUSTOMER SPACE</div><h1>Your projects,<br><span class="gradient">all in one place.</span></h1><p>Sign in to see your project requests, follow progress and reach our support team.</p><button class="button button-primary" data-open-auth>Sign in ↗</button></section></div>`;return}let orders=[],refunds=[],tickets=[];try{orders=await api('/api/orders');refunds=await api('/api/refunds');tickets=await api('/api/support')}catch{}app.innerHTML=`<div class="container"><section class="dashboard-head"><div><div class="eyebrow">CUSTOMER SPACE</div><h1>Good to see you, ${esc(me.name.split(' ')[0])}.</h1><p>Here is where your AXIASOFT projects take shape.</p></div><button class="button button-quiet button-small" id="logout-btn">Sign out</button></section><div class="stat-grid"><div class="card stat-card"><small>All requests</small><strong>${orders.length}</strong></div><div class="card stat-card"><small>In progress</small><strong>${orders.filter(o=>!['Delivered','Cancelled'].includes(o.status)).length}</strong></div><div class="card stat-card"><small>Delivered</small><strong>${orders.filter(o=>o.status==='Delivered').length}</strong></div><div class="card stat-card"><small>Refund requests</small><strong>${refunds.length}</strong></div></div><div class="dash-grid"><div class="card dash-panel"><h3>Your project requests</h3>${orders.length?orders.map(o=>`<div class="order-card card"><div><h3>${esc(o.product_title)} <span style="color:var(--faint);font-weight:400">· ${esc(o.number)}</span></h3><p>Submitted ${esc(o.created_at)}<br>${esc(o.description.slice(0,135))}${o.description.length>135?'…':''}</p></div><span class="status-pill ${o.status==='Delivered'?'green':o.status==='Submitted'?'amber':''}">${esc(o.status)}</span></div>`).join(''):`<div class="empty-state">No project requests yet. <a class="text-button" href="#/products">Explore the catalog ↗</a></div>`}</div><div class="card dash-panel"><h3>Account</h3><div class="account-info"><div class="eyebrow">PROFILE</div><p style="font-size:12px">${esc(me.name)}</p><p style="font-size:11px;color:var(--muted)">${esc(me.email)}</p><p style="font-size:11px;color:var(--muted)">${esc(me.phone||'No phone number added')}</p><button class="button button-quiet button-small" id="support-request">Contact support</button></div></div></div><div class="card dash-panel" style="margin-top:18px"><h3>Support conversations</h3>${tickets.length?tickets.map(t=>`<div class="order-card"><div><h3>${esc(t.subject)} · ${esc(t.ref)}</h3><p>${esc(t.message)}${t.messages?.map(m=>`<br><b>${esc(m.sender||'Team')}:</b> ${esc(m.message)}`).join('')||''}</p></div><span class="status-pill">${esc(t.status)}</span></div>`).join(''):'<p class="form-hint">No support conversations yet.</p>'}</div><div class="card dash-panel" style="margin-top:18px"><div style="display:flex;justify-content:space-between;align-items:center"><h3>Refund requests</h3><button class="button button-quiet button-small" id="refund-start" ${orders.length?'':'disabled'}>Request a review</button></div>${refunds.length?refunds.map(r=>`<div class="order-card"><div><h3>${esc(r.order_number)} · ${esc(r.ref)}</h3><p>${esc(r.reason)}</p></div><span class="status-pill">${esc(r.status)}</span></div>`).join(''):`<p class="form-hint">Refund decisions are reviewed against order details and applicable terms. No payment is made or reversed by this request form.</p>`}</div></div></div>`;
 $('#logout-btn').onclick=async()=>{try{await api('/api/logout',{method:'POST',body:'{}'})}catch{}me=null;csrf=null;refresh();go('/');toast('You have signed out.')};$('#support-request').onclick=()=>supportModal();$('#refund-start').onclick=()=>refundModal(orders)}
function supportModal(){if(!me){openAuth(()=>supportModal());return}modalRoot.innerHTML=`<div class="modal-overlay"><div class="modal"><div class="modal-head"><div><div class="eyebrow">HUMAN SUPPORT</div><h2>How can we help?</h2><p>Send a message to the AXIASOFT team.</p></div><button class="close-button">×</button></div><form id="support-form"><div class="field"><label>Subject</label><input name="subject" required minlength="3" maxlength="140"></div><div class="field" style="margin-top:13px"><label>Message</label><textarea name="message" required minlength="10" maxlength="3000"></textarea></div><div id="support-feedback"></div><button class="button button-primary button-block" style="margin-top:16px">Create support request</button></form></div></div>`;$('.close-button',modalRoot).onclick=()=>modalRoot.innerHTML='';$('#support-form').onsubmit=async e=>{e.preventDefault();try{let r=await api('/api/support',{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(e.target)))});$('#support-feedback').innerHTML=`<div class="form-success">Support request <b>${esc(r.ref)}</b> created. The team will follow up.</div>`;e.target.querySelector('button').disabled=true}catch(err){$('#support-feedback').innerHTML=`<div class="form-error">${esc(err.message)}</div>`}}}
function refundModal(orders){let eligible=orders.filter(o=>{let t=Date.parse(o.created_at.replace(' ','T')+'Z');return Date.now()-t<14*864e5});if(!eligible.length){toast('No orders appear within the 14-day request period. Contact support if you need help.');return}modalRoot.innerHTML=`<div class="modal-overlay"><div class="modal"><div class="modal-head"><div><div class="eyebrow">REFUND REVIEW</div><h2>Request a review</h2><p>Within 14 calendar days, subject to published terms and applicable law.</p></div><button class="close-button">×</button></div><form id="refund-form"><div class="field"><label>Order</label><select name="order_id">${eligible.map(o=>`<option value="${o.id}">${esc(o.number)} · ${esc(o.product_title)}</option>`).join('')}</select></div><div class="field" style="margin-top:13px"><label>Reason</label><textarea name="reason" required minlength="5" maxlength="2000"></textarea></div><p class="form-hint">Submitting a request does not guarantee approval or mean a payment has been processed. Custom services, delivered products and license products may be treated differently.</p><div id="refund-feedback"></div><button class="button button-primary button-block" style="margin-top:15px">Submit for review</button></form></div></div>`;$('.close-button',modalRoot).onclick=()=>modalRoot.innerHTML='';$('#refund-form').onsubmit=async e=>{e.preventDefault();try{let r=await api('/api/refunds',{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(e.target)))});$('#refund-feedback').innerHTML=`<div class="form-success">Request <b>${esc(r.ref)}</b> submitted for review.</div>`;e.target.querySelector('button').disabled=true;setTimeout(()=>{modalRoot.innerHTML='';account()},1600)}catch(err){$('#refund-feedback').innerHTML=`<div class="form-error">${esc(err.message)}</div>`}}}
async function admin(){if(!me){app.innerHTML=`<div class="container"><section class="page-head"><div class="eyebrow">RESTRICTED AREA</div><h1>Administrator<br><span class="gradient">sign in required.</span></h1><p>Admin capabilities are enforced by server-side role checks; hiding this route does not grant access.</p><button class="button button-primary" data-open-auth>Sign in ↗</button></section></div>`;return}if(me.role!=='admin'){app.innerHTML=`<div class="container"><section class="page-head"><div class="eyebrow">ACCESS DENIED</div><h1>Administrator access<br><span class="gradient">required.</span></h1><p>Your account does not have administrative privileges.</p><a class="button button-quiet" href="#/account">Return to account</a></section></div>`;return}let d;try{d=await api('/api/admin/overview')}catch(e){app.innerHTML=`<div class="container page-head"><h1>Admin unavailable</h1><p>${esc(e.message)}</p></div>`;return}let c=d.counts;app.innerHTML=`<div class="container"><section class="dashboard-head"><div><div class="eyebrow">CONTROL ROOM / ADMIN</div><h1>Operations overview.</h1><p>Welcome back, ${esc(me.name)}. Sensitive changes are recorded in the audit log.</p></div><button class="button button-quiet button-small" id="logout-btn">Sign out</button></section><div class="stat-grid">${[['Customers',c.customers],['Orders',c.orders],['Awaiting review',c.pending],['In development',c.active],['Delivered',c.completed],['Open support',c.tickets]].map(x=>`<div class="card stat-card"><small>${x[0]}</small><strong>${x[1]}</strong></div>`).join('')}</div><div class="admin-tabs">${['Orders','Products','Support','Refunds'].map(x=>`<button class="admin-tab ${adminTab===x?'active':''}" data-admin-tab="${x}">${x}</button>`).join('')}</div><div id="admin-content"></div></div>`;$('#logout-btn').onclick=async()=>{await api('/api/logout',{method:'POST',body:'{}'}).catch(()=>{});me=null;csrf=null;refresh();go('/')};$$('[data-admin-tab]').forEach(b=>b.onclick=()=>{adminTab=b.dataset.adminTab;admin()});renderAdminTab(d)}
async function renderAdminTab(d){let box=$('#admin-content');if(!box)return;if(adminTab==='Orders'){box.innerHTML=`<div class="card dash-panel"><h3>All project requests</h3><div class="table-wrap"><table class="data-table"><thead><tr><th>Reference</th><th>Customer</th><th>Product</th><th>Received</th><th>Status</th><th>Update</th></tr></thead><tbody>${d.orders.map(o=>`<tr><td>${esc(o.number)}</td><td>${esc(o.name)}<br>${esc(o.email)}</td><td>${esc(o.product_title)}</td><td>${esc(o.created_at)}</td><td><span class="status-pill">${esc(o.status)}</span></td><td><select data-order-status="${o.id}" class="admin-status">${['Submitted','Under Review','Requirements Analysis','Quotation Sent','Awaiting Confirmation','In Development','Testing','Ready for Delivery','Delivered','Cancelled'].map(s=>`<option ${o.status===s?'selected':''}>${s}</option>`).join('')}</select></td></tr>`).join('')||`<tr><td colspan="6">No order requests yet.</td></tr>`}</tbody></table></div></div>`;$$('[data-order-status]').forEach(sel=>sel.onchange=async()=>{try{await api('/api/admin/orders/status',{method:'PUT',body:JSON.stringify({id:+sel.dataset.orderStatus,status:sel.value})});toast('Order status updated.');admin()}catch(e){toast(e.message)}})}
else if(adminTab==='Products'){box.innerHTML=`<div class="dash-grid"><div class="card dash-panel"><h3>Catalog products (${d.products.length})</h3><div class="table-wrap"><table class="data-table"><thead><tr><th>Product</th><th>Category</th><th>Price label</th><th>Visibility</th><th>Actions</th></tr></thead><tbody>${d.products.map(p=>`<tr><td>${esc(p.title)}<br><span class="form-hint">${esc(p.slug)}</span></td><td>${esc(p.category)}</td><td>${esc(p.price_label)}</td><td>${p.published?'Published':'Hidden'}</td><td><button class="button button-quiet button-small" data-edit-product="${p.id}">Edit</button> <button class="button button-quiet button-small" data-toggle-publish="${p.id}">${p.published?'Unpublish':'Publish'}</button></td></tr>`).join('')}</tbody></table></div><p class="form-hint" style="margin-top:13px">Products are database-backed. Remove is a soft unpublish so order history and references stay intact. Image/file uploads are not yet enabled.</p></div><div class="card dash-panel"><h3>Add a product</h3><form id="new-product"><div class="field"><label>Title</label><input name="title" required maxlength="140"></div><div class="field" style="margin-top:10px"><label>Slug (lowercase letters, numbers, hyphens)</label><input name="slug" required pattern="[a-z0-9-]{3,100}"></div><div class="field" style="margin-top:10px"><label>Category</label><select name="category"><option>Websites</option><option>Applications</option><option>Aurion</option></select></div><div class="field" style="margin-top:10px"><label>Summary</label><input name="summary" required maxlength="300"></div><div class="field" style="margin-top:10px"><label>Description</label><textarea name="description" required maxlength="3000"></textarea></div><div class="field" style="margin-top:10px"><label>Price label</label><input name="price_label" placeholder="Request a quote"></div><div id="product-feedback"></div><button class="button button-primary button-block" style="margin-top:12px">Create product</button></form></div></div>`;$('#new-product').onsubmit=async e=>{e.preventDefault();let payload=Object.fromEntries(new FormData(e.target));try{await api('/api/admin/products',{method:'POST',body:JSON.stringify(payload)});toast('Product added to the catalog.');await loadProducts();admin()}catch(err){$('#product-feedback').innerHTML=`<div class="form-error">${esc(err.message)}</div>`}};$$('[data-edit-product]').forEach(b=>b.onclick=async()=>{let p=d.products.find(x=>x.id===+b.dataset.editProduct);let title=prompt('Product title',p.title);if(title===null)return;let summary=prompt('Short description',p.summary);if(summary===null)return;let description=prompt('Full description',p.description);if(description===null)return;let price=prompt('Price label',p.price_label);if(price===null)return;try{await api('/api/admin/products',{method:'PUT',body:JSON.stringify({id:p.id,title,summary,description,price_label:price,category:p.category,published:!!p.published})});toast('Product updated.');await loadProducts();admin()}catch(e){toast(e.message)}});$$('[data-toggle-publish]').forEach(b=>b.onclick=async()=>{let p=d.products.find(x=>x.id===+b.dataset.togglePublish);try{await api(p.published?'/api/admin/products':'/api/admin/products',{method:p.published?'DELETE':'PUT',body:JSON.stringify(p.published?{id:p.id}:{id:p.id,title:p.title,summary:p.summary,description:p.description,price_label:p.price_label,category:p.category,published:true})});toast(p.published?'Product unpublished.':'Product published.');await loadProducts();admin()}catch(e){toast(e.message)}})}
else if(adminTab==='Support'){let tickets=[];try{tickets=await api('/api/support')}catch{}box.innerHTML=`<div class="card dash-panel"><h3>Support requests (${tickets.length})</h3>${tickets.map(t=>`<div class="order-card card"><div><h3>${esc(t.ref)} · ${esc(t.subject)}</h3><p>${esc(t.email)} · ${esc(t.created_at)}<br>${esc(t.message)}</p></div><div style="display:flex;gap:8px;align-items:center"><span class="status-pill">${esc(t.status)}</span><button class="button button-quiet button-small" data-reply-ticket="${t.id}">Reply</button><button class="button button-quiet button-small" data-close-ticket="${t.id}" ${t.status==='Closed'?'disabled':''}>Close</button></div></div>${t.messages?.map(m=>`<div class="form-hint" style="padding:4px 14px">${esc(m.sender||'Team')}: ${esc(m.message)}</div>`).join('')||''}`).join('')||'<div class="empty-state">No support requests.</div>'}</div>`;$$('[data-close-ticket]').forEach(b=>b.onclick=async()=>{try{await api('/api/admin/tickets/status',{method:'PUT',body:JSON.stringify({id:+b.dataset.closeTicket,status:'Closed'})});toast('Ticket closed.');admin()}catch(e){toast(e.message)}});$$('[data-reply-ticket]').forEach(b=>b.onclick=async()=>{let message=prompt('Reply to customer:');if(!message)return;try{await api('/api/admin/tickets/reply',{method:'POST',body:JSON.stringify({id:+b.dataset.replyTicket,message})});toast('Reply sent to ticket.');admin()}catch(e){toast(e.message)}})}
else {let refunds=[];try{refunds=await api('/api/refunds')}catch{}box.innerHTML=`<div class="card dash-panel"><h3>Refund review</h3>${refunds.map(r=>`<div class="order-card card"><div><h3>${esc(r.ref)} · ${esc(r.order_number)}</h3><p>${esc(r.reason)}<br>${esc(r.created_at)}</p></div><div style="display:flex;gap:7px;align-items:center"><span class="status-pill">${esc(r.status)}</span>${r.status==='Under review'?`<button class="button button-quiet button-small" data-refund="${r.id}" data-decision="Approved">Approve</button><button class="button button-quiet button-small" data-refund="${r.id}" data-decision="Rejected">Reject</button>`:''}</div></div>`).join('')||'<div class="empty-state">No refund requests.</div>'}<p class="form-hint">Approving records a decision only. It does not process or confirm a payment-provider refund.</p></div>`;$$('[data-refund]').forEach(b=>b.onclick=async()=>{let note=prompt(`Optional note for ${b.dataset.decision.toLowerCase()} decision:`)||'';try{await api('/api/admin/refunds/decision',{method:'PUT',body:JSON.stringify({id:+b.dataset.refund,status:b.dataset.decision,note})});toast('Refund decision recorded.');admin()}catch(e){toast(e.message)}})}}
async function loadProducts(){try{products=await api('/api/products')}catch(e){products=[]}}
/* Settings carry the brand list as well as the copy, and the brand strip is
   rendered from window.AXIA_BRANDS. Brands are applied here, after the settings
   have arrived, so a brand added or removed in the console shows up on the very
   next render rather than after a reload. On the static build the same document
   already reached brands.js synchronously, and re-applying it is idempotent. */
function applySettingsBrands(){
  if(typeof window.AXIA_BRANDS_APPLY!=='function')return;
  if(!Array.isArray(site.brands))return;
  window.AXIA_BRANDS_APPLY(site.brands);
}
async function loadSite(){try{const r=await api('/api/site');if(r&&r.settings)site={...siteDefaults,...r.settings}}catch(e){const snap=window.AXIA_STATIC&&window.AXIA_STATIC.settings;if(snap)site={...siteDefaults,...snap}}applySettingsBrands()}
/* Reflect settings that live in the page chrome (header, footer, announcement
   bar, support assistant) rather than in a rendered route. These are re-applied
   after every route change because the mobile menu and the auth modals rebuild
   their own markup. */
function applyChrome(){
  let bar = $('#announcement-bar');
  if (!site.announcement_enabled || !site.announcement_text) {
    if (bar) bar.hidden = true;
  } else {
    // The element is hidden rather than removed: settings arrive asynchronously,
    // and a removed bar could never come back once they load.
    if (!bar) {
      bar = document.createElement('div');
      bar.id = 'announcement-bar';
      bar.className = 'announcement tone-info';
      document.body.insertBefore(bar, document.querySelector('.topbar'));
    }
    bar.hidden = false;
    bar.className = 'announcement tone-' + (site.announcement_tone || 'info');
    const link = site.announcement_link
      ? `<a class="announcement-link" href="${esc(site.announcement_link)}">${site.announcement_link.startsWith('#/') ? 'Open' : 'Learn more'} ↗</a>`
      : '';
    bar.innerHTML = `<span class="announcement-text">${esc(site.announcement_text)}</span>${link}<button class="announcement-close" aria-label="Dismiss announcement">×</button>`;
    const close = bar.querySelector('.announcement-close');
    if (close) close.onclick = () => { bar.hidden = true; };
  }

  const navFlags = {'#/products':'show_catalog','#/services':'show_services','#/aurion':'show_aurion','#/aurion/plans':'show_aurion','#/about':'show_about'};
  $$('.nav-links a, .mobile-nav a, .footer-links a').forEach(a => {
    const flag = navFlags[a.getAttribute('href')];
    if (flag) a.hidden = !visible(flag);
  });
  applyBrand();
  const cta = $('.nav-cta');
  if (cta) cta.hidden = !visible('show_contact');
  const chat = $('#chat-launcher');
  if (chat) chat.hidden = !visible('show_assistant');

  const footNote = $('.footer-top>p');
  if (footNote && site.footer_note) footNote.textContent = site.footer_note;

  const links = $('.footer-links');
  if (links && !links.querySelector('[data-contact]')) {
    let extra = '';
    if (site.contact_email) extra += `<a data-contact href="mailto:${esc(site.contact_email)}">${esc(site.contact_email)}</a>`;
    if (site.contact_phone) extra += `<a data-contact href="tel:${esc(String(site.contact_phone).replace(/[^+0-9]/g, ''))}">${esc(site.contact_phone)}</a>`;
    if (site.github_url) extra += `<a data-contact href="${esc(site.github_url)}" target="_blank" rel="noopener noreferrer">GitHub ↗</a>`;
    if (extra) links.insertAdjacentHTML('beforeend', extra);
  }
}
/* The contact form works without an account. It posts to /api/contact,
   which files the message as a ticket the console already lists, and shows
   the reference number so the visitor has something to quote back. A failed
   request reports the server's own sentence rather than a generic error,
   because the most common failures (a short message, a mistyped address) are
   fixable and the visitor should know which one it was. */
function bindContactForm(){
  const form=$('#contact-form');
  if(!form)return;
  form.onsubmit=async e=>{
    e.preventDefault();
    const box=$('#contact-feedback');
    const payload=Object.fromEntries(new FormData(form));
    const button=form.querySelector('button[type=submit]');
    box.innerHTML='';
    if(!payload.name||payload.name.trim().length<2){box.innerHTML='<div class="form-error">Please tell us your name.</div>';return}
    if(!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(String(payload.email||'').trim())){box.innerHTML='<div class="form-error">That email address does not look complete.</div>';return}
    if(String(payload.message||'').trim().length<20){box.innerHTML='<div class="form-error">Please describe the project in at least 20 characters.</div>';return}
    button.disabled=true;
    try{
      const res=await api('/api/contact',{method:'POST',body:JSON.stringify(payload)});
      form.querySelectorAll('input,textarea').forEach(el=>{el.value=''});
      box.innerHTML=`<div class="form-success">Message sent. Your reference is <b>${esc(res.ref)}</b>. We reply within two working days.</div>`;
      toast('Message sent.');
    }catch(err){
      box.innerHTML=`<div class="form-error">${esc(err.message)}</div>`;
    }finally{button.disabled=false}
  };
}
function render(){let raw=decodeURIComponent(location.hash.slice(1)||'/');let [path,query]=raw.split('?');currentPath=path;if(path==='/products'&&!visible('show_catalog')){app.innerHTML=sectionOff('catalog');return}if(path==='/products'){let params=new URLSearchParams(query||'');productFilter=params.get('category')||productFilter;app.innerHTML=catalog();bindFilters();return}
/* '#/' is the AXIASOFT home. A visitor who follows any link back to it is
   asking for the studio, not for the last product brand they browsed, so the
   brand is dropped here too. Without this the header kept showing e.g. Homa
   after a trip home, and the brand could only be cleared from the catalog. */
if(path==='/'){productFilter='All';if(localStorage.getItem(BRAND_STORAGE)){localStorage.removeItem(BRAND_STORAGE);activeBrand=null}applyBrand();app.innerHTML=home();return}if(path==='/about'){app.innerHTML=visible('show_about')?about():sectionOff('about');return}if(path==='/services'){app.innerHTML=visible('show_services')?services():sectionOff('services');return}if(path==='/contact'){app.innerHTML=visible('show_contact')?contact():sectionOff('contact');if(visible('show_contact'))bindContactForm();return}if(path==='/aurion'){app.innerHTML=visible('show_aurion')?aurion():sectionOff('aurion');return}if(path==='/aurion/plans'){app.innerHTML=visible('show_aurion')?aurionPlans():sectionOff('aurion');return}if(path==='/account'){account();return}if(path==='/admin'){location.assign('/admin/');return}if(path==='/privacy'||path==='/terms'||path==='/refunds-policy'){app.innerHTML=policy(path.slice(1));return}if(path.startsWith('/products/')){let slug=path.split('/')[2];let p=products.find(x=>x.slug===slug);if(!p){api('/api/products/'+encodeURIComponent(slug)).then(x=>{products.push(x);app.innerHTML=detail(x)}).catch(()=>{app.innerHTML='<div class="container page-head"><h1>Product not found</h1><a href="#/products">Return to products</a></div>'});return}app.innerHTML=detail(p);return}/* The preview is a layer over the page, not a route of its own: it opens over
   whatever the visitor was looking at and closing it returns them there. The
   hash is kept in step so a shared link lands on the same preview, and the
   route below re-creates the layer when the page loads directly at that hash. */
if(path.startsWith('/preview/')){let slug=path.split('/')[2];let p=products.find(x=>x.slug===slug);if(!p){app.innerHTML='<div class="container page-head"><h1>Preview not found</h1><a class="back-link" href="#/products">Return to products</a></div>';return}app.innerHTML=catalog();bindFilters();setTimeout(()=>openPreview(slug,false),0);return}app.innerHTML=home()}
$('#year').textContent=new Date().getFullYear();themeInit();applyThemePreference();applyChrome();loadSite().then(async()=>{applyChrome();applyThemePreference();await loadProducts();await refresh();render();applyChrome();teachXiona()}).catch(async()=>{await loadProducts();await refresh();render();applyChrome();teachXiona()});window.addEventListener('hashchange',()=>{if(location.hash.includes('/products?category=')){productFilter=new URLSearchParams(location.hash.split('?')[1]).get('category')||'All'}render();applyChrome();teachXiona();window.scrollTo({top:0,behavior:'smooth'})});document.addEventListener('click',e=>{const pick=e.target.closest('[data-brand-pick]');if(pick){setBrand(pick.dataset.brandPick);return}if(e.target.closest('[data-brand-clear]')){clearBrand();return}
/* Pressing the header lockup while a product brand is running returns to
   AXIASOFT. The link has always pointed at '#/', but the home route never
   touched the brand, so from the home page the href was already satisfied: the
   hash did not change, no navigation happened, and the brand logo stayed put.
   This drops the brand itself rather than calling clearBrand(), which would
   take the visitor to the catalog — the logo means home, not products. */
if(e.target.closest('#brand-link')&&currentBrand()){
  e.preventDefault();
  localStorage.removeItem(BRAND_STORAGE);
  activeBrand=null;
  applyBrand();
  if(location.hash&&location.hash!=='#/')location.hash='#/';
  return}const previewBtn=e.target.closest('[data-preview]');if(previewBtn){e.preventDefault();openPreview(previewBtn.dataset.preview);return}let btn=e.target.closest('[data-order]');if(btn)orderModal(btn.dataset.order);if(e.target.closest('[data-open-auth]'))openAuth();if(e.target.closest('[data-aurion-presentation]'))toast('AURION is a symbolic showcase; purchasing is not enabled.');const cardEl=e.target.closest('[data-open-product]');if(cardEl&&!e.target.closest('a,button,[data-order]')){location.hash='#/products/'+cardEl.dataset.openProduct}});
/* Keyboard parity: a card is focusable and responds to Enter/Space. */
document.addEventListener('keydown',e=>{if(e.key!=='Enter'&&e.key!==' ')return;const cardEl=e.target.closest&&e.target.closest('[data-open-product]');if(!cardEl||e.target.closest('a,button'))return;e.preventDefault();location.hash='#/products/'+cardEl.dataset.openProduct});
/* Xiona — the assistant behind the launcher.

   It is self-contained: public/xiona.js builds a searchable knowledge base in
   the browser out of what this site publishes, and answers from it. No key, no
   outbound request, no model download. The server build uses the same scoring
   via /api/agent; on the static build this is the only path, and it is enough.

   The knowledge grows as the site grows: every render teaches Xiona the page
   the visitor is looking at, and the snapshot carries the catalog and the
   articles. Nothing here reads orders, accounts or payments. */
const launcher=$('#chat-launcher');launcher.onclick=toggleChat;
/* The launcher changes shape with the panel: a circle invites a question, the
   pill says who the visitor is already talking to. */
function syncLauncher(){const l=$('#chat-launcher');if(!l)return;l.classList.toggle('is-open',chatOpen);l.setAttribute('aria-expanded',String(chatOpen));l.setAttribute('aria-label',chatOpen?'Close the Xiona assistant':'Open the Xiona assistant')}

/* One engine for the session. It is built lazily on first use so the launcher
   costs nothing until someone asks something. */
let xiona=null,xionaPagesSeen={};
/* The assistant's Persian/English vocabulary is a 45 KB table that only it
   reads. It used to ride along in the catalog snapshot, so every visitor
   downloaded it before the hero had resolved, whether or not they ever opened
   the chat. app.js fetches it the first time the panel is opened and merges it
   into the snapshot the engine reads; a second open reuses the same promise. */
let vocabularyRequest=null;
function loadVocabulary(){
  if(window.AXIA_STATIC&&Array.isArray(window.AXIA_STATIC.pairs)&&window.AXIA_STATIC.pairs.length)return Promise.resolve(window.AXIA_STATIC.pairs);
  if(vocabularyRequest)return vocabularyRequest;
  const base=document.baseURI||location.href;
  vocabularyRequest=fetch(new URL('data/vocabulary.js',base).href,{cache:'force-cache'})
    .then(r=>r.ok?r.text():'')
    .then(text=>{
      if(!text)return[];
      /* A snapshot file is a plain script, not JSON: it assigns to the same
         window.AXIA_STATIC the rest of the build writes to. Evaluating it is
         what the browser would have done had the tag been in the page. */
      new Function(text)();
      return (window.AXIA_STATIC&&window.AXIA_STATIC.pairs)||[];
    })
    .catch(()=>[]);
  return vocabularyRequest;
}
function xionaEngine(){
  if(xiona)return xiona;
  if(!window.Xiona){xiona=null;return null}
  xiona=new window.Xiona.Engine().learnSite({document:document,window:window});
  return xiona;
}
/* Every render re-teaches the assistant the page in front of the visitor, so a
   post published from the console is answerable without a redeploy. */
function teachXiona(){
  const engine=xionaEngine(); if(!engine)return;
  const source=window.Xiona.readSite({document:document,window:window,path:location.hash});
  const page=source.pages[0]; if(!page||xionaPagesSeen[page.route])return;
  xionaPagesSeen[page.route]=true;
  engine.learn(source);
}

function toggleChat(){
  /* Opening the panel is the first moment the vocabulary is worth its bytes. */
  if(!chatOpen&&!(window.AXIA_STATIC&&(window.AXIA_STATIC.pairs||[]).length)){
    loadVocabulary().then(()=>{
      /* The engine has already indexed the pages with no dictionary. Rebuilding
         it is cheaper than teaching a live one a second vocabulary, and it is a
         one-off: this runs the first time the panel opens and never again. */
      xiona=null;
      xionaEngine();
      teachXiona();
    })
  }
  chatOpen=!chatOpen;syncLauncher();let panel=$('#chat-panel');if(!chatOpen){panel?.remove();return}if(panel)return;panel=document.createElement('section');panel.id='chat-panel';panel.className='chat-panel';const chatFa=document.documentElement.lang==='fa';
 panel.innerHTML=`<div class="chat-head"><div><strong>Xiona · ${chatFa?'دستیار همین سایت':'on-site assistant'}</strong><small>${chatFa?'همین سایت را یاد می‌گیرد · خودش پاسخ می‌دهد · بدون سرویس بیرونی':'Learns this site · answers on its own · no outside service'}</small></div><button class="close-button" aria-label="${chatFa?'بستن گفت‌وگو':'Close support'}">×</button></div><div class="chat-messages" id="chat-messages"></div><div class="chat-chips"></div><div class="chat-disclaimer">${chatFa?'Xiona فقط از آنچه این سایت منتشر کرده پاسخ می‌دهد و به سفارش‌ها، پرداخت‌ها یا حساب شما دسترسی ندارد.':'Xiona answers only from what this site publishes. It cannot see orders, payments or your account.'}</div><form class="chat-form" id="chat-form"><input id="chat-input" placeholder="${chatFa?'دربارهٔ محصولات، خدمات یا فرایند کار بپرسید…':'Ask about products, services or the process…'}" maxlength="500" required><button>${chatFa?'بفرست':'Send'}</button></form>`;document.body.append(panel);
  /* The panel is the site telling the visitor what this assistant is. Teach it
     the moment it exists, so "who are you" is answered from the panel text the
     visitor can read - not from a sentence kept in the engine. */
  if(xiona&&xiona.add){const claims=[...panel.querySelectorAll('.chat-head strong,.chat-head small,.chat-disclaimer')].map(n=>n.textContent.trim()).filter(Boolean);if(claims.length)xiona.add({id:'shell-assistant',title:'Xiona',topic:'assistant',route:'#/contact',text:claims.join('. '),keywords:'assistant bot ai robot who xiona دستیار ربات هوش مصنوعی کی ساخت'})}
  $('.close-button',panel).onclick=toggleChat;$('#chat-form',panel).onsubmit=e=>{e.preventDefault();let input=$('#chat-input');sendChat(input.value);input.value=''};
 /* Open with the conversation this visitor already had, or with a real answer
    rather than a fixed greeting: the engine names what it can actually answer,
    which on an empty catalog is honestly "not much yet". */
 const engine=xionaEngine();
 const fa=document.documentElement.lang==='fa';
 const hello=engine?engine.answer(fa?'سلام':'hello').text:(fa?'سلام. من Xiona هستم؛ دستیار همین سایت.':'Hi, I am Xiona, this site\'s assistant.');
 loadChatHistory().then(saved=>{
   /* The panel may have been closed again while the account was answering. */
   if(!$('#chat-panel'))return;
   chatHistory=Array.isArray(saved)?saved.slice(-CHAT_MAX):[];
   if(chatHistory.length){
     /* A resumed conversation: replay it and skip the greeting, which would
        otherwise sit between the visitor's own last question and its answer. */
     chatHistory.forEach(turn=>addChat(turn.text, turn.role==='user'?'user':'bot'));
     const divider=document.createElement('div');
     divider.className='chat-resumed';
     divider.textContent=fa?'ادامهٔ گفت‌وگوی پیشین':'Resumed conversation';
     $('#chat-messages')?.prepend(divider);
   }else{
     addChat(hello,'bot');
   }
   const box=$('#chat-messages'); if(box)box.scrollTop=box.scrollHeight;
 });
 const chips=$('.chat-chips',panel);
 [fa?'محصولات را معرفی کن':'What products do you offer?',fa?'فرایند سفارش چطور است؟':'How do I start a project?',fa?'AURION چیست؟':'What is AURION?'].forEach(label=>{const b=document.createElement('button');b.className='chat-chip';b.textContent=label;b.onclick=()=>sendChat(label);chips.append(b)});
 teachXiona();
}
function addChat(text,who='bot',thinking=false){let box=$('#chat-messages');if(!box)return null;let node=document.createElement('div');node.className='chat-msg '+(who==='user'?'user':'')+(thinking?' chat-thinking':'');node.textContent=text;box.append(node);box.scrollTop=box.scrollHeight;return node}
/* --------------------------------------------------------------- history

   The conversation outlives the panel, the page and the tab.

   Signed in, it is kept on the account and comes back on any device: the
   session cookie is what identifies it, so a returning visitor resumes where
   they left off. Signed out, there is no identity to hang it on, so it lives
   in sessionStorage instead - which the browser clears when the tab (and
   therefore the browser session) is closed, and keeps across a reload, a
   back-button and a route change. localStorage would have kept it forever for
   someone who never signed in, on a shared machine, which is the wrong default.

   The store is a small wrapper because the two backends answer differently:
   sessionStorage is synchronous, the account API is not. Both fail quietly -
   a browser with storage disabled, or a static build with no API, still gets a
   working chat for the length of the visit. */
const CHAT_KEY='axia-chat-v1', CHAT_MAX=60;
let chatHistory=[], chatSavedAt=0, chatStoreMode='guest';

function chatStorage(){
  try{ return window.sessionStorage }catch(e){ return null }
}
/* The signed-in copy is the account's; the guest copy is the tab's. Reading
   prefers the account so a signed-in visitor never sees a stranger's tab
   history, and writing mirrors into the tab so a reload mid-session is instant
   even before the API answers. */
function loadChatHistory(){
  const raw=(()=>{ try{ return chatStorage()?.getItem(CHAT_KEY) }catch(e){ return null } })();
  let local=null;
  if(raw){ try{ const parsed=JSON.parse(raw); if(Array.isArray(parsed)) local=parsed }catch(e){} }
  if(me){
    chatStoreMode='account';
    /* The account is authoritative. The tab copy is NOT used as a head start
       here: on a shared machine it could belong to the previous person to sign
       in, and showing one visitor another's conversation is worse than a flash
       of empty panel. It is kept only as an offline fallback. */
    return api('/api/agent/history').then(d=>Array.isArray(d?.history)?d.history:(local||[]))
      .catch(()=>local||[]);
  }
  chatStoreMode='guest';
  return Promise.resolve(local||[]);
}
function saveChatHistory(){
  const turns=chatHistory.slice(-CHAT_MAX);
  chatHistory=turns;
  chatSavedAt=Date.now();
  try{ chatStorage()?.setItem(CHAT_KEY, JSON.stringify(turns)) }catch(e){}
  if(me){ api('/api/agent/history',{method:'POST',body:JSON.stringify({history:turns})}).catch(()=>{}) }
}
function clearChatHistory(){
  chatHistory=[];
  try{ chatStorage()?.removeItem(CHAT_KEY) }catch(e){}
  if(me)api('/api/agent/history',{method:'DELETE'}).catch(()=>{});
}
/* A citation is the one bit of markup the answer carries: a link to the page it
   came from, so a claim can be checked instead of trusted. */
function addCitations(list){
  const box=$('#chat-messages'); if(!box||!list||!list.length)return;
  const seen={}; const links=[];
  list.forEach(c=>{ if(!c.route||seen[c.route])return; seen[c.route]=true; links.push(c) });
  if(!links.length)return;
  const row=document.createElement('div'); row.className='chat-cites';
  const fa=document.documentElement.lang==='fa';
  const label=document.createElement('span'); label.textContent=(fa?'منبع: ':'Source: '); row.append(label);
  links.slice(0,3).forEach(c=>{
    const a=document.createElement('a'); a.href=c.route; a.textContent=c.title;
    a.onclick=()=>{ if(chatOpen)toggleChat() };
    row.append(a);
  });
  box.append(row); box.scrollTop=box.scrollHeight;
}
/* Ask the agent. The browser engine is asked first: it is instant, works with
   no network, and is the same knowledge the server has. /api/agent is used when
   a model is configured server-side, because a model can phrase an answer
   better than retrieval can — but it never replaces the local answer, and a
   failure falls back to it. */
async function sendChat(text){
 text=String(text||'').trim(); if(!text)return;
 addChat(text,'user'); chatHistory.push({role:'user',text});
 const thinking=addChat('…','bot',true);
 const engine=xionaEngine();
 const answer=engine?engine.answer(text):null;
 let reply=null, usedModel=false;
 /* The server is asked first now, and always. It is the only side that can
    reach a language model, and a model is the only thing here that can answer
    a question the site never wrote down or reply in the language the visitor
    actually used. The local engine stays as the fallback: on the static build
    there is no server, and on the server build a provider outage must not turn
    into a refusal. */
 try{
   const res=await fetch('/api/agent',{method:'POST',headers:{'Content-Type':'application/json'},
     credentials:'same-origin',body:JSON.stringify({question:text,history:chatHistory.slice(-6),
     language:document.documentElement.lang==='fa'?'fa':'en'})});
   if(res.ok){
     const data=await res.json();
     if(data&&data.answer&&data.provider==='model'){reply=data.answer;usedModel=true}
   }
 }catch(e){ /* static build or offline: the local answer stands */ }
 if(!reply)reply=answer&&answer.source==='knowledge'?answer.text:null;
 if(!reply)reply=answer?answer.text:(document.documentElement.lang==='fa'
   ?'همین حالا نتوانستم به دانش خودم دست پیدا کنم؛ لطفاً دوباره بپرسید.'
   :'I could not reach my knowledge just now.');
 thinking.remove();
 addChat(reply,'bot');
 if(!usedModel&&answer&&answer.citations)addCitations(answer.citations);
 chatHistory.push({role:'bot',text:reply});
 saveChatHistory()}
// Responsive mobile navigation.
const mobileMenuButton=$('.mobile-menu');mobileMenuButton.setAttribute('aria-expanded','false');mobileMenuButton.onclick=()=>{if($('.mobile-nav'))return;const rect=mobileMenuButton.getBoundingClientRect(),x=rect.left+rect.width/2,y=rect.top+rect.height/2,w=window.innerWidth,h=window.innerHeight,radius=Math.ceil(Math.max(Math.hypot(x,y),Math.hypot(w-x,y),Math.hypot(x,h-y),Math.hypot(w-x,h-y))*1.08);let nav=document.createElement('nav');nav.className='mobile-nav';nav.setAttribute('aria-label','Mobile navigation');nav.style.setProperty('--menu-x',`${x}px`);nav.style.setProperty('--menu-y',`${y}px`);nav.style.setProperty('--menu-radius',`${radius}px`);nav.innerHTML=`<button class="close-button close-mobile" aria-label="Close menu">×</button><a href="#/products">Products</a><a href="#/services">Services</a><a href="/blog/">Blog</a><a href="#/aurion">AURION</a><a href="#/about">About</a><a href="#/contact">Start a project</a>`;document.body.append(nav);mobileMenuButton.setAttribute('aria-expanded','true');const duration=matchMedia('(prefers-reduced-motion: reduce)').matches?0:440;let closing=false;const closeMenu=()=>{if(closing)return;closing=true;nav.classList.remove('is-open');mobileMenuButton.setAttribute('aria-expanded','false');window.setTimeout(()=>{nav.remove();mobileMenuButton.focus()},duration)};$('.close-mobile',nav).onclick=closeMenu;$$('a',nav).forEach(a=>a.onclick=closeMenu);nav.addEventListener('keydown',e=>{if(e.key==='Escape')closeMenu()});requestAnimationFrame(()=>{nav.classList.add('is-open');requestAnimationFrame(()=>$('a',nav)?.focus())})};
window.openAuth=openAuth;

/* Every card and every in-page button tilts; the header controls do not.

   Doing this by hand would mean editing fifty template strings and remembering
   the rule on every new one — the kind of thing that rots the first time
   somebody adds a card. It runs instead at the end of each render: one selector
   list, one pass, and the header is excluded explicitly because a nav bar that
   tips under the pointer is a toy, not a flourish.

   data-no-tilt is the escape hatch, and the two big illustrations opt out
   through it below because their tilt is already custom. */
const TILT_SELECTORS = [
  '.category-card', '.product-card', '.package', '.stat-card', '.dash-panel',
  '.cta-band', '.contact-card', '.feature-panel', '.workflow-card',
  '.detail-visual', '.brand-pick', '.plan-table-wrap', '.faq',
  '.button:not(.button-small)', '.contact-product',
];
function applyTiltClasses(root){
  if(!root)return;
  const header=root.querySelector('.topbar');
  root.querySelectorAll(TILT_SELECTORS.join(',')).forEach(el=>{
    if(header&&header.contains(el))return;   // header controls keep their own size
    if(el.closest('.topbar'))return;
    if(el.hasAttribute('data-no-tilt'))return;
    el.classList.add('tilt-hover');
    // The light that follows the pointer is for panels, not for buttons: a
    // radial glare inside a 38px pill looks like a smudge.
    if(!el.matches('.button,.contact-product'))el.classList.add('mouse-light');
  });
}
/* Apply the classes whenever the page content changes.

   render() returns early on half its branches, and several routes build their
   markup later still (the catalog after filters, the account page after its
   fetch), so hanging this off one call site would miss most of the site. A
   MutationObserver on #app costs one callback per render — not per frame — and
   covers every path including the ones added after this was written. */
function startTiltWatcher(){
  applyTiltClasses(app);
  if(startTiltWatcher.done)return;
  startTiltWatcher.done=true;
  new MutationObserver(()=>applyTiltClasses(app)).observe(app,{childList:true,subtree:true});
}
function initPointerEffects(){
 if(matchMedia('(prefers-reduced-motion: reduce)').matches)return;
 /* Two input models, one element class.

    Mouse: the tilt follows the pointer anywhere inside the element, and
    releases on leave.

    Touch: there is no hover, so a press is what starts it. The tilt tracks the
    finger while it is down and springs back on release. That is the only way
    this effect can exist on a phone, and it is also the right one — a card that
    tilts when you touch it feels like a card; a card that tilts on scroll
    position would be noise.

    Both write the same three custom properties, so there is one drawing path. */
 const fine=matchMedia('(hover:hover) and (pointer:fine)').matches;
 const coarse=matchMedia('(pointer:coarse)').matches;
 // Cards get a bigger angle than buttons: a 16-degree tip on a 100px pill
 // would look broken, on a 340px card it looks deliberate.
 const strength=el=>{
   if(el.hasAttribute('data-no-tilt'))return 0;
   if(el.classList.contains('hero-logo')||el.classList.contains('aurion-logo-hover'))return 18;
   // A pill 38px tall tipping 16 degrees looks broken; 7 is a press, not a
   // tumble. Cards get the full angle.
   if(el.matches('.button,.btn,.icon-button,.contact-product,.brand-pick'))return 7;
   return 16;
 };

 function tiltTo(el,clientX,clientY){
   const r=el.getBoundingClientRect();
   if(!r.width||!r.height)return;
   const k=strength(el);
   const nx=(clientX-r.left)/r.width-.5, ny=(clientY-r.top)/r.height-.5;
   el.classList.add('is-tilting');
   el.style.setProperty('--tilt-x',(nx*k).toFixed(2)+'deg');
   el.style.setProperty('--tilt-y',(-ny*k*0.8).toFixed(2)+'deg');
   if(el.classList.contains('mouse-light')){
     el.classList.add('is-lit');
     el.style.setProperty('--light-x',((clientX-r.left)/r.width*100).toFixed(1)+'%');
     el.style.setProperty('--light-y',((clientY-r.top)/r.height*100).toFixed(1)+'%');
   }
 }
 function reset(el){
   el.style.setProperty('--tilt-x','0deg');
   el.style.setProperty('--tilt-y','0deg');
   el.classList.remove('is-tilting','is-lit');
 }

 if(fine){
   app.addEventListener('pointerover',e=>{
     if(e.pointerType==='touch')return;
     const el=e.target.closest('.tilt-hover');
     if(!el||!app.contains(el))return;
     let frame=0,pending=null;
     if(!el.dataset.tiltBound){
       el.dataset.tiltBound='1';
       el.addEventListener('pointermove',ev=>{
         if(ev.pointerType==='touch')return;
         pending=ev;
         if(frame)return;
         frame=requestAnimationFrame(()=>{frame=0;if(pending)tiltTo(el,pending.clientX,pending.clientY)});
       },{passive:true});
       el.addEventListener('pointerleave',()=>reset(el),{passive:true});
       el.addEventListener('pointercancel',()=>reset(el),{passive:true});
     }
   },{passive:true});
 }

 if(coarse){
   // Capture phase, because a press on a link must still tilt before the link
   // navigates away, and a press on a card must not be swallowed by its child.
   let active=null;
   const start=e=>{
     const el=e.target.closest('.tilt-hover');
     if(!el||!app.contains(el))return;
     active=el;
     tiltTo(el,e.clientX,e.clientY);
   };
   const move=e=>{
     if(!active)return;
     // Only while the finger is still down; a scroll gesture releases it.
     if(e.buttons===0&&e.pointerType==='touch')return;
     tiltTo(active,e.clientX,e.clientY);
   };
   const end=()=>{if(active){reset(active);active=null}};
   app.addEventListener('pointerdown',start,{passive:true});
   app.addEventListener('pointermove',move,{passive:true});
   app.addEventListener('pointerup',end,{passive:true});
   app.addEventListener('pointercancel',end,{passive:true});
   // `scroll` does not bubble, so a listener on #app would never fire. The
   // window captures it from the scrolling element instead. A finger that
   // scrolls the page has stopped pressing the card, so the tilt is released.
   window.addEventListener('scroll',()=>{if(active){reset(active);active=null}},{passive:true,capture:true});
 }
}
initPointerEffects();
startTiltWatcher();

/* -------------------------------------------------------------------------
   Product brands

   The brand buttons on the Websites tab let a visitor open the catalog the way
   a specific product presents itself: its logo in the header, its colour, its
   name in the title. A brand is offered only when the catalog holds a published
   product for it — the mapping is by slug and by title — so a button never
   leads to an empty page.
   ------------------------------------------------------------------------- */

/* A brand may have no image at all: the shipped brands deliberately carry none
   and an operator uploads their own. Drawing nothing left an empty square, so
   this returns the markup for either the uploaded picture or a monogram built
   from the brand's initial and its accent colour — always something to look at,
   and never a broken-image icon. `kind` is 'logo' or 'mark'. */
function brandGlyph(brand, kind = 'logo') {
  if (!brand) return '';
  const path = kind === 'logo' ? (brand.logo || brand.mark || '') : (brand.mark || brand.logo || '');
  const name = brandName(brand) || brand.name || '';
  if (path) {
    return `<img src="${esc(assetUrl(path))}" alt="${esc(name)}" draggable="false" loading="lazy" decoding="async">`;
  }
  /* The initial is the first letter in the language being read, so a Persian
     visitor sees «آ» for آریا rather than an «A» that belongs to neither. */
  const initial = (name.trim()[0] || '·').toUpperCase();
  return `<span class="brand-glyph" style="--glyph-accent:${esc(brand.accent || '#1f5fa8')}" aria-hidden="true">${esc(initial)}</span>`;
}

function brandCatalog() {
  return Array.isArray(window.AXIA_BRANDS) ? window.AXIA_BRANDS : [];
}

// A product belongs to a brand when its slug starts with the brand id or its
// title carries the brand name. Both are checked so an admin can add a product
// either way and still have the button work.
function brandMatches(brand, product, productSlug) {
  const slug = String(productSlug || product?.slug || '').toLowerCase();
  const title = String(product?.title || '').toLowerCase();
  return slug === brand.id || slug.startsWith(brand.id + '-') ||
         new RegExp('(^|[^a-z])' + brand.id + '([^a-z]|$)', 'i').test(title) ||
         title.includes(String(brand.nameFa || ''));
}

// The brand a product belongs to, or null for an ordinary AXIASOFT product.
function brandForProduct(product) {
  if (!product) return null;
  return brandCatalog().find((b) => brandMatches(b, product)) || null;
}

// Brands that currently have something to show.
function availableBrands() {
  const list = brandCatalog();
  return list.filter((b) => products.some((p) => brandMatches(b, p)));
}

function currentBrand() {
  if (activeBrand) return activeBrand;
  const saved = localStorage.getItem(BRAND_STORAGE);
  if (!saved) return null;
  const found = brandCatalog().find((b) => b.id === saved);
  return found && availableBrands().some((b) => b.id === found.id) ? found : null;
}

function brandName(brand) {
  if (!brand) return 'AXIASOFT';
  return document.documentElement.lang === 'fa' ? (brand.nameFa || brand.name) : brand.name;
}

/* Applying a brand is deliberately limited to presentation: the logo, the
   accent variables and the document title. Nothing about the product data, the
   order flow or the account changes. */
/* Asset URLs must keep whatever prefix the site is served under. GitHub Pages
   serves this build from /AxiaPlatform/, so a hard-coded "/brand/x.png" 404s
   there — which is exactly what happened to the header logo. */
function assetUrl(path) {
  const raw = String(path || '');
  const base = (window.AXIA_STATIC && window.AXIA_STATIC.base)
    || document.currentScript?.dataset?.base
    || '';
  // A path the build already prefixed with the deploy base — a product cover
  // written by tools/build_static.py, for instance — must be returned as it is.
  // Prefixing it again produced /AxiaPlatform/AxiaPlatform/brand/… and the
  // image 404ed. Checking the base rather than the leading '/' also keeps a
  // genuinely root-relative '/brand/x.png' working, because that is exactly
  // what the base-prefixed form looks like once the base is '/' or '/sub/'.
  if (base && raw.startsWith(base.replace(/\/$/, '') + '/')) return raw;
  const clean = raw.replace(/^\//, '');
  if (base) return base.replace(/\/$/, '') + '/' + clean;
  // Fall back to the deployed sub-path, derived from this page's own address.
  const marker = '/blog/';
  const here = location.pathname;
  if (here.includes('/admin/')) return here.slice(0, here.indexOf('/admin/') + 1) + clean;
  if (here.includes(marker)) return here.slice(0, here.indexOf(marker) + 1) + clean;
  return '/' + clean;
}

function applyBrand() {
  const brand = currentBrand();
  const root = document.documentElement;
  if (!brand) {
    root.removeAttribute('data-brand');
    root.style.removeProperty('--brand-accent');
    root.style.removeProperty('--brand-accent-soft');
    const mark = $('#brand-mark img');
    if (mark) mark.src = assetUrl('brand/axiasoft-original.webp');
    const word = $('#brand-wordmark');
    if (word) word.hidden = false;
    const name = $('#brand-name');
    if (name) { name.hidden = true; name.textContent = ''; }
    const label = $('.brand-eyebrow');
    if (label) label.textContent = 'AXIASOFT';
    document.title = 'AXIASOFT — ' + AXIA_T('Thoughtful software. Built for what comes next.');
    return;
  }
  root.setAttribute('data-brand', brand.id);
  root.style.setProperty('--brand-accent', brand.accent);
  root.style.setProperty('--brand-accent-soft', brand.accentSoft);
  const mark = $('#brand-mark img');
  if (mark && !mark.src.endsWith(brand.mark)) mark.src = assetUrl(brand.mark);
  // The brand marks are bare symbols (no lettering), so the AXIASOFT wordmark
  // is swapped for the brand's own name rather than simply hidden — hiding it
  // left a header with a bird and no company name at all.
  const word = $('#brand-wordmark');
  if (word) word.hidden = true;
  const name = $('#brand-name');
  if (name) { name.hidden = false; name.textContent = brandName(brand); }
  const label = $('.brand-eyebrow');
  if (label) label.textContent = brandName(brand);
  document.title = brandName(brand) + ' — ' + AXIA_T('Thoughtful software. Built for what comes next.');
}

function setBrand(id) {
  const brand = brandCatalog().find((b) => b.id === id);
  if (!brand) return;
  if (localStorage.getItem(BRAND_STORAGE) === id) {
    // Pressing the active brand again returns to the AXIASOFT catalog.
    clearBrand();
    return;
  }
  localStorage.setItem(BRAND_STORAGE, id);
  activeBrand = null;
  applyBrand();
  showBrand();
}

function clearBrand() {
  localStorage.removeItem(BRAND_STORAGE);
  activeBrand = null;
  applyBrand();
  showBrand();
}

/* Choosing a brand should show that brand's catalog immediately. Setting the
   hash alone does not re-render when the visitor is already on /products, so
   the catalog is drawn here and the hash is corrected afterwards. */
function showBrand() {
  location.hash = '#/products';
  app.innerHTML = catalog();
  bindFilters();
  applyChrome();
}

/* The tab buttons are re-bound after any render that replaces the catalog, and
   choosing a brand does exactly that. */
/* ------------------------------------------------------------- preview ---- */
/* A product's preview used to cost the visitor the site: the button opened the
   GitHub repository in a new tab, and the built-in concept demo was a card at
   the bottom of the detail page. The preview belongs *in* the site now — a
   fullscreen layer the visitor can browse without leaving AXIASOFT.

   The layer is one fixed element with three stacked parts: a slim toolbar that
   carries the product name, an "open on GitHub" escape hatch and the close
   button; the frame itself; and a loading veil that lifts when the frame
   reports it has loaded. The frame is an <iframe> with sandbox="allow-scripts
   allow-same-origin allow-popups" — enough for a real site to run, not enough
   for it to reach back into this page's storage or navigate the top window. */
let previewSlug = null;

function previewProduct(slug) {
  return products.find((p) => p.slug === slug) || null;
}

/* Where a product's preview actually points. A valid https link is the real
   thing; without one the product gets the built-in concept page, which is a
   document this build writes to data/preview/<slug>.html. Both are loaded into
   the same frame, so the visitor's experience is identical either way. */
function previewSrc(p) {
  const live = safePreview(p.github_url);
  if (live) return live;
  const path = 'data/preview/' + encodeURIComponent(p.slug) + '.html';
  return assetUrl(path);
}

function openPreview(slug, pushHash) {
  const p = previewProduct(slug);
  if (!p) {
    toast('That product preview is not available.');
    return;
  }
  closePreview(false);
  previewSlug = slug;
  const fa = document.documentElement.lang === 'fa';
  const src = previewSrc(p);
  const live = safePreview(p.github_url);
  const layer = document.createElement('section');
  layer.className = 'preview-layer';
  layer.id = 'preview-layer';
  layer.setAttribute('role', 'dialog');
  layer.setAttribute('aria-modal', 'true');
  layer.setAttribute('aria-label', (fa ? 'پیش‌نمایش ' : 'Preview of ') + p.title);
  layer.innerHTML = `
    <header class="preview-bar">
      <div class="preview-bar-title"><span class="preview-bar-dot"></span><strong>${esc(p.title)}</strong><span class="preview-bar-slug">${esc(p.slug)}</span></div>
      <div class="preview-bar-actions">
        ${live ? `<a class="preview-btn" href="${esc(live)}" target="_blank" rel="noopener noreferrer">${fa ? 'بازکردن در زبانهٔ تازه ↗' : 'Open in a new tab ↗'}</a>` : ''}
        <a class="preview-btn" href="#/products/${esc(p.slug)}" data-preview-details>${fa ? 'جزئیات محصول' : 'Product details'}</a>
        <button class="preview-btn preview-close" data-preview-close aria-label="${fa ? 'بستن پیش‌نمایش' : 'Close preview'}">×</button>
      </div>
    </header>
    <div class="preview-stage">
      <div class="preview-loading" data-preview-loading><span class="preview-spinner"></span><span>${fa ? 'در حال بارگذاری پیش‌نمایش…' : 'Loading the preview…'}</span></div>
      <iframe class="preview-frame-live" data-preview-frame src="${esc(src)}" title="${esc(p.title)}"
        loading="eager" referrerpolicy="no-referrer"
        sandbox="allow-scripts allow-same-origin allow-popups allow-forms allow-popups-to-escape-sandbox"></iframe>
    </div>`;
  document.body.append(layer);
  document.body.classList.add('preview-open');
  const frame = $('[data-preview-frame]', layer);
  const veil = $('[data-preview-loading]', layer);
  const reveal = () => { if (veil) veil.remove(); layer.classList.add('is-ready'); };
  if (frame) {
    frame.addEventListener('load', reveal, { once: true });
    /* A site that sends X-Frame-Options: DENY renders as an empty browser error
       page and fires no useful event, and the failure is invisible from here —
       the frame is cross-origin, so its contentDocument stays unreadable. The
       only honest move is to say so on the timer: lift the veil, but leave a
       note naming the escape hatch that has been in the toolbar all along. */
    setTimeout(() => {
      if (!layer.classList.contains('is-ready')) {
        reveal();
        if (live) {
          const note = document.createElement('p');
          note.className = 'preview-blocked';
          note.innerHTML = (fa ? 'این سایت اجازهٔ نمایش درون‌برنامه‌ای نمی‌دهد. ' : 'This site does not allow being shown inside another page. ')
            + `<a href="${esc(live)}" target="_blank" rel="noopener noreferrer">${fa ? 'در زبانهٔ تازه باز کنید ↗' : 'Open it in a new tab ↗'}</a>`;
          layer.append(note);
        }
      }
    }, 6000);
  }
  layer.addEventListener('click', (event) => {
    if (event.target.closest('[data-preview-close]') || event.target.closest('[data-preview-details]')) {
      closePreview();
    }
  });
  document.addEventListener('keydown', previewKeys);
  if (pushHash !== false && location.hash !== '#/preview/' + slug) location.hash = '#/preview/' + slug;
  $('[data-preview-close]', layer)?.focus();
}

function closePreview(dropHash = true) {
  const layer = $('#preview-layer');
  if (layer) layer.remove();
  document.body.classList.remove('preview-open');
  document.removeEventListener('keydown', previewKeys);
  previewSlug = null;
  if (dropHash && location.hash.startsWith('#/preview/')) {
    /* Back to the catalog rather than stripping the hash. Stripping it left the
       page empty: no hash means the home route, but the viewer was opened over
       the catalog, so the visitor lost their place. replaceState is used so the
       history keeps one stop instead of gaining one that points at a closed
       layer. */
    history.replaceState(null, '', '#/products');
    render();
    applyChrome();
  }
}

/* Escape closes, and focus is kept inside the layer while it is open — the
   storefront behind it is visually covered and should not take a Tab. */
function previewKeys(event) {
  const layer = $('#preview-layer');
  if (!layer) return;
  if (event.key === 'Escape') { event.preventDefault(); closePreview(); return; }
  if (event.key !== 'Tab') return;
  const focusable = $$('a[href],button:not([disabled]),iframe,[tabindex]:not([tabindex="-1"])', layer);
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
}

function bindFilters() {
  $$('[data-filter]').forEach((b) => {
    b.onclick = () => {
      productFilter = b.dataset.filter;
      go('/products' + (productFilter === 'All' ? '' : '?category=' + productFilter));
      app.innerHTML = catalog();
      bindFilters();
      applyChrome();
    };
  });
}

/* The brand strip. It renders nothing when the catalog has no branded products,
   so an empty installation shows no dead buttons. */
function brandStrip() {
  const available = availableBrands();
  if (!available.length) return '';
  const active = currentBrand();
  const fa = document.documentElement.lang === 'fa';
  const cards = available.map((b) => {
    const items = products.filter((p) => brandMatches(b, p));
    const isActive = active && active.id === b.id;
    /* `tilt-hover mouse-light` is the same 3D tilt and pointer-following halo the
       service and category cards use, so the brand row feels like the same
       family of surfaces. The brand card is a <button>, so the halo pseudo
       element is suppressed when the card is disabled — these never are — and
       the tilt is skipped for coarse pointers and reduced motion by
       initPointerEffects(), which is the behaviour we want on a phone. */
    return `<button class="brand-pick tilt-hover mouse-light${isActive ? ' is-active' : ''}" type="button"
              data-brand-pick="${esc(b.id)}" aria-pressed="${isActive ? 'true' : 'false'}"
              title="${esc(fa ? b.taglineFa : b.tagline)}">
        <span class="brand-pick-logo">${brandGlyph(b, 'logo')}</span>
        <span class="brand-pick-copy">
          <strong>${esc(fa ? b.nameFa : b.name)}</strong>
          <small>${esc(fa ? b.taglineFa : b.tagline)}</small>
        </span>
        <span class="brand-pick-count">${String(items.length)}</span>
      </button>`;
  }).join('');
  return `<section class="brand-picker" aria-label="${esc(fa ? 'برندهای محصول' : 'Product brands')}">
    <div class="brand-picker-head">
      <div>
        <div class="eyebrow">${esc(fa ? 'برندهای سایت' : 'Site brands')}</div>
        <h2>${esc(fa ? 'با کدام برند شروع کنیم؟' : 'Which brand should it launch under?')}</h2>
      </div>
      ${active ? `<button class="button button-quiet button-small" type="button" data-brand-clear>${esc(fa ? 'نمایش همه' : 'Show all')}</button>` : ''}
    </div>
    <div class="brand-picker-row">${cards}</div>
  </section>`;
}

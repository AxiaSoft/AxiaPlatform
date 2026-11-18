(()=>{
'use strict';
const root=document.querySelector('#adminApp'),overlays=document.querySelector('#overlayRoot');
const $=(s,r=document)=>r.querySelector(s),$$=(s,r=document)=>[...r.querySelectorAll(s)];
const T=v=>window.AXIA_T?window.AXIA_T(v):v;
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const moneyFreeDate=v=>{if(!v)return'—';const d=new Date(String(v).replace(' ','T')+'Z');return Number.isNaN(+d)?esc(v):new Intl.DateTimeFormat(document.documentElement.lang==='fa'?'fa-IR':'en-GB',{dateStyle:'medium',timeStyle:'short'}).format(d)};
const ordersStatus=['Submitted','Under Review','Requirements Analysis','Quotation Sent','Awaiting Confirmation','In Development','Testing','Ready for Delivery','Delivered','Cancelled'];
/* Which permission opens each console page.

   The sidebar used to list every page to every administrator, because there
   was only one kind. Now a support agent who opens Refunds gets a 403 from the
   server, so the link is not drawn either - the list below is the single place
   that decides, and the server decides the same way with the same group names.

   Anything missing from this map is treated as 'activity' (read-only), which is
   why adding a page without a decision does not silently open it to everyone. */
const PAGE_PERMISSION = {
  dashboard: 'activity',      // the overview reads counts only
  site: 'content',
  products: 'catalog',
  articles: 'content',
  orders: 'sales',
  customers: 'customers',
  support: 'support',
  refunds: 'sales',
  activity: 'activity',
  admins: 'admins',
};
const ALL_PAGES = Object.keys(PAGE_PERMISSION);
function myPermissions(){
  return Array.isArray(state.me?.permissions) ? state.me.permissions : [];
}
function can(permission){
  // A console that has not heard from the server yet shows nothing rather than
  // everything: the safe direction when the answer is unknown.
  return myPermissions().includes(permission);
}
function allowedPage(page){ return can(PAGE_PERMISSION[page] || 'activity'); }
function allowedPages(){ return ALL_PAGES.filter(allowedPage); }
const PAGES=ALL_PAGES;
const state={me:null,csrf:null,page:'dashboard',overview:null,orders:[],products:[],customers:[],tickets:[],refunds:[],audit:[],articles:[],articleDraft:null,agent:null,admins:null,adminForm:null,settings:null,savedSettings:null,siteTab:'identity',search:'',statusFilter:'All',productFilter:'All',categoryFilter:'All',productSort:'manual',selected:new Set(),dirty:false,menu:false,loading:false,lastSync:null,customerId:null,customer:null,foldCategories:false,productDraft:null};
async function api(path,{method='GET',body,headers={}}={}){
 const h={'Content-Type':'application/json',...headers};
 if(method!=='GET'&&path!=='/api/login'){if(!state.csrf){const session=await fetch('/api/me',{credentials:'same-origin'}).then(r=>r.json()).catch(()=>({}));state.csrf=session.csrf||null}if(state.csrf)h['X-CSRF-Token']=state.csrf}
 const response=await fetch(path,{method,headers:h,body:body===undefined?undefined:JSON.stringify(body),credentials:'same-origin'});
 const token=response.headers.get('X-CSRF-Token');if(token)state.csrf=token;
 const data=await response.json().catch(()=>({error:'The server returned an unreadable response.'}));
 if(!response.ok)throw Object.assign(new Error(data.error||`Request failed (${response.status})`),{status:response.status});return data;
}
function toast(message,isError=false){const stack=$('.toast-stack')||(()=>{const d=document.createElement('div');d.className='toast-stack';document.body.append(d);return d})();const item=document.createElement('div');item.className='toast'+(isError?' error':'');item.textContent=message;stack.append(item);setTimeout(()=>item.remove(),3800)}
function fmtNum(n){return new Intl.NumberFormat(document.documentElement.lang==='fa'?'fa-IR':'en').format(Number(n)||0)}
function pillClass(s){const x=String(s||'').toLowerCase();if(['delivered','closed','approved','available','published','active'].includes(x))return'green';if(['submitted','under review','open','awaiting confirmation','quotation sent','in progress','showcase'].includes(x))return'amber';if(['cancelled','rejected','hidden','inactive'].includes(x))return'red';return'blue'}
function pill(s){return`<span class="pill ${pillClass(s)}">${esc(s||'Unknown')}</span>`}
/* The console's sidebar used to draw a different character per page from
   whatever the font happened to have: ◫ ⚙ ▤ ◈ ♙ ✳ ↩ ◷. They were mixed
   weights, some had colour glyphs on some platforms, and they read as
   decoration rather than as a wayfinding aid. They map onto the shared icon
   set now, so the sidebar matches the site it administers. */
const ICON=(n,c)=>typeof AXIA_ICON==='function'?AXIA_ICON(n,c):'';
function iconFor(page){
  return ICON(({dashboard:'dashboard',site:'settings',orders:'order',products:'package',
    customers:'users',support:'inbox',refunds:'refund',activity:'clock'})[page]||'spark','nav-icon');
}
function loginView(error=''){
 root.innerHTML=`<main class="login-wrap"><section class="login-card"><div class="login-brand"><span class="logo-mark"><img src="/AxiaPlatform/brand/axiasoft-original.webp" alt="" width="37" height="37" decoding="async"></span><div><strong>AXIASOFT</strong><small>ADMIN CONSOLE</small></div><span style="margin-left:auto"><button id="languageToggle" class="language-btn" aria-label="Switch language">${document.documentElement.lang==='fa'?'EN':'فارسی'}</button></span></div><div class="eyebrow">Restricted workspace</div><h1>Administrator sign in</h1><p class="muted">Use your AXIASOFT administrator account to access operational records and tools.</p>${error?`<div class="error-note" role="alert">${esc(error)}</div>`:''}<form data-form="login"><div class="field" style="margin-bottom:12px"><label for="loginEmail">Administrator email</label><input id="loginEmail" name="email" type="email" autocomplete="username" required maxlength="254" placeholder="name@company.com"></div><div class="field"><label for="loginPassword">Password</label><input id="loginPassword" name="password" type="password" autocomplete="current-password" required maxlength="256" placeholder="Your password"></div><button class="btn btn-primary" style="width:100%;margin-top:18px;min-height:42px">Sign in securely ${ICON('arrow','dir-icon')}</button></form><div class="secure-note"><span class="secure-dot"></span> Server-verified administrator role · secure session</div><p class="setup-command">No default administrator credentials are provided. To create or reset an admin account, run <code>python3 provision_admin.py</code> from the server directory.</p></section></main>`;
}
function deniedView(){root.innerHTML=`<main class="login-wrap"><section class="login-card"><div class="login-brand"><span class="logo-mark"><img src="/AxiaPlatform/brand/axiasoft-original.webp" alt="" width="37" height="37" decoding="async"></span><div><strong>AXIASOFT</strong><small>ADMIN CONSOLE</small></div></div><div class="eyebrow">Access restricted</div><h1>Administrator access required</h1><p class="muted">This account does not have the required administrator role. The server has denied protected data access.</p><div class="head-actions"><button class="btn btn-quiet" data-act="logout">Sign out</button><a class="btn btn-primary" href="/AxiaPlatform/#/">Return to website</a></div></section></main>`}
function shell(){
 const navAll=[['dashboard','Overview'],['site','Website'],['products','Products'],['articles','Blog articles'],['orders','Project requests'],['customers','Customers'],['support','Support'],['refunds','Refunds'],['activity','Activity log'],['admins','Administrators']];
 const nav=navAll.filter(([id])=>allowedPage(id));
 root.innerHTML=`<div class="admin-shell"><div class="side-scrim" data-act="close-nav"></div><aside class="sidebar" id="sidebar"><a href="/" class="side-brand"><span class="logo-mark"><img src="/AxiaPlatform/brand/axiasoft-original.webp" alt="" width="37" height="37" decoding="async"></span><span><strong>AXIASOFT</strong><small>ADMIN CONSOLE</small></span></a><div class="side-label">Workspace</div><nav class="nav-list">${nav.map(([id,label])=>`<button class="side-link ${state.page===id?'active':''}" data-page="${id}"><span class="nav-glyph">${iconFor(id)}</span><span>${T(label)}</span>${id==='refunds'&&state.overview?.counts?.refunds?`<span class="nav-count">${fmtNum(state.overview.counts.refunds)}</span>`:''}${id==='orders'&&state.overview?.counts?.pending?`<span class="nav-count">${fmtNum(state.overview.counts.pending)}</span>`:''}</button>`).join('')}</nav><div class="side-label" style="margin-top:23px">Website</div><a class="side-link" href="/"><span class="nav-glyph">${ICON('external')}</span><span>Open public website</span></a><div class="sidebar-bottom"><div class="sidebar-foot"><span class="avatar">${esc((state.me?.name||'A').slice(0,1).toUpperCase())}</span><div class="user-min"><strong>${esc(state.me?.name||'Administrator')}</strong><small>${esc(state.me?.email||'')}</small></div><button class="icon-btn" data-act="logout" title="Sign out" aria-label="Sign out">${ICON('logout')}</button></div></div></aside><section class="workspace"><header class="topbar"><div class="top-left"><button class="icon-btn mobile-toggle" data-act="toggle-nav" aria-label="Open navigation">${ICON('menu')}</button><div class="crumb">AXIASOFT <span style="color:var(--faint)">/</span> <strong>${nav.find(x=>x[0]===state.page)?.[1]||'Overview'}</strong></div></div><div class="top-right"><button class="language-btn" id="languageToggle" aria-label="Switch language">${document.documentElement.lang==='fa'?'EN':'فارسی'}</button><button class="icon-btn" data-act="theme" title="Toggle color theme" aria-label="Toggle color theme">${themeGlyph()}</button><button class="icon-btn" data-act="refresh" title="Refresh data" aria-label="Refresh data">${ICON('refresh')}</button><div class="top-user"><span class="avatar">${esc((state.me?.name||'A').slice(0,1).toUpperCase())}</span><div class="user-min-top"><strong>${esc(state.me?.name||'Administrator')}</strong><small>Administrator</small></div></div></div></header><main class="content" id="pageContent"><div class="panel" style="height:190px"><div class="skeleton" style="width:170px;margin:14px 0"></div><div class="skeleton" style="width:78%;height:50px;margin:14px 0"></div><div class="skeleton" style="width:55%"></div></div></main></section></div>`;
}
function chartSvg(rows){
 const months=[];const now=new Date();for(let i=5;i>=0;i--){const d=new Date(now.getFullYear(),now.getMonth()-i,1);months.push({year:d.getFullYear(),month:d.getMonth(),label:new Intl.DateTimeFormat(document.documentElement.lang==='fa'?'fa-IR':'en',{month:'short'}).format(d),value:0})}
 for(const o of rows){const d=new Date(String(o.created_at||'').replace(' ','T')+'Z');const m=months.find(x=>x.month===d.getMonth()&&x.year===d.getFullYear());if(m)m.value++}
 const max=Math.max(1,...months.map(x=>x.value)),w=640,h=190,left=28,right=12,top=12,bottom=28,innerW=w-left-right,innerH=h-top-bottom;
 const pts=months.map((x,i)=>({x:left+i*(innerW/(months.length-1)),y:top+innerH-(x.value/max)*(innerH*.82),...x}));const path=pts.map((p,i)=>`${i?'L':'M'}${p.x},${p.y}`).join(' ');const area=`${path} L${pts.at(-1).x},${top+innerH} L${pts[0].x},${top+innerH} Z`;
 return`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Project requests over the last six months"><defs><linearGradient id="chartGradient" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#6aa9ff" stop-opacity=".27"/><stop offset="1" stop-color="#6aa9ff" stop-opacity="0"/></linearGradient></defs>${[0,1,2,3].map(i=>`<line class="chart-grid-line" x1="${left}" x2="${w-right}" y1="${top+i*innerH/3}" y2="${top+i*innerH/3}"/>`).join('')}<path class="chart-area" d="${area}"/><path class="chart-line" d="${path}"/>${pts.map(p=>`<circle class="chart-dot" cx="${p.x}" cy="${p.y}" r="3.5"/><text class="chart-label" x="${p.x}" y="${h-6}" text-anchor="middle">${esc(p.label)}</text>`).join('')}</svg>`;
}
/* A relative label reads better than a raw timestamp in a 9px meta row. */
function syncLabel(date){
 const diff=Math.max(0,Math.round((Date.now()-date.getTime())/1000));
 const fa=document.documentElement.lang==='fa';
 const n=new Intl.NumberFormat(fa?'fa-IR':'en').format;
 if(diff<45)return fa?'همین حالا':'just now';
 if(diff<3600)return fa?`${n(Math.round(diff/60))} دقیقه پیش`:`${n(Math.round(diff/60))} min ago`;
 return new Intl.DateTimeFormat(fa?'fa-IR':'en-GB',{timeStyle:'short'}).format(date);
}
function trendPct(rows){
 const now=new Date(),monthAgo=new Date(now.getTime()-30*86400000);
 const recent=rows.filter(o=>{const d=new Date(String(o.created_at||'').replace(' ','T')+'Z');return !Number.isNaN(+d)&&d>=monthAgo}).length;
 const prev=rows.filter(o=>{const d=new Date(String(o.created_at||'').replace(' ','T')+'Z');return !Number.isNaN(+d)&&d<monthAgo&&d>=new Date(now.getTime()-60*86400000)}).length;
 if(!prev)return recent?{value:recent,label:'new this month',up:true}:{value:0,label:'no change',up:null};
 const pct=Math.round(((recent-prev)/prev)*100);
 return{value:pct,label:'vs. previous 30 days',up:pct>=0};
}
/* Last 14 days of request volume as a compact bar strip. It answers "what has
   been happening this fortnight" at a glance, where the six-month line chart
   answers "what is the trend". */
function sparkBars(rows,days=14){
 const today=new Date();const buckets=[];
 for(let i=days-1;i>=0;i--){const d=new Date(today.getFullYear(),today.getMonth(),today.getDate()-i);buckets.push({key:d.toISOString().slice(0,10),label:new Intl.DateTimeFormat(document.documentElement.lang==='fa'?'fa-IR':'en',{day:'numeric'}).format(d),value:0})}
 for(const o of rows){const key=String(o.created_at||'').slice(0,10);const b=buckets.find(x=>x.key===key);if(b)b.value++}
 const max=Math.max(1,...buckets.map(b=>b.value));
 return`<div class="spark" role="img" aria-label="Requests per day for the last ${days} days">${buckets.map(b=>`<span class="spark-bar" style="--h:${Math.max(6,Math.round(b.value/max*100))}%" title="${esc(b.key)} · ${fmtNum(b.value)}"><i></i><em>${esc(b.label)}</em></span>`).join('')}</div>`;
}
function healthRows(){
 const c=state.overview?.counts||{},s=state.settings||{};
 const rows=[
  [T('Server session'), state.overview?.demo?T('Demo (browser storage)'):T('Live Python API'), state.overview?.demo?'warn':'ok'],
  [T('Storefront status'), (s.show_catalog===false?T('Catalog hidden'):T('Catalog visible')),'ok'],
  [T('Pending reviews'), c.pending?`${fmtNum(c.pending)} ${T('requests waiting')}`:T('Nothing waiting'), c.pending?'warn':'ok'],
  [T('Open support'), c.tickets?`${fmtNum(c.tickets)} ${T('tickets')}`:T('No open tickets'), c.tickets?'warn':'ok'],
  [T('Suspended accounts'), c.customers_suspended?`${fmtNum(c.customers_suspended)} ${T('accounts')}`:T('None'), c.customers_suspended?'warn':'ok'],
  [T('Catalog'), `${fmtNum(c.published||0)} ${T('published')} · ${fmtNum(c.hidden||0)} ${T('hidden')} · ${fmtNum(c.featured||0)} ${T('featured')}`,'ok']
 ];
 return rows.map(([label,value,level])=>`<div class="health-row"><span class="health-dot ${level}"></span><span class="health-label">${esc(label)}</span><strong>${esc(value)}</strong></div>`).join('');
}
function activityFeed(limit=7){
 const rows=(Array.isArray(state.audit)?state.audit:[]).slice(0,limit);
 if(!rows.length)return`<div class="empty" style="padding:22px"><div class="empty-icon">${ICON('clock')}</div>No events recorded yet.</div>`;
 return rows.map(a=>`<div class="activity-item"><span class="activity-glyph">${({create:ICON('plus'),update:ICON('edit'),unpublish:ICON('download'),status_change:ICON('refresh'),ticket_status:ICON('inbox'),ticket_reply:ICON('send'),refund_decision:ICON('refund'),customer_access:ICON('users'),login:ICON('logout'),settings:ICON('settings')})[a.action]||'•'}</span><div><strong>${esc(T(actionLabel(a.action)))}</strong><small>${esc(T(a.entity||'system'))}${a.entity_id?' · '+esc(String(a.entity_id)):''}</small></div><time>${moneyFreeDate(a.created_at)}</time></div>`).join('');
}
function topProducts(products,orders){
 const counts={};for(const o of orders){const key=o.product_title||'Unassigned';counts[key]=(counts[key]||0)+1}
 // The catalog can be empty while requests still reference past products, so
 // both sources contribute: real catalog rows first, then request titles.
 const rows=products.map(p=>({title:p.title,requests:counts[p.title]||0,published:!!p.published,slug:p.slug}));
 for(const title of Object.keys(counts)){
  if(!rows.some(r=>r.title===title))rows.push({title,requests:counts[title],published:false,slug:'past product'});
 }
 rows.sort((a,b)=>b.requests-a.requests);
 const top=rows.slice(0,5);
 const max=Math.max(1,...top.map(r=>r.requests));
 if(!top.length)return`<div class="empty" style="padding:22px">No products in the catalog.</div>`;
 return`<div class="rank-list">${top.map((r,i)=>`<div class="rank-row"><span class="rank-num">${fmtNum(i+1)}</span><div class="rank-main"><strong>${esc(r.title)}</strong><small>/${esc(r.slug==='past product'?T('past product'):r.slug).replace(/\s+/g,'-')} · ${r.published?T('Published'):T('Hidden')}</small></div><div class="rank-bar"><i style="width:${Math.max(3,r.requests/max*100)}%"></i></div><span class="rank-value">${fmtNum(r.requests)}</span></div>`).join('')}</div>`;
}
function overviewHTML(){
 const d=state.overview||{counts:{},orders:[],products:[],tickets:[],customers:[]},c=d.counts||{},orders=Array.isArray(d.orders)?d.orders:[],products=Array.isArray(d.products)?d.products:[];
 const trend=trendPct(orders);
 const hero=`<section class="hero-strip panel"><div class="hero-strip-copy"><div class="eyebrow">Control room / today</div><h2>Good to see you, ${esc(state.me?.name||'Administrator')}.</h2><p>${c.pending?`${T('Awaiting a first review: {n}').replace('{n}',fmtNum(c.pending))} `:''}${c.tickets?`${T('Open support tickets: {n}').replace('{n}',fmtNum(c.tickets))} `:''}${!c.pending&&!c.tickets?T('Nothing is waiting for you right now.'):''} ${T('Everything on this page is editable from the sidebar.')}</p><div class="hero-strip-actions"><button class="btn btn-quiet" data-act="refresh">${ICON('refresh')} Refresh</button><button class="btn btn-quiet" data-page="site">${ICON('settings')} Website settings</button><button class="btn btn-primary" data-act="new-product">${ICON('plus')} Add product</button></div></div><div class="hero-strip-side"><div class="trend ${trend.up===null?'flat':trend.up?'up':'down'}"><strong>${trend.up===null?fmtNum(trend.value):(trend.up?ICON('up'):ICON('down'))+fmtNum(Math.abs(trend.value))+'%'}</strong><small>${esc(trend.label)}</small></div><div class="hero-meta"><span>Last data: <strong>${state.lastSync?syncLabel(state.lastSync):'—'}</strong></span><span>Mode: <strong>${d.demo?'demo':'live'}</strong></span></div></div></section>`;
 const cards=[['Customers',c.customers,ICON('users'),`${fmtNum(c.customers_active||0)} ${T('active')}`],['Project requests',c.orders,ICON('order'),`${fmtNum(c.pending||0)} ${T('awaiting review')}`],['In development',c.active,ICON('code'),`${fmtNum(c.completed||0)} ${T('delivered')}`],['Open support',c.tickets,ICON('inbox'),`${fmtNum(c.tickets_open??c.tickets??0)} ${T('not closed')}`],['Published products',c.published,ICON('package'),`${fmtNum(c.hidden||0)} ${T('hidden')} · ${fmtNum(c.featured||0)} ${T('featured')}`],['Refund reviews',c.refunds,ICON('refund'),T('Decision only · no payment')]];
 const statuses=ordersStatus.map(s=>({name:s,count:orders.filter(o=>o.status===s).length})).filter(x=>x.count||['Submitted','In Development','Delivered'].includes(x.name));
 const max=Math.max(1,...statuses.map(x=>x.count));
 return `${hero}<section class="grid stats-grid">${cards.map(([label,value,icon,sub])=>`<article class="stat-card"><div class="stat-top"><span>${T(label)}</span><span class="stat-icon">${icon}</span></div><strong>${fmtNum(value)}</strong><small>${sub}</small></article>`).join('')}</section>
 <section class="grid overview-grid"><article class="panel"><div class="panel-head"><div><h2>Project requests over time</h2><p>Submitted requests, last six months</p></div><span class="pill blue">${fmtNum(orders.length)} ${T('total')}</span></div><div class="chart-wrap">${chartSvg(orders)}</div><div class="chart-foot"><span>Last 14 days</span>${sparkBars(orders)}</div></article>
 <article class="panel"><div class="panel-head"><div><h2>Request status</h2><p>Current distribution</p></div><button class="btn btn-sm btn-quiet" data-page="orders">Manage ${ICON('arrow','dir-icon')}</button></div><div class="status-summary">${statuses.map(x=>`<div class="status-row"><span>${esc(T(x.name))}</span><div class="status-track"><div class="status-fill" style="width:${Math.max(x.count?5:0,x.count/max*100)}%"></div></div><strong class="status-value">${fmtNum(x.count)}</strong></div>`).join('')}</div><div class="panel-sep"></div><h3 class="mini-head">Most requested products</h3>${topProducts(products,orders)}</article></section>
 <section class="grid lower-grid"><article class="panel"><div class="panel-head"><div><h2>Recent project requests</h2><p>Latest customer submissions</p></div><button class="btn btn-sm btn-quiet" data-page="orders">View all ${ICON('arrow','dir-icon')}</button></div>${orders.length?`<div class="table-wrap"><table class="data-table"><thead><tr><th>Reference</th><th>Customer</th><th>Product</th><th>Updated</th><th>Status</th><th></th></tr></thead><tbody>${orders.slice(0,7).map(o=>`<tr><td><span class="cell-main">${esc(o.number)}</span></td><td>${esc(o.name)}<span class="cell-sub">${esc(o.email)}</span></td><td>${esc(o.product_title)}</td><td>${moneyFreeDate(o.updated_at||o.created_at)}</td><td>${pill(o.status)}</td><td><button class="btn btn-sm btn-quiet" data-act="view-order" data-id="${o.id}">Open</button></td></tr>`).join('')}</tbody></table></div>`:`<div class="empty"><div class="empty-icon">${ICON('order')}</div>No project requests yet. Requests from the public site appear here.</div>`}</article>
 <div class="stack"><article class="panel"><div class="panel-head"><div><h2>Site health</h2><p>What needs attention</p></div></div><div class="health-list">${healthRows()}</div></article><article class="panel"><div class="panel-head"><div><h2>Activity</h2><p>Latest audited events</p></div><button class="btn btn-sm btn-quiet" data-page="activity">Log ${ICON('arrow','dir-icon')}</button></div><div class="activity-list">${activityFeed(6)}</div></article></div></section>
 <section class="grid quick-section"><article class="panel"><div class="panel-head"><div><h2>Quick actions</h2><p>Common administrative tasks</p></div></div><div class="quick-grid"><button class="quick-card" data-page="site"><span>${ICON('settings')}</span><strong>Website settings</strong><small>Banner, hero copy, features</small></button><button class="quick-card" data-act="new-product"><span>${ICON('plus')}</span><strong>Add product</strong><small>Publish with a preview link</small></button><button class="quick-card" data-page="orders"><span>${ICON('order')}</span><strong>Review requests</strong><small>Update status and notes</small></button><button class="quick-card" data-page="support"><span>${ICON('inbox')}</span><strong>Open support</strong><small>Reply to customers</small></button></div><div class="notice">Payments and refunds are not processed here. An approval records an administrative decision only.</div></article></section>`;
}
/* A list of choices the console draws itself.

   <select> was the last browser-native control in the console: on Android it
   opens a sheet in the operating system's own font, in the operating system's
   language, and on desktop it opens a menu the page cannot style at all. This
   is a button and a listbox, so the console looks the same everywhere.

   It keeps the contract a <select> had: a hidden input carries the value for
   the form that contains it, so `new FormData(form)` still reads it. The
   options are {value, label}; `value` is never translated.

   `onPick` receives the new value. Events the console already listens for are
   dispatched on the hidden input, so existing handlers keep working. */
function picker(name, options, current, {id='', label='', placeholder='', onPick='', dataId=''}={}){
  const chosen = options.find(o => String(o.value) === String(current));
  return `<div class="picker" data-picker ${onPick ? `data-picker-act="${esc(onPick)}"` : ''}${dataId ? ` data-id="${esc(dataId)}"` : ''}>
    <button type="button" class="picker-btn" data-picker-btn ${id ? `id="${esc(id)}"` : ''}
      aria-haspopup="listbox" aria-expanded="false" ${label ? `aria-label="${esc(label)}"` : ''}>
      <span class="picker-value${chosen ? '' : ' is-empty'}">${esc(chosen ? chosen.label : (placeholder || label))}</span>
      <span class="picker-chev">${ICON('down')}</span>
    </button>
    <div class="picker-list" role="listbox" hidden>
      ${options.map(o => `<button type="button" role="option" class="picker-option${chosen && String(o.value) === String(chosen.value) ? ' is-on' : ''}"
        data-picker-option data-value="${esc(o.value)}" aria-selected="${chosen && String(o.value) === String(chosen.value) ? 'true' : 'false'}">
        <span>${esc(o.label)}</span>${chosen && String(o.value) === String(chosen.value) ? ICON('check') : ''}
      </button>`).join('')}
    </div>
    <input type="hidden" name="${esc(name)}" value="${esc(current)}" data-picker-input>
  </div>`;
}

function pageHead(kicker,title,desc,action=''){return`<div class="page-head"><div><div class="eyebrow">${kicker}</div><h1>${title}</h1><p>${desc}</p></div><div class="head-actions">${action}</div></div>`}
function toolbar(searchPlaceholder,filterOptions=[],action=''){return`<div class="toolbar"><div class="toolbar-left"><label class="search"><input data-search placeholder="${searchPlaceholder}" value="${esc(state.search)}" autocomplete="off"></label>${filterOptions.length?`${picker('status', filterOptions.map(x=>({value:x,label:T(x)})), state.statusFilter, {label:T('Filter by status'), onPick:'pickerStatusFilter'})}`:''}</div><div class="toolbar-right">${action}</div></div>`}
function ordersHTML(){const data=state.orders.filter(o=>{const q=state.search.toLowerCase();const hay=[o.number,o.name,o.email,o.product_title,o.status].join(' ').toLowerCase();return(!q||hay.includes(q))&&(state.statusFilter==='All'||o.status===state.statusFilter)});return`${pageHead('Work queue','Project requests','Review customer submissions, update progress and keep a clear status history.',`<button class="btn btn-quiet" data-act="export" data-kind="orders">${ICON('download')} Export CSV</button>`)}${toolbar('Search by reference, customer or product…',['All',...ordersStatus])}<div class="panel" style="padding:14px"><div class="panel-head"><div><h2>All requests</h2><p>${fmtNum(data.length)} shown · customer/project records</p></div></div>${data.length?`<div class="table-wrap"><table class="data-table"><thead><tr><th>Reference</th><th>Customer</th><th>Product</th><th>Received</th><th>Last update</th><th>Status</th><th></th></tr></thead><tbody>${data.map(o=>`<tr><td><span class="cell-main">${esc(o.number)}</span></td><td><span class="cell-main">${esc(o.name)}</span><span class="cell-sub">${esc(o.email)} · ${esc(o.phone)}</span></td><td>${esc(o.product_title)}</td><td>${moneyFreeDate(o.created_at)}</td><td>${moneyFreeDate(o.updated_at)}</td><td>${pill(o.status)}</td><td><button class="btn btn-sm btn-quiet" data-act="view-order" data-id="${o.id}">Details</button></td></tr>`).join('')}</tbody></table></div>`:`<div class="empty"><div class="empty-icon">⌕</div>No matching requests.</div>`}</div>`}
function productSortValue(p){
 return state.productSort==='title'?String(p.title).toLowerCase()
  :state.productSort==='category'?String(p.category).toLowerCase()
  :state.productSort==='newest'?-Number(p.id)
  :[Number(p.featured)?0:1,Number(p.position)||0,Number(p.id)||0];
}
function productSortCompare(a,b){
 if(state.productSort==='newest')return Number(b.id)-Number(a.id);
 if(state.productSort==='title')return String(a.title).localeCompare(String(b.title));
 if(state.productSort==='category')return String(a.category).localeCompare(String(b.category))||String(a.title).localeCompare(String(b.title));
 const fa=Number(a.featured)?0:1,fb=Number(b.featured)?0:1;
 const pa=Number(a.position)||0,pb=Number(b.position)||0;
 return fa-fb||pa-pb||Number(a.id)-Number(b.id);
}
/* ---------------------------------------------------------------- catalog */
/* The catalog screen shows the same rows two ways. On a desktop it is a table
   with a column per fact; a table with nine columns is unreadable on a phone,
   and the row still needs to carry every fact, so below 900px the same data is
   drawn as a card per product. Both are rendered from the functions below and
   the stylesheet chooses which one is displayed - no re-render on resize, and
   nothing is duplicated in the markup a screen reader walks. */

/* The categories, as the operator defined them. Products store a category id,
   so this is what turns 'websites' back into the label the site prints. A
   category that has been deleted still has products pointing at it; those
   fall back to the raw id rather than to an empty cell, so the gap is visible
   instead of silent. */
function siteCategories(){
 const list=Array.isArray(state.settings?.categories)?state.settings.categories:[];
 return list.filter(c=>c&&c.id&&c.name).map(c=>({id:String(c.id),name:String(c.name),nameFa:String(c.nameFa||'')}));
}
function categoryLabel(id){
 const cat=siteCategories().find(c=>c.id===id);
 if(!cat)return id?String(id):'—';
 return document.documentElement.lang==='fa'&&cat.nameFa?cat.nameFa:cat.name;
}
/* A product whose category no longer exists is flagged in the row, so an
   operator who deletes a category can find the products it orphaned. */
function orphanCategory(p){return !!p.category&&!siteCategories().some(c=>c.id===p.category)}

function productStats(counts){
 return `<div class="mini-stats"><div><strong>${fmtNum(counts.all)}</strong><span>${T('Total')}</span></div><div><strong>${fmtNum(counts.published)}</strong><span>${T('Published')}</span></div><div><strong>${fmtNum(counts.hidden)}</strong><span>${T('Hidden')}</span></div><div><strong>${fmtNum(counts.featured)}</strong><span>${T('Featured')}</span></div></div>`;
}

function productActions(p){
 return `<div class="row-actions">
  <button class="btn btn-sm ${p.featured?'btn-primary':'btn-quiet'}" data-act="feature-product" data-id="${p.id}" data-featured="${p.featured?1:0}" title="${T('Feature on the storefront')}" aria-label="${T('Feature on the storefront')}" aria-pressed="${p.featured?'true':'false'}">${p.featured?'★':'☆'}</button>
  <button class="btn btn-sm btn-quiet" data-act="edit-product" data-id="${p.id}">${T('Edit')}</button>
  <button class="btn btn-sm ${p.published?'btn-danger':'btn-quiet'}" data-act="toggle-product" data-id="${p.id}" data-published="${p.published?1:0}">${p.published?T('Unpublish'):T('Publish')}</button>
 </div>`;
}

/* The desktop table. Ordering, selection and bulk actions stay where they
   were; the only structural change is that Category now prints the operator's
   label instead of the raw value, and flags an orphan. */
function productsTable(data,allShownSelected){
 return `<div class="table-wrap product-table-wrap"><table class="data-table product-table"><thead><tr><th class="check-col"><input type="checkbox" data-select-all aria-label="${T('Select all shown products')}" ${allShownSelected?'checked':''}></th><th>${T('Product')}</th><th>${T('Category')}</th><th>${T('Price label')}</th><th>${T('Availability')}</th><th>${T('Preview link')}</th><th>${T('Visibility')}</th><th>${T('Order')}</th><th>${T('Actions')}</th></tr></thead><tbody>${data.map(p=>`<tr class="${p.published?'':'is-hidden'}"><td class="check-col"><input type="checkbox" data-select-product="${p.id}" aria-label="${T('Select')} ${esc(p.title)}" ${state.selected.has(Number(p.id))?'checked':''}></td><td><span class="cell-main">${p.featured?'★ ':''}${esc(p.title)}</span><span class="cell-sub">/${esc(p.slug)}</span></td><td>${orphanCategory(p)?`<span class="cell-main cat-orphan">${esc(categoryLabel(p.category))}</span><span class="cell-sub">${T('category removed')}</span>`:esc(categoryLabel(p.category))}</td><td>${esc(p.price_label)}</td><td>${pill(p.status)}</td><td>${safeHttp(p.github_url)?`<a class="cell-sub link-cell" href="${esc(p.github_url)}" target="_blank" rel="noopener noreferrer">${esc(String(p.github_url).replace(/^https:\/\//,'').slice(0,42))}</a>`:`<span class="cell-sub">${T('Built-in preview')}</span>`}</td><td>${pill(p.published?T('Published'):T('Hidden'))}</td><td><div class="order-ctl"><button class="chip-btn" data-act="move-product" data-id="${p.id}" data-dir="-1" aria-label="${T('Move up')}">↑</button><span class="order-num">${fmtNum(Number(p.position)||0)}</span><button class="chip-btn" data-act="move-product" data-id="${p.id}" data-dir="1" aria-label="${T('Move down')}">↓</button></div></td><td>${productActions(p)}</td></tr>`).join('')}</tbody></table></div>`;
}

/* The phone card. Everything the table shows that a person actually decides
   on is here — cover, title, category, price, state — and the controls are
   full-width buttons instead of a row of 10px chips. */
function productCards(data,allShownSelected){
 const cover=p=>p.cover?`<img src="${esc(String(p.cover).replace(/^https:\/\//,'').startsWith('brand')||String(p.cover).startsWith('/')?p.cover:p.cover)}" alt="" loading="lazy" onerror="this.parentNode.classList.add('is-empty');this.remove()">`:'';
 return `<div class="product-cards">
  <div class="product-cards-head"><label class="check-line"><input type="checkbox" data-select-all aria-label="${T('Select all shown products')}" ${allShownSelected?'checked':''}> ${T('Select all shown products')}</label></div>
  ${data.map(p=>`<article class="product-card-admin ${p.published?'':'is-hidden'}" data-card-id="${p.id}">
   <div class="pca-top">
    <span class="pca-cover ${p.cover?'':'is-empty'}">${cover(p)}</span>
    <div class="pca-title">
     <strong>${p.featured?'★ ':''}${esc(p.title)}</strong>
     <span class="pca-slug">/${esc(p.slug)}</span>
     <div class="pca-pills">${pill(p.published?T('Published'):T('Hidden'))} ${pill(p.status)}</div>
    </div>
    <label class="pca-select"><input type="checkbox" data-select-product="${p.id}" aria-label="${T('Select')} ${esc(p.title)}" ${state.selected.has(Number(p.id))?'checked':''}></label>
   </div>
   <div class="pca-facts">
    <div><small>${T('Category')}</small><span class="${orphanCategory(p)?'cat-orphan':''}">${esc(categoryLabel(p.category))}${orphanCategory(p)?' ⚠':''}</span></div>
    <div><small>${T('Price label')}</small><span>${esc(p.price_label||'—')}</span></div>
    <div><small>${T('Order')}</small><span class="order-ctl"><button class="chip-btn" data-act="move-product" data-id="${p.id}" data-dir="-1" aria-label="${T('Move up')}">↑</button><span class="order-num">${fmtNum(Number(p.position)||0)}</span><button class="chip-btn" data-act="move-product" data-id="${p.id}" data-dir="1" aria-label="${T('Move down')}">↓</button></span></div>
   </div>
   ${productActions(p)}
  </article>`).join('')}
 </div>`;
}

/* Which layout this viewport gets. 900px is where nine table columns stop being
   readable; it matches the stylesheet's breakpoint. Reading it in JS means only
   one of the two is in the DOM — rendering both and hiding one duplicated every
   product for assistive technology, and a resize re-renders rather than merely
   revealing what was already there. */
function compact(){return window.matchMedia('(max-width: 900px)').matches}
function productsHTML(){
 const q=state.search.toLowerCase();
 const data=state.products
  .filter(p=>(!q||[p.title,p.slug,p.category,p.summary].join(' ').toLowerCase().includes(q))
   &&(state.productFilter==='All'||(state.productFilter==='Published'?!!p.published:state.productFilter==='Featured'?!!p.featured:!p.published))
   &&(state.categoryFilter==='All'||(state.categoryFilter==='__orphan'?orphanCategory(p):p.category===state.categoryFilter)))
  .slice().sort(productSortCompare);
 const counts={all:state.products.length,published:state.products.filter(p=>p.published).length,hidden:state.products.filter(p=>!p.published).length,featured:state.products.filter(p=>p.featured).length};
 const sel=[...state.selected].filter(id=>state.products.some(p=>Number(p.id)===Number(id)));
 const allShownSelected=data.length>0&&data.every(p=>state.selected.has(Number(p.id)));
 const cats=siteCategories();
 return `${pageHead('Catalog management','Products','Create, order, feature and publish the products shown by the AXIASOFT site.',`<button class="btn btn-quiet" data-act="export" data-kind="products">⇩ ${T('Export CSV')}</button><button class="btn btn-primary" data-act="new-product">${ICON('plus')} ${T('Add product')}</button>`)}
 ${productStats(counts)}
 <div class="toolbar products-toolbar"><div class="toolbar-left"><label class="search"><input data-search placeholder="${T('Search title, slug or category…')}" value="${esc(state.search)}" autocomplete="off"></label>
 ${picker('product_filter', ['All','Published','Hidden','Featured'].map(x=>({value:x,label:T(x)})), state.productFilter, {label:T('Filter by visibility'), onPick:'pickerProductFilter'})}
 ${picker('category_filter',
   [{value:'All',label:T('All categories')},
    ...cats.map(c=>({value:String(c.id),label:categoryLabel(c.id)})),
    ...(state.products.some(orphanCategory)?[{value:'__orphan',label:T('No category')}]:[])],
   state.categoryFilter, {label:T('Filter by category'), onPick:'pickerCategoryFilter'})}
 ${picker('product_sort', [['manual','Manual order'],['newest','Newest first'],['title','Title A–Z'],['category','Category']].map(([v,l])=>({value:v,label:T(l)})), state.productSort, {label:T('Sort products'), onPick:'pickerProductSort'})}</div>
 <div class="toolbar-right"><span class="muted" style="font-size:10px">${fmtNum(data.length)} ${T('of')} ${fmtNum(counts.all)} ${T('products')}</span>${sel.length?`<button class="btn btn-sm btn-quiet" data-act="bulk-publish">${T('Publish')} ${fmtNum(sel.length)}</button><button class="btn btn-sm btn-danger" data-act="bulk-unpublish">${T('Hide')} ${fmtNum(sel.length)}</button>`:''}</div></div>
 <div class="panel product-panel" style="padding:14px">${data.length?`${compact()?productCards(data,allShownSelected):productsTable(data,allShownSelected)}`:`<div class="empty"><div class="empty-icon">${ICON('package')}</div>${counts.all?T('No products match these filters. Clear the filters, or add a product.'):T('The catalog is empty — add the first product.')}</div>`}
 <div class="notice">${T('Removing a product unpublishes it. Featured products lead the catalog.')}</div></div>
 <details class="fold" data-fold="categories" ${state.foldCategories?'open':''}>
   <summary class="fold-head"><span class="fold-title">${T('Catalog categories')}</span><span class="fold-meta">${fmtNum(cats.length)} ${T('categories')}</span><span class="fold-chev">${ICON('down')}</span></summary>
   ${categoriesPanel(cats, true)}
 </details>
 `;
}

/* ------------------------------------------------------------- categories */
/* The catalog's categories are edited here, not in the shape of the products
   screen: a short list with one row per category, drag-free reordering through
   the same ↑ ↓ buttons the products use, and a delete that warns when products
   still point at the row. Ids are the value products store, so they are shown
   (greyed, small) but not editable once a category exists - renaming the id
   would orphan every product in it. The labels are what the site prints. */
function categoryRow(c,i,count){
 const used=state.products.filter(p=>p.category===c.id).length;
 return `<div class="cat-row" data-cat-id="${esc(c.id)}">
  <span class="cat-handle" aria-hidden="true">${ICON('layers')}</span>
  <div class="cat-labels">
   <span class="cat-meta"><code>${esc(c.id)}</code> · ${fmtNum(used)} ${T(used===1?'product':'products')}</span>
   ${used?`<span class="cat-hint">${T('Move its products out to remove it')}</span>`:''}
  </div>
  <label class="cat-field"><span>${T('Category name')}</span><input class="cat-input" data-cat-name="${esc(c.id)}" value="${esc(c.name)}" maxlength="40" aria-label="${T('Category name')}"></label>
  <label class="cat-field"><span>${T('Persian name')}</span><input class="cat-input cat-input-fa" data-cat-name-fa="${esc(c.id)}" value="${esc(c.nameFa)}" maxlength="40" placeholder="${T('optional')}" aria-label="${T('Persian name')}" dir="rtl"></label>
  <div class="order-ctl"><button class="chip-btn" data-act="move-category" data-cat="${esc(c.id)}" data-dir="-1" aria-label="${T('Move up')}" ${i===0?'disabled':''}>↑</button><span class="order-num">${fmtNum(i+1)}</span><button class="chip-btn" data-act="move-category" data-cat="${esc(c.id)}" data-dir="1" aria-label="${T('Move down')}" ${i===count-1?'disabled':''}>↓</button></div>
  <button class="btn btn-sm ${used?'btn-quiet':'btn-danger'}" data-act="delete-category" data-cat="${esc(c.id)}" data-used="${used}" ${used?'disabled title="'+T('Move its products to another category first')+'"':''}>${T('Remove')}</button>
 </div>`;
}
function categoriesPanel(cats, bare){
 const orphaned=state.products.filter(orphanCategory);
 // `bare` means the fold above already names this panel, so it does not draw a
 // second heading of its own.
 return `<section class="panel cat-panel${bare?' cat-panel-bare':''}" id="categoriesPanel">
  ${bare?'':`<div class="panel-head"><div><h2>${T('Catalog categories')}</h2><p>${T('The tabs the public catalog offers. The site ships none; the demo carries its own.')}</p></div><span class="muted" style="font-size:10px">${fmtNum(cats.length)} ${T('categories')}</span></div>`}
  ${cats.length?`<div class="cat-list">${cats.map((c,i)=>categoryRow(c,i,cats.length)).join('')}</div>`:`<div class="empty" style="padding:18px"><div class="empty-icon">${ICON('package')}</div>${T('No categories yet. The catalog shows one grid and no tab row until you add one.')}</div>`}
  <form class="cat-add" data-form="category-add"><div class="field"><label>${T('Category name')}</label><input name="name" maxlength="40" required placeholder="${T('e.g. Websites')}"></div><div class="field"><label>${T('Persian name')}</label><input name="nameFa" maxlength="40" dir="rtl" placeholder="${T('optional')}"></div><div class="field"><label>${T('Category id')}</label><input name="id" maxlength="40" pattern="[a-z0-9-]{2,40}" required placeholder="websites"><span class="field-hint">${T('Lowercase letters, digits and hyphens. Products store this id, so it cannot change later.')}</span></div><button class="btn btn-primary">${T('Add category')}</button></form>
  ${orphaned.length?`<div class="notice">${fmtNum(orphaned.length)} ${T('products point at a category that no longer exists. Edit each one and pick a new category.')}</div>`:''}
 </section>`;
}

/* Only plain https URLs are ever rendered as a link, mirroring the storefront's
   safePreview() and the server's clean_github_url(). */
function safeHttp(u){const v=String(u||'').trim();return /^https:\/\/[^\s<>"']+$/i.test(v)?v:''}
/* ------------------------------------------------------------------ website */
/* Everything the storefront shows can be driven from here: the identity,
   the hero copy, contact details, which sections are published, and the
   first-visit theme. Fields write into the same JSON document the server and
   the static build both understand. */
const SITE_TABS=[['identity','Identity'],['brands','Site brands'],['hero','Home hero'],['sections','Visibility'],['contact','Contact & links'],['faq','Questions'],['danger','Maintenance']];
const SECTION_FIELDS=[['show_catalog','Product catalog','The products grid and product pages'],['show_services','Services page','Website, mobile and custom software services'],['show_aurion','AURION showcase','The AURION concept page and its links'],['show_about','About page','The studio story and values'],['show_contact','Contact entry points','Contact links, the header CTA and request buttons'],['show_assistant','Support assistant','The floating AXIA chat guide on the storefront'],['show_prices','Price labels','Indicative price labels on product cards and detail pages']];
/* The same sun/moon the storefront draws. The console had the old ◐/☼ pair,
   which is illegible at this size and says nothing in the light theme. */
const ADMIN_SUN='<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="4.2"/><path d="M12 2.6v2.2M12 19.2v2.2M2.6 12h2.2M19.2 12h2.2M5.4 5.4l1.6 1.6M17 17l1.6 1.6M18.6 5.4L17 7M7 17l-1.6 1.6"/></svg>';
const ADMIN_MOON='<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20.5 14.3A8.6 8.6 0 0 1 9.7 3.5a8.6 8.6 0 1 0 10.8 10.8Z"/></svg>';
function themeGlyph(){return document.documentElement.dataset.theme==='dark'?ADMIN_MOON:ADMIN_SUN}
function siteVal(key){return state.settings?.[key]??''}
function switchField(name,label,hint,on){
 return `<label class="switch"><input type="checkbox" name="${name}" ${on?'checked':''}><span class="switch-track" aria-hidden="true"></span><span class="switch-copy"><strong>${T(label)}</strong><small>${T(hint)}</small></span></label>`;
}
function fieldText(name,label,value,hint='',extra=''){
 return `<div class="field"><label for="s-${name}">${label}</label><input id="s-${name}" name="${name}" value="${esc(value??'')}" ${extra}><span class="field-hint">${hint}</span></div>`;
}
/* ---------------------------------------------------------------- brands */
/* The site brands are what the Websites tab offers as a starting point: pick
   one and the whole site wears that name, logo and accent colour. They used to
   be hardcoded in public/brands.js, which meant a new brand needed a code edit
   and a redeploy. They are a settings list now, edited here.
   The editor keeps the working copy in state.siteBrands and only writes on
   save, so a half-typed brand never reaches the storefront. */
/* The admin console does not load app.js, so assetUrl() from the storefront is
   not in scope here. Brand assets are stored root- or base-relative, and the
   console lives one level down, so they resolve through AXIA_BASE exactly as
   the storefront resolves them. */
function brandAsset(path){
 const raw=String(path||'').trim();
 if(!raw)return '';
 if(/^(?:https?:)?\/\//i.test(raw))return raw;
 return baseUrl(raw);
}
/* Prefix an absolute path with the deploy base.

   The console page always lives at <deploy base>admin/, so its own path is the
   most reliable statement of the base: /AxiaPlatform/admin/ implies
   /AxiaPlatform/. AXIA_STATIC.base is preferred when the build shipped
   static-config.js to this page, and the derived value covers the case where it
   did not — which is how brand assets used to 404 at the server root.

   Every link the console hands the browser goes through here. The blog "View"
   link did not, so on GitHub Pages it pointed at /blog/<slug>/ when the file is
   at /AxiaPlatform/blog/<slug>/ — a 404 on a page that had just been published. */
function baseUrl(path){
 const raw=String(path||'').trim();
 if(!raw)return '';
 if(/^(?:https?:)?\/\//i.test(raw))return raw;
 const fromConfig=String((window.AXIA_STATIC&&window.AXIA_STATIC.base)||'');
 const fromPath=(location.pathname.replace(/\/admin\/?[^/]*$/,'/'));
 const base=(fromConfig||fromPath).replace(/\/$/,'')+'/';
 if(base!=='/'&&raw.startsWith(base))return raw;
 return base+raw.replace(/^\//,'');
}
function brandDraft(){
 if(!Array.isArray(state.siteBrands))state.siteBrands=(siteVal('brands')||[]).map(b=>({...b}));
 return state.siteBrands;
}
/* The little square at the top of a brand row. It shows the uploaded mark when
   there is one and the brand's initial when there is not, so the row is never a
   blank tile and an operator can see at a glance which brands still need an
   image. */
function brandSwatch(b){
 const path=b.mark||b.logo||'';
 if(path)return `<img src="${esc(brandAsset(path))}" alt="" onerror="this.replaceWith(document.createTextNode('·'))">`;
 const initial=String(b.name||b.nameFa||'·').trim()[0].toUpperCase();
 return `<span class="brand-swatch-glyph" aria-hidden="true">${esc(initial)}</span>`;
}
function brandRowHTML(b,i){
 return `<div class="brand-edit" data-brand-row="${i}">
  <div class="brand-edit-head">
   <span class="brand-swatch" style="--swatch:${esc(b.accent||'#1f5fa8')}">${brandSwatch(b)}</span>
   <div><strong>${esc(b.name||T('New brand'))}</strong><span class="muted">${esc(b.nameFa||'')}</span></div>
   <div class="brand-edit-actions">
    <button class="btn btn-sm btn-quiet" type="button" data-act="brand-up" data-i="${i}" ${i===0?'disabled':''} title="${T('Move up')}">↑</button>
    <button class="btn btn-sm btn-quiet" type="button" data-act="brand-down" data-i="${i}" ${i===brandDraft().length-1?'disabled':''} title="${T('Move down')}">↓</button>
    <button class="btn btn-sm btn-quiet danger" type="button" data-act="brand-remove" data-i="${i}" title="${T('Remove this brand')}">${T('Remove')}</button>
   </div>
  </div>
  <div class="setting-grid">
   <div class="field"><label for="b-${i}-id">${T('Id')}</label><input id="b-${i}-id" data-brand="${i}" data-field="id" maxlength="31" value="${esc(b.id)}" placeholder="arya"><span class="field-hint">${T('Lowercase letters, numbers and hyphens. Used in the link.')}</span></div>
   <div class="field"><label for="b-${i}-name">${T('Name (English)')}</label><input id="b-${i}-name" data-brand="${i}" data-field="name" maxlength="40" value="${esc(b.name)}" placeholder="Arya"></div>
   <div class="field"><label for="b-${i}-nameFa">${T('Name (Persian)')}</label><input id="b-${i}-nameFa" data-brand="${i}" data-field="nameFa" maxlength="40" value="${esc(b.nameFa)}" placeholder="آریا" dir="rtl"></div>
   <div class="field"><label for="b-${i}-tagline">${T('Tagline (English)')}</label><input id="b-${i}-tagline" data-brand="${i}" data-field="tagline" maxlength="90" value="${esc(b.tagline)}" placeholder="${T('Software with wings.')}"></div>
   <div class="field"><label for="b-${i}-taglineFa">${T('Tagline (Persian)')}</label><input id="b-${i}-taglineFa" data-brand="${i}" data-field="taglineFa" maxlength="90" value="${esc(b.taglineFa)}" placeholder="نرم‌افزاری با بال‌های پرواز." dir="rtl"></div>
   <div class="field"><label for="b-${i}-accent">${T('Accent colour')}</label><input id="b-${i}-accent" type="color" data-brand="${i}" data-field="accent" value="${esc(b.accent||'#1f5fa8')}"><span class="field-hint">${T('Drives buttons, links and the glow behind the header.')}</span></div>
   <div class="field"><label for="b-${i}-accentSoft">${T('Soft accent')}</label><input id="b-${i}-accentSoft" type="color" data-brand="${i}" data-field="accentSoft" value="${esc(b.accentSoft||b.accent||'#3f8ad8')}"><span class="field-hint">${T('The lighter half of the gradient.')}</span></div>
   <div class="field brand-asset-field"><label>${T('Header mark')}</label>${brandAssetField(i,'mark',b.mark,T('Small square emblem shown in the header.'))}</div>
   <div class="field brand-asset-field"><label>${T('Card logo')}</label>${brandAssetField(i,'logo',b.logo,T('Wider lockup for the brand card. Falls back to the mark.'))}</div>
  </div>
 </div>`;
}
/* One image slot for a brand: the current picture, a picker and a remove.
   Two things are kept in step — the visible preview and the hidden input the
   form reads — so a save sends exactly the path shown.

   A brand mark is transparent artwork, not a photograph, so nothing is
   re-encoded or cropped here: the bytes are stored and shown as they are.
   The text field stays for a path an operator already has in the repo. */
function brandAssetField(i, which, current, hint){
 const url = current ? brandAsset(current) : '';
 return `<div class="brand-asset" data-brand-asset="${which}">
   <input type="hidden" data-brand="${i}" data-field="${which}" value="${esc(current||'')}" data-brand-asset-input>
   <span class="brand-asset-preview" data-brand-asset-preview>${url?`<img src="${esc(url)}" alt="">`:'<span class="brand-asset-empty">—</span>'}</span>
   <div class="brand-asset-actions">
    <label class="btn btn-sm btn-quiet"><input type="file" accept="image/png,image/jpeg,image/webp,image/gif,image/svg+xml" hidden data-brand-asset-file>${T('Choose image…')}</label>
    <button class="btn btn-sm btn-quiet" type="button" data-act="brand-asset-clear" ${current?'':'hidden'}>${T('Remove')}</button>
    <input class="brand-asset-path" type="text" maxlength="200" value="${esc(current||'')}" placeholder="brand/arya-mark.png" data-brand-asset-path aria-label="${T('Or type a path')}">
   </div>
   <span class="field-hint">${hint}</span>
   <span class="brand-asset-status" data-brand-asset-status role="status"></span>
  </div>`;
}
function faqDraft(){
 if(!Array.isArray(state.siteFaq))state.siteFaq=(siteVal('faq')||[]).map(x=>({...x}));
 return state.siteFaq;
}
function faqRowHTML(x,i){
 /* Both languages on every row. The Persian pair is optional — the storefront
    falls back to the English text — but keeping the two inputs side by side is
    what stops an operator from writing an English answer and forgetting there
    is a Persian site. */
 return `<div class="brand-edit" data-faq-row="${i}">
  <div class="brand-edit-head">
   <span class="brand-swatch" style="--swatch:#2f6fd0"><span class="brand-swatch-glyph" aria-hidden="true">?</span></span>
   <div><strong>${esc(x.q||T('New question'))}</strong><span class="muted">${esc(x.qFa||'')}</span></div>
   <div class="brand-edit-actions">
    <button class="btn btn-sm btn-quiet" type="button" data-act="faq-up" data-i="${i}" ${i===0?'disabled':''} title="${T('Move up')}">↑</button>
    <button class="btn btn-sm btn-quiet" type="button" data-act="faq-down" data-i="${i}" ${i===faqDraft().length-1?'disabled':''} title="${T('Move down')}">↓</button>
    <button class="btn btn-sm btn-quiet danger" type="button" data-act="faq-remove" data-i="${i}">${T('Remove')}</button>
   </div>
  </div>
  <div class="setting-grid">
   <div class="field full"><label for="f-${i}-q">${T('Question (English)')}</label><input id="f-${i}-q" data-faq="${i}" data-field="q" maxlength="160" value="${esc(x.q||'')}" placeholder="Does AURION place trades?"><span class="field-hint">${T('Shown on the AURION page and its plan landing.')}</span></div>
   <div class="field full"><label for="f-${i}-a">${T('Answer (English)')}</label><textarea id="f-${i}-a" data-faq="${i}" data-field="a" maxlength="900" rows="3" placeholder="No. This showcase does not connect to a broker or execute trades.">${esc(x.a||'')}</textarea><span class="field-hint">${T('Two or three sentences is the sweet spot. This is the whole answer a visitor reads.')}</span></div>
   <div class="field full"><label for="f-${i}-qFa">${T('Question (Persian)')}</label><input id="f-${i}-qFa" data-faq="${i}" data-field="qFa" maxlength="160" dir="rtl" value="${esc(x.qFa||'')}" placeholder="آیا اوریون معامله انجام می‌دهد؟"><span class="field-hint">${T('Leave empty to show the English question on the Persian site.')}</span></div>
   <div class="field full"><label for="f-${i}-aFa">${T('Answer (Persian)')}</label><textarea id="f-${i}-aFa" data-faq="${i}" data-field="aFa" maxlength="900" rows="3" dir="rtl" placeholder="نه. این نمایش به کارگزاری متصل نمی‌شود و معامله‌ای اجرا نمی‌کند.">${esc(x.aFa||'')}</textarea><span class="field-hint">${T('Leave empty to show the English answer on the Persian site.')}</span></div>
  </div>
 </div>`;
}
function faqTabHTML(){
 const list=faqDraft();
 return `<div class="panel form-panel"><div class="panel-head"><div><h2>${T('Frequently asked questions')}</h2><p>${T('The questions under the AURION plans, shown on both the product page and its landing.')}</p></div></div>
  <div class="notice">${T('An empty list removes the questions section entirely.')} ${T('Order here is the order on the site.')}</div>
  <form data-form="faq"><div class="brand-edit-list">${list.length?list.map(faqRowHTML).join(''):'<div class="empty">'+T('No questions yet. The AURION page will not show a questions section until you add one.')+'</div>'}</div>
  <div class="form-actions">
   <button class="btn btn-primary" type="submit">${T('Save questions')}</button>
   <button class="btn btn-quiet" type="button" data-act="faq-add">+ ${T('Add question')}</button>
   <button class="btn btn-quiet" type="button" data-act="settings-reset">${T('Discard changes')}</button>
  </div></form></div>`;
}
function brandsTabHTML(){
 const list=brandDraft();
 return `<div class="panel form-panel"><div class="panel-head"><div><h2>${T('Site brands')}</h2><p>${T('The starting points on the Websites tab. Picking one wears that brand everywhere.')}</p></div><span class="pill blue">${list.length} ${T(list.length===1?'brand':'brands')}</span></div>
  <div class="notice">${T('A brand changes the header, the accent and the page title for that visitor only.')} ${T('Order here is the order on the site.')} ${T('Remove a brand to hide it; products are untouched.')}</div>
  <form data-form="brands"><div class="brand-edit-list">${list.length?list.map(brandRowHTML).join(''):'<div class="empty">'+T('No brands yet. The Websites tab will not offer a brand picker until you add one.')+'</div>'}</div>
  <div class="form-actions">
   <button class="btn btn-primary" type="submit">${T('Save brands')}</button>
   <button class="btn btn-quiet" type="button" data-act="brand-add">+ ${T('Add brand')}</button>
   <button class="btn btn-quiet" type="button" data-act="settings-reset">Discard changes</button>
  </div></form></div>`;
}
function siteTabHTML(){
 const t=state.siteTab;
 if(t==='hero'){
  return `<div class="panel form-panel"><div class="panel-head"><div><h2>Home hero</h2><p>The first three lines a visitor reads.</p></div><button class="btn btn-sm btn-quiet" data-act="preview-site" data-target="#/">Preview ${ICON('external')}</button></div>
   <form data-form="settings"><div class="setting-grid">${fieldText('hero_title','Headline',siteVal('hero_title'),'Shown in white. Keep it under about 45 characters so it does not wrap awkwardly.','maxlength="90" required')}${fieldText('hero_accent','Highlighted line',siteVal('hero_accent'),'Shown in the gradient, directly under the headline.','maxlength="90"')}
   <div class="field full"><label for="s-hero_subtitle">Sub-headline</label><textarea id="s-hero_subtitle" name="hero_subtitle" maxlength="300" rows="3">${esc(siteVal('hero_subtitle'))}</textarea><span class="field-hint">One or two sentences about what the studio does.</span></div></div>
   <div class="form-actions"><button class="btn btn-primary" type="submit">Save hero</button><button class="btn btn-quiet" type="button" data-act="settings-reset">Discard changes</button></div></form></div>`;
 }
 if(t==='sections'){
  return `<div class="panel form-panel"><div class="panel-head"><div><h2>Page visibility</h2><p>Hide a whole area of the site without deleting anything.</p></div></div>
   <form data-form="settings"><div class="switch-list">${SECTION_FIELDS.map(([name,label,hint])=>switchField(name,label,hint,visibleSetting(name))).join('')}</div>
   <div class="notice">Hidden pages stay in the site and simply return a short "not published" message. Nothing is deleted, and links to hidden pages disappear from the header, footer and home page.</div>
   <div class="form-actions"><button class="btn btn-primary" type="submit">Save visibility</button><button class="btn btn-quiet" type="button" data-act="settings-reset">Discard changes</button></div></form></div>`;
 }
 if(t==='contact'){
  return `<div class="panel form-panel"><div class="panel-head"><div><h2>Contact and links</h2><p>Where visitors reach you, and the footer line under the logo.</p></div></div>
   <form data-form="settings"><div class="setting-grid">${fieldText('contact_email','Support email',siteVal('contact_email'),'Shown in the footer and used as a mailto link.','type="email" maxlength="254" placeholder="hello@axiasoft.dev"')}
   ${fieldText('contact_phone','Phone',siteVal('contact_phone'),'Optional. Rendered as a click-to-call link.','maxlength="40" placeholder="+49 911 000000"')}
   ${fieldText('github_url','GitHub organisation',siteVal('github_url'),'Opened in a new tab from the footer. Must start with https://.','maxlength="300" placeholder="https://github.com/AxiaSoft"')}
   <div class="field full"><label for="s-footer_note">Footer note</label><input id="s-footer_note" name="footer_note" maxlength="120" value="${esc(siteVal('footer_note'))}"><span class="field-hint">The short sentence next to the footer logo.</span></div></div>
   <div class="form-actions"><button class="btn btn-primary" type="submit">Save contact details</button><button class="btn btn-quiet" type="button" data-act="settings-reset">Discard changes</button></div></form></div>`;
 }
 if(t==='danger'){
  return `<div class="panel"><div class="panel-head"><div><h2>Maintenance</h2><p>Bulk actions for the catalog and the browser demo.</p></div></div>
   <div class="danger-grid">
    <div class="danger-card"><strong>Publish every hidden product</strong><p>Puts all hidden products back in the public catalog. Order history is untouched.</p><button class="btn btn-quiet" data-act="bulk-publish-all">Publish all</button></div>
    <div class="danger-card"><strong>Hide the whole catalog</strong><p>Removes the products page from the site navigation and shows a short notice there.</p><button class="btn btn-danger" data-act="hide-catalog">Hide catalog</button></div>
    <div class="danger-card"><strong>Support agent (Xiona)</strong>
     <p>${state.agent? (function(a){
        /* "A key is set" is not "the model answers". The old copy said a live
           model was answering whenever a key existed, so a revoked key or a
           model Google had shut down still read as healthy while every visitor
           silently got the on-site answer. Ask what actually happened. */
        const base=T('Grounded in')+' '+a.topics+' '+T('published site facts.');
        const at=a.model_base? ' @ '+esc(a.model_base||'') : '';
        if(a.model_state==='ok') return T('A live model is answering')+' — '+esc(a.model||'')+at+'. '+base;
        if(a.model_state==='untested') return T('A model is configured but has not answered yet')+' — '+esc(a.model||'')+at+'. '+T('Ask the assistant one question to check it.')+' '+base;
        if(a.model_state==='failing') return T('The model is configured but its last call failed')+' — '+esc(a.model_last_error||'')+'. '+T('Visitors are getting the on-site answer.')+' '+base;
        if(a.provider==='model') return T('Local retrieval only')+': '+a.topics+' '+T('approved facts, no outbound request.');
        return T('Local retrieval only')+': '+a.topics+' '+T('approved facts, no API key, no outbound request.')+' '+T('Set AXIA_AGENT_KEY and AXIA_AGENT_URL to let a model answer.');
      })(state.agent)
        : T('Status unavailable in this mode.')}</p>
     <p class="form-hint">Free options: Groq, Google AI Studio (Gemini), OpenRouter free tier, Mistral, Cerebras, or a local Ollama — all OpenAI-compatible.</p></div>
   <div class="danger-card"><strong>Load sample catalog</strong><p>Demo only: adds six illustrative products with GitHub preview links so the catalog and dashboard have something to show.</p><button class="btn btn-quiet" data-act="demo-samples">Load samples</button></div>
    <div class="danger-card"><strong>Reset demo data</strong><p>Only in the GitHub Pages demo: clears the browser copy of products and settings, then reloads. Nothing in the repository changes.</p><button class="btn btn-danger" data-act="demo-reset">Reset demo</button></div>
    <div class="danger-card"><strong>Export settings</strong><p>Downloads the current settings as JSON, ready to commit as <code>data/settings.json</code>.</p><button class="btn btn-quiet" data-act="export-settings">Export JSON</button></div>
   </div><div class="notice">Deleting an account or a request is deliberately not possible here; those records stay for audit. Products are hidden rather than deleted so old requests keep their references.</div></div>`;
 }
 const s=state.settings||{};
 return `<div class="panel form-panel"><div class="panel-head"><div><h2>Site identity</h2><p>The first-visit theme for visitors who have never chosen one.</p></div></div>
  <form data-form="settings"><div class="setting-grid"><div class="field"><label for="s-default_theme">Default theme</label>${picker('default_theme', [['dark','Dark'],['light','Light'],['system','Match the device']].map(([v,l])=>({value:v,label:T(l)})), s.default_theme||'dark', {id:'s-default_theme', label:T('Default theme'), onPick:'pickerMarkDirty'})}<span class="field-hint">A visitor's own saved choice always wins.</span></div>
  <div class="field"><label>Site address</label><input value="${esc(location.origin)}" readonly><span class="field-hint">The host this console publishes to.</span></div>
  <div class="field full"><label>Administrator</label><input value="${esc(state.me?.name||'')} · ${esc(state.me?.email||'')}" readonly><span class="field-hint">Roles are enforced by the server, not by this screen.</span></div></div>
  <div class="form-actions"><button class="btn btn-primary" type="submit">Save identity</button></div></form></div>`;
}
function visibleSetting(name){return state.settings?state.settings[name]!==false:true}
function siteHTML(){
 const dirty=state.dirty;
 return `${pageHead('Storefront control','Website','Control the home hero, contact details and which sections the public site shows.',`<button class="btn btn-quiet" data-act="settings-refresh">${ICON('refresh')} Reload</button><button class="btn btn-quiet" data-act="preview-site" data-target="/">Open site ${ICON('external')}</button>`)}
 <div class="tabs">${SITE_TABS.map(([id,label])=>`<button class="tab ${state.siteTab===id?'active':''}" data-site-tab="${id}">${T(label)}</button>`).join('')}</div>
 ${dirty?`<div class="dirty-note" role="status"><span>●</span> Unsaved changes on this page — press <strong>Save</strong> to publish them to the site.</div>`:''}
 <div class="site-tab-body">${siteTabHTML()}</div>`;
}
/* ------------------------------------------------------------ one customer
   The directory answers "who are my customers". This answers "who is this
   one", and it is the page an operator asks for when a customer writes in:
   their details, what they ordered, what they paid or asked back, what they
   have said to support, and what has happened on the account.

   Every control here is one the server already enforces. Nothing on this page
   can move money or reveal a credential, and the page says so where a control
   looks more powerful than it is.
   ---------------------------------------------------------------------- */

async function openCustomer(id) {
  state.customerId = Number(id);
  state.customer = null;
  $('#pageContent').innerHTML = `<div class="panel" style="padding:26px"><p class="empty-note">Loading customer…</p></div>`;
  try {
    const r = await api('/api/admin/customers/detail?id=' + Number(id));
    state.customer = r;
  } catch (e) {
    $('#pageContent').innerHTML = `<div class="panel" style="padding:26px"><p class="empty-note">${esc(e.message)}</p><button class="btn btn-quiet" data-act="customer-back">← Back to customers</button></div>`;
    return;
  }
  $('#pageContent').innerHTML = customerHTML();
}

function backToCustomers() {
  state.customerId = null;
  state.customer = null;
  $('#pageContent').innerHTML = customersHTML();
}

/* The profile is one record split into the four questions an operator
   actually has, in that order, rather than one long dump. */
function customerHTML() {
  const r = state.customer;
  if (!r) return '';
  const c = r.customer;
  const open = r.tickets.filter(t => t.status !== 'Closed').length;
  const appr = r.refunds.filter(x => x.status === 'Approved').length;
  const ticketRows = r.tickets.length ? r.tickets.map(t => `<div class="cust-row"><div class="cust-row-main"><b>${esc(t.subject)}</b><span class="cell-sub">${esc(t.ref)} · ${esc(moneyFreeDate(t.created_at))}${t.priority && t.priority !== 'Normal' ? ` · <span class="pri pri-${esc(String(t.priority).toLowerCase())}">${esc(T(t.priority))}</span>` : ''}</span></div><div class="cust-row-side">${pill(T(t.status))}<button class="btn btn-sm btn-quiet" data-act="customer-ticket" data-id="${t.id}">Open thread</button></div></div>`).join('') : '<p class="empty-note">No support conversations.</p>';
  const orderRows = r.orders.length ? r.orders.map(o => `<div class="cust-row"><div class="cust-row-main"><b>${esc(o.number)} · ${esc(o.product_title || 'Project request')}</b><span class="cell-sub">${esc(moneyFreeDate(o.created_at))}</span></div><div class="cust-row-side"><span class="status-pill">${esc(T(o.status))}</span>${picker('status', ['Submitted','Under Review','Requirements Analysis','Quotation Sent','Awaiting Confirmation','In Development','Testing','Ready for Delivery','Delivered','Cancelled'].map(x=>({value:x,label:T(x)})), o.status, {className:'cust-status', label:T('Status'), onPick:'pickerCustomerOrderStatus', dataId:o.id})}</div></div>`).join('') : '<p class="empty-note">No project requests.</p>';
  const refundRows = r.refunds.length ? r.refunds.map(x => `<div class="cust-row"><div class="cust-row-main"><b>${esc(x.order_number || '')} · ${esc(x.ref)}</b><span class="cell-sub">${esc(x.reason)}</span></div><div class="cust-row-side">${pill(T(x.status))}${x.status === 'Under review' ? `<button class="btn btn-sm btn-quiet" data-act="customer-refund" data-id="${x.id}" data-decision="Approved">${esc(T('Approve'))}</button><button class="btn btn-sm btn-quiet" data-act="customer-refund" data-id="${x.id}" data-decision="Rejected">${esc(T('Reject'))}</button>` : ''}</div></div>`).join('') : '<p class="empty-note">No refund requests.</p>';
  const eventRows = r.events.length ? r.events.slice(0, 18).map(e => `<div class="cust-event"><span>${esc(moneyFreeDate(e.created_at))}</span><b>${esc(T(e.action))}</b><span class="cell-sub">${esc(e.entity)}${e.entity_id ? ' · ' + esc(e.entity_id) : ''}${e.actor_name ? ' · ' + esc(e.actor_name) : ''}</span></div>`).join('') : '<p class="empty-note">No recorded activity.</p>';
  return `${pageHead(esc(c.name), 'Customer profile', 'Everything recorded about this account, and the controls the server allows over it.', `<button class="btn btn-quiet" data-act="customer-back">← All customers</button>`)}
  <div class="stat-grid">
    <div class="panel stat"><small>${esc(T('Requests'))}</small><strong>${fmtNum(r.orders.length)}</strong></div>
    <div class="panel stat"><small>${esc(T('Open conversations'))}</small><strong>${fmtNum(open)}</strong></div>
    <div class="panel stat"><small>${esc(T('Refunds'))}</small><strong>${fmtNum(r.refunds.length)}${appr ? ` <span class="cell-sub">${appr} ${esc(T('approved'))}</span>` : ''}</strong></div>
    <div class="panel stat"><small>${esc(T('Account'))}</small><strong style="font-size:15px">${pill(T(c.active ? 'Active' : 'Suspended'))}</strong></div>
  </div>
  <div class="panel" style="padding:18px;margin-bottom:18px">
    <h2 style="font-size:15px;margin:0 0 14px">${esc(T('Details'))}</h2>
    <div class="cust-facts">
      <div><small>${esc(T('Name'))}</small><b>${esc(c.name)}</b></div>
      <div><small>${esc(T('Email'))}</small><b>${esc(c.email)}</b></div>
      <div><small>${esc(T('Phone'))}</small><b>${esc(c.phone || T('No phone on file'))}</b></div>
      <div><small>${esc(T('Customer ID'))}</small><b>${c.id}</b></div>
      <div><small>${esc(T('Joined'))}</small><b>${esc(moneyFreeDate(c.created_at))}</b></div>
      <div><small>${esc(T('Role'))}</small><b>${esc(T(c.role))}</b></div>
    </div>
    <div class="cust-actions">
      <button class="btn ${c.active ? 'btn-danger' : 'btn-quiet'}" data-act="customer-status" data-id="${c.id}" data-active="${c.active ? 1 : 0}">${esc(T(c.active ? 'Suspend account' : 'Reactivate account'))}</button>
      <span class="lock-note">${esc(T('Suspending revokes active sessions immediately.'))} ${esc(T('Passwords and card details are never shown, and nothing here moves money.'))}</span>
    </div>
  </div>
  <div class="panel" style="padding:18px;margin-bottom:18px"><div class="panel-head"><div><h2>${esc(T('Project requests'))}</h2><p>${esc(T('Change a status here and the customer sees it in their account.'))}</p></div></div>${orderRows}</div>
  <div class="panel" style="padding:18px;margin-bottom:18px"><div class="panel-head"><div><h2>${esc(T('Refunds'))}</h2><p>${esc(T('A decision is recorded only. No money is transferred.'))}</p></div></div>${refundRows}</div>
  <div class="panel" style="padding:18px;margin-bottom:18px"><div class="panel-head"><div><h2>${esc(T('Support'))}</h2><p>${esc(T('Replies written from the ticket thread reach the customer in their messages page.'))}</p></div></div>${ticketRows}</div>
  <div class="panel" style="padding:18px"><div class="panel-head"><div><h2>${esc(T('Activity'))}</h2><p>${esc(T('Sign-ins, changes and decisions recorded against this account.'))}</p></div></div>${eventRows}</div>`;
}

/* From a customer's profile into one of their conversations.
   The profile already has the ticket, so it is handed straight to openTicket()
   rather than being looked up in an inbox this page never fetched. */
function openCustomerTicket(id){
  const t=(state.customer?.tickets||[]).find(x=>Number(x.id)===Number(id));
  if(!t){toast(T('That conversation is no longer available.'),true);return}
  openTicket(id, t);
}

/* Order status and refund decisions are re-issued from here, reusing the same
   endpoints the Orders and Refunds tabs use, then the profile is redrawn so the
   operator sees the new state in place. */


async function customerRefund(btn) {
  const decision = btn.dataset.decision;
  if (!await confirmDialog({title:`${decision} this refund?`,
    body:'The decision is recorded in the audit log. No money moves: this build has no payment provider connected.',
    confirmLabel:decision, cancelLabel:'Back'})) return;
  try {
    await api('/api/admin/refunds/decision', { method: 'PUT', body: { id: Number(btn.dataset.id), status: decision, note: '' } });
    toast(T('Refund decision recorded.'));
    await openCustomer(state.customerId);
  } catch (e) { toast(e.message, true); }
}

function customersHTML(){const data=state.customers.filter(c=>{const q=state.search.toLowerCase();return !q||[c.name,c.email,c.phone].join(' ').toLowerCase().includes(q)});return`${pageHead('Customer records','Customers','View customer accounts and their support/request counts. Account access changes revoke active sessions.',`<button class="btn btn-quiet" data-act="export" data-kind="customers">${ICON('download')} Export CSV</button>`)}${toolbar('Search name, email or phone…')}<div class="panel" style="padding:14px"><div class="panel-head"><div><h2>Customer directory</h2><p>${fmtNum(data.length)} ${T('records · customer accounts only')}</p></div></div>${data.length?`<div class="table-wrap"><table class="data-table"><thead><tr><th>Customer</th><th>Contact</th><th>Joined</th><th>Requests</th><th>Tickets</th><th>Access</th><th>Action</th></tr></thead><tbody>${data.map(c=>`<tr><td><span class="cell-main"><a href="#" data-act="customer-open" data-id="${c.id}" style="color:inherit;text-decoration:none;border-bottom:1px solid var(--line)">${esc(c.name)}</a></span><span class="cell-sub">Customer ID ${c.id}</span></td><td>${esc(c.email)}<span class="cell-sub">${esc(c.phone||'No phone on file')}</span></td><td>${moneyFreeDate(c.created_at)}</td><td>${fmtNum(c.order_count)}</td><td>${fmtNum(c.ticket_count)}</td><td>${pill(T(c.active?'Active':'Suspended'))}</td><td style="white-space:nowrap"><button class="btn btn-sm btn-quiet" data-act="customer-open" data-id="${c.id}">${T('Open profile')}</button> <button class="btn btn-sm ${c.active?'btn-danger':'btn-quiet'}" data-act="customer-status" data-id="${c.id}" data-active="${c.active?1:0}">${T(c.active?'Suspend':'Reactivate')}</button></td></tr>`).join('')}</tbody></table></div>`:`<div class="empty">No customers found.</div>`}<div class="notice">Suspending an account blocks future sign-in and invalidates its active sessions. Admin accounts cannot be changed from this screen.</div></div>`}
function supportHTML(){const data=state.tickets.filter(t=>{const q=state.search.toLowerCase();return(!q||[t.ref,t.email,t.subject,t.message].join(' ').toLowerCase().includes(q))&&(state.statusFilter==='All'||t.status===state.statusFilter)});return`${pageHead('Customer care','Support tickets','Review conversations and reply through the website support channel.',`<button class="btn btn-quiet" data-act="export" data-kind="tickets">${ICON('download')} Export CSV</button>`)}${toolbar('Search reference, email or subject…',['All','Open','In progress','Closed'])}<div class="panel" style="padding:14px"><div class="panel-head"><div><h2>Support inbox</h2><p>${fmtNum(data.length)} ${T('matching tickets')}</p></div></div>${data.length?`<div class="table-wrap"><table class="data-table"><thead><tr><th>Reference</th><th>Customer email</th><th>Subject / first message</th><th>Priority</th><th>Created</th><th>Status</th><th></th></tr></thead><tbody>${data.map(t=>`<tr><td><span class="cell-main">${esc(t.ref)}</span></td><td>${esc(t.email)}</td><td><span class="cell-main">${esc(t.subject)}</span><span class="cell-sub">${esc(t.message)}</span></td><td>${t.priority&&t.priority!=='Normal'?`<span class="pri pri-${esc(String(t.priority).toLowerCase())}">${esc(T(t.priority))}</span>`:`<span class="cell-sub">${esc(T('Normal'))}</span>`}</td><td>${moneyFreeDate(t.created_at)}</td><td>${pill(t.status)}</td><td style="white-space:nowrap">${t.unread_for_team?`<span class="pill amber">${t.unread_for_team} new</span> `:''}<button class="btn btn-sm btn-quiet" data-act="view-ticket" data-id="${t.id}">Open thread</button></td></tr>`).join('')}</tbody></table></div>`:`<div class="empty"><div class="empty-icon">${ICON('inbox')}</div>No tickets found.</div>`}</div>`}
function refundsHTML(){const data=state.refunds.filter(r=>{const q=state.search.toLowerCase();return(!q||[r.ref,r.order_number,r.reason,r.status].join(' ').toLowerCase().includes(q))&&(state.statusFilter==='All'||r.status===state.statusFilter)});return`${pageHead('Policy review','Refund requests','Review requests against the published policy. This panel does not issue payments or move funds.',`<button class="btn btn-quiet" data-act="export" data-kind="refunds">${ICON('download')} Export CSV</button>`)}${toolbar('Search request, order or reason…',['All','Under review','Approved','Rejected'])}<div class="panel" style="padding:14px"><div class="panel-head"><div><h2>Refund queue</h2><p>${fmtNum(data.filter(x=>x.status==='Under review').length)} ${T('awaiting a decision')} · ${fmtNum(data.length)} ${T('total shown')}</p></div></div>${data.length?`<div class="table-wrap"><table class="data-table"><thead><tr><th>Request</th><th>Order</th><th>Reason</th><th>Submitted</th><th>Status</th><th>Decision</th></tr></thead><tbody>${data.map(r=>`<tr><td><span class="cell-main">${esc(r.ref)}</span></td><td>${esc(r.order_number)}</td><td><span class="cell-sub reason-cell">${esc(r.reason)}</span></td><td>${moneyFreeDate(r.created_at)}</td><td>${pill(r.status)}</td><td>${r.status==='Under review'?`<div class="row-actions"><button class="btn btn-sm btn-primary" data-act="refund-decision" data-id="${r.id}" data-decision="Approved">Approve</button><button class="btn btn-sm btn-danger" data-act="refund-decision" data-id="${r.id}" data-decision="Rejected">Reject</button></div>`:`<span class="cell-sub">${esc(r.admin_note||'Decision recorded')}</span>`}</td></tr>`).join('')}</tbody></table></div>`:`<div class="empty">No refund requests found.</div>`}<div class="notice">Approval records a review decision only. No payment is processed or guaranteed. Requests are subject to applicable law and the published policy.</div></div>`}
/* ---------------------------------------------------------------------------
   Blog articles
   ---------------------------------------------------------------------------
   The editor is deliberately Word-like: a toolbar of formatting buttons over a
   contenteditable surface, with a word count, a live preview of exactly what
   the public page will show, and autosave to localStorage so a reload never
   loses a draft. The textarea is the source of truth (plain text + light
   markdown), because the server renders it and a contenteditable's HTML would
   not survive that round trip faithfully. */
function articlesHTML(){
 const rows=state.articles||[];
 const editing=state.articleDraft;
 if(editing)return editorHTML(editing);
 const published=rows.filter(a=>a.status==='published').length;
 const cards=rows.length?rows.map(a=>`<article class="article-row">
   <div class="article-row-main">
     <div class="article-row-meta"><span class="pill ${a.status==='published'?'green':'blue'}">${a.status==='published'?'Published':'Draft'}</span>
       <time>${moneyFreeDate(a.published_at||a.updated_at)}</time><span>${fmtNum(a.reading_minutes||1)} min read</span></div>
     <h3>${esc(a.title)}</h3>
     <p>${esc(a.summary||'')}</p>
     <small>/${esc(a.slug)}</small>
   </div>
   <div class="article-row-actions">
     <a class="btn btn-sm btn-quiet" href="${baseUrl(`blog/${esc(a.slug)}/`)}" target="_blank" rel="noopener">View ${ICON('external')}</a>
     <button class="btn btn-sm btn-quiet" data-act="edit-article" data-id="${a.id}">Edit</button>
     <button class="btn btn-sm btn-danger" data-act="delete-article" data-id="${a.id}">Delete</button>
   </div>
 </article>`).join(''):`<div class="empty-state">No articles yet. Write the first one — it publishes to /blog/ with its own page, sitemap entry and RSS item.</div>`;
 return `<div class="panel-head"><div><h2>Blog articles</h2><p>${fmtNum(rows.length)} total · ${fmtNum(published)} published · ${fmtNum(rows.length-published)} draft</p></div>
   <button class="btn btn-sm btn-primary" data-act="new-article">✎ New article</button></div>
 <div class="article-list">${cards}</div>
 <div class="panel-foot"><h3>How publishing works</h3>
   <p>Articles are rendered on the server at <code>/blog/&lt;slug&gt;/</code> with a canonical URL, Open Graph tags,
   <code>BlogPosting</code> structured data and an entry in <code>/sitemap.xml</code> and <code>/blog/feed.xml</code>.
   That is what lets a search engine index them without running JavaScript. Publish, then submit the sitemap once in
   Google Search Console.</p></div>`}

const ARTICLE_TOOLS=[
 ['h2','Heading','H'],['h3','Subheading','h'],['bold','Bold','B'],['italic','Italic','I'],
 ['ul','Bullet list','•'],['ol','Numbered list','1.'],['quote','Quote','❝'],
 ['code','Code','</>'],['link','Link','🔗'],['hr','Divider','—']
];

function editorHTML(a){
 const tags=(a.tags||[]).join(', ');
 const words=(a.body||'').trim().split(/\s+/).filter(Boolean).length;
 return `<div class="editor-bar">
   <button class="btn btn-sm btn-quiet" data-act="close-article">← Back</button>
   <div class="editor-bar-mid"><strong>${a.id?'Editing':'New article'}</strong><small>${fmtNum(words)} words · ${fmtNum(Math.max(1,Math.round(words/200)))} min read</small></div>
   <div class="editor-bar-right">
     <button class="btn btn-sm btn-quiet" data-act="article-preview">Preview</button>
     <button class="btn btn-sm btn-quiet" data-act="save-article" data-status="draft">Save draft</button>
     <button class="btn btn-sm btn-primary" data-act="save-article" data-status="published">${a.status==='published'?'Update':'Publish'}</button>
   </div>
 </div>
 <form data-form="article" class="editor-form" data-id="${a.id||''}">
  <div class="editor-fields">
   <label class="field"><span>Title</span><input name="title" value="${esc(a.title||'')}" maxlength="120" placeholder="A clear, specific headline" required></label>
   <label class="field"><span>URL slug</span><input name="slug" value="${esc(a.slug||'')}" maxlength="90" placeholder="leave empty to generate from the title" dir="ltr"></label>
  </div>
  <label class="field"><span>Summary <small>(shown on the blog card and used as the meta description)</small></span><textarea name="summary" rows="2" maxlength="320" placeholder="One or two sentences that make someone want to read on.">${esc(a.summary||'')}</textarea></label>
  <label class="field"><span>Tags <small>(comma separated, up to 6)</small></span><input name="tags" value="${esc(tags)}" placeholder="design, engineering, seo"></label>
  <div class="field"><span>Article</span>
    <div class="rte">
      <div class="rte-toolbar">${ARTICLE_TOOLS.map(([cmd,label,glyph])=>`<button type="button" class="rte-btn" data-rte="${cmd}" title="${label}" aria-label="${label}">${glyph}</button>`).join('')}</div>
      <div class="rte-surface" id="articleBody" contenteditable="true" role="textbox" aria-multiline="true" aria-label="Article body" spellcheck="true">${markdownToEditorHTML(a.body||'')}</div>
    </div>
    <small class="field-hint">Line breaks create paragraphs. Use the toolbar for headings, lists, quotes, code and links. Everything is escaped before it renders.</small>
  </div>
 </form>`}

/* The editor shows the article as formatted text. The markdown itself lives in
   the hidden store below so nothing is lost while the editor rewrites blocks. */
function markdownToEditorHTML(md){
 const esc2=v=>String(v??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
 return md.split(/\n{2,}/).map(block=>{
   const b=block.trim(); if(!b)return '';
   if(/^###\s/.test(b))return `<h3>${esc2(b.replace(/^###\s+/,''))}</h3>`;
   if(/^##\s/.test(b))return `<h2>${esc2(b.replace(/^##\s+/,''))}</h2>`;
   if(/^#\s/.test(b))return `<h2>${esc2(b.replace(/^#\s+/,''))}</h2>`;
   if(/^[-*]\s/m.test(b))return `<ul>${b.split('\n').map(l=>`<li>${esc2(l.replace(/^[-*]\s+/,''))}</li>`).join('')}</ul>`;
   if(/^\d+[.)]\s/m.test(b))return `<ol>${b.split('\n').map(l=>`<li>${esc2(l.replace(/^\d+[.)]\s+/,''))}</li>`).join('')}</ol>`;
   if(/^>\s?/m.test(b))return `<blockquote>${esc2(b.replace(/^>\s?/gm,''))}</blockquote>`;
   if(/^```/.test(b))return `<pre>${esc2(b.replace(/^```\w*\n?|```$/g,''))}</pre>`;
   if(/^---$/.test(b))return '<hr>';
   return `<p>${esc2(b).replace(/\n/g,'<br>')}</p>`;
 }).join('')}

/* And back again, so the textarea the server receives is plain markdown. */
function editorHTMLToMarkdown(root){
 const out=[];
 root.childNodes.forEach(node=>{
   if(node.nodeType===3){const t=node.textContent.trim();if(t)out.push(t);return}
   if(node.nodeType!==1)return;
   const tag=node.tagName.toLowerCase();
   if(tag==='br')return;
   const text=node.textContent.trim(); if(!text)return;
   if(tag==='h2')out.push('## '+text);
   else if(tag==='h3')out.push('### '+text);
   else if(tag==='h4'||tag==='h5')out.push('#### '+text);
   else if(tag==='ul')out.push([...node.querySelectorAll('li')].map(li=>'- '+li.textContent.trim()).join('\n'));
   else if(tag==='ol')out.push([...node.querySelectorAll('li')].map((li,i)=>`${i+1}. ${li.textContent.trim()}`).join('\n'));
   else if(tag==='blockquote')out.push(node.textContent.trim().split('\n').map(l=>'> '+l).join('\n'));
   else if(tag==='pre')out.push('```\n'+node.textContent.replace(/\n+$/,'')+'\n```');
   else if(tag==='hr')out.push('---');
   else out.push(text);
 });
 return out.join('\n\n')}

/* ---- editor behaviour ------------------------------------------------- */

/* Format the current selection. Uses execCommand deliberately: it is the only
   formatting API that behaves the same across Chrome, Firefox and Safari, and
   the output is converted back to markdown before it ever reaches the server. */
function applyFormat(cmd){
 const surface=$('#articleBody'); if(!surface)return;
 surface.focus();
 const sel=window.getSelection();
 const wrap={
   bold:['strong',null], italic:['em',null], h2:['h2',null], h3:['h3',null],
   ul:['ul','insertUnorderedList'], ol:['ol','insertOrderedList'],
   quote:['blockquote','formatBlock'], code:['pre','formatBlock'], hr:['hr','insertHorizontalRule']
 }[cmd];
 if(cmd==='h2'||cmd==='h3'){document.execCommand('formatBlock',false,cmd==='h2'?'h2':'h3');return}
 if(cmd==='ul'||cmd==='ol'){document.execCommand(cmd==='ul'?'insertUnorderedList':'insertOrderedList');return}
 if(cmd==='quote'){document.execCommand('formatBlock',false,'blockquote');return}
 if(cmd==='code'){document.execCommand('formatBlock',false,'pre');return}
 if(cmd==='hr'){document.execCommand('insertHorizontalRule');return}
 if(cmd==='bold'){document.execCommand('bold');return}
 if(cmd==='italic'){document.execCommand('italic');return}
 if(cmd==='link'){
   const url=prompt('Link address (https://… or #/path)','https://');
   if(!url)return;
   if(sel&&!sel.isCollapsed)document.execCommand('createLink',false,url);
   else document.execCommand('insertHTML',false,`<a href="${url.replace(/"/g,'&quot;')}">${url.replace(/</g,'&lt;')}</a>`);
   return
 }}

function openArticle(id){
 const cached=(state.articles||[]).find(a=>a.id===id);
 if(cached)state.articleDraft=Object.assign({},cached);
 api('/api/admin/articles/'+id).then(full=>{state.articleDraft=Object.assign({},full); $('#pageContent').innerHTML=contentHTML()})
   .catch(err=>{if(!cached)toast(err.message);else  $('#pageContent').innerHTML=contentHTML()})}

/* Reading the form is shared by the two save paths (the form's submit, and the
   Publish button in the toolbar, which sits outside the form). */
function readArticleForm(){
 const form=$('[data-form="article"]'); if(!form)return null;
 const surface=$('#articleBody');
 const values={};
 new FormData(form).forEach((v,k)=>{values[k]=v});
 values.body=surface?editorHTMLToMarkdown(surface):'';
 values.tags=(values.tags||'').split(',').map(t=>t.trim()).filter(Boolean);
 values.id=+(form.dataset.id||0)||undefined;
 return values}

function saveArticle(form,status){
 const values=readArticleForm(); if(!values)return;
 if(status)values.status=status;
 if(!values.status)values.status='draft';
 if(!values.title||values.title.trim().length<4){toast('Give the article a title first.');$('[name="title"]')?.focus();return}
 if((values.body||'').trim().length<40){toast('Write at least a short paragraph.');$('#articleBody')?.focus();return}
 const btn=$('[data-act="save-article"][data-status="'+values.status+'"]');
 if(btn){btn.disabled=true;btn.textContent=values.status==='published'?'Publishing…':'Saving…'}
 const method=values.id?'PUT':'POST';
 api('/api/admin/articles',{method,body:values})
   .then(async res=>{
     toast(values.status==='published'?'Published to /blog/.':'Draft saved.');
     state.articleDraft=null;
     state.articles=(await api('/api/admin/articles')).articles||[];
      $('#pageContent').innerHTML=contentHTML()})
   .catch(err=>{
     if(btn){btn.disabled=false;btn.textContent=values.status==='published'?'Publish':'Save draft'}
     toast(err.message)})}

function previewArticle(){
 const values=readArticleForm(); if(!values)return;
 const title=values.title||'Untitled';
 const html=blogMarkdown(values.body||'');
 showModal(`<section class="modal modal-wide" role="dialog" aria-modal="true" aria-label="Article preview">
   <div class="modal-head"><div><h2>${esc(title)}</h2><p>Preview · exactly what /blog/ will show</p></div>
   <button class="btn btn-sm btn-quiet" data-act="close-modal" aria-label="Close">${ICON('close')}</button></div>
   <article class="preview-article"><div class="blog-prose">${html}</div></article>
   <p class="form-hint" style="margin-top:16px">The public page adds the headline, date, reading time, tags and structured data around this body.</p>
 </section>`)}

async function deleteArticle(id){
 const row=(state.articles||[]).find(a=>a.id===id);
 if(!await confirmDialog({title:'Delete this article?',
    body:`\u201c${esc(row?row.title:'this article')}\u201d comes off the site immediately: its page, its sitemap entry and its RSS item all go. This cannot be undone.`,
    confirmLabel:'Delete article', cancelLabel:'Keep it', danger:true}))return;
 api('/api/admin/articles',{method:'DELETE',body:{id}})
   .then(async()=>{toast('Article deleted.');state.articles=(await api('/api/admin/articles')).articles||[]; $('#pageContent').innerHTML=contentHTML()})
   .catch(err=>toast(err.message))}

/* ---------------------------------------------------------------------------
   The article renderer, in the browser.
   ---------------------------------------------------------------------------
   The server renders articles (server/blog.py) because search engines have to
   receive real HTML. The console also needs to render one, for the live
   preview, so this is a line-for-line port of the same rules. If you change
   one, change the other: they must agree, or the preview lies. */
function blogMarkdown(source){
 const escapeHTML=v=>String(v??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
 if(!source)return '';
 const inline=text=>{
   let protected_=text.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g,(m,label,href)=>{
     if(!/^(https?:\/\/|#\/|\/)/.test(href))return m;
     return '\u0000LINK'+label+'\u0000'+href+'\u0001'});
   protected_=escapeHTML(protected_);
   protected_=protected_.replace(/`([^`\n]+)`/g,'<code>$1</code>')
     .replace(/\*\*([^*\n]+)\*\*/g,'<strong>$1</strong>')
     .replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g,'$1<em>$2</em>');
   return protected_.replace(/\u0000LINK(.*?)\u0000(.*?)\u0001/g,(m,label,href)=>{
     if(!/^(https?:\/\/|#\/|\/)/.test(href.trim()))return '['+label+']('+href+')';
     return '<a href="'+escapeHTML(href.trim())+'">'+label+'</a>'})};

 const lines=String(source).replace(/\r\n?/g,'\n').split('\n');
 const out=[]; let buffer=[], mode=null;
 const flush=()=>{
   if(!buffer.length){mode=null;return}
   if(mode==='ul')out.push('<ul>'+buffer.map(x=>'<li>'+inline(x)+'</li>').join('')+'</ul>');
   else if(mode==='ol')out.push('<ol>'+buffer.map(x=>'<li>'+inline(x)+'</li>').join('')+'</ol>');
   else if(mode==='quote')out.push('<blockquote>'+buffer.map(x=>'<p>'+inline(x)+'</p>').join(' ')+'</blockquote>');
   else if(mode==='code')out.push('<pre><code>'+escapeHTML(buffer.join('\n'))+'</code></pre>');
   buffer=[]; mode=null};

 for(let i=0;i<lines.length;i++){
   const raw=lines[i], line=raw.replace(/\s+$/,''), trimmed=line.trim();
   if(trimmed.startsWith('```')){ if(mode==='code')flush(); else {flush();mode='code'} continue }
   if(mode==='code'){ buffer.push(raw); continue }
   if(!trimmed){ flush(); continue }
   if(/^(-{3,}|\*{3,})$/.test(trimmed)){ flush(); out.push('<hr>'); continue }
   const heading=trimmed.match(/^(#{1,4})\s+(.*)$/);
   if(heading){ flush(); const lvl=Math.min(heading[1].length+1,5); out.push('<h'+lvl+'>'+inline(heading[2])+'</h'+lvl+'>'); continue }
   const bullet=trimmed.match(/^[-*+]\s+(.*)$/);
   if(bullet){ if(mode!=='ul'){flush();mode='ul'} buffer.push(bullet[1]); continue }
   const numbered=trimmed.match(/^\d{1,3}[.)]\s+(.*)$/);
   if(numbered){ if(mode!=='ol'){flush();mode='ol'} buffer.push(numbered[1]); continue }
   const quoted=trimmed.match(/^>\s?(.*)$/);
   if(quoted){ if(mode!=='quote'){flush();mode='quote'} buffer.push(quoted[1]); continue }
   if(mode==='ul'||mode==='ol'||mode==='quote'){ buffer[buffer.length-1]+=' '+trimmed; continue }
   flush(); out.push('<p>'+inline(trimmed)+'</p>')}
 flush();
 return out.join('\n')}

function activityHTML(){return`${pageHead('Security & operations','Activity log','Recent audited administrative and account events. The log is read-only.',`<button class="btn btn-quiet" data-act="refresh">${ICON('refresh')} Refresh log</button>`)}<div class="panel activity-panel"><div class="panel-head"><div><h2>Audit events</h2><p>Latest ${fmtNum(state.audit.length)} recorded events</p></div></div>${state.audit.length?`<div class="activity-list" tabindex="0" aria-label="${T('Audit events')}">${state.audit.map(a=>`<div class="activity-item"><span class="activity-dot">${iconFor(a.entity)}</span><div><strong>${esc(actionLabel(a.action))} · ${esc(a.entity)}</strong><p>${esc(a.actor_name||'System')} ${a.actor_email?`(${esc(a.actor_email)})`:''} · Record ${esc(a.entity_id)}</p></div><time>${moneyFreeDate(a.created_at)}</time></div>`).join('')}</div>`:`<div class="empty">No audited events recorded yet.</div>`}</div>`}
/* ---------------------------------------------------------------- admins
   Who else can open this console, and what each of them may reach.

   There is exactly one owner: the account that can create, re-role and reset
   every other administrator. It cannot be demoted or removed from here,
   because doing so would leave the console with nobody able to hand out a
   role, and no second owner to undo it. Recovery for a lost owner password is
   a command on the server (server/reset_owner.py), not a button - the trust
   boundary for "I control every administrator" should be shell access.
*/
function adminsHTML(){
  const data = state.admins || {admins:[], roles:[], is_owner:false};
  const roles = data.roles || [];
  const list = data.admins || [];
  const isOwner = !!data.is_owner;

  const roleChips = r => `<span class="role-chip role-${esc(r)}">${esc(T((roles.find(x=>x.id===r)||{}).label || r))}</span>`;

  const rows = list.map(a => `
    <tr>
      <td><span class="cell-main">${esc(a.name)}</span><span class="cell-sub">${esc(a.email)}</span></td>
      <td>${roleChips(a.admin_role)}</td>
      <td>${a.is_me ? `<span class="pill">${esc(T('You'))}</span>` : (a.active ? `<span class="pill green">${esc(T('Active'))}</span>` : `<span class="pill amber">${esc(T('Suspended'))}</span>`)}</td>
      <td style="white-space:nowrap">
        ${a.is_owner ? `<span class="cell-sub">${esc(T('Fixed role'))}</span>` : (isOwner ? `
          ${picker('admin_role', roles.filter(r=>r.id!=='owner').map(r=>({value:r.id,label:T(r.label)})), a.admin_role, {label:T('Role'), onPick:'pickerAdminRole', dataId:a.id})}
          <button class="btn btn-sm btn-quiet" data-act="admin-password" data-id="${a.id}" data-email="${esc(a.email)}">${ICON('lock')} ${esc(T('Reset password'))}</button>
          <button class="btn btn-sm btn-danger" data-act="admin-remove" data-id="${a.id}" data-email="${esc(a.email)}">${ICON('trash')} ${esc(T('Remove'))}</button>
        ` : `<span class="cell-sub">${esc(T('Owner only'))}</span>`)}
      </td>
    </tr>`).join('');

  const roleCards = roles.map(r => `
    <div class="role-card ${r.id==='owner'?'is-owner':''}">
      <div class="role-card-head">${roleChips(r.id)}<small>${esc(T(r.summary))}</small></div>
      <div class="role-perms">${(r.permissions||[]).map(p=>`<span class="perm">${esc(T(p))}</span>`).join('')}</div>
    </div>`).join('');

  const form = state.adminForm;
  const formHTML = form ? `
    <form data-form="admin-create" class="panel" style="padding:20px">
      <div class="panel-head"><div><h2>${esc(T('New administrator'))}</h2><p>${esc(T('They sign in at /admin/ with this email and password.'))}</p></div></div>
      <div class="form-grid">
        <div class="field"><label for="adm-name">${esc(T('Name'))}</label><input id="adm-name" name="name" required minlength="2" maxlength="120"></div>
        <div class="field"><label for="adm-email">${esc(T('Email'))}</label><input id="adm-email" name="email" type="email" required maxlength="254"></div>
        <div class="field"><label for="adm-role">${esc(T('Role'))}</label>
          ${picker('admin_role', roles.filter(r=>r.id!=='owner').map(r=>({value:r.id,label:`${T(r.label)} · ${T(r.summary)}`})), 'support', {id:'adm-role', label:T('Role')})}</div>
        <div class="field"><label for="adm-pass">${esc(T('Initial password'))}</label><input id="adm-pass" name="password" type="password" required minlength="12" autocomplete="new-password"><span class="field-hint">${esc(T('At least 12 characters. Give it to them directly; there is no email in this build.'))}</span></div>
      </div>
      <div class="row-actions" style="margin-top:14px">
        <button class="btn btn-primary" type="submit">${ICON('check')} ${esc(T('Create administrator'))}</button>
        <button class="btn btn-quiet" type="button" data-act="admin-form-cancel">${esc(T('Cancel'))}</button>
      </div>
    </form>` : '';

  return `${pageHead('Access control','Administrators',
      'Who can open this console, and what each role reaches. The owner is fixed: it is the account that hands out every other role.',
      isOwner ? `<button class="btn btn-primary" data-act="admin-new">${ICON('plus')} ${esc(T('New administrator'))}</button>` : '')}
    ${state.adminsError?`<div class="panel" style="padding:16px;border-color:rgba(255,90,110,.35)"><p style="margin:0;color:var(--red)">${esc(state.adminsError)}</p></div>`:''}
    ${formHTML}
    <div class="panel" style="padding:14px">
      <div class="panel-head"><div><h2>${esc(T('Administrators'))}</h2><p>${fmtNum(list.length)} ${esc(T('accounts'))}</p></div></div>
      <div class="table-wrap"><table class="data-table">
        <thead><tr><th>${esc(T('Account'))}</th><th>${esc(T('Role'))}</th><th>${esc(T('Status'))}</th><th></th></tr></thead>
        <tbody>${rows || `<tr><td colspan="4"><span class="cell-sub">${esc(T('No administrators yet.'))}</span></td></tr>`}</tbody>
      </table></div>
    </div>
    <div class="panel" style="padding:20px">
      <div class="panel-head"><div><h2>${esc(T('What each role reaches'))}</h2><p>${esc(T('Chosen when the account is created. Every console route checks it on the server.'))}</p></div></div>
      <div class="role-grid">${roleCards}</div>
      <div class="notice" style="margin-top:16px">${ICON('shield')} ${esc(T('Only the owner appoints administrators. A reset ends every session.'))}</div>
      <p class="form-hint" style="margin-top:12px">${esc(T('Locked out? Run python3 server/reset_owner.py on the server.'))}</p>
    </div>`;
}

function actionLabel(s){return({create:'Created',update:'Updated',unpublish:'Unpublished',status_change:'Changed order status',ticket_status:'Changed ticket status',ticket_reply:'Replied to ticket',refund_decision:'Recorded refund decision',customer_access:'Changed customer access',settings:'Updated website settings',login:'Signed in',register:'Registered'})[s]||s}
function contentHTML(){switch(state.page){case'site':return siteHTML();case'articles':return articlesHTML();case'orders':return ordersHTML();case'products':return state.productDraft ? productDraftHTML() : productsHTML();case'customers':return customersHTML();case'support':return supportHTML();case'refunds':return refundsHTML();case'activity':return activityHTML();case'admins':return adminsHTML();default:return overviewHTML()}}
async function fetchPageData(){state.loading=true;try{
 if(state.page==='dashboard'){
state.overview=await api('/api/admin/overview');
state.orders=state.overview.orders||[];
state.products=state.overview.products||[];
state.settings=state.overview.settings||state.settings;
state.lastSync=new Date();
state.audit=await api('/api/admin/audit?limit=8').catch(()=>state.audit||[])}
 else if(state.page==='site'){
const r=await api('/api/admin/settings');
state.settings=r.settings||state.settings;
state.overview=state.overview||await api('/api/admin/overview').catch(()=>null);
state.lastSync=new Date();
state.dirty=false}
 else if(state.page==='orders'){state.overview=state.overview||await api('/api/admin/overview');state.orders=state.overview.orders||[]}
 else if(state.page==='products'){
  state.overview=state.overview||await api('/api/admin/overview');
  state.products=state.overview.products||[];
  /* This screen prints category labels and edits the category list, so it needs
     the settings document the site also reads. It is fetched only when it is not
     already in memory: the Website page loads it too, and an operator moving
     between the two should not pay for it twice. */
  if(!state.settings){try{const r=await api('/api/admin/settings');state.settings=r.settings||null}catch(e){state.settings=null}}
 }
 else if(state.page==='customers'){const r=await api('/api/admin/customers');state.customers=r.customers||[]}
 else if(state.page==='admins'){state.admins=await api('/api/admin/admins')}
 else if(state.page==='support'){try{state.tickets=await api('/api/support')}catch(e){state.tickets=[]}}
 else if(state.page==='refunds'){try{state.refunds=await api('/api/refunds')}catch(e){state.refunds=[]}}
 else if(state.page==='articles')state.articles=(await api('/api/admin/articles')).articles||[]
 if(state.page==='dashboard')state.agent=await api('/api/admin/agent').catch(()=>null)
 else if(state.page==='activity')state.audit=await api('/api/admin/audit?limit=150')
 }catch(e){if(e.status===401||e.status===403){state.me=null;state.csrf=null;/* Both paths go through T(): the 403 text is this file's own English, and a
   401's message comes from the server. Either way a Persian console has to
   show Persian, and the fallback is the server's wording, untranslated but
   truthful, rather than an empty red box. */
  loginView(e.status===403?T('Administrator access required. Please sign in with an administrator account.'):T(e.message));return}toast(e.message,true)}finally{state.loading=false}
 $('#pageContent')&&($('#pageContent').innerHTML=contentHTML());updateNav();
}
function updateNav(){ $$('.side-link[data-page]').forEach(b=>b.classList.toggle('active',b.dataset.page===state.page));const title=$('.crumb strong');if(title)title.textContent=({dashboard:'Overview',site:'Website',orders:'Project requests',products:'Products',customers:'Customers',support:'Support',refunds:'Refunds',activity:'Activity log'})[state.page]||'Overview';const side=$('#sidebar');if(side)side.classList.remove('open');$('.side-scrim')?.classList.remove('show') }
async function loadSession(){try{const s=await api('/api/me');state.me=s.user;state.csrf=s.csrf}catch{state.me=null;state.csrf=null}if(!state.me){loginView();return}if(state.me.role!=='admin'){deniedView();return}if(!root.querySelector('.admin-shell'))shell();await fetchPageData()}
async function nav(page){
if(state.dirty&&!await confirmDialog({title:'Discard your changes?',
    body:'The settings on this tab have not been saved. Leaving loses them.',
    confirmLabel:'Discard', cancelLabel:'Keep editing', danger:true}))return;
state.dirty=false;
state.page=page;
state.search='';
state.selected=new Set();
state.statusFilter='All';
state.productFilter='All';
state.categoryFilter='All';
if(location.hash!=='#'+page)history.replaceState(null,'','#'+page);updateNav();fetchPageData()}
function showModal(html,wide=false){overlays.innerHTML=`<div class="modal-backdrop" data-act="backdrop-close"><section class="modal ${wide?'modal-wide':''}" role="dialog" aria-modal="true">${html}</section></div>`;document.body.style.overflow='hidden';$('.modal input, .modal select, .modal textarea',overlays)?.focus()}
function closeModal(){overlays.innerHTML='';document.body.style.overflow=''}

/* A question with two buttons, in the console's own clothes.

   window.confirm() is a browser widget: it carries the browser's font, the
   browser's language and the browser's button order, and on some platforms it
   says "OK / Cancel" in a language the operator may not read. It is also
   blocking, so nothing on the page can run while it is open - which is why the
   console could not show what an action was about to affect.

   This returns a promise that resolves true or false, so callers keep the shape
   they already had:
       if (!await confirmDialog({...})) return;
*/
function confirmDialog({title, body='', confirmLabel='Confirm', cancelLabel='Cancel',
                        danger=false, extra=''}={}){
  return new Promise(resolve=>{
    const done = value => { closeModal(); resolve(value); };
    showModal(`${modalHead('Confirm', esc(title))}
      <div class="modal-body"><p style="margin:0 0 14px;line-height:1.75">${body}</p>${extra}</div>
      <div class="row-actions" style="margin-top:18px;justify-content:flex-end">
        <button class="btn btn-quiet" type="button" data-confirm-no>${esc(cancelLabel)}</button>
        <button class="btn ${danger?'btn-danger':'btn-primary'}" type="button" data-confirm-yes>${esc(confirmLabel)}</button>
      </div>`);
    const yes = overlays.querySelector('[data-confirm-yes]');
    const no = overlays.querySelector('[data-confirm-no]');
    if (yes) yes.onclick = () => done(true);
    if (no) no.onclick = () => done(false);
    // The backdrop and the X are the other way of saying no.
    overlays.querySelector('.modal-backdrop').addEventListener('click', e => {
      if (e.target === e.currentTarget) done(false);
    });
    overlays.querySelector('[data-act="close-modal"]')?.addEventListener('click', () => done(false));
    if (yes) yes.focus();
  });
}

/* Open one listbox, choose, close. Only one is ever open, and a click anywhere
   else or Escape closes it - the same two ways a <select> closes. */
function closePickers(except){
  document.querySelectorAll('[data-picker].is-open').forEach(p=>{
    if(p===except)return;
    p.classList.remove('is-open');
    const btn=p.querySelector('[data-picker-btn]'), list=p.querySelector('[data-picker-list]');
    if(btn)btn.setAttribute('aria-expanded','false');
    if(list)list.hidden=true;
  });
}
function togglePicker(pickerEl, open){
  const btn=pickerEl.querySelector('[data-picker-btn]'), list=pickerEl.querySelector('[data-picker-list]');
  if(!btn||!list)return;
  const next = open===undefined ? list.hidden : open;
  if(next)closePickers(pickerEl);
  pickerEl.classList.toggle('is-open',next);
  btn.setAttribute('aria-expanded',String(next));
  list.hidden=!next;
  if(next){
    const on=list.querySelector('.picker-option.is-on')||list.querySelector('.picker-option');
    if(on)on.focus();
  }
}
document.addEventListener('toggle', e => {
  const fold = e.target.closest && e.target.closest('[data-fold="categories"]');
  if (fold) state.foldCategories = fold.open;
}, true);

document.addEventListener('click',e=>{
  const btn=e.target.closest('[data-picker-btn]');
  if(btn){togglePicker(btn.closest('[data-picker]'));return}
  const opt=e.target.closest('[data-picker-option]');
  if(opt){
    const host=opt.closest('[data-picker]');
    const input=host.querySelector('[data-picker-input]');
    const value=opt.dataset.value;
    const act=host.dataset.pickerAct;
    // Close and commit *before* calling anything that might re-render the page.
    // The callback does exactly that - the filter handlers replace #pageContent
    // - and a re-render detaches this whole picker, so anything that touched
    // host after the callback would be working on a node that is no longer in
    // the document (the list it looks for is already gone).
    togglePicker(host,false);
    host.querySelectorAll('[data-picker-option]').forEach(o=>{
      const on=o===opt;
      o.classList.toggle('is-on',on);
      o.setAttribute('aria-selected',on?'true':'false');
      const tick=o.querySelector('.icon');
      if(on&&!tick)o.insertAdjacentHTML('beforeend',ICON('check'));
      if(!on&&tick)tick.remove();
    });
    const label=opt.querySelector('span');
    const shown=host.querySelector('.picker-value');
    if(shown){shown.textContent=label?label.textContent:'';shown.classList.remove('is-empty')}
    // The hidden input is what a <select> used to be. It is filled here, before
    // the callback runs, so a `change` listener sees the new value.
    if(input)input.value=value;
    if(act&&typeof window[act]==='function')window[act](value,host);
    else if(input)input.dispatchEvent(new Event('change',{bubbles:true}));
    return;
  }
  if(!e.target.closest('[data-picker]'))closePickers();
});
document.addEventListener('keydown',e=>{
  const open=document.querySelector('[data-picker].is-open');
  if(!open)return;
  if(e.key==='Escape'){e.preventDefault();const b=open.querySelector('[data-picker-btn]');togglePicker(open,false);if(b)b.focus();return}
  if(e.key!=='ArrowDown'&&e.key!=='ArrowUp')return;
  e.preventDefault();
  const opts=[...open.querySelectorAll('[data-picker-option]')];
  const i=opts.indexOf(document.activeElement);
  const next=e.key==='ArrowDown'?Math.min(opts.length-1,i+1):Math.max(0,i-1);
  if(opts[next])opts[next].focus();
});

/* Reset an administrator's password. The owner types the new one and passes it
   on; there is no mail server in this build, so inventing a "we emailed you" step
   would be a lie on screen. */
function openResetModal(id, email){
  showModal(`${modalHead('Access', esc(T('Reset password')))}
    <form data-form="admin-password" data-id="${id}">
      <div class="modal-body">
        <p style="margin:0 0 14px;color:var(--muted);font-size:12px;line-height:1.7">
          ${esc(T('Set a new password for'))} <strong>${esc(email)}</strong>.
          ${esc(T('Every session that account has open ends now.'))}
        </p>
        <div class="field"><label for="adm-reset">${esc(T('New password'))}</label>
          <input id="adm-reset" name="password" type="password" required minlength="12" autocomplete="new-password">
          <span class="field-hint">${esc(T('At least 12 characters.'))}</span></div>
      </div>
      <div class="row-actions" style="margin-top:18px;justify-content:flex-end">
        <button class="btn btn-quiet" type="button" data-act="close-modal">${esc(T('Cancel'))}</button>
        <button class="btn btn-primary" type="submit">${ICON('lock')} ${esc(T('Set password'))}</button>
      </div>
    </form>`);
}

/* The console's own way of telling the operator something happened. It sits in
   the corner for a few seconds; nothing blocks. */
function toast(message){
  let box = document.getElementById('admin-toast');
  if (!box){ box = document.createElement('div'); box.id = 'admin-toast'; box.className = 'admin-toast'; document.body.append(box); }
  box.textContent = message;
  box.classList.add('show');
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => box.classList.remove('show'), 3200);
}

function modalHead(kicker,title,sub=''){return`<div class="modal-head"><div><div class="eyebrow">${kicker}</div><h2>${title}</h2>${sub?`<p>${sub}</p>`:''}</div><button class="icon-close" type="button" data-act="close-modal" aria-label="Close">${ICON('close')}</button></div>`}
async function openOrder(id){const o=state.orders.find(x=>x.id===Number(id));if(!o)return;showModal(`${modalHead('Project request',esc(o.number),`${esc(o.product_title)} · submitted ${moneyFreeDate(o.created_at)}`)}<div class="detail-grid"><div class="detail-item"><small>Customer</small><strong>${esc(o.name)}</strong></div><div class="detail-item"><small>Email / phone</small><strong>${esc(o.email)}<br>${esc(o.phone)}</strong></div><div class="detail-item"><small>Contact preference</small><strong>${esc(o.contact_method||'Email')}</strong></div><div class="detail-item"><small>Current status</small><strong>${pill(o.status)}</strong></div><div class="detail-item full"><small>Project details</small><p>${esc(o.description)}</p></div><div class="detail-item full"><small>Additional requirements</small><p>${esc(o.requirements||'No additional requirements supplied.')}</p></div></div><h3 style="font-size:11px;margin:19px 0 9px">Status history</h3><div class="timeline" id="orderTimeline"><div class="skeleton" style="width:70%;margin:8px"></div><div class="skeleton" style="width:50%;margin:8px"></div></div><form data-form="order-update" data-id="${o.id}"><div class="form-grid"><div class="field"><label>Update status</label>${picker('status', ordersStatus.map(x=>({value:x,label:T(x)})), o.status, {label:T('Status')})}</div><div class="field"><label>Internal status note</label><input name="note" maxlength="1000" placeholder="Optional note for the audit trail"></div></div><div class="modal-actions"><button class="btn btn-quiet" type="button" data-act="close-modal">Close</button><button class="btn btn-primary">Save status update</button></div></form>`,true);
 try{const history=await api(`/api/admin/orders/${Number(id)}/history`);const box=$('#orderTimeline');if(box)box.innerHTML=history.length?history.map(h=>`<div class="timeline-item"><strong>${esc(h.status)}</strong><p>${esc(h.note||'Status recorded')}</p><small>${moneyFreeDate(h.created_at)} · ${esc(h.actor_name||'System')}</small></div>`).join(''):'<div class="muted" style="font-size:9px">No history yet.</div>'}catch(e){const box=$('#orderTimeline');if(box)box.innerHTML=`<div class="muted" style="font-size:9px">${esc(e.message)}</div>`}
}
/* The product form. It was one flat list of twelve fields in DOM order, which
   is how a form ends up with the price label between the slug and the summary
   and the description three screens below the title. The same fields are here,
   grouped into the four decisions an operator actually makes in order:

     Content → Presentation → Links → Publishing

   Each group is a <fieldset> with a legend, so the grouping is real structure
   for a screen reader and for the stylesheet, not just a heading in the markup.
   Categories come from the settings document (the operator's list), and a
   product whose category has been deleted keeps it available as an option so
   saving the product cannot silently move it somewhere else. */
/* The product editor's own page header, replacing the modal title it had.
   A page can say where it goes back to; a modal could only be dismissed. */
function productFormHead(edit, p){
  return `<div class="page-head"><div><div class="eyebrow">${T(edit?'Catalog editor':'New catalog product')}</div>
    <h1>${T(edit?'Edit product':'Add a product concept')}</h1>
    <p>${T(edit?'Changes affect the public product data, its featured slot and its order.':'Add a product to the database-backed catalog.')}</p></div>
    <div class="head-actions"><button class="btn btn-quiet" type="button" data-act="product-cancel">${ICON('back')} ${T('Back to products')}</button></div></div>`;
}

/* Open the product editor as a page of the console.

   It was a modal. A modal cannot be scrolled from the browser's scrollbar,
   cannot be linked to, cannot survive a refresh, and on a phone the keyboard
   covers the field you are typing in with no way to move the dialog. The
   fields are unchanged; only where they are drawn has moved. */
async function openProductEditor(p){
  state.productDraft = p ? p.id : 'new';
  const html = await productForm(p);
  if (!html) return;                       // the "add a category first" guard
  if (location.hash !== '#products') history.replaceState(null, '', '#products');
  state.page = 'products';
  $('#pageContent').innerHTML = html;
  updateNav();
}
/* contentHTML() draws the draft synchronously on a re-render, so a refresh or a
   language switch does not throw away what the operator opened. */
function productDraftHTML(){
  const p = state.productDraft === 'new'
    ? null
    : state.products.find(x => Number(x.id) === Number(state.productDraft));
  return productForm(p, true) || productsHTML();
}

async function productForm(p=null, sync=false){
 const edit=!!p;
 /* The categories live in the settings document. Fetch it if this screen has
    not already, so the form is not limited to the one route that preloads it. */
 if(!state.settings && !sync){
  try{const r=await api('/api/admin/settings');state.settings=r.settings||null}catch(e){state.settings=null}
 }
 const cats=siteCategories();
 /* A product cannot be saved without a category the site can print, and the
    category list is the operator's. Rather than let the form submit into a 400
    from the API, the whole action is refused with the reason on screen and a
    button that jumps to the editor below. */
 if(!cats.length){
  if(!sync) $('#pageContent').innerHTML = `${modalHead('Catalog editor',T('Add a category first'),T('Products are filed under a category, and this site has none yet.'))}
   <p class="muted" style="font-size:11px;line-height:1.8">${T('Categories are the tabs the public catalog offers.')} ${T('Add one below, then come back and add the product.')}</p>
   <div class="form-actions"><button class="btn btn-quiet" type="button" data-act="product-cancel">${T('Cancel')}</button><button class="btn btn-primary" type="button" data-act="goto-categories">${T('Go to categories')}</button></div>`;
  return '';
 }
 const current=p?.category||(cats[0]?.id||'');
 // A product whose category was deleted keeps its value, marked, so that saving
 // the form does not silently move it to whichever category sorts first.
 const catOptions=cats.map(c=>({value:c.id,label:categoryLabel(c.id)}));
 if(current&&!cats.some(c=>c.id===current))
   catOptions.push({value:current,label:`${current} (${T('category removed')})`});
  return `${productFormHead(edit, p)}
 <form data-form="product" data-id="${p?.id||''}" class="product-form">
  <fieldset class="form-group"><legend>${T('Content')}</legend><div class="form-grid">
   <div class="field full"><label for="pf-title">${T('Product title')}</label><input id="pf-title" name="title" required maxlength="140" value="${esc(p?.title||'')}" placeholder="${T('Arya — Software with wings.')}"></div>
   <div class="field full"><label for="pf-summary">${T('Short summary')}</label><input id="pf-summary" name="summary" required maxlength="300" value="${esc(p?.summary||'')}" placeholder="${T('One line the catalog card can print.')}"></div>
   <div class="field full"><label for="pf-description">${T('Full description')}</label><textarea id="pf-description" name="description" required maxlength="3000" placeholder="${T('What it is, who it is for and what it does.')}">${esc(p?.description||'')}</textarea></div>
   <div class="field"><label for="pf-features">${T('Features')}</label><textarea id="pf-features" name="features" placeholder="${T('Separate each item with a comma')}">${esc((p?.features||[]).join(', '))}</textarea></div>
   <div class="field"><label for="pf-tech">${T('Technologies')}</label><textarea id="pf-tech" name="technologies" placeholder="${T('Separate each item with a comma')}">${esc((p?.technologies||[]).join(', '))}</textarea></div>
  </div></fieldset>

  <fieldset class="form-group"><legend>${T('Presentation')}</legend><div class="form-grid">
   <div class="field full"><label>${T('Cover image')}</label>${coverUploader(p?.cover||'')}<span class="field-hint">${T('PNG, JPEG, WebP or GIF, up to 5 MB.')} ${T('The image is re-encoded on upload, so camera metadata is removed.')}</span></div>
   <div class="field"><label for="pf-category">${T('Category')}</label>${picker('category', catOptions, current, {id:'pf-category', label:T('Category')})}</div>
   <div class="field"><label for="pf-price">${T('Price label')}</label><input id="pf-price" name="price_label" maxlength="80" value="${esc(p?.price_label||'Request a quote')}" placeholder="${T('Request a quote')}"></div>
  </div></fieldset>

  <fieldset class="form-group"><legend>${T('Links & availability')}</legend><div class="form-grid">
   <div class="field full"><label for="pf-github">${T('GitHub preview link')}</label><input id="pf-github" name="github_url" type="url" inputmode="url" maxlength="300" pattern="https://.+" placeholder="https://github.com/your-org/your-project" value="${esc(p?.github_url||'')}"><span class="field-hint">${T('Preview opens inside the site. Must start with https://.')} ${T('Leave empty to show the built-in concept preview.')}</span></div>
   <div class="field"><label for="pf-status">${T('Availability label')}</label>${picker('status', [{value:'available',label:T('Available')},{value:'showcase',label:T('Showcase only')}], p?.status||'available', {id:'pf-status', label:T('Availability label')})}</div>
   <div class="field"><label for="pf-slug">${T('URL slug')}</label><input id="pf-slug" name="slug" required pattern="[a-z0-9-]{3,100}" maxlength="100" value="${esc(p?.slug||'')}"><span class="field-hint">${T('Lowercase letters, digits and hyphens.')}</span></div>
  </div></fieldset>

  <fieldset class="form-group"><legend>${T('Publishing')}</legend><div class="form-grid">
   <div class="field"><label for="p-position">${T('Catalog order')}</label><input id="p-position" name="position" type="number" min="0" max="9999" step="1" value="${Number(p?.position)||0}"><span class="field-hint">${T('Lower numbers appear first.')}</span></div>
   <div class="field" style="align-content:end"><label class="check-line"><input name="featured" type="checkbox" ${p&&p.featured?'checked':''}> ${T('Feature this product')}</label><span class="field-hint">${T('Featured products lead the public catalog.')}</span></div>
   <div class="field full"><label class="check-line"><input name="published" type="checkbox" ${p&&!p.published?'':'checked'}> ${T('Published in product data')}</label><span class="field-hint">${T('AURION stays a showcase concept; no trading or payment is enabled.')}</span></div>
  </div></fieldset>

  <div class="form-actions"><button class="btn btn-quiet" type="button" data-act="product-cancel">${T('Cancel')}</button><button class="btn btn-primary">${edit?T('Save product'):T('Create product')}</button></div>
 </form>`;
}

/* Open a conversation's thread.
   The ticket is passed in when the caller already has it - the customer
   profile holds its own copy and never loads the whole support inbox, so
   looking it up in state.tickets alone left that button doing nothing. */
function openTicket(id, ticket){const t=ticket||state.tickets.find(x=>x.id===Number(id));if(!t)return;const msgs=[{message:t.message,sender:t.email,created_at:t.created_at},...(t.messages||[])];showModal(`${modalHead('Support conversation',esc(t.ref),esc(t.subject))}<div class="detail-grid" style="margin-bottom:14px"><div class="detail-item"><small>Customer email</small><strong>${esc(t.email)}</strong></div><div class="detail-item"><small>Ticket state</small><strong>${pill(t.status)}</strong></div><div class="detail-item"><small>Priority</small><strong>${t.priority?`<span class="pri pri-${esc(String(t.priority).toLowerCase())}">${esc(T(t.priority))}</span>`:'—'}</strong></div></div><div class="thread">${msgs.map(m=>`<div class="message ${m.sender==='Team'||m.sender===state.me.name?'admin':''}">${esc(m.message)}<small>${esc(m.sender||'Customer')} · ${moneyFreeDate(m.created_at)}</small></div>`).join('')}</div><form data-form="ticket-reply" data-id="${t.id}"><div class="field"><label>Reply to customer</label><textarea name="message" required minlength="2" maxlength="3000" placeholder="Write a clear, helpful response…"></textarea></div><div class="form-grid" style="margin-top:10px"><div class="field"><label>Ticket status</label>${picker('status', ['Open','In progress','Closed'].map(x=>({value:x,label:T(x)})), t.status, {label:T('Status')})}</div><div class="field" style="align-content:end"><span class="field-hint">Saving a reply moves the ticket to In progress.</span></div></div><div class="modal-actions"><button class="btn btn-quiet" type="button" data-act="close-modal">Close</button><button class="btn btn-primary">Send reply</button></div></form>`,true)}
function refundModal(id,decision){const r=state.refunds.find(x=>x.id===Number(id));if(!r)return;showModal(`${modalHead('Refund review',`${decision} request ${esc(r.ref)}`,`Order ${esc(r.order_number)} · submitted ${moneyFreeDate(r.created_at)}`)}<div class="detail-item"><small>Customer's stated reason</small><p>${esc(r.reason)}</p></div><form data-form="refund" data-id="${r.id}" data-decision="${decision}"><div class="field" style="margin-top:12px"><label>Administrative note</label><textarea name="note" maxlength="1000" placeholder="Record the review rationale. This will not trigger a payment."></textarea></div><div class="field" style="margin-top:10px"><label>Transaction reference (optional, record only)</label><input name="transaction_ref" maxlength="120"></div><div class="notice">${decision==='Approved'?'Approval records a decision only.':'Rejection records a decision only.'} The website does not process or confirm payment-provider refunds.</div><div class="modal-actions"><button class="btn btn-quiet" type="button" data-act="close-modal">Cancel</button><button class="btn ${decision==='Approved'?'btn-primary':'btn-danger'}">Record ${decision.toLowerCase()}</button></div></form>`)}
function exportCsv(kind){const data=({orders:state.orders,products:state.products,customers:state.customers,tickets:state.tickets,refunds:state.refunds})[kind]||[];if(!data.length){toast('There are no records to export.');return}const columns=Object.keys(data[0]).filter(k=>!['password_hash','csrf','token_hash'].includes(k));const csv=[columns.map(qcsv).join(','),...data.map(row=>columns.map(k=>qcsv(Array.isArray(row[k])?row[k].join('; '):row[k])).join(','))].join('\r\n');const blob=new Blob(['\ufeff'+csv],{type:'text/csv;charset=utf-8'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=`axiasoft-${kind}-${new Date().toISOString().slice(0,10)}.csv`;a.click();URL.revokeObjectURL(a.href);toast('CSV export downloaded.')}
function qcsv(v){return'"'+String(v??'').replace(/"/g,'""')+'"'}
async function refreshAll(){state.overview=null;state.orders=[];state.products=[];await fetchPageData();toast('Data refreshed.');state.savedSettings={...state.settings};state.dirty=false}
function setSearch(value){state.search=value;const c=$('#pageContent');if(c)c.innerHTML=contentHTML()}
async function clickHandler(e){
 const page=e.target.closest('[data-page]');if(page){e.preventDefault();nav(page.dataset.page);return}
 const toggle=e.target.closest('#languageToggle');if(toggle){localStorage.setItem('axia-lang',document.documentElement.lang==='fa'?'en':'fa');location.reload();return}
 const siteTab=e.target.closest('[data-site-tab]');
if(siteTab){
if(state.dirty&&!await confirmDialog({title:'Discard your changes?',
    body:'The values on this tab have not been saved. Leaving loses them.',
    confirmLabel:'Discard', cancelLabel:'Keep editing', danger:true}))return;
state.siteTab=siteTab.dataset.siteTab;
state.dirty=false;
$('#pageContent').innerHTML=contentHTML();
return}
 const rteBtn=e.target.closest('[data-rte]');
 if(rteBtn){applyFormat(rteBtn.dataset.rte);return}
 const b=e.target.closest('[data-act]');if(!b)return;const act=b.dataset.act;
 if(act==='close-modal'||(act==='backdrop-close'&&e.target===b)){closeModal();return}
 if(act==='goto-categories'){state.page='products';state.foldCategories=true;if(location.hash!=='#products')history.replaceState(null,'','#products');fetchPageData().then(()=>{document.querySelector('#categoriesPanel')?.scrollIntoView({behavior:'smooth',block:'center'});const f=$('[data-form="category-add"] input');if(f)f.focus();});return}
 if(act==='move-category'){moveCategory(b);return}
 if(act==='delete-category'){deleteCategory(b);return}
 if(act==='toggle-nav'){const s=$('#sidebar');s?.classList.toggle('open');$('.side-scrim')?.classList.toggle('show',s?.classList.contains('open'));return}
 if(act==='close-nav'){$('#sidebar')?.classList.remove('open');$('.side-scrim')?.classList.remove('show');return}
 if(act==='theme'){const t=document.documentElement.dataset.theme==='dark'?'light':'dark';document.documentElement.dataset.theme=t;localStorage.setItem('axia-theme',t);b.innerHTML=themeGlyph();return}
 if(act==='refresh'){refreshAll();return}
 /* ---- administrators ---- */
 if(act==='admin-new'){state.adminForm=true;state.adminsError='';$('#pageContent').innerHTML=contentHTML();$('#adm-name')?.focus();return}
 if(act==='admin-form-cancel'){state.adminForm=false;$('#pageContent').innerHTML=contentHTML();return}
 if(act==='admin-password'){
   const id=Number(b.dataset.id), email=b.dataset.email||'';
   openResetModal(id,email);
   return;
 }
 if(act==='admin-remove'){
   const id=Number(b.dataset.id), email=b.dataset.email||'';
   confirmDialog({
     title:T('Remove this administrator?'),
     body:`${email} ${T('loses console access now. Their customer account stays.')}`,
     confirmLabel:T('Remove access'),
     danger:true,
   }).then(async ok=>{
     if(!ok)return;
     try{await api('/api/admin/admins',{method:'DELETE',body:JSON.stringify({id})});
       state.admins=await api('/api/admin/admins');$('#pageContent').innerHTML=contentHTML();toast(T('Administrator removed.'))}
     catch(err){state.adminsError=err.message;$('#pageContent').innerHTML=contentHTML()}
   });
   return;
 }
 /* A brand image is uploaded with the same endpoint the product covers use.
    The reply carries one URL; it goes into both the preview and the hidden
    field, and the path box is filled too so the operator can see what was
    stored. */
 if(act==='brand-asset-clear'){
  const box=b.closest('[data-brand-asset]');
  const hidden=$('[data-brand-asset-input]',box);
  hidden.value='';
  $('[data-brand-asset-preview]',box).innerHTML='<span class="brand-asset-empty">—</span>';
  $('[data-brand-asset-path]',box).value='';
  $('[data-brand-asset-status]',box).textContent='';
  const clear=$('[data-act="brand-asset-clear"]',box); if(clear)clear.hidden=true;
  return;
 }
 if(act==='brand-add'){const list=brandDraft();if(list.length>=12){toast('Twelve brands is the maximum.');return}list.push({id:'',name:'',nameFa:'',tagline:'',taglineFa:'',accent:'#1f5fa8',accentSoft:'#3f8ad8',mark:'',logo:''});state.dirty=true;$('#pageContent').innerHTML=contentHTML();const last=$('.brand-edit:last-child [data-field="id"]');last?.focus();return}
 if(act==='brand-remove'){const i=Number(b.dataset.i);brandDraft().splice(i,1);state.dirty=true;$('#pageContent').innerHTML=contentHTML();return}
 if(act==='brand-up'){const i=Number(b.dataset.i);const list=brandDraft();if(i>0){[list[i-1],list[i]]=[list[i],list[i-1]];state.dirty=true;$('#pageContent').innerHTML=contentHTML()}return}
 if(act==='brand-down'){const i=Number(b.dataset.i);const list=brandDraft();if(i<list.length-1){[list[i+1],list[i]]=[list[i],list[i+1]];state.dirty=true;$('#pageContent').innerHTML=contentHTML()}return}
 if(act==='faq-add'){const list=faqDraft();if(list.length>=20){toast(T('Twenty questions is the maximum.'));return}list.push({q:'',qFa:'',a:'',aFa:''});state.dirty=true;$('#pageContent').innerHTML=contentHTML();const last=$('[data-faq-row]:last-child [data-field="q"]');last?.focus();return}
 if(act==='faq-remove'){const i=Number(b.dataset.i);faqDraft().splice(i,1);state.dirty=true;$('#pageContent').innerHTML=contentHTML();return}
 if(act==='faq-up'){const i=Number(b.dataset.i);const list=faqDraft();if(i>0){[list[i-1],list[i]]=[list[i],list[i-1]];state.dirty=true;$('#pageContent').innerHTML=contentHTML()}return}
 if(act==='faq-down'){const i=Number(b.dataset.i);const list=faqDraft();if(i<list.length-1){[list[i+1],list[i]]=[list[i],list[i+1]];state.dirty=true;$('#pageContent').innerHTML=contentHTML()}return}
 if(act==='new-article'){state.articleDraft={title:'',slug:'',summary:'',tags:[],body:'',status:'draft'};$('#pageContent').innerHTML=contentHTML();return}
 if(act==='close-article'){state.articleDraft=null;$('#pageContent').innerHTML=contentHTML();return}
 if(act==='article-preview'){previewArticle();return}
 if(act==='save-article'){saveArticle(null,b.dataset.status);return}
 if(act==='edit-article'){openArticle(+b.dataset.id);return}
 if(act==='delete-article'){deleteArticle(+b.dataset.id);return}
 if(act==='product-cancel'){state.productDraft=null;state.page='products';location.hash='#products';if(!state.products.length)fetchPageData();else $('#pageContent').innerHTML=contentHTML();return}
 if(act==='logout'){logout();return}
 if(act==='new-product'){openProductEditor(null);return}
 if(act==='edit-product'){const p=state.products.find(x=>x.id===Number(b.dataset.id));if(p)openProductEditor(p);return}
 if(act==='view-order'){openOrder(b.dataset.id);return}
 if(act==='view-ticket'){openTicket(b.dataset.id);return}
 if(act==='refund-decision'){refundModal(b.dataset.id,b.dataset.decision);return}
 if(act==='export'){exportCsv(b.dataset.kind);return}
 if(act==='toggle-product'){toggleProduct(b);return}
 if(act==='settings-refresh'){state.dirty=false;state.settings=null;fetchPageData().then(()=>toast('Settings reloaded.'));return}
 if(act==='settings-reset'){if(state.savedSettings)state.settings={...state.savedSettings};state.siteBrands=null;state.dirty=false;$('#pageContent').innerHTML=contentHTML();toast('Unsaved changes discarded.');return}
 if(act==='preview-site'){window.open(String(b.dataset.target||'/'),'_blank','noopener');return}
 if(act==='feature-product'){toggleFeature(b);return}
 if(act==='move-product'){moveProduct(b);return}
 if(act==='bulk-publish'){bulkPublish(true);return}
 if(act==='bulk-unpublish'){bulkPublish(false);return}
 if(act==='bulk-publish-all'){bulkPublishAll();return}
 if(act==='hide-catalog'){api('/api/admin/settings',{method:'PUT',body:{show_catalog:false}}).then(r=>{state.settings=r.settings||{...state.settings,show_catalog:false};toast('The catalog is hidden from the site.');$('#pageContent').innerHTML=contentHTML()}).catch(e=>toast(e.message,true));return}
 if(act==='demo-reset'){if(window.AXIA_DEMO_RESET)window.AXIA_DEMO_RESET();else toast('Reset is only available in the GitHub Pages demo.',true);return}
 if(act==='demo-samples'){
  if(!window.AXIA_DEMO_SAMPLES){toast('Sample products are only available in the GitHub Pages demo.',true);return}
  const added=window.AXIA_DEMO_SAMPLES();
  state.overview=null;
  state.settings=null;
  fetchPageData().then(()=>toast(`${added} product(s) available. Open Products to manage them.`));
  return}
 if(act==='export-settings'){exportSettings();return}
 if(act==='customer-status'){changeCustomerStatus(b);return}
 if(act==='customer-open'){openCustomer(b.dataset.id);return}
 if(act==='customer-back'){backToCustomers();return}
 if(act==='customer-refund'){customerRefund(b);return}
 if(act==='customer-ticket'){openCustomerTicket(b.dataset.id);return}
}
async function bulkPublishAll(){
 if(!await confirmDialog({title:'Publish every hidden product?',
    body:'Every product that is currently hidden becomes visible on the storefront, in the catalog and in search.',
    confirmLabel:'Publish all'}))return;
 try{
  const hidden=state.products.filter(p=>!p.published);
  for(const p of hidden)await api('/api/admin/products',{method:'PUT',body:{id:p.id,published:true}});
  toast(`${hidden.length} product(s) published.`);
  state.overview=null;
  await fetchPageData();
 }catch(e){toast(e.message,true)}
}
async function bulkPublish(publish){
 const ids=[...state.selected];
 if(!ids.length)return;
 if(!await confirmDialog({title:`${publish?'Publish':'Hide'} ${ids.length} product${ids.length===1?'':'s'}?`,
    body:publish?'They become visible on the storefront straight away.':'They come off the storefront. Existing order history is preserved.',
    confirmLabel:publish?'Publish':'Hide'}))return;
 try{
  for(const id of ids){
   if(publish)await api('/api/admin/products',{method:'PUT',body:{id,published:true}});
   else await api('/api/admin/products',{method:'DELETE',body:{id}});
  }
  state.selected=new Set();
  state.overview=null;
  await fetchPageData();
  toast(`${ids.length} product(s) ${publish?'published':'hidden'}.`);
 }catch(e){toast(e.message,true)}
}
function exportSettings(){
 const blob=new Blob([JSON.stringify(state.settings||{},null,2)],{type:'application/json'});
 const link=document.createElement('a');
 link.href=URL.createObjectURL(blob);
 link.download='settings.json';
 link.click();
 URL.revokeObjectURL(link.href);
 toast('settings.json downloaded.');
}
/* Saves the whole brand list in one request. The list is a single setting, so a
   partial save would leave the storefront with a brand the console no longer
   shows — all or nothing is the only safe shape.
   Validation runs in the browser first so a typo is reported next to the field
   it belongs to rather than as one generic server error. */
async function saveBrands(form){
 const list=brandDraft();
 // A blank row is what "+ Add brand" leaves behind; dropping it here means the
 // common case (add, then change your mind) needs no Remove click.
 const cleaned=list.filter(b=>String(b.name||'').trim()||String(b.id||'').trim());
 const verdict=window.AXIA_BRANDS_VALIDATE?window.AXIA_BRANDS_VALIDATE(cleaned):{ok:true,brands:cleaned};
 const old=$('.error-note',form);if(old)old.remove();
 if(!verdict.ok){
  const note=document.createElement('div');note.className='error-note';note.textContent=verdict.error;form.prepend(note);
  note.scrollIntoView({block:'center'});return;
 }
 const button=$('button[type="submit"]',form);
 if(button){button.disabled=true;button.dataset.old=button.textContent;button.textContent='Saving…'}
 try{
  const r=await api('/api/admin/settings',{method:'PUT',body:{brands:verdict.brands}});
  state.settings=r.settings||{...state.settings,brands:verdict.brands};
  state.savedSettings={...state.settings};
  state.siteBrands=null;
  state.dirty=false;
  $('#pageContent').innerHTML=contentHTML();
  toast('Site brands saved. The Websites tab now offers them.');
 }catch(e){
  const note=document.createElement('div');note.className='error-note';note.textContent=e.message;form.prepend(note);
  if(button){button.disabled=false;button.textContent=button.dataset.old||'Try again'}
 }
}

async function saveFaq(form){
 /* Same contract as the brand editor: the draft is the source of truth, a
    blank row is dropped (that is what "Add question" leaves behind), and the
    server answer is adopted wholesale so the console shows what was actually
    stored rather than what was typed. */
 const list=faqDraft().filter(x=>String(x.q||'').trim()||String(x.a||'').trim());
 const old=$('.error-note',form);if(old)old.remove();
 const incomplete=list.find(x=>!String(x.q||'').trim()||!String(x.a||'').trim());
 if(incomplete){
  const note=document.createElement('div');note.className='error-note';
  note.textContent=T('Every question needs an English question and answer. The Persian pair is optional.');
  form.prepend(note);note.scrollIntoView?.({block:'center'});return;
 }
 const button=$('button[type="submit"]',form);
 if(button){button.disabled=true;button.dataset.old=button.textContent;button.textContent=T('Saving…')}
 try{
  const r=await api('/api/admin/settings',{method:'PUT',body:{faq:list}});
  state.settings=r.settings||{...state.settings,faq:list};
  state.savedSettings={...state.settings};
  state.siteFaq=null;
  state.dirty=false;
  $('#pageContent').innerHTML=contentHTML();
  toast(T('Questions saved. The AURION pages now show these.'));
 }catch(e){
  const note=document.createElement('div');note.className='error-note';note.textContent=e.message;form.prepend(note);
  if(button){button.disabled=false;button.textContent=button.dataset.old||T('Try again')}
 }
}

async function saveSettings(form){
 const payload={};
 for(const el of form.elements){
  if(!el.name||el.disabled)continue;
  payload[el.name]=el.type==='checkbox'?el.checked:el.value;
 }
 const button=$('button[type="submit"]',form);
 if(button){button.disabled=true;button.dataset.old=button.textContent;button.textContent='Saving…'}
 try{
  const r=await api('/api/admin/settings',{method:'PUT',body:payload});
  state.settings=r.settings||{...state.settings,...payload};
  state.savedSettings={...state.settings};
  state.dirty=false;
  $('#pageContent').innerHTML=contentHTML();
  toast('Website settings saved. The public site now uses them.');
 }catch(e){
  const old=$('.error-note',form);
  if(old)old.remove();
  const note=document.createElement('div');
  note.className='error-note';
  note.textContent=e.status===400?'Some settings were not saved. Check the fields below.':e.message;
  form.prepend(note);
  if(button){button.disabled=false;button.textContent=button.dataset.old||'Try again'}
 }
}
/* One write path for all four category edits. The console sends the whole list
   in one PUT, the same way brands are saved, so a half-applied reorder is not a
   state the server can end up in. */
async function saveCategories(list){
 const r=await api('/api/admin/settings',{method:'PUT',body:{categories:list}});
 state.settings=r.settings||{...(state.settings||{}),categories:list};
 $('#pageContent').innerHTML=contentHTML();
}
async function moveCategory(btn){
 const id=btn.dataset.cat,dir=Number(btn.dataset.dir);
 const cats=siteCategories().slice();
 const at=cats.findIndex(c=>c.id===id);
 const to=at+dir;
 if(at<0||to<0||to>=cats.length)return;
 const [row]=cats.splice(at,1);cats.splice(to,0,row);
 try{await saveCategories(cats)}catch(e){toast(e.message,true)}
}
async function deleteCategory(btn){
 const id=btn.dataset.cat;
 const used=Number(btn.dataset.used)||0;
 if(used){
  /* Deleting a category does not touch its products: they keep the id and are
     flagged as orphaned on this screen until an operator moves them. The
     warning says exactly that, because the button is disabled for this case
     and a disabled button that explains nothing is a dead end. */
  toast('Move its products to another category first.',true);
  return;
 }
 const cats=siteCategories().filter(c=>c.id!==id);
 try{await saveCategories(cats);toast('Category removed.')}catch(e){toast(e.message,true)}
}
async function toggleFeature(btn){
 const p=state.products.find(x=>x.id===Number(btn.dataset.id));
 if(!p)return;
 const featured=!p.featured;
 try{
  await api('/api/admin/products',{method:'PUT',body:{id:p.id,featured}});
  p.featured=featured?1:0;
  toast(featured?'Featured — it now leads the public catalog.':'Removed from the featured list.');
  await fetchPageData();
 }catch(e){toast(e.message,true)}
}
async function moveProduct(btn){
 const p=state.products.find(x=>x.id===Number(btn.dataset.id));
 if(!p)return;
 const dir=Number(btn.dataset.dir);
 const ordered=state.products.slice().sort(productSortCompare);
 const at=ordered.findIndex(x=>x.id===p.id);
 const swap=ordered[at+dir];
 if(at<0||!swap){toast('Already at the edge of the list.',true);return}
 try{
  const positions=ordered.map(x=>Number(x.position)||0);
  const a=positions[at],b=positions[at+dir];
  await api('/api/admin/products',{method:'PUT',body:{id:p.id,position:b}});
  await api('/api/admin/products',{method:'PUT',body:{id:swap.id,position:a}});
  state.productSort='manual';
  state.overview=null;
  await fetchPageData();
 }catch(e){toast(e.message,true)}
}
async function toggleProduct(btn){const p=state.products.find(x=>x.id===Number(btn.dataset.id));if(!p)return;const publish=!p.published;if(!await confirmDialog({title:publish?'Publish this product?':'Unpublish this product?',
    body:publish?'It becomes visible on the storefront, in the catalog and in search.':'It comes off the storefront. Existing order history is preserved.',
    confirmLabel:publish?'Publish':'Unpublish'}))return;try{if(publish){await api('/api/admin/products',{method:'PUT',body:{id:p.id,published:true}})}else{await api('/api/admin/products',{method:'DELETE',body:{id:p.id}})}toast(publish?'Product published.':'Product unpublished; history is preserved.');state.overview=null;await fetchPageData()}catch(e){toast(e.message,true)}}
async function changeCustomerStatus(btn){const c=state.customers.find(x=>x.id===Number(btn.dataset.id));if(!c)return;const active=!c.active;if(!await confirmDialog({title:active?`Reactivate ${c.name}?`:`Suspend ${c.name}?`,
    body:active?'They can sign in again. Their orders and messages are untouched.':'Every active session for this customer ends now. Their orders and messages are untouched.',
    confirmLabel:active?'Reactivate':'Suspend', danger:!active}))return;try{await api('/api/admin/customers/status',{method:'PUT',body:{id:c.id,active}});toast(active?'Customer reactivated.':'Customer suspended; sessions revoked.');const r=await api('/api/admin/customers');state.customers=r.customers;$('#pageContent').innerHTML=customersHTML()}catch(e){toast(e.message,true)}}
async function submitHandler(e){const form=e.target.closest('form[data-form]');if(!form){console.log('no form found');return}e.preventDefault();const submit=$('button[type="submit"]',form)||$('button:not([type="button"])',form);if(submit){submit.disabled=true;submit.dataset.old=submit.textContent;submit.textContent='Saving…'}const values=Object.fromEntries(new FormData(form));try{
 if(form.dataset.form==='login'){const data=await api('/api/login',{method:'POST',body:{email:values.email,password:values.password}});state.me=data.user;if(state.me.role!=='admin'){deniedView();return}const s=await api('/api/me');state.csrf=s.csrf;state.page=location.hash.slice(1)||'dashboard';if(!PAGES.includes(state.page))state.page='dashboard';shell();await fetchPageData();toast('Administrator session established.');return}
 if(form.dataset.form==='settings'){await saveSettings(form);return}
 if(form.dataset.form==='admin-create'){
   try{
     await api('/api/admin/admins',{method:'POST',body:JSON.stringify({
       name:values.name,email:values.email,password:values.password,admin_role:values.admin_role})});
     state.admins=await api('/api/admin/admins');state.adminForm=false;state.adminsError='';
     $('#pageContent').innerHTML=contentHTML();toast(T('Administrator created.'));
   }catch(err){state.adminsError=err.message;state.adminForm=false;$('#pageContent').innerHTML=contentHTML()}
   return;
 }
 if(form.dataset.form==='admin-password'){
   try{
     await api('/api/admin/admins/password',{method:'POST',body:JSON.stringify({
       id:Number(form.dataset.id),password:values.password})});
     closeModal();toast(T('Password changed. That account is signed out everywhere.'));
   }catch(err){toast(err.message)}
   return;
 }
 if(form.dataset.form==='faq'){await saveFaq(form);return}
 if(form.dataset.form==='brands'){await saveBrands(form);return}
 if(form.dataset.form==='product'){const features=String(values.features||'').split(/[\n,]+/).map(x=>x.trim()).filter(Boolean).slice(0,20);const technologies=String(values.technologies||'').split(/[\n,]+/).map(x=>x.trim()).filter(Boolean).slice(0,20);const payload={title:values.title,slug:values.slug,category:values.category,status:values.status,price_label:values.price_label,cover:values.cover_image||'',summary:values.summary,description:values.description,github_url:(values.github_url||'').trim(),features,technologies,published:form.elements.published.checked,featured:form.elements.featured?.checked||false,position:Number(values.position)||0};if(form.dataset.id){payload.id=Number(form.dataset.id);await api('/api/admin/products',{method:'PUT',body:payload});toast('Product changes saved.')}else{await api('/api/admin/products',{method:'POST',body:payload});toast('Product added.')}state.overview=null;await fetchPageData();state.page='products';if(location.hash!=='#products')history.replaceState(null,'','#products');return}
 if(form.dataset.form==='category-add'){
  const cats=siteCategories().slice();
  const id=String(values.id||'').trim().toLowerCase();
  if(cats.some(c=>c.id===id))throw new Error('That category id is already in use.');
  cats.push({id,name:String(values.name||'').trim(),nameFa:String(values.nameFa||'').trim()});
  await saveCategories(cats);
  toast('Category added.');
  return;
 }
 if(form.dataset.form==='order-update'){await api('/api/admin/orders/status',{method:'PUT',body:{id:Number(form.dataset.id),status:values.status,note:values.note||''}});closeModal();toast('Project status and history updated.');state.overview=null;await fetchPageData();return}
 if(form.dataset.form==='ticket-reply'){const __id=Number(form.dataset.id);if(values.message?.trim())await api('/api/admin/tickets/reply',{method:'POST',body:{id:__id,message:values.message.trim()}});const __status=values.status||'In progress';try{await api('/api/admin/tickets/status',{method:'PUT',body:{id:__id,status:__status}})}catch(e){toast(e.message)}await api('/api/admin/tickets/read',{method:'POST',body:{id:__id}}).catch(()=>{});closeModal();toast(values.message?.trim()?'Reply sent. The customer sees it in their account.':'Ticket status updated.');state.tickets=await api('/api/support');$('#pageContent').innerHTML=supportHTML();return}
 if(form.dataset.form==='refund'){await api('/api/admin/refunds/decision',{method:'PUT',body:{id:Number(form.dataset.id),status:form.dataset.decision,note:values.note||'',transaction_ref:values.transaction_ref||''}});closeModal();toast('Refund decision recorded. No payment was processed.');state.refunds=await api('/api/refunds');$('#pageContent').innerHTML=refundsHTML();return}
 }catch(err){const old=$('.error-note',form);if(old)old.remove();const note=document.createElement('div');note.className='error-note';note.textContent=err.message;form.prepend(note);if(submit){submit.disabled=false;submit.textContent=submit.dataset.old||'Try again'}}}
/* Typing in the brand editor writes straight into the draft, because every
   other control in this tab re-renders the panel and would otherwise throw the
   half-typed value away. The draft is what Save sends. */
function faqInput(e){
 const el=e.target.closest('[data-faq]');
 if(!el)return;
 const list=faqDraft(),row=list[Number(el.dataset.faq)];
 if(!row)return;
 row[el.dataset.field]=el.value;
 state.dirty=true;
 // Same reason as brandInput: update the header line in place rather than
 // re-rendering, or the caret jumps out of the field on every keystroke.
 const card=el.closest('.brand-edit');
 if(card&&(el.dataset.field==='q'||el.dataset.field==='qFa')){
  const strong=$('strong',card),muted=$('.muted',card);
  if(strong)strong.textContent=row.q||T('New question');
  if(muted)muted.textContent=row.qFa||'';
 }
}
function brandInput(e){
 const el=e.target.closest('[data-brand]');
 if(!el)return;
 const list=brandDraft(),row=list[Number(el.dataset.brand)];
 if(!row)return;
 row[el.dataset.field]=el.value;
 state.dirty=true;
 // Keep the header line in step without a full re-render, which would steal
 // the caret out of the field being typed into.
 const card=el.closest('.brand-edit');
 if(card&&(el.dataset.field==='name'||el.dataset.field==='nameFa')){
  const strong=$('strong',card),muted=$('.muted',card);
  if(strong)strong.textContent=row.name||T('New brand');
  if(muted)muted.textContent=row.nameFa||'';
 }
 if(el.dataset.field==='accent'){const sw=$('.brand-swatch',card);if(sw)sw.style.setProperty('--swatch',row.accent)}
}
/* The pickers call back by name: the markup is built as a string, so a closure
   cannot be attached at render time. These are the four filters plus the two
   admin controls, and each does exactly what its <select> handler did. */
window.pickerStatusFilter = value => {
  state.statusFilter = value;
  const c = $('#pageContent'); if (c) c.innerHTML = contentHTML();
};
window.pickerProductFilter = value => {
  state.productFilter = value;
  const c = $('#pageContent'); if (c) c.innerHTML = productsHTML();
};
window.pickerCategoryFilter = value => {
  state.categoryFilter = value;
  const c = $('#pageContent'); if (c) c.innerHTML = productsHTML();
};
window.pickerProductSort = value => {
  state.productSort = value;
  const c = $('#pageContent'); if (c) c.innerHTML = productsHTML();
};
window.pickerMarkDirty = () => {
  state.dirty = true;
  if (!$('.dirty-note')) {
    $('.site-tab-body')?.insertAdjacentHTML('beforebegin',
      '<div class="dirty-note" role="status"><span>●</span> Unsaved changes on this page — press <strong>Save</strong> to publish them to the site.</div>');
  }
};
window.pickerCustomerOrderStatus = async (value, host) => {
  const id = Number(host.dataset.id || 0);
  if (!id) return;
  try {
    await api('/api/admin/orders/status', {method:'PUT', body:{id, status:value}});
    toast(T('Order status updated.'));
    await openCustomer(state.customerId);
  } catch (e) { toast(e.message, true); }
};

window.pickerAdminRole = async (value, host) => {
  const id = Number(host.dataset.id || 0);
  if (!id) return;
  try {
    await api('/api/admin/admins', {method:'PUT', body:JSON.stringify({id, admin_role:value})});
    state.admins = await api('/api/admin/admins');
    $('#pageContent').innerHTML = contentHTML();
    toast(T('Role updated.'));
  } catch (err) {
    state.adminsError = err.message;
    state.admins = await api('/api/admin/admins').catch(() => state.admins);
    $('#pageContent').innerHTML = contentHTML();
  }
};

function inputHandler(e){
 brandInput(e);faqInput(e);
if(e.target.matches('[data-search]')){state.search=e.target.value;clearTimeout(inputHandler.timer);inputHandler.timer=setTimeout(()=>{const c=$('#pageContent');if(c)c.innerHTML=contentHTML();const input=$('[data-search]');if(input){input.focus();input.setSelectionRange(input.value.length,input.value.length)}},180)}if(e.target.matches('[data-status-filter]')){state.statusFilter=e.target.value;$('#pageContent').innerHTML=contentHTML()}if(e.target.matches('[data-product-filter]')){state.productFilter=e.target.value;$('#pageContent').innerHTML=contentHTML()}
if(e.target.matches('[data-cat-name],[data-cat-name-fa]')){
 const id=e.target.dataset.catName||e.target.dataset.catNameFa;
 const field=e.target.dataset.catName?'name':'nameFa';
 const cats=siteCategories().map(c=>c.id===id?{...c,[field]:String(e.target.value||'').trim().slice(0,40)}:c);
 clearTimeout(inputHandler.catTimer);
 // Debounced: a rename is typed, and writing on every keystroke would rebuild
 // the panel and take the caret with it.
 inputHandler.catTimer=setTimeout(()=>{saveCategories(cats).catch(err=>toast(err.message,true))},700);
}
if(e.target.matches('[data-select-product]')){const id=Number(e.target.dataset.selectProduct);e.target.checked?state.selected.add(id):state.selected.delete(id);$('#pageContent').innerHTML=productsHTML()}
if(e.target.matches('[data-select-all]')){$$('[data-select-product]').forEach(box=>{const id=Number(box.dataset.selectProduct);e.target.checked?state.selected.add(id):state.selected.delete(id)});$('#pageContent').innerHTML=productsHTML()}
if(e.target.closest('[data-form="settings"]')){state.dirty=true;if(!$('.dirty-note')){$('.site-tab-body')?.insertAdjacentHTML('beforebegin','<div class="dirty-note" role="status"><span>●</span> Unsaved changes on this page — press <strong>Save</strong> to publish them to the site.</div>')}}}
/* The console's Sign out asks first, in the console's own dialog - window.confirm()
   would be the browser's furniture in the middle of an AXIASOFT screen, and it
   cannot be styled, translated or focus-managed. */
async function logout(){
  const yes=await confirmDialog({
    title:T('Sign out of the console?'),
    body:T('Your session ends on this device. Nothing else changes.'),
    confirmLabel:T('Sign out'), cancelLabel:T('Stay signed in')});
  if(!yes)return;
  try{await api('/api/logout',{method:'POST',body:{}})}catch{}
  state.me=null;state.csrf=null;closeModal();loginView()}
root.addEventListener('click',clickHandler);root.addEventListener('submit',submitHandler);root.addEventListener('input',inputHandler);root.addEventListener('change',inputHandler);overlays.addEventListener('click',clickHandler);overlays.addEventListener('submit',submitHandler);overlays.addEventListener('input',inputHandler);overlays.addEventListener('change',inputHandler);
document.addEventListener('keydown',e=>{if(e.key==='Escape'){closeModal();$('#sidebar')?.classList.remove('open');$('.side-scrim')?.classList.remove('show')}});
/* One listener for the breakpoint, not one per render. It only fires on the
   crossing itself, so a window drag does not rebuild the page every pixel. */
(() => {
  const query = window.matchMedia('(max-width: 900px)');
  const sync = () => {
    if (state.page === 'products') {
      const box = $('#pageContent');
      if (box) box.innerHTML = contentHTML();
    }
  };
  if (query.addEventListener) query.addEventListener('change', sync);
  else if (query.addListener) query.addListener(sync);
})();
window.addEventListener('hashchange',()=>{const p=location.hash.slice(1);if(p&&PAGES.includes(p)){state.page=p;state.search='';state.statusFilter='All';fetchPageData();updateNav()}});
(async()=>{document.documentElement.dataset.theme=localStorage.getItem('axia-theme')||'dark';const page=location.hash.slice(1);if(PAGES.includes(page))state.page=page;await loadSession()})();
  /* -------------------------------------------------------------------------
     Product cover upload

     The console sends the file itself rather than a URL, so an administrator
     never has to host an image somewhere else first. The widget keeps the
     uploaded path in a hidden input, which is what the product form reads, so the
     rest of the save path is unchanged.
     ------------------------------------------------------------------------- */
  const COVER_ACCEPT = 'image/png,image/jpeg,image/webp,image/gif';
  const COVER_MAX = 5 * 1024 * 1024;

  function coverPreview(url) {
    /* Only shapes this page produces are rendered: a stored path, an https URL,
       or the data URL a demo console creates. Anything else stays text and never
       becomes an <img src>. */
    if (!url) return '';
    const allowed = /^(\/uploads\/covers\/[\w-]+\.png|\/brand\/[\w-]+\.(png|jpg|jpeg|webp|svg)|https:\/\/|data:image\/(png|jpeg|webp|gif);base64,)/;
    if (!allowed.test(url)) return '';
    return `<img class="cover-thumb" src="${esc(url)}" alt="Current cover">`;
  }

  function coverUploader(current) {
    return `<div class="cover-uploader" data-cover-uploader>
      <input type="hidden" name="cover_image" value="${esc(current || '')}">
      <div class="cover-preview" data-cover-preview>${coverPreview(current) || '<span class="cover-empty">No cover image</span>'}</div>
      <div class="cover-actions">
        <label class="btn btn-quiet cover-pick">
          <input type="file" data-cover-file accept="${COVER_ACCEPT}" hidden>
          <span>Choose image…</span>
        </label>
        <button type="button" class="btn btn-quiet" data-cover-clear ${current ? '' : 'hidden'}>Remove</button>
        <span class="cover-status" data-cover-status role="status"></span>
      </div>
      <p class="field-hint">The image is stored under /uploads/covers. Choose a new image to replace the current one.</p>
    </div>`;
  }

  /* One upload at a time. The request is a plain binary body with the image's own
     Content-Type: it needs no multipart wrapper, and it keeps the server's
     handling of the bytes identical to what the decoder expects. */
  async function uploadCover(file, options = {}) {
    if (!file) return null;
    if (!/^image\/(png|jpeg|webp|gif)$/.test(file.type)) {
      throw new Error('Choose a PNG, JPEG, WebP or GIF image.');
    }
    if (file.size > COVER_MAX) {
      throw new Error('That image is larger than 5 MB.');
    }
    const headers = { 'Content-Type': file.type };
    // ?raw=1 asks the server to store the bytes as sent. A logo keeps its
    // transparency and its exact pixels; a cover is normalised to PNG.
    if (options.convert === false) headers['X-Upload-Raw'] = '1';
    if (!state.csrf) {
      const session = await fetch('/api/me', { credentials: 'same-origin' }).then((r) => r.json()).catch(() => ({}));
      state.csrf = session.csrf || null;
    }
    if (state.csrf) headers['X-CSRF-Token'] = state.csrf;
    const response = await fetch('/api/admin/uploads', {
      method: 'POST', headers, body: file, credentials: 'same-origin',
    });
    const data = await response.json().catch(() => ({ error: 'The server returned an unreadable response.' }));
    if (response.status === 501) {
      // The static demo console has no server. Reading the file here keeps the
      // feature usable, and the caller labels it as browser-local so nobody
      // believes the image was uploaded.
      return { url: await readAsDataUrl(file), local: true };
    }
    if (!response.ok) throw new Error(data.error || `Upload failed (${response.status})`);
    return { url: data.url, local: false };
  }

  // Delegated so it survives the modal being rebuilt.
  /* A brand logo or mark. Same endpoint and limits as a cover, but the image is
     not re-encoded: a logo is line art with transparent edges, and a lossy pass
     would fringe it. SVG is accepted here because a mark is often one. */
  document.addEventListener('change', async (event) => {
    const input = event.target.closest('[data-brand-asset-file]');
    if (!input) return;
    const box = input.closest('[data-brand-asset]');
    const status = $('[data-brand-asset-status]', box);
    const hidden = $('[data-brand-asset-input]', box);
    const preview = $('[data-brand-asset-preview]', box);
    const file = input.files && input.files[0];
    input.value = '';
    if (!file) return;
    status.className = 'brand-asset-status';
    status.textContent = T('Uploading…');
    try {
      const result = await uploadCover(file, { convert: false });
      hidden.value = result.url;
      const pathBox = $('[data-brand-asset-path]', box);
      if (pathBox) pathBox.value = result.url;
      preview.innerHTML = `<img src="${esc(brandAsset(result.url))}" alt="">`;
      const clear = $('[data-act="brand-asset-clear"]', box);
      if (clear) clear.hidden = false;
      status.textContent = result.local
        ? T('Read in this browser only — the demo console has no server to store it.')
        : T('Uploaded.');
    } catch (error) {
      status.className = 'brand-asset-status is-error';
      status.textContent = error.message;
    }
  });

  /* Typing a path is the other way in, and it keeps the two fields together. */
  document.addEventListener('input', (event) => {
    const pathBox = event.target.closest('[data-brand-asset-path]');
    if (!pathBox) return;
    const box = pathBox.closest('[data-brand-asset]');
    const value = pathBox.value.trim();
    $('[data-brand-asset-input]', box).value = value;
    $('[data-brand-asset-preview]', box).innerHTML = value
      ? `<img src="${esc(brandAsset(value))}" alt="" onerror="this.replaceWith(Object.assign(document.createElement('span'),{className:'brand-asset-empty',textContent:'✕'}))">`
      : '<span class="brand-asset-empty">—</span>';
    const clear = $('[data-act="brand-asset-clear"]', box);
    if (clear) clear.hidden = !value;
  });

  document.addEventListener('change', async (event) => {
    const input = event.target.closest('[data-cover-file]');
    if (!input) return;
    const box = input.closest('[data-cover-uploader]');
    const status = $('[data-cover-status]', box);
    const hidden = $('input[name="cover_image"]', box);
    const preview = $('[data-cover-preview]', box);
    const file = input.files && input.files[0];
    input.value = '';
    if (!file) return;
    status.textContent = 'Uploading…';
    status.className = 'cover-status';
    $('[data-cover-clear]', box)?.setAttribute('hidden', '');
    try {
      const result = await uploadCover(file);
      hidden.value = result.url;
      preview.innerHTML = coverPreview(result.url);
      status.textContent = result.local
        ? 'Read in this browser only — the demo console has no server to store it.'
        : 'Uploaded.';
      $('[data-cover-clear]', box)?.removeAttribute('hidden');
    } catch (error) {
      status.textContent = error.message;
      status.className = 'cover-status is-error';
    }
  });

  document.addEventListener('click', (event) => {
    const clear = event.target.closest('[data-cover-clear]');
    if (!clear) return;
    const box = clear.closest('[data-cover-uploader]');
    $('input[name="cover_image"]', box).value = '';
    $('[data-cover-preview]', box).innerHTML = '<span class="cover-empty">No cover image</span>';
    $('[data-cover-status]', box).textContent = '';
    clear.setAttribute('hidden', '');
  });

  /* A demo console has no server to store a file. Reading it in the browser keeps
     the cover picker usable there, and the caller says plainly that the image was
     not uploaded anywhere. */
  function readAsDataUrl(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ''));
      reader.onerror = () => reject(new Error('That file could not be read.'));
      reader.readAsDataURL(file);
    });
  }
})();

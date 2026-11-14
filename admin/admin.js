(()=>{
'use strict';
const root=document.querySelector('#adminApp'),overlays=document.querySelector('#overlayRoot');
const $=(s,r=document)=>r.querySelector(s),$$=(s,r=document)=>[...r.querySelectorAll(s)];
const T=v=>window.AXIA_T?window.AXIA_T(v):v;
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const moneyFreeDate=v=>{if(!v)return'—';const d=new Date(String(v).replace(' ','T')+'Z');return Number.isNaN(+d)?esc(v):new Intl.DateTimeFormat(document.documentElement.lang==='fa'?'fa-IR':'en-GB',{dateStyle:'medium',timeStyle:'short'}).format(d)};
const ordersStatus=['Submitted','Under Review','Requirements Analysis','Quotation Sent','Awaiting Confirmation','In Development','Testing','Ready for Delivery','Delivered','Cancelled'];
const PAGES=['dashboard','site','products','articles','orders','customers','support','refunds','activity'];
const state={me:null,csrf:null,page:'dashboard',overview:null,orders:[],products:[],customers:[],tickets:[],refunds:[],audit:[],articles:[],articleDraft:null,agent:null,settings:null,savedSettings:null,siteTab:'identity',search:'',statusFilter:'All',productFilter:'All',categoryFilter:'All',productSort:'manual',selected:new Set(),dirty:false,menu:false,loading:false,lastSync:null};
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
function iconFor(page){return({dashboard:'◫',site:'⚙',orders:'▤',products:'◈',customers:'♙',support:'✳',refunds:'↩',activity:'◷'})[page]||'•'}
function loginView(error=''){
 root.innerHTML=`<main class="login-wrap"><section class="login-card"><div class="login-brand"><span class="logo-mark"><img src="/AxiaPlatform/brand/axiasoft-original.png" alt=""></span><div><strong>AXIASOFT</strong><small>ADMIN CONSOLE</small></div><span style="margin-left:auto"><button id="languageToggle" class="language-btn" aria-label="Switch language">${document.documentElement.lang==='fa'?'EN':'فارسی'}</button></span></div><div class="eyebrow">Restricted workspace</div><h1>Administrator sign in</h1><p class="muted">Use your AXIASOFT administrator account to access operational records and tools.</p>${error?`<div class="error-note" role="alert">${esc(error)}</div>`:''}<form data-form="login"><div class="field" style="margin-bottom:12px"><label for="loginEmail">Administrator email</label><input id="loginEmail" name="email" type="email" autocomplete="username" required maxlength="254" placeholder="name@company.com"></div><div class="field"><label for="loginPassword">Password</label><input id="loginPassword" name="password" type="password" autocomplete="current-password" required maxlength="256" placeholder="Your password"></div><button class="btn btn-primary" style="width:100%;margin-top:18px;min-height:42px">Sign in securely <span>↗</span></button></form><div class="secure-note"><span class="secure-dot"></span> Server-verified administrator role · secure session</div><p class="setup-command">No default administrator credentials are provided. To create or reset an admin account, run <code>python3 provision_admin.py</code> from the server directory.</p></section></main>`;
}
function deniedView(){root.innerHTML=`<main class="login-wrap"><section class="login-card"><div class="login-brand"><span class="logo-mark"><img src="/AxiaPlatform/brand/axiasoft-original.png" alt=""></span><div><strong>AXIASOFT</strong><small>ADMIN CONSOLE</small></div></div><div class="eyebrow">Access restricted</div><h1>Administrator access required</h1><p class="muted">This account does not have the required administrator role. The server has denied protected data access.</p><div class="head-actions"><button class="btn btn-quiet" data-act="logout">Sign out</button><a class="btn btn-primary" href="/AxiaPlatform/#/">Return to website</a></div></section></main>`}
function shell(){
 const nav=[['dashboard','Overview'],['site','Website'],['products','Products'],['articles','Blog articles'],['orders','Project requests'],['customers','Customers'],['support','Support'],['refunds','Refunds'],['activity','Activity log']];
 root.innerHTML=`<div class="admin-shell"><div class="side-scrim" data-act="close-nav"></div><aside class="sidebar" id="sidebar"><a href="/" class="side-brand"><span class="logo-mark"><img src="/AxiaPlatform/brand/axiasoft-original.png" alt=""></span><span><strong>AXIASOFT</strong><small>ADMIN CONSOLE</small></span></a><div class="side-label">Workspace</div><nav class="nav-list">${nav.map(([id,label])=>`<button class="side-link ${state.page===id?'active':''}" data-page="${id}"><span class="nav-glyph">${iconFor(id)}</span><span>${T(label)}</span>${id==='refunds'&&state.overview?.counts?.refunds?`<span class="nav-count">${fmtNum(state.overview.counts.refunds)}</span>`:''}${id==='orders'&&state.overview?.counts?.pending?`<span class="nav-count">${fmtNum(state.overview.counts.pending)}</span>`:''}</button>`).join('')}</nav><div class="side-label" style="margin-top:23px">Website</div><a class="side-link" href="/"><span class="nav-glyph">↗</span><span>Open public website</span></a><div class="sidebar-bottom"><div class="sidebar-foot"><span class="avatar">${esc((state.me?.name||'A').slice(0,1).toUpperCase())}</span><div class="user-min"><strong>${esc(state.me?.name||'Administrator')}</strong><small>${esc(state.me?.email||'')}</small></div><button class="icon-btn" data-act="logout" title="Sign out" aria-label="Sign out">⇥</button></div></div></aside><section class="workspace"><header class="topbar"><div class="top-left"><button class="icon-btn mobile-toggle" data-act="toggle-nav" aria-label="Open navigation">☰</button><div class="crumb">AXIASOFT <span style="color:var(--faint)">/</span> <strong>${nav.find(x=>x[0]===state.page)?.[1]||'Overview'}</strong></div></div><div class="top-right"><button class="language-btn" id="languageToggle" aria-label="Switch language">${document.documentElement.lang==='fa'?'EN':'فارسی'}</button><button class="icon-btn" data-act="theme" title="Toggle color theme" aria-label="Toggle color theme">${document.documentElement.dataset.theme==='dark'?'◐':'☼'}</button><button class="icon-btn" data-act="refresh" title="Refresh data" aria-label="Refresh data">↻</button><div class="top-user"><span class="avatar">${esc((state.me?.name||'A').slice(0,1).toUpperCase())}</span><div class="user-min-top"><strong>${esc(state.me?.name||'Administrator')}</strong><small>Administrator</small></div></div></div></header><main class="content" id="pageContent"><div class="panel" style="height:190px"><div class="skeleton" style="width:170px;margin:14px 0"></div><div class="skeleton" style="width:78%;height:50px;margin:14px 0"></div><div class="skeleton" style="width:55%"></div></div></main></section></div>`;
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
  [T('Storefront status'), (s.show_catalog===false?T('Catalog hidden'):T('Catalog visible'))+' · '+(s.announcement_enabled&&s.announcement_text?T('banner on'):T('banner off')),'ok'],
  [T('Pending reviews'), c.pending?`${fmtNum(c.pending)} ${T('requests waiting')}`:T('Nothing waiting'), c.pending?'warn':'ok'],
  [T('Open support'), c.tickets?`${fmtNum(c.tickets)} ${T('tickets')}`:T('No open tickets'), c.tickets?'warn':'ok'],
  [T('Suspended accounts'), c.customers_suspended?`${fmtNum(c.customers_suspended)} ${T('accounts')}`:T('None'), c.customers_suspended?'warn':'ok'],
  [T('Catalog'), `${fmtNum(c.published||0)} ${T('published')} · ${fmtNum(c.hidden||0)} ${T('hidden')} · ${fmtNum(c.featured||0)} ${T('featured')}`,'ok']
 ];
 return rows.map(([label,value,level])=>`<div class="health-row"><span class="health-dot ${level}"></span><span class="health-label">${esc(label)}</span><strong>${esc(value)}</strong></div>`).join('');
}
function activityFeed(limit=7){
 const rows=(Array.isArray(state.audit)?state.audit:[]).slice(0,limit);
 if(!rows.length)return`<div class="empty" style="padding:22px"><div class="empty-icon">◷</div>No events recorded yet.</div>`;
 return rows.map(a=>`<div class="activity-item"><span class="activity-glyph">${({create:'＋',update:'✎',unpublish:'⤓',status_change:'⇄',ticket_status:'✳',ticket_reply:'↩',refund_decision:'◈',customer_access:'♙',login:'⇥',settings:'⚙'})[a.action]||'•'}</span><div><strong>${esc(T(actionLabel(a.action)))}</strong><small>${esc(T(a.entity||'system'))}${a.entity_id?' · '+esc(String(a.entity_id)):''}</small></div><time>${moneyFreeDate(a.created_at)}</time></div>`).join('');
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
 const hero=`<section class="hero-strip panel"><div class="hero-strip-copy"><div class="eyebrow">Control room / today</div><h2>Good to see you, ${esc(state.me?.name||'Administrator')}.</h2><p>${c.pending?`${T('Awaiting a first review: {n}').replace('{n}',fmtNum(c.pending))} `:''}${c.tickets?`${T('Open support tickets: {n}').replace('{n}',fmtNum(c.tickets))} `:''}${!c.pending&&!c.tickets?T('Nothing is waiting for you right now.'):''} ${T('Everything on this page is editable from the sidebar.')}</p><div class="hero-strip-actions"><button class="btn btn-quiet" data-act="refresh">↻ Refresh</button><button class="btn btn-quiet" data-page="site">⚙ Website settings</button><button class="btn btn-primary" data-act="new-product">＋ Add product</button></div></div><div class="hero-strip-side"><div class="trend ${trend.up===null?'flat':trend.up?'up':'down'}"><strong>${trend.up===null?fmtNum(trend.value):(trend.up?'▲ ':'▼ ')+fmtNum(Math.abs(trend.value))+'%'}</strong><small>${esc(trend.label)}</small></div><div class="hero-meta"><span>Last data: <strong>${state.lastSync?syncLabel(state.lastSync):'—'}</strong></span><span>Mode: <strong>${d.demo?'demo':'live'}</strong></span></div></div></section>`;
 const cards=[['Customers',c.customers,'♙',`${fmtNum(c.customers_active||0)} ${T('active')}`],['Project requests',c.orders,'▤',`${fmtNum(c.pending||0)} ${T('awaiting review')}`],['In development',c.active,'⌘',`${fmtNum(c.completed||0)} ${T('delivered')}`],['Open support',c.tickets,'✳',`${fmtNum(c.tickets_open??c.tickets??0)} ${T('not closed')}`],['Published products',c.published,'◈',`${fmtNum(c.hidden||0)} ${T('hidden')} · ${fmtNum(c.featured||0)} ${T('featured')}`],['Refund reviews',c.refunds,'↩',T('Decision only · no payment')]];
 const statuses=ordersStatus.map(s=>({name:s,count:orders.filter(o=>o.status===s).length})).filter(x=>x.count||['Submitted','In Development','Delivered'].includes(x.name));
 const max=Math.max(1,...statuses.map(x=>x.count));
 return `${hero}<section class="grid stats-grid">${cards.map(([label,value,icon,sub])=>`<article class="stat-card"><div class="stat-top"><span>${T(label)}</span><span class="stat-icon">${icon}</span></div><strong>${fmtNum(value)}</strong><small>${sub}</small></article>`).join('')}</section>
 <section class="grid overview-grid"><article class="panel"><div class="panel-head"><div><h2>Project requests over time</h2><p>Submitted requests, last six months</p></div><span class="pill blue">${fmtNum(orders.length)} ${T('total')}</span></div><div class="chart-wrap">${chartSvg(orders)}</div><div class="chart-foot"><span>Last 14 days</span>${sparkBars(orders)}</div></article>
 <article class="panel"><div class="panel-head"><div><h2>Request status</h2><p>Current distribution</p></div><button class="btn btn-sm btn-quiet" data-page="orders">Manage ↗</button></div><div class="status-summary">${statuses.map(x=>`<div class="status-row"><span>${esc(T(x.name))}</span><div class="status-track"><div class="status-fill" style="width:${Math.max(x.count?5:0,x.count/max*100)}%"></div></div><strong class="status-value">${fmtNum(x.count)}</strong></div>`).join('')}</div><div class="panel-sep"></div><h3 class="mini-head">Most requested products</h3>${topProducts(products,orders)}</article></section>
 <section class="grid lower-grid"><article class="panel"><div class="panel-head"><div><h2>Recent project requests</h2><p>Latest customer submissions</p></div><button class="btn btn-sm btn-quiet" data-page="orders">View all ↗</button></div>${orders.length?`<div class="table-wrap"><table class="data-table"><thead><tr><th>Reference</th><th>Customer</th><th>Product</th><th>Updated</th><th>Status</th><th></th></tr></thead><tbody>${orders.slice(0,7).map(o=>`<tr><td><span class="cell-main">${esc(o.number)}</span></td><td>${esc(o.name)}<span class="cell-sub">${esc(o.email)}</span></td><td>${esc(o.product_title)}</td><td>${moneyFreeDate(o.updated_at||o.created_at)}</td><td>${pill(o.status)}</td><td><button class="btn btn-sm btn-quiet" data-act="view-order" data-id="${o.id}">Open</button></td></tr>`).join('')}</tbody></table></div>`:`<div class="empty"><div class="empty-icon">▤</div>No project requests yet. Requests from the public site appear here.</div>`}</article>
 <div class="stack"><article class="panel"><div class="panel-head"><div><h2>Site health</h2><p>What needs attention</p></div></div><div class="health-list">${healthRows()}</div></article><article class="panel"><div class="panel-head"><div><h2>Activity</h2><p>Latest audited events</p></div><button class="btn btn-sm btn-quiet" data-page="activity">Log ↗</button></div><div class="activity-list">${activityFeed(6)}</div></article></div></section>
 <section class="grid quick-section"><article class="panel"><div class="panel-head"><div><h2>Quick actions</h2><p>Common administrative tasks</p></div></div><div class="quick-grid"><button class="quick-card" data-page="site"><span>⚙</span><strong>Website settings</strong><small>Banner, hero copy, features</small></button><button class="quick-card" data-act="new-product"><span>◈</span><strong>Add product</strong><small>Publish with a preview link</small></button><button class="quick-card" data-page="orders"><span>▤</span><strong>Review requests</strong><small>Update status and notes</small></button><button class="quick-card" data-page="support"><span>✳</span><strong>Open support</strong><small>Reply to customers</small></button></div><div class="notice">Payments and refunds are not processed here. An approval records an administrative decision only.</div></article></section>`;
}
function pageHead(kicker,title,desc,action=''){return`<div class="page-head"><div><div class="eyebrow">${kicker}</div><h1>${title}</h1><p>${desc}</p></div><div class="head-actions">${action}</div></div>`}
function toolbar(searchPlaceholder,filterOptions=[],action=''){return`<div class="toolbar"><div class="toolbar-left"><label class="search"><input data-search placeholder="${searchPlaceholder}" value="${esc(state.search)}" autocomplete="off"></label>${filterOptions.length?`<select class="filter-select" data-status-filter>${filterOptions.map(x=>`<option ${state.statusFilter===x?'selected':''}>${esc(x)}</option>`).join('')}</select>`:''}</div><div class="toolbar-right">${action}</div></div>`}
function ordersHTML(){const data=state.orders.filter(o=>{const q=state.search.toLowerCase();const hay=[o.number,o.name,o.email,o.product_title,o.status].join(' ').toLowerCase();return(!q||hay.includes(q))&&(state.statusFilter==='All'||o.status===state.statusFilter)});return`${pageHead('Work queue','Project requests','Review customer submissions, update progress and keep a clear status history.',`<button class="btn btn-quiet" data-act="export" data-kind="orders">⇩ Export CSV</button>`)}${toolbar('Search by reference, customer or product…',['All',...ordersStatus])}<div class="panel" style="padding:14px"><div class="panel-head"><div><h2>All requests</h2><p>${fmtNum(data.length)} shown · customer/project records</p></div></div>${data.length?`<div class="table-wrap"><table class="data-table"><thead><tr><th>Reference</th><th>Customer</th><th>Product</th><th>Received</th><th>Last update</th><th>Status</th><th></th></tr></thead><tbody>${data.map(o=>`<tr><td><span class="cell-main">${esc(o.number)}</span></td><td><span class="cell-main">${esc(o.name)}</span><span class="cell-sub">${esc(o.email)} · ${esc(o.phone)}</span></td><td>${esc(o.product_title)}</td><td>${moneyFreeDate(o.created_at)}</td><td>${moneyFreeDate(o.updated_at)}</td><td>${pill(o.status)}</td><td><button class="btn btn-sm btn-quiet" data-act="view-order" data-id="${o.id}">Details</button></td></tr>`).join('')}</tbody></table></div>`:`<div class="empty"><div class="empty-icon">⌕</div>No matching requests.</div>`}</div>`}
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
function productsHTML(){
 const q=state.search.toLowerCase();
 const data=state.products
  .filter(p=>(!q||[p.title,p.slug,p.category,p.summary].join(' ').toLowerCase().includes(q))
   &&(state.productFilter==='All'||(state.productFilter==='Published'?!!p.published:state.productFilter==='Featured'?!!p.featured:!p.published))
   &&(state.categoryFilter==='All'||p.category===state.categoryFilter))
  .slice().sort(productSortCompare);
 const counts={all:state.products.length,published:state.products.filter(p=>p.published).length,hidden:state.products.filter(p=>!p.published).length,featured:state.products.filter(p=>p.featured).length};
 const sel=[...state.selected].filter(id=>state.products.some(p=>Number(p.id)===Number(id)));
 const allShownSelected=data.length>0&&data.every(p=>state.selected.has(Number(p.id)));
 return `${pageHead('Catalog management','Products','Create, order, feature and publish the products shown by the AXIASOFT site.',`<button class="btn btn-quiet" data-act="export" data-kind="products">⇩ Export CSV</button><button class="btn btn-primary" data-act="new-product">＋ Add product</button>`)}
 <div class="mini-stats"><div><strong>${fmtNum(counts.all)}</strong><span>${T('Total')}</span></div><div><strong>${fmtNum(counts.published)}</strong><span>${T('Published')}</span></div><div><strong>${fmtNum(counts.hidden)}</strong><span>${T('Hidden')}</span></div><div><strong>${fmtNum(counts.featured)}</strong><span>${T('Featured')}</span></div></div>
 <div class="toolbar"><div class="toolbar-left"><label class="search"><input data-search placeholder="Search title, slug or category…" value="${esc(state.search)}"></label>
 <select class="filter-select" data-product-filter>${['All','Published','Hidden','Featured'].map(x=>`<option ${state.productFilter===x?'selected':''}>${T(x)}</option>`).join('')}</select>
 <select class="filter-select" data-category-filter>${['All','Websites','Applications','Aurion'].map(x=>`<option ${x==='All'?'':'value="'+x+'"'} ${state.categoryFilter===x?'selected':''}>${x==='All'?T('All categories'):T(x)}</option>`).join('')}</select>
 <select class="filter-select" data-product-sort>${[['manual','Manual order'],['newest','Newest first'],['title','Title A–Z'],['category','Category']].map(([v,l])=>`<option value="${v}" ${state.productSort===v?'selected':''}>${T(l)}</option>`).join('')}</select></div>
 <div class="toolbar-right"><span class="muted" style="font-size:10px">${fmtNum(data.length)} of ${fmtNum(counts.all)} products</span>${sel.length?`<button class="btn btn-sm btn-quiet" data-act="bulk-publish">${T('Publish')} ${fmtNum(sel.length)}</button><button class="btn btn-sm btn-danger" data-act="bulk-unpublish">${T('Hide')} ${fmtNum(sel.length)}</button>`:''}</div></div>
 <div class="panel" style="padding:14px">${data.length?`<div class="table-wrap"><table class="data-table"><thead><tr><th class="check-col"><input type="checkbox" data-select-all aria-label="Select all shown products" ${allShownSelected?'checked':''}></th><th>Product</th><th>Category</th><th>Price label</th><th>Availability</th><th>${T('Preview link')}</th><th>Visibility</th><th>Order</th><th>Actions</th></tr></thead><tbody>${data.map(p=>`<tr class="${p.published?'':'is-hidden'}"><td class="check-col"><input type="checkbox" data-select-product="${p.id}" aria-label="Select ${esc(p.title)}" ${state.selected.has(Number(p.id))?'checked':''}></td><td><span class="cell-main">${p.featured?'★ ':''}${esc(p.title)}</span><span class="cell-sub">/${esc(p.slug)} · ${esc(T(p.summary))}</span></td><td>${esc(T(p.category))}</td><td>${esc(p.price_label)}</td><td>${pill(p.status)}</td><td>${safeHttp(p.github_url)?`<a class="cell-sub link-cell" href="${esc(p.github_url)}" target="_blank" rel="noopener noreferrer">${esc(String(p.github_url).replace(/^https:\/\//,'').slice(0,42))}</a>`:`<span class="cell-sub">${T('Built-in preview')}</span>`}</td><td>${pill(p.published?'Published':'Hidden')}</td><td><div class="order-ctl"><button class="chip-btn" data-act="move-product" data-id="${p.id}" data-dir="-1" aria-label="${T('Move up')}">↑</button><span class="order-num">${fmtNum(Number(p.position)||0)}</span><button class="chip-btn" data-act="move-product" data-id="${p.id}" data-dir="1" aria-label="${T('Move down')}">↓</button></div></td><td><div class="row-actions"><button class="btn btn-sm ${p.featured?'btn-primary':'btn-quiet'}" data-act="feature-product" data-id="${p.id}" data-featured="${p.featured?1:0}" title="Feature on the storefront">${p.featured?'★':'☆'}</button><button class="btn btn-sm btn-quiet" data-act="edit-product" data-id="${p.id}">Edit</button><button class="btn btn-sm ${p.published?'btn-danger':'btn-quiet'}" data-act="toggle-product" data-id="${p.id}" data-published="${p.published?1:0}">${p.published?'Unpublish':'Publish'}</button></div></td></tr>`).join('')}</tbody></table></div>`:`<div class="empty"><div class="empty-icon">◈</div>No products match these filters. ${counts.all?'Clear the filters, or add a product.':'The catalog is empty — add the first product.'}</div>`}<div class="notice">Product removal is a soft unpublish. A featured product leads the public catalog; the others follow the manual order. File uploads and image management are not enabled.</div></div>`;
}
/* Only plain https URLs are ever rendered as a link, mirroring the storefront's
   safePreview() and the server's clean_github_url(). */
function safeHttp(u){const v=String(u||'').trim();return /^https:\/\/[^\s<>"']+$/i.test(v)?v:''}
/* ------------------------------------------------------------------ website */
/* Everything the storefront shows can be driven from here: the announcement
   bar, the hero copy, contact details, which sections are published, and the
   first-visit theme. Fields write into the same JSON document the server and
   the static build both understand. */
const SITE_TABS=[['identity','Identity'],['announcement','Announcement'],['hero','Home hero'],['sections','Visibility'],['contact','Contact & links'],['danger','Maintenance']];
const SECTION_FIELDS=[['show_catalog','Product catalog','The products grid and product pages'],['show_services','Services page','Website, mobile and custom software services'],['show_aurion','AURION showcase','The AURION concept page and its links'],['show_about','About page','The studio story and values'],['show_contact','Contact entry points','Contact links, the header CTA and request buttons'],['show_assistant','Support assistant','The floating AXIA chat guide on the storefront'],['show_prices','Price labels','Indicative price labels on product cards and detail pages']];
function siteVal(key){return state.settings?.[key]??''}
function switchField(name,label,hint,on){
 return `<label class="switch"><input type="checkbox" name="${name}" ${on?'checked':''}><span class="switch-track" aria-hidden="true"></span><span class="switch-copy"><strong>${T(label)}</strong><small>${T(hint)}</small></span></label>`;
}
function fieldText(name,label,value,hint='',extra=''){
 return `<div class="field"><label for="s-${name}">${label}</label><input id="s-${name}" name="${name}" value="${esc(value??'')}" ${extra}><span class="field-hint">${hint}</span></div>`;
}
function siteTabHTML(){
 const t=state.siteTab;
 if(t==='announcement'){
  const tone=siteVal('announcement_tone')||'info';
  return `<div class="panel form-panel"><div class="panel-head"><div><h2>Announcement bar</h2><p>A single line above the header, for launches, holidays or service notices.</p></div><span class="pill ${siteVal('announcement_enabled')?'green':'blue'}">${T(siteVal('announcement_enabled')?'Visible':'Hidden')}</span></div>
   <form data-form="settings"><div class="setting-grid">${switchField('announcement_enabled','Show the announcement bar','Visitors see it on every page until they dismiss it',!!siteVal('announcement_enabled'))}
   <div class="field full"><label for="s-announcement_text">Message</label><input id="s-announcement_text" name="announcement_text" maxlength="180" value="${esc(siteVal('announcement_text'))}" placeholder="New: the Northstar catalog is live"><span class="field-hint">Up to 180 characters. Plain text; links go in the field below.</span></div>
   ${fieldText('announcement_link','Link',siteVal('announcement_link'),'An https:// address, or an in-site link like #/products. Leave empty for a plain message.','maxlength="300"')}
   <div class="field"><label for="s-announcement_tone">Colour</label><select id="s-announcement_tone" name="announcement_tone">${[['info','Blue — general news'],['promo','Green — launch or offer'],['warning','Amber — service notice']].map(([v,l])=>`<option value="${v}" ${tone===v?'selected':''}>${l}</option>`).join('')}</select><span class="field-hint">Sets the bar's accent colour only.</span></div></div>
   <div class="form-actions"><button class="btn btn-primary" type="submit">Save announcement</button><button class="btn btn-quiet" type="button" data-act="settings-reset">Discard changes</button></div></form></div>`;
 }
 if(t==='hero'){
  return `<div class="panel form-panel"><div class="panel-head"><div><h2>Home hero</h2><p>The first three lines a visitor reads.</p></div><button class="btn btn-sm btn-quiet" data-act="preview-site" data-target="#/">Preview ↗</button></div>
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
     <p>${state.agent? (state.agent.configured
        ? 'Connected to an OpenAI-compatible model ('+esc(state.agent.model||'')+'). Answers are grounded in the '+state.agent.topics+' approved site facts.'
        : 'Running in local retrieval mode: '+state.agent.topics+' approved facts, no API key, no outbound request. Set AXIA_AGENT_KEY to let a model phrase the answers.')
        : 'Status unavailable in this mode.'}</p>
     <p class="form-hint">Free options: Groq, Google AI Studio (Gemini), OpenRouter free tier, Mistral, Cerebras, or a local Ollama — all OpenAI-compatible.</p></div>
   <div class="danger-card"><strong>Load sample catalog</strong><p>Demo only: adds six illustrative products with GitHub preview links so the catalog and dashboard have something to show.</p><button class="btn btn-quiet" data-act="demo-samples">Load samples</button></div>
    <div class="danger-card"><strong>Reset demo data</strong><p>Only in the GitHub Pages demo: clears the browser copy of products and settings, then reloads. Nothing in the repository changes.</p><button class="btn btn-danger" data-act="demo-reset">Reset demo</button></div>
    <div class="danger-card"><strong>Export settings</strong><p>Downloads the current settings as JSON, ready to commit as <code>data/settings.json</code>.</p><button class="btn btn-quiet" data-act="export-settings">Export JSON</button></div>
   </div><div class="notice">Deleting an account or a request is deliberately not possible here; those records stay for audit. Products are hidden rather than deleted so old requests keep their references.</div></div>`;
 }
 const s=state.settings||{};
 return `<div class="panel form-panel"><div class="panel-head"><div><h2>Site identity</h2><p>The first-visit theme for visitors who have never chosen one.</p></div></div>
  <form data-form="settings"><div class="setting-grid"><div class="field"><label for="s-default_theme">Default theme</label><select id="s-default_theme" name="default_theme">${[['dark','Dark'],['light','Light'],['system','Match the device']].map(([v,l])=>`<option value="${v}" ${s.default_theme===v?'selected':''}>${l}</option>`).join('')}</select><span class="field-hint">A visitor's own saved choice always wins.</span></div>
  <div class="field"><label>Site address</label><input value="${esc(location.origin)}" readonly><span class="field-hint">The host this console publishes to.</span></div>
  <div class="field full"><label>Administrator</label><input value="${esc(state.me?.name||'')} · ${esc(state.me?.email||'')}" readonly><span class="field-hint">Roles are enforced by the server, not by this screen.</span></div></div>
  <div class="form-actions"><button class="btn btn-primary" type="submit">Save identity</button></div></form></div>`;
}
function visibleSetting(name){return state.settings?state.settings[name]!==false:true}
function siteHTML(){
 const dirty=state.dirty;
 return `${pageHead('Storefront control','Website','Control the announcement bar, the home hero, contact details and which sections the public site shows.',`<button class="btn btn-quiet" data-act="settings-refresh">↻ Reload</button><button class="btn btn-quiet" data-act="preview-site" data-target="/">Open site ↗</button>`)}
 <div class="tabs">${SITE_TABS.map(([id,label])=>`<button class="tab ${state.siteTab===id?'active':''}" data-site-tab="${id}">${T(label)}</button>`).join('')}</div>
 ${dirty?`<div class="dirty-note" role="status"><span>●</span> Unsaved changes on this page — press <strong>Save</strong> to publish them to the site.</div>`:''}
 <div class="site-tab-body">${siteTabHTML()}</div>`;
}
function customersHTML(){const data=state.customers.filter(c=>{const q=state.search.toLowerCase();return !q||[c.name,c.email,c.phone].join(' ').toLowerCase().includes(q)});return`${pageHead('Customer records','Customers','View customer accounts and their support/request counts. Account access changes revoke active sessions.',`<button class="btn btn-quiet" data-act="export" data-kind="customers">⇩ Export CSV</button>`)}${toolbar('Search name, email or phone…')}<div class="panel" style="padding:14px"><div class="panel-head"><div><h2>Customer directory</h2><p>${fmtNum(data.length)} ${T('records · customer accounts only')}</p></div></div>${data.length?`<div class="table-wrap"><table class="data-table"><thead><tr><th>Customer</th><th>Contact</th><th>Joined</th><th>Requests</th><th>Tickets</th><th>Access</th><th>Action</th></tr></thead><tbody>${data.map(c=>`<tr><td><span class="cell-main">${esc(c.name)}</span><span class="cell-sub">Customer ID ${c.id}</span></td><td>${esc(c.email)}<span class="cell-sub">${esc(c.phone||'No phone on file')}</span></td><td>${moneyFreeDate(c.created_at)}</td><td>${fmtNum(c.order_count)}</td><td>${fmtNum(c.ticket_count)}</td><td>${pill(T(c.active?'Active':'Suspended'))}</td><td><button class="btn btn-sm ${c.active?'btn-danger':'btn-quiet'}" data-act="customer-status" data-id="${c.id}" data-active="${c.active?1:0}">${T(c.active?'Suspend':'Reactivate')}</button></td></tr>`).join('')}</tbody></table></div>`:`<div class="empty">No customers found.</div>`}<div class="notice">Suspending an account blocks future sign-in and invalidates its active sessions. Admin accounts cannot be changed from this screen.</div></div>`}
function supportHTML(){const data=state.tickets.filter(t=>{const q=state.search.toLowerCase();return(!q||[t.ref,t.email,t.subject,t.message].join(' ').toLowerCase().includes(q))&&(state.statusFilter==='All'||t.status===state.statusFilter)});return`${pageHead('Customer care','Support tickets','Review conversations and reply through the website support channel.',`<button class="btn btn-quiet" data-act="export" data-kind="tickets">⇩ Export CSV</button>`)}${toolbar('Search reference, email or subject…',['All','Open','In progress','Closed'])}<div class="panel" style="padding:14px"><div class="panel-head"><div><h2>Support inbox</h2><p>${fmtNum(data.length)} ${T('matching tickets')}</p></div></div>${data.length?`<div class="table-wrap"><table class="data-table"><thead><tr><th>Reference</th><th>Customer email</th><th>Subject / first message</th><th>Created</th><th>Status</th><th></th></tr></thead><tbody>${data.map(t=>`<tr><td><span class="cell-main">${esc(t.ref)}</span></td><td>${esc(t.email)}</td><td><span class="cell-main">${esc(t.subject)}</span><span class="cell-sub">${esc(t.message)}</span></td><td>${moneyFreeDate(t.created_at)}</td><td>${pill(t.status)}</td><td><button class="btn btn-sm btn-quiet" data-act="view-ticket" data-id="${t.id}">Open thread</button></td></tr>`).join('')}</tbody></table></div>`:`<div class="empty"><div class="empty-icon">✳</div>No tickets found.</div>`}</div>`}
function refundsHTML(){const data=state.refunds.filter(r=>{const q=state.search.toLowerCase();return(!q||[r.ref,r.order_number,r.reason,r.status].join(' ').toLowerCase().includes(q))&&(state.statusFilter==='All'||r.status===state.statusFilter)});return`${pageHead('Policy review','Refund requests','Review requests against the published policy. This panel does not issue payments or move funds.',`<button class="btn btn-quiet" data-act="export" data-kind="refunds">⇩ Export CSV</button>`)}${toolbar('Search request, order or reason…',['All','Under review','Approved','Rejected'])}<div class="panel" style="padding:14px"><div class="panel-head"><div><h2>Refund queue</h2><p>${fmtNum(data.filter(x=>x.status==='Under review').length)} ${T('awaiting a decision')} · ${fmtNum(data.length)} ${T('total shown')}</p></div></div>${data.length?`<div class="table-wrap"><table class="data-table"><thead><tr><th>Request</th><th>Order</th><th>Reason</th><th>Submitted</th><th>Status</th><th>Decision</th></tr></thead><tbody>${data.map(r=>`<tr><td><span class="cell-main">${esc(r.ref)}</span></td><td>${esc(r.order_number)}</td><td><span class="cell-sub reason-cell">${esc(r.reason)}</span></td><td>${moneyFreeDate(r.created_at)}</td><td>${pill(r.status)}</td><td>${r.status==='Under review'?`<div class="row-actions"><button class="btn btn-sm btn-primary" data-act="refund-decision" data-id="${r.id}" data-decision="Approved">Approve</button><button class="btn btn-sm btn-danger" data-act="refund-decision" data-id="${r.id}" data-decision="Rejected">Reject</button></div>`:`<span class="cell-sub">${esc(r.admin_note||'Decision recorded')}</span>`}</td></tr>`).join('')}</tbody></table></div>`:`<div class="empty">No refund requests found.</div>`}<div class="notice">Approval records a review decision only. No payment is processed or guaranteed. Requests are subject to applicable law and the published policy.</div></div>`}
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
     <a class="btn btn-sm btn-quiet" href="/AxiaPlatform/blog/${esc(a.slug)}/" target="_blank" rel="noopener">View ↗</a>
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
   <button class="btn btn-sm btn-quiet" data-act="close-modal" aria-label="Close">×</button></div>
   <article class="preview-article"><div class="blog-prose">${html}</div></article>
   <p class="form-hint" style="margin-top:16px">The public page adds the headline, date, reading time, tags and structured data around this body.</p>
 </section>`)}

function deleteArticle(id){
 const row=(state.articles||[]).find(a=>a.id===id);
 if(!confirm('Delete "'+(row?row.title:'this article')+'"? The public page is removed immediately.'))return;
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

function activityHTML(){return`${pageHead('Security & operations','Activity log','Recent audited administrative and account events. The log is read-only.',`<button class="btn btn-quiet" data-act="refresh">↻ Refresh log</button>`)}<div class="panel"><div class="panel-head"><div><h2>Audit events</h2><p>Latest ${fmtNum(state.audit.length)} recorded events</p></div></div>${state.audit.length?`<div class="activity-list">${state.audit.map(a=>`<div class="activity-item"><span class="activity-dot">${iconFor(a.entity)}</span><div><strong>${esc(actionLabel(a.action))} · ${esc(a.entity)}</strong><p>${esc(a.actor_name||'System')} ${a.actor_email?`(${esc(a.actor_email)})`:''} · Record ${esc(a.entity_id)}</p></div><time>${moneyFreeDate(a.created_at)}</time></div>`).join('')}</div>`:`<div class="empty">No audited events recorded yet.</div>`}</div>`}
function actionLabel(s){return({create:'Created',update:'Updated',unpublish:'Unpublished',status_change:'Changed order status',ticket_status:'Changed ticket status',ticket_reply:'Replied to ticket',refund_decision:'Recorded refund decision',customer_access:'Changed customer access',settings:'Updated website settings',login:'Signed in',register:'Registered'})[s]||s}
function contentHTML(){switch(state.page){case'site':return siteHTML();case'articles':return articlesHTML();case'orders':return ordersHTML();case'products':return productsHTML();case'customers':return customersHTML();case'support':return supportHTML();case'refunds':return refundsHTML();case'activity':return activityHTML();default:return overviewHTML()}}
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
 else if(state.page==='products'){state.overview=state.overview||await api('/api/admin/overview');state.products=state.overview.products||[]}
 else if(state.page==='customers'){const r=await api('/api/admin/customers');state.customers=r.customers||[]}
 else if(state.page==='support'){try{state.tickets=await api('/api/support')}catch(e){state.tickets=[]}}
 else if(state.page==='refunds'){try{state.refunds=await api('/api/refunds')}catch(e){state.refunds=[]}}
 else if(state.page==='articles')state.articles=(await api('/api/admin/articles')).articles||[]
 if(state.page==='dashboard')state.agent=await api('/api/admin/agent').catch(()=>null)
 else if(state.page==='activity')state.audit=await api('/api/admin/audit?limit=150')
 }catch(e){if(e.status===401||e.status===403){state.me=null;state.csrf=null;loginView(e.status===403?'Administrator access required. Please sign in with an administrator account.':e.message);return}toast(e.message,true)}finally{state.loading=false}
 $('#pageContent')&&($('#pageContent').innerHTML=contentHTML());updateNav();
}
function updateNav(){ $$('.side-link[data-page]').forEach(b=>b.classList.toggle('active',b.dataset.page===state.page));const title=$('.crumb strong');if(title)title.textContent=({dashboard:'Overview',site:'Website',orders:'Project requests',products:'Products',customers:'Customers',support:'Support',refunds:'Refunds',activity:'Activity log'})[state.page]||'Overview';const side=$('#sidebar');if(side)side.classList.remove('open');$('.side-scrim')?.classList.remove('show') }
async function loadSession(){try{const s=await api('/api/me');state.me=s.user;state.csrf=s.csrf}catch{state.me=null;state.csrf=null}if(!state.me){loginView();return}if(state.me.role!=='admin'){deniedView();return}if(!root.querySelector('.admin-shell'))shell();await fetchPageData()}
function nav(page){
if(state.dirty&&!confirm('Discard the unsaved settings changes?'))return;
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
function modalHead(kicker,title,sub=''){return`<div class="modal-head"><div><div class="eyebrow">${kicker}</div><h2>${title}</h2>${sub?`<p>${sub}</p>`:''}</div><button class="icon-close" type="button" data-act="close-modal" aria-label="Close">×</button></div>`}
async function openOrder(id){const o=state.orders.find(x=>x.id===Number(id));if(!o)return;showModal(`${modalHead('Project request',esc(o.number),`${esc(o.product_title)} · submitted ${moneyFreeDate(o.created_at)}`)}<div class="detail-grid"><div class="detail-item"><small>Customer</small><strong>${esc(o.name)}</strong></div><div class="detail-item"><small>Email / phone</small><strong>${esc(o.email)}<br>${esc(o.phone)}</strong></div><div class="detail-item"><small>Contact preference</small><strong>${esc(o.contact_method||'Email')}</strong></div><div class="detail-item"><small>Current status</small><strong>${pill(o.status)}</strong></div><div class="detail-item full"><small>Project details</small><p>${esc(o.description)}</p></div><div class="detail-item full"><small>Additional requirements</small><p>${esc(o.requirements||'No additional requirements supplied.')}</p></div></div><h3 style="font-size:11px;margin:19px 0 9px">Status history</h3><div class="timeline" id="orderTimeline"><div class="skeleton" style="width:70%;margin:8px"></div><div class="skeleton" style="width:50%;margin:8px"></div></div><form data-form="order-update" data-id="${o.id}"><div class="form-grid"><div class="field"><label>Update status</label><select name="status">${ordersStatus.map(s=>`<option ${o.status===s?'selected':''}>${s}</option>`).join('')}</select></div><div class="field"><label>Internal status note</label><input name="note" maxlength="1000" placeholder="Optional note for the audit trail"></div></div><div class="modal-actions"><button class="btn btn-quiet" type="button" data-act="close-modal">Close</button><button class="btn btn-primary">Save status update</button></div></form>`,true);
 try{const history=await api(`/api/admin/orders/${Number(id)}/history`);const box=$('#orderTimeline');if(box)box.innerHTML=history.length?history.map(h=>`<div class="timeline-item"><strong>${esc(h.status)}</strong><p>${esc(h.note||'Status recorded')}</p><small>${moneyFreeDate(h.created_at)} · ${esc(h.actor_name||'System')}</small></div>`).join(''):'<div class="muted" style="font-size:9px">No history yet.</div>'}catch(e){const box=$('#orderTimeline');if(box)box.innerHTML=`<div class="muted" style="font-size:9px">${esc(e.message)}</div>`}
}
function productForm(p=null){const edit=!!p;showModal(`${modalHead(edit?'Catalog editor':'New catalog product',edit?'Edit product':'Add a product concept',edit?'Changes affect the public product data, its featured slot and its order.':'Add a product to the database-backed catalog.') }<form data-form="product" data-id="${p?.id||''}"><div class="form-grid"><div class="field"><label>Product title</label><input name="title" required maxlength="140" value="${esc(p?.title||'')}"></div><div class="field"><label>URL slug</label><input name="slug" required pattern="[a-z0-9-]{3,100}" maxlength="100" value="${esc(p?.slug||'')}"><span class="field-hint">Lowercase letters, digits and hyphens.</span></div><div class="field"><label>Category</label><select name="category">${['Websites','Applications','Aurion'].map(x=>`<option ${p?.category===x?'selected':''}>${x}</option>`).join('')}</select></div><div class="field"><label>Availability label</label><select name="status"><option value="available" ${p?.status==='available'?'selected':''}>Available</option><option value="showcase" ${p?.status==='showcase'?'selected':''}>Showcase only</option></select></div><div class="field"><label>Price label</label><input name="price_label" maxlength="80" value="${esc(p?.price_label||'Request a quote')}"></div><div class="field full"><label>GitHub preview link</label><input name="github_url" type="url" inputmode="url" maxlength="300" pattern="https://.+" placeholder="https://github.com/your-org/your-project" value="${esc(p?.github_url||'')}"><span class="field-hint">Opened by the product preview button. Must start with https://. Leave empty to show the built-in concept preview.</span></div><div class="field full"><label>Cover image</label>${coverUploader(p?.cover||'')}<span class="field-hint">PNG, JPEG, WebP or GIF, up to 5 MB. Shown on the product card and its detail page. The image is re-encoded on upload, so camera metadata is removed.</span></div><div class="field full"><label>Short summary</label><input name="summary" required maxlength="300" value="${esc(p?.summary||'')}"></div><div class="field full"><label>Full description</label><textarea name="description" required maxlength="3000">${esc(p?.description||'')}</textarea></div><div class="field"><label>Features</label><textarea name="features" placeholder="Separate each item with a comma">${esc((p?.features||[]).join(', '))}</textarea></div><div class="field"><label>Technologies</label><textarea name="technologies" placeholder="Separate each item with a comma">${esc((p?.technologies||[]).join(', '))}</textarea></div><div class="field"><label for="p-position">Catalog order</label><input id="p-position" name="position" type="number" min="0" max="9999" step="1" value="${Number(p?.position)||0}"><span class="field-hint">Lower numbers appear first.</span></div><div class="field" style="align-content:end"><label class="check-line"><input name="featured" type="checkbox" ${p&&p.featured?'checked':''}> Feature this product</label><span class="field-hint">Featured products lead the public catalog.</span></div><div class="field full"><label><input name="published" type="checkbox" ${p&&!p.published?'':'checked'}> Published in product data</label><span class="field-hint">AURION remains a showcase concept; no trading or real license/payment features are enabled.</span></div></div><div class="modal-actions"><button class="btn btn-quiet" type="button" data-act="close-modal">Cancel</button><button class="btn btn-primary">${edit?'Save product':'Create product'}</button></div></form>`,true)}
function openTicket(id){const t=state.tickets.find(x=>x.id===Number(id));if(!t)return;const msgs=[{message:t.message,sender:t.email,created_at:t.created_at},...(t.messages||[])];showModal(`${modalHead('Support conversation',esc(t.ref),esc(t.subject))}<div class="detail-grid" style="margin-bottom:14px"><div class="detail-item"><small>Customer email</small><strong>${esc(t.email)}</strong></div><div class="detail-item"><small>Ticket state</small><strong>${pill(t.status)}</strong></div></div><div class="thread">${msgs.map(m=>`<div class="message ${m.sender==='Team'||m.sender===state.me.name?'admin':''}">${esc(m.message)}<small>${esc(m.sender||'Customer')} · ${moneyFreeDate(m.created_at)}</small></div>`).join('')}</div><form data-form="ticket-reply" data-id="${t.id}"><div class="field"><label>Reply to customer</label><textarea name="message" required minlength="2" maxlength="3000" placeholder="Write a clear, helpful response…"></textarea></div><div class="form-grid" style="margin-top:10px"><div class="field"><label>Ticket status</label><select name="status">${['Open','In progress','Closed'].map(s=>`<option ${t.status===s?'selected':''}>${s}</option>`).join('')}</select></div><div class="field" style="align-content:end"><span class="field-hint">Saving a reply moves the ticket to In progress.</span></div></div><div class="modal-actions"><button class="btn btn-quiet" type="button" data-act="close-modal">Close</button><button class="btn btn-primary">Send reply</button></div></form>`,true)}
function refundModal(id,decision){const r=state.refunds.find(x=>x.id===Number(id));if(!r)return;showModal(`${modalHead('Refund review',`${decision} request ${esc(r.ref)}`,`Order ${esc(r.order_number)} · submitted ${moneyFreeDate(r.created_at)}`)}<div class="detail-item"><small>Customer's stated reason</small><p>${esc(r.reason)}</p></div><form data-form="refund" data-id="${r.id}" data-decision="${decision}"><div class="field" style="margin-top:12px"><label>Administrative note</label><textarea name="note" maxlength="1000" placeholder="Record the review rationale. This will not trigger a payment."></textarea></div><div class="field" style="margin-top:10px"><label>Transaction reference (optional, record only)</label><input name="transaction_ref" maxlength="120"></div><div class="notice">${decision==='Approved'?'Approval records a decision only.':'Rejection records a decision only.'} The website does not process or confirm payment-provider refunds.</div><div class="modal-actions"><button class="btn btn-quiet" type="button" data-act="close-modal">Cancel</button><button class="btn ${decision==='Approved'?'btn-primary':'btn-danger'}">Record ${decision.toLowerCase()}</button></div></form>`)}
function exportCsv(kind){const data=({orders:state.orders,products:state.products,customers:state.customers,tickets:state.tickets,refunds:state.refunds})[kind]||[];if(!data.length){toast('There are no records to export.');return}const columns=Object.keys(data[0]).filter(k=>!['password_hash','csrf','token_hash'].includes(k));const csv=[columns.map(qcsv).join(','),...data.map(row=>columns.map(k=>qcsv(Array.isArray(row[k])?row[k].join('; '):row[k])).join(','))].join('\r\n');const blob=new Blob(['\ufeff'+csv],{type:'text/csv;charset=utf-8'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=`axiasoft-${kind}-${new Date().toISOString().slice(0,10)}.csv`;a.click();URL.revokeObjectURL(a.href);toast('CSV export downloaded.')}
function qcsv(v){return'"'+String(v??'').replace(/"/g,'""')+'"'}
async function refreshAll(){state.overview=null;state.orders=[];state.products=[];await fetchPageData();toast('Data refreshed.');state.savedSettings={...state.settings};state.dirty=false}
function setSearch(value){state.search=value;const c=$('#pageContent');if(c)c.innerHTML=contentHTML()}
function clickHandler(e){
 const page=e.target.closest('[data-page]');if(page){e.preventDefault();nav(page.dataset.page);return}
 const toggle=e.target.closest('#languageToggle');if(toggle){localStorage.setItem('axia-lang',document.documentElement.lang==='fa'?'en':'fa');location.reload();return}
 const siteTab=e.target.closest('[data-site-tab]');
if(siteTab){
if(state.dirty&&!confirm('Discard the unsaved changes on this tab?'))return;
state.siteTab=siteTab.dataset.siteTab;
state.dirty=false;
$('#pageContent').innerHTML=contentHTML();
return}
 const rteBtn=e.target.closest('[data-rte]');
 if(rteBtn){applyFormat(rteBtn.dataset.rte);return}
 const b=e.target.closest('[data-act]');if(!b)return;const act=b.dataset.act;
 if(act==='close-modal'||(act==='backdrop-close'&&e.target===b)){closeModal();return}
 if(act==='toggle-nav'){const s=$('#sidebar');s?.classList.toggle('open');$('.side-scrim')?.classList.toggle('show',s?.classList.contains('open'));return}
 if(act==='close-nav'){$('#sidebar')?.classList.remove('open');$('.side-scrim')?.classList.remove('show');return}
 if(act==='theme'){const t=document.documentElement.dataset.theme==='dark'?'light':'dark';document.documentElement.dataset.theme=t;localStorage.setItem('axia-theme',t);b.textContent=t==='dark'?'◐':'☼';return}
 if(act==='refresh'){refreshAll();return}
 if(act==='new-article'){state.articleDraft={title:'',slug:'',summary:'',tags:[],body:'',status:'draft'};$('#pageContent').innerHTML=contentHTML();return}
 if(act==='close-article'){state.articleDraft=null;$('#pageContent').innerHTML=contentHTML();return}
 if(act==='article-preview'){previewArticle();return}
 if(act==='save-article'){saveArticle(null,b.dataset.status);return}
 if(act==='edit-article'){openArticle(+b.dataset.id);return}
 if(act==='delete-article'){deleteArticle(+b.dataset.id);return}
 if(act==='logout'){logout();return}
 if(act==='new-product'){productForm();return}
 if(act==='edit-product'){const p=state.products.find(x=>x.id===Number(b.dataset.id));if(p)productForm(p);return}
 if(act==='view-order'){openOrder(b.dataset.id);return}
 if(act==='view-ticket'){openTicket(b.dataset.id);return}
 if(act==='refund-decision'){refundModal(b.dataset.id,b.dataset.decision);return}
 if(act==='export'){exportCsv(b.dataset.kind);return}
 if(act==='toggle-product'){toggleProduct(b);return}
 if(act==='settings-refresh'){state.dirty=false;state.settings=null;fetchPageData().then(()=>toast('Settings reloaded.'));return}
 if(act==='settings-reset'){if(state.savedSettings)state.settings={...state.savedSettings};state.dirty=false;$('#pageContent').innerHTML=contentHTML();toast('Unsaved changes discarded.');return}
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
}
async function bulkPublishAll(){
 if(!confirm('Publish every hidden product?'))return;
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
 if(!confirm(`${publish?'Publish':'Hide'} ${ids.length} selected product(s)?`))return;
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
async function toggleProduct(btn){const p=state.products.find(x=>x.id===Number(btn.dataset.id));if(!p)return;const publish=!p.published;if(!confirm(publish?'Publish this product in public product data?':'Unpublish this product? Existing order history is preserved.'))return;try{if(publish){await api('/api/admin/products',{method:'PUT',body:{id:p.id,published:true}})}else{await api('/api/admin/products',{method:'DELETE',body:{id:p.id}})}toast(publish?'Product published.':'Product unpublished; history is preserved.');state.overview=null;await fetchPageData()}catch(e){toast(e.message,true)}}
async function changeCustomerStatus(btn){const c=state.customers.find(x=>x.id===Number(btn.dataset.id));if(!c)return;const active=!c.active;if(!confirm(active?`Reactivate sign-in for ${c.name}?`:`Suspend ${c.name}? This will revoke active sessions.`))return;try{await api('/api/admin/customers/status',{method:'PUT',body:{id:c.id,active}});toast(active?'Customer reactivated.':'Customer suspended; sessions revoked.');const r=await api('/api/admin/customers');state.customers=r.customers;$('#pageContent').innerHTML=customersHTML()}catch(e){toast(e.message,true)}}
async function submitHandler(e){const form=e.target.closest('form[data-form]');if(!form)return;e.preventDefault();const submit=$('button[type="submit"]',form)||$('button:not([type="button"])',form);if(submit){submit.disabled=true;submit.dataset.old=submit.textContent;submit.textContent='Saving…'}const values=Object.fromEntries(new FormData(form));try{
 if(form.dataset.form==='login'){const data=await api('/api/login',{method:'POST',body:{email:values.email,password:values.password}});state.me=data.user;if(state.me.role!=='admin'){deniedView();return}const s=await api('/api/me');state.csrf=s.csrf;state.page=location.hash.slice(1)||'dashboard';if(!PAGES.includes(state.page))state.page='dashboard';shell();await fetchPageData();toast('Administrator session established.');return}
 if(form.dataset.form==='settings'){await saveSettings(form);return}
 if(form.dataset.form==='product'){const features=String(values.features||'').split(/[\n,]+/).map(x=>x.trim()).filter(Boolean).slice(0,20);const technologies=String(values.technologies||'').split(/[\n,]+/).map(x=>x.trim()).filter(Boolean).slice(0,20);const payload={title:values.title,slug:values.slug,category:values.category,status:values.status,price_label:values.price_label,cover:values.cover_image||'',summary:values.summary,description:values.description,github_url:(values.github_url||'').trim(),features,technologies,published:form.elements.published.checked,featured:form.elements.featured?.checked||false,position:Number(values.position)||0};if(form.dataset.id){payload.id=Number(form.dataset.id);await api('/api/admin/products',{method:'PUT',body:payload});toast('Product changes saved.')}else{await api('/api/admin/products',{method:'POST',body:payload});toast('Product added.')}closeModal();state.overview=null;await fetchPageData();return}
 if(form.dataset.form==='order-update'){await api('/api/admin/orders/status',{method:'PUT',body:{id:Number(form.dataset.id),status:values.status,note:values.note||''}});closeModal();toast('Project status and history updated.');state.overview=null;await fetchPageData();return}
 if(form.dataset.form==='ticket-reply'){if(values.message?.trim())await api('/api/admin/tickets/reply',{method:'POST',body:{id:Number(form.dataset.id),message:values.message.trim()}});if(values.status!=='In progress')await api('/api/admin/tickets/status',{method:'PUT',body:{id:Number(form.dataset.id),status:values.status}});closeModal();toast(values.message?.trim()?'Reply added and ticket updated.':'Ticket status updated.');state.tickets=await api('/api/support');$('#pageContent').innerHTML=supportHTML();return}
 if(form.dataset.form==='refund'){await api('/api/admin/refunds/decision',{method:'PUT',body:{id:Number(form.dataset.id),status:form.dataset.decision,note:values.note||'',transaction_ref:values.transaction_ref||''}});closeModal();toast('Refund decision recorded. No payment was processed.');state.refunds=await api('/api/refunds');$('#pageContent').innerHTML=refundsHTML();return}
 }catch(err){const old=$('.error-note',form);if(old)old.remove();const note=document.createElement('div');note.className='error-note';note.textContent=err.message;form.prepend(note);if(submit){submit.disabled=false;submit.textContent=submit.dataset.old||'Try again'}}}
function inputHandler(e){if(e.target.matches('[data-search]')){state.search=e.target.value;clearTimeout(inputHandler.timer);inputHandler.timer=setTimeout(()=>{const c=$('#pageContent');if(c)c.innerHTML=contentHTML();const input=$('[data-search]');if(input){input.focus();input.setSelectionRange(input.value.length,input.value.length)}},180)}if(e.target.matches('[data-status-filter]')){state.statusFilter=e.target.value;$('#pageContent').innerHTML=contentHTML()}if(e.target.matches('[data-product-filter]')){state.productFilter=e.target.value;$('#pageContent').innerHTML=contentHTML()}
if(e.target.matches('[data-category-filter]')){state.categoryFilter=e.target.value;$('#pageContent').innerHTML=productsHTML()}
if(e.target.matches('[data-product-sort]')){state.productSort=e.target.value;$('#pageContent').innerHTML=productsHTML()}
if(e.target.matches('[data-select-product]')){const id=Number(e.target.dataset.selectProduct);e.target.checked?state.selected.add(id):state.selected.delete(id);$('#pageContent').innerHTML=productsHTML()}
if(e.target.matches('[data-select-all]')){$$('[data-select-product]').forEach(box=>{const id=Number(box.dataset.selectProduct);e.target.checked?state.selected.add(id):state.selected.delete(id)});$('#pageContent').innerHTML=productsHTML()}
if(e.target.closest('[data-form="settings"]')){state.dirty=true;if(!$('.dirty-note')){$('.site-tab-body')?.insertAdjacentHTML('beforebegin','<div class="dirty-note" role="status"><span>●</span> Unsaved changes on this page — press <strong>Save</strong> to publish them to the site.</div>')}}}
async function logout(){try{await api('/api/logout',{method:'POST',body:{}})}catch{}state.me=null;state.csrf=null;closeModal();loginView()}
root.addEventListener('click',clickHandler);root.addEventListener('submit',submitHandler);root.addEventListener('input',inputHandler);root.addEventListener('change',inputHandler);overlays.addEventListener('click',clickHandler);overlays.addEventListener('submit',submitHandler);overlays.addEventListener('input',inputHandler);overlays.addEventListener('change',inputHandler);
document.addEventListener('keydown',e=>{if(e.key==='Escape'){closeModal();$('#sidebar')?.classList.remove('open');$('.side-scrim')?.classList.remove('show')}});
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
  async function uploadCover(file) {
    if (!file) return null;
    if (!/^image\/(png|jpeg|webp|gif)$/.test(file.type)) {
      throw new Error('Choose a PNG, JPEG, WebP or GIF image.');
    }
    if (file.size > COVER_MAX) {
      throw new Error('That image is larger than 5 MB.');
    }
    const headers = { 'Content-Type': file.type };
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

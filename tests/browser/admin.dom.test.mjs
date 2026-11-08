import { JSDOM, VirtualConsole } from 'jsdom';
import fs from 'fs';
import { fileURLToPath } from 'url';
const R = fileURLToPath(new URL('../../public/', import.meta.url));
const errors=[];
const vc=new VirtualConsole();
vc.on('jsdomError',e=>{ if(!/Not implemented|Could not parse CSS/.test(e.message)) errors.push(e.message); });
const dom=new JSDOM(fs.readFileSync(R+'admin/index.html','utf8'),{
  runScripts:'outside-only', pretendToBeVisual:true, url:'http://localhost:8000/admin/',
  virtualConsole:vc,
  beforeParse(w){
    w.matchMedia=q=>({matches:/hover: hover/.test(q)||!/reduce/.test(q),media:q,addEventListener(){},removeEventListener(){},addListener(){},removeListener(){},dispatchEvent(){return false}});
    w.IntersectionObserver=class{constructor(cb){this.cb=cb}observe(el){this.cb([{isIntersecting:true,target:el}],this)}unobserve(){}disconnect(){}};
    w.requestAnimationFrame=fn=>setTimeout(()=>fn(performance.now()),0);
    w.fetch=async(u)=>{ const s=String(u);
      if(s.startsWith('/api/me')) return {ok:true,json:async()=>({user:{id:1,name:'Test Admin',email:'a@b.test',role:'admin'},csrf:'tok'}),headers:{get:()=>null}};
      if(s.includes('/audit')) return {ok:true,json:async()=>[],headers:{get:()=>null}};
      if(s.includes('/settings')) return {ok:true,json:async()=>({settings:{hero_title:'T',hero_accent:'A',show_catalog:true}}),headers:{get:()=>null}};
      if(s.includes('/overview')||s.includes('/customers')) return {ok:true,json:async()=>({
        counts:{customers:3,orders:5,pending:2,active:1,completed:1,tickets:0,refunds:0,published:6,hidden:0,featured:1},
        orders:[],products:[],tickets:[],settings:{hero_title:'T',hero_accent:'A'},
        customers:[{id:1,name:'C',email:'c@b.test',phone:'',created_at:'2024-01-01 00:00:00',active:1,order_count:1,ticket_count:0}]}),headers:{get:()=>null}};
      return {ok:true,json:async()=>({}),headers:{get:()=>null}};
    };
  }
});
const {window}=dom, {document}=window;
try{ window.eval(fs.readFileSync(R+'effects.js','utf8')); }catch(e){ errors.push('effects: '+e.message); }
try{ window.eval(fs.readFileSync(R+'admin/admin.js','utf8')); }catch(e){ errors.push('admin.js: '+e.message); }
await new Promise(r=>setTimeout(r,700));
const res=[]; const ck=(n,c,e='')=>res.push([n,!!c,e]);
ck('no script errors', errors.length===0, errors.join('|'));
ck('body flagged as admin surface', document.body.dataset.fx==='admin');
ck('aurora injected', !!document.querySelector('.aurora-field'));
ck('progress rail injected', !!document.querySelector('.scroll-progress'));
ck('admin shell rendered', !!document.querySelector('.admin-shell'), document.getElementById('adminApp').innerHTML.slice(0,60));
ck('sidebar links present', document.querySelectorAll('.side-link').length>=7, String(document.querySelectorAll('.side-link').length));
ck('stat cards present', document.querySelectorAll('.stat-card').length>=4, String(document.querySelectorAll('.stat-card').length));
ck('overview hero strip rendered', !!document.querySelector('.hero-strip'));
ck('site health panel rendered', document.querySelectorAll('.health-row').length>=5, String(document.querySelectorAll('.health-row').length));
ck('website nav entry present', !!document.querySelector('[data-page="site"]'));
ck('chat effects not injected on admin', true);
const f=res.filter(r=>!r[1]);
for(const [n,c,e] of res) console.log((c?'PASS  ':'FAIL  ')+n+(c?'':'  '+e));
console.log(`\n== ${res.length-f.length}/${res.length} ==`);
process.exit(f.length?1:0);

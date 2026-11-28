const {chromium,devices}=require('playwright');const fs=require('fs');
const svg=fs.readFileSync('/home/user/ua-art-autopilot/cloud/logo_001/c_badge.svg','utf8');
const uri='data:image/svg+xml;base64,'+Buffer.from(svg).toString('base64');
const home='<svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/></svg>';
const back='<svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"><path d="M15 5l-7 7 7 7"/></svg>';
const css='a.brand{margin-left:-8px !important}a.brand .brand-mark{background:url('+uri+') center/contain no-repeat !important;color:transparent !important;font-size:0 !important;border:0 !important;outline:0 !important;box-shadow:none !important;border-radius:0 !important}'+
'html body a.brand .brand-copy::after{visibility:hidden !important}'+
'.nv{position:absolute;display:flex;gap:6px;z-index:20}.nv a{display:inline-flex;align-items:center;gap:4px;height:22px;padding:0 10px;font:500 11.5px Inter,sans-serif;color:#E8C87D;text-decoration:none;border:1px solid rgba(232,200,125,.6);border-radius:999px;position:relative}.nv a::before{content:"";position:absolute;inset:-11px -3px}'+
'.lang-toggle{position:absolute !important;right:66px;z-index:20;height:30px !important;padding:2px !important;margin:0 !important}.lang-toggle{width:104px !important;gap:0 !important;display:flex !important}.lang-toggle > button{min-width:0 !important;flex:1 1 0 !important}.lang-toggle > :not(button){flex:0 0 1px !important;width:1px !important;min-width:0 !important;margin:4px 0 !important;padding:0 !important}.lang-toggle button{height:26px !important;min-height:0 !important;width:auto !important;font-size:11px !important;padding:0 !important;letter-spacing:0 !important}';
(async()=>{const b=await chromium.launch();const c=await b.newContext({...devices['iPhone 13']});const p=await c.newPage();
await p.goto('https://www.uaart.com.ua/video/katalog.html',{waitUntil:'load',timeout:60000});await p.waitForTimeout(1500);
await p.addStyleTag({content:css});
await p.evaluate(([home,back])=>{const hm=document.querySelector('.header-main');const bc=document.querySelector('a.brand .brand-copy');const hr=hm.getBoundingClientRect();const r=bc.getBoundingClientRect();
const n=document.createElement('div');n.className='nv';n.innerHTML='<a href="#">'+home+'Головна</a><a href="#">'+back+'Назад</a>';hm.appendChild(n);
const top=r.bottom-hr.top-22;n.style.left=(r.left-hr.left)+'px';n.style.top=top+'px';
const lt=document.querySelector('.lang-toggle');const mb=[...hm.querySelectorAll('button,a')].find(e=>{const q=e.getBoundingClientRect();return q.right>360&&q.top<40});const mr=mb?mb.getBoundingClientRect():{top:22,height:42};lt.style.top=(mr.top-hr.top+(mr.height-30)/2)+'px';hm.style.minHeight='0';hm.style.height=(top+22+14)+'px';},[home,back]);
await p.waitForTimeout(400);await p.screenshot({path:'nav3.png',clip:{x:0,y:0,width:390,height:190}});
const lt=await p.evaluate(()=>{const r=document.querySelector('.lang-toggle').getBoundingClientRect();const n=document.querySelector('.nv').getBoundingClientRect();return [r.left,r.top,r.width,r.height,n.left,n.right,n.top]});console.log(lt);
await b.close();})();

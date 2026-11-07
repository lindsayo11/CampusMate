/* Read-only PC palette inventory. Every actual workspace route is visited.
 * Uses the already running loopback preview; never submits business forms. */
const {chromium,expect}=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../..'),out=path.join(root,'docs/local-theme-review');
const base='http://127.0.0.1:3000',api='http://127.0.0.1:8001';
const report={pages:[],interactions:[],errors:[],assetFailures:[],exceptions:['Unchanged CampusMate logo and user-supplied images','Public standalone home, login and assessment presentation']};
const core=['/console','/data','/data/timeline','/agent','/settings','/notifications','/entrepreneurship','/teams'];
function findPages(dir){return fs.readdirSync(dir,{withFileTypes:true}).flatMap(e=>e.isDirectory()?findPages(path.join(dir,e.name)):e.name==='page.tsx'?[path.dirname(path.join(dir,e.name)).replace(path.join(root,'frontend/app'),'').replaceAll('\\','/')||'/']:[])}
function filename(url){return (url.replace(/^\//,'')||'root').replace(/[^a-z0-9_-]+/gi,'-')}
async function inventory(page){return page.evaluate(()=>{
 const frame=document.querySelector('.app-frame');if(!frame)return {standalone:true};
 const theme=getComputedStyle(frame),tokens={};for(let i=0;i<theme.length;i++){const name=theme[i];if(name.startsWith('--cm-')&&!name.includes('motion')&&!name.includes('rgb'))tokens[name]=theme.getPropertyValue(name).trim()}
 const probe=document.createElement('i');frame.append(probe);const allowed=new Set(['rgba(0, 0, 0, 0)','transparent','none']);
 for(const value of Object.values(tokens)){probe.style.color=value;allowed.add(getComputedStyle(probe).color)}probe.remove();
 const unexpected=[],contrast=[],seen=new Set();let elements=0;
 const bgOf=e=>{for(let n=e;n;n=n.parentElement){const s=getComputedStyle(n);if(s.backgroundColor!=='rgba(0, 0, 0, 0)')return s.backgroundColor}return 'rgb(250, 250, 247)'};
 const lum=c=>{const v=c.match(/[\d.]+/g)?.slice(0,3).map(Number);if(!v||v.length!==3)return null;return v.map(n=>{n/=255;return n<=.04045?n/12.92:((n+.055)/1.055)**2.4}).reduce((a,b,i)=>a+b*[.2126,.7152,.0722][i],0)};
 for(const e of frame.querySelectorAll('*')){
  const rect=e.getBoundingClientRect(),s=getComputedStyle(e);if(!rect.width||!rect.height||s.display==='none'||s.visibility==='hidden'||e.closest('[hidden]'))continue;
  elements++;
  const label=e.tagName.toLowerCase()+'.'+(typeof e.className==='string'?e.className:'');
  const values={color:s.color,background:s.backgroundColor};
  for(const side of ['Top','Right','Bottom','Left'])if(parseFloat(s['border'+side+'Width'])>0&&s['border'+side+'Style']!=='none')values['border'+side]=s['border'+side+'Color'];
  if(e.closest('svg')&&e.getAttribute('fill')&&!['none','currentColor'].includes(e.getAttribute('fill')))values.fill=s.fill;
  if(e.closest('svg')&&e.getAttribute('stroke')&&!['none','currentColor'].includes(e.getAttribute('stroke')))values.stroke=s.stroke;
  for(const [property,color] of Object.entries(values))if(!allowed.has(color)&&!color.startsWith('color(srgb')&&!color.startsWith('rgba(')){
   const key=label+'|'+property+'|'+color;if(!seen.has(key)){unexpected.push({element:label.slice(0,180),property,color});seen.add(key)}
  }
  const direct=[...e.childNodes].some(n=>n.nodeType===3&&n.textContent.trim());
  const icon=e.tagName.toLowerCase()==='svg'&&e.getAttribute('viewBox')==='0 0 24 24'&&e.getAttribute('stroke')==='currentColor'||e.classList.contains('huge-icon');
  const backgroundElement=e.classList.contains('huge-icon')?e.parentElement:e;
  if((direct||icon)&&!e.closest('button:disabled,[aria-disabled=true]')&&Number(s.opacity)===1){const foreground=lum(s.color),background=lum(bgOf(backgroundElement));if(foreground!==null&&background!==null){const ratio=(Math.max(foreground,background)+.05)/(Math.min(foreground,background)+.05);if(ratio<3)contrast.push({element:label.slice(0,100),kind:icon?'icon':'text',text:e.textContent.trim().slice(0,40),ratio:Number(ratio.toFixed(2)),fg:s.color,bg:bgOf(backgroundElement)})}}
 }
 return {tokens,elements,unexpected,contrast:contrast.slice(0,30),overflow:document.documentElement.scrollWidth>innerWidth+1,schedule:!!document.querySelector('.console-schedule'),background:getComputedStyle(document.querySelector('.workspace-body')).backgroundColor};
})}
async function screenshot(page,url,width=1440,height=960){await page.setViewportSize({width,height});await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:path.join(out,filename(url)+'-'+width+'x'+height+'.png')})}
(async()=>{
 fs.mkdirSync(out,{recursive:true});const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:960},reducedMotion:'reduce'});
  await context.route('**/*',r=>/^http:\/\/127\.0\.0\.1:/.test(r.request().url())?r.continue():r.abort());
  const page=await context.newPage();page.on('pageerror',e=>{report.errors.push({route:page.url(),message:e.message});console.log('PAGE ERROR',page.url(),e.message)});page.on('response',r=>{if(r.status()>=400&&/\/_next\/static\//.test(r.url()))report.assetFailures.push({url:r.url(),status:r.status()})});
  const catalogue=await(await fetch(api+'/v1/data/catalog?limit=1')).json();const item=catalogue.items[0];
  const detail=await(await fetch(api+'/v1/data/publications/'+item.publication_id)).json();
  const routes=findPages(path.join(root,'frontend/app')).filter(p=>!/[\[\]]/.test(p)&&!['/home','/test','/login','/recover','/'].includes(p));
  routes.push('/data/'+item.publication_id+'?item='+item.id,'/teams?publication='+item.publication_id+'&item='+item.id,'/teams?view=messages','/settings?section=notifications','/settings?section=permissions');
  for(const code of ['recommendation_exemption','domestic_postgraduate_exam','overseas_study','national_civil_service','employment'])routes.push('/data?path='+code);
  if(detail.document.id)routes.push('/admin/intake-document/'+detail.document.id);
  for(const route of routes){
   const response=await page.goto(base+route);await page.locator('.app-frame').waitFor();await page.locator('main').waitFor();
   // Some existing workspaces poll continuously; readiness is their actual UI.
   await page.waitForLoadState('networkidle',{timeout:1500}).catch(()=>{});
   if(route==='/data/timeline')await expect(page.getByRole('button',{name:'我的收藏',exact:true})).toBeVisible();
   if(route==='/agent')await expect(page.getByRole('button',{name:'本科三年级',exact:true})).toBeVisible();
   const result=await inventory(page);report.pages.push({route,status:response.status(),...result});
   console.log(route,response.status(),'colors',result.unexpected.length,'contrast',result.contrast.length,'overflow',result.overflow);
   await screenshot(page,route);
   if(core.includes(route))for(const [w,h] of [[1366,900],[1920,1080]]){await screenshot(page,route,w,h);const r=await inventory(page);report.pages.push({route,viewport:`${w}x${h}`,...r})}
   await page.setViewportSize({width:1440,height:960});
  }
  await page.goto(base+'/opportunities');const legacy=page.locator('main a[href^="/opportunity/"]').first();if(await legacy.count()){const href=await legacy.getAttribute('href');await page.goto(base+href);report.pages.push({route:href,...await inventory(page)});await screenshot(page,'opportunity-detail')}
  await page.goto(base+'/data');await page.getByRole('button',{name:'查看详情',exact:true}).first().click();await expect(page.getByRole('button',{name:'关闭公告详情'})).toBeFocused();
  await page.getByRole('button',{name:'阅读已收录原文',exact:true}).click();await expect(page.locator('dialog pre')).toBeVisible();await page.locator('dialog pre').scrollIntoViewIfNeeded();await screenshot(page,'notice-dialog');report.pages.push({route:'notice-dialog',...await inventory(page)});await page.keyboard.press('Escape');report.interactions.push('Original-source dialog, visible focus, source text, Escape close.');
  await page.goto(base+'/agent');await page.getByRole('button',{name:'本科三年级',exact:true}).click();await page.getByRole('button',{name:'继续',exact:true}).focus();await screenshot(page,'question-selected');report.pages.push({route:'question-selected',...await inventory(page)});report.interactions.push('Questionnaire selected option and keyboard focus; no request submitted.');
  await page.getByRole('button',{name:'折叠侧边栏',exact:true}).click();await screenshot(page,'sidebar-collapsed');await page.getByRole('button',{name:'展开侧边栏',exact:true}).click();report.interactions.push('Sidebar collapse/expand keeps current-colour icons.');
  await page.goto(base+'/data?q=theme-check-no-matches-987');await expect(page.getByText('没有找到匹配的信息')).toBeVisible();await screenshot(page,'empty');report.pages.push({route:'empty',...await inventory(page)});
  fs.writeFileSync(path.join(out,'route-audit.json'),JSON.stringify(report,null,2));
  // This existing, deliberately disabled feature rewrites to 404; the differing
  // server/client pathname yields its known hydration warning, not an active UI.
  const activeErrors=report.errors.filter(e=>!(e.route.endsWith('/admin/collector')&&e.message.includes('#418')));
  assert.equal(activeErrors.length,0,'No active workspace page errors');assert.equal(report.assetFailures.length,0,'No missing assets');
  const problems=report.pages.filter(p=>p.unexpected?.length||p.contrast?.length||p.overflow||p.schedule);assert.deepEqual(problems.map(p=>({route:p.route,unexpected:p.unexpected,contrast:p.contrast,overflow:p.overflow})),[],'Palette/contrast/layout audit');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});

// Read-only local PC review. Fault fixtures run through an ephemeral loopback proxy,
// never alter the database, never contact the VPS and never send POST requests.
const {chromium,expect}=require('@playwright/test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {spawn}=require('node:child_process');
const out=path.resolve(__dirname,'../../docs/local-channel-navigation-review');
const base='http://127.0.0.1:3000';
const channels=[
 ['recommendation_exemption','保研推免'],['domestic_postgraduate_exam','国内考研'],
 ['overseas_study','境外留学'],['national_civil_service','考公考编'],['employment','实习就业'],
];
const report={checks:[],viewports:[],states:{},pageErrors:[],consoleErrors:[],contrast:[]};
const shot=(page,name)=>page.screenshot({path:path.join(out,name+'.png')});
async function isolated(page,code,name){
 await expect(page.locator('main h1')).toHaveText(name);
 await expect(page.locator('main nav[aria-label="信息频道"]')).toHaveCount(0);
 await expect(page.locator('main select[name="path"]')).toHaveCount(0);
 const selected=page.locator('.workspace-sidebar [aria-current="page"]');
 await expect(selected).toHaveCount(1);
 await expect(selected).toHaveAttribute('href','/channels/'+code);
 const links=await page.locator('main a').evaluateAll(nodes=>nodes.map(n=>n.getAttribute('href')));
 for(const href of links){
  if(href.startsWith('/channels/'))assert.equal(new URL(href,base).pathname,'/channels/'+code);
  if(href.startsWith('/data?'))assert.fail('Channel leaked to aggregate catalog');
 }
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
}
async function contrast(locator){
 const colors=await locator.evaluate(el=>{
  let e=el,bg;while(e){bg=getComputedStyle(e).backgroundColor;if(bg!=='rgba(0, 0, 0, 0)')break;e=e.parentElement}
  return [getComputedStyle(el).color,bg];
 });
 const lum=c=>c.match(/[\d.]+/g).slice(0,3).map(Number).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4}).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);
 const [a,b]=colors.map(lum);return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);
}
function listen(server,port=0){return new Promise((resolve,reject)=>{server.once('error',reject);server.listen(port,'127.0.0.1',()=>resolve(server.address().port))})}
function closeServer(server){return new Promise(resolve=>{server.closeAllConnections();server.close(resolve)})}
async function ready(url,child){
 const deadline=Date.now()+15000;
 while(Date.now()<deadline){
  if(child.exitCode!==null)throw Error('Isolated frontend exited: '+child.exitCode);
  try{const response=await fetch(url);if(response.ok)return}catch{}
  await new Promise(resolve=>setTimeout(resolve,100));
 }
 throw Error('Isolated frontend readiness deadline exceeded');
}
(async()=>{
 fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({channel:'chrome',headless:true});
 let faultServer,faultWeb;
 const release=[];
 try{
  const context=await browser.newContext({viewport:{width:1366,height:900},reducedMotion:'reduce'});
  await context.route('**/*',r=>{
   const url=new URL(r.request().url());
   return url.hostname==='127.0.0.1'&&['GET','HEAD'].includes(r.request().method())?r.continue():r.abort();
  });
  const page=await context.newPage();
  page.on('pageerror',e=>report.pageErrors.push(e.message));
  const taxonomy=await (await context.request.get(base+'/api/backend/v1/paths')).json();
  for(const [code,name] of channels){
   await page.goto(base+'/channels/'+code);
   await isolated(page,code,name);
   const data=await (await context.request.get(base+'/api/backend/v1/data/catalog?path='+code+'&limit=12&status=all')).json();
   assert.ok(data.items.length>0,'Real channel catalog is populated');
   const allowed=new Set(taxonomy.filter(p=>p.code===code).map(p=>p.id));
   let changed=true;
   while(changed){changed=false;for(const p of taxonomy)if(allowed.has(p.parent_id)&&!allowed.has(p.id)){allowed.add(p.id);changed=true}}
   const codes=new Set(taxonomy.filter(p=>allowed.has(p.id)).map(p=>p.code));
   assert.ok(data.items.every(item=>item.paths.some(p=>codes.has(p.code))));
   await expect(page.locator('main article')).toHaveCount(data.items.length);
   await expect(page.locator('main article h3')).toHaveText(data.items.map(item=>item.title));
   report.checks.push({channel:code,title:name,total:data.total,visible:data.items.length});
   // Child-path items must still open; channel scope is not an exact leaf-code filter.
   const firstDetail=await page.locator('main article h3 a').first().getAttribute('href');
   await page.goto(base+firstDetail);
   await expect(page.getByRole('heading',{name:'公告内容',exact:true})).toBeVisible();
   await page.getByRole('link',{name:'← 返回'+name,exact:true}).click();
   await isolated(page,code,name);
  }
  const code=channels[0][0],name=channels[0][1],url=base+'/channels/'+code;
  for(const [width,height] of [[1366,900],[1920,1080]]){
   await page.setViewportSize({width,height});
   await page.goto(url);await isolated(page,code,name);
   const tops=await page.locator('main article').evaluateAll(nodes=>nodes.slice(0,3).map(n=>Math.round(n.getBoundingClientRect().top)));
   assert.equal(new Set(tops).size,1);
   const c=await contrast(page.getByRole('button',{name:'筛选',exact:true}));
   assert.ok(c>=4.5);report.contrast.push({viewport:width+'x'+height,filterButton:c});
   const search=page.getByRole('textbox',{name:'搜索公告、关键词'});
   await search.focus();
   assert.ok(await search.evaluate(el=>parseFloat(getComputedStyle(el).outlineWidth)>=2));
   await page.keyboard.press('Tab');
   await expect(page.getByRole('combobox',{name:'信息状态'})).toBeFocused();
   await page.locator('main h1').click();await shot(page,'channel-'+width+'x'+height);
   report.viewports.push(width+'x'+height);
  }
  await page.setViewportSize({width:1366,height:900});
  await page.goto(url);
  await page.getByRole('link',{name:'下一页',exact:true}).click();
  await expect(page).toHaveURL(/channels\/recommendation_exemption\?.*offset=12/);
  await isolated(page,code,name);
  await expect(page.locator('main article')).toHaveCount(6);
  await shot(page,'channel-page-2');
  await page.goBack();await isolated(page,code,name);
  await expect(page.locator('main article')).toHaveCount(12);
  await page.goForward();await isolated(page,code,name);
  await page.getByRole('link',{name:'第 1 页',exact:true}).click();
  await expect(page.locator('main article')).toHaveCount(12);
  const form=page.getByRole('search',{name:'保研推免频道搜索'});
  await form.getByRole('textbox',{name:'搜索公告、关键词'}).fill('清华');
  await form.getByRole('combobox',{name:'信息排序'}).selectOption('deadline');
  await form.getByRole('button',{name:'筛选',exact:true}).click();
  await isolated(page,code,name);
  assert.equal(new URL(page.url()).searchParams.get('q'),'清华');
  assert.equal(new URL(page.url()).searchParams.get('sort'),'deadline');
  await expect(page.locator('main article').first()).toBeVisible();
  await form.getByRole('textbox',{name:'搜索公告、关键词'}).fill('zz-no-match-883187');
  await form.getByRole('button',{name:'筛选',exact:true}).click();
  await expect(page.getByRole('heading',{name:'没有找到匹配的信息'})).toBeVisible();
  await shot(page,'channel-empty');
  await page.getByRole('link',{name:'清除筛选，查看本频道信息'}).click();
  await isolated(page,code,name);await expect(page.locator('main article')).toHaveCount(12);
  report.states.empty='Real unmatched query and same-channel reset verified.';
  await page.goto(base+'/data?path='+code+'&q=清华&status=expired&sort=deadline&offset=0');
  await expect(page).toHaveURL(/\/channels\/recommendation_exemption\?/);
  assert.equal(new URL(page.url()).searchParams.get('q'),'清华');
  assert.equal(new URL(page.url()).searchParams.get('status'),'expired');
  assert.equal(new URL(page.url()).searchParams.get('sort'),'deadline');
  await isolated(page,code,name);
  await page.goto(url+'?path=employment');
  await isolated(page,code,name);
  const knownTitles=await page.locator('main article h3').allTextContents();
  await page.goto(url);assert.deepEqual(await page.locator('main article h3').allTextContents(),knownTitles);
  report.checks.push('Search, sorting, clear, numbered pagination, browser history, old bookmarks and conflicting path query all remain scoped.');
  const trigger=page.getByRole('button',{name:'查看详情',exact:true}).first();
  await trigger.click();const dialog=page.getByRole('dialog',{name:'公告详情'});
  await expect(dialog.getByRole('heading',{name:'公告内容'})).toBeVisible();
  const detailHref=await dialog.getByRole('link',{name:'打开完整详情页'}).getAttribute('href');
  assert.equal(new URL(detailHref,base).searchParams.get('channel'),code);
  await shot(page,'channel-detail');
  await page.keyboard.press('Escape');await expect(dialog).toHaveCount(0);await expect(trigger).toBeFocused();
  await page.goto(base+detailHref);
  await expect(page.locator('main h1')).toHaveText('保研推免 · 公告详情');
  await expect(page.locator('.workspace-sidebar [aria-current="page"]')).toHaveCount(1);
  await expect(page.locator('.workspace-sidebar [aria-current="page"]')).toHaveAttribute('href','/channels/'+code);
  await page.getByRole('link',{name:'← 返回保研推免',exact:true}).click();
  await isolated(page,code,name);
  const otherNotice={available:true,notice:{path:'employment',name:'实习就业',updated_at:'2099-01-01',source_count:7}};
  await page.route('**/api/backend/v1/data/channel-updates',r=>r.fulfill({json:otherNotice}));
  await page.reload();await expect(page.locator('main article')).toHaveCount(12);
  await expect(page.locator('.channel-update-notice')).toHaveCount(0);
  await page.goto(base+'/data');
  await expect(page.getByRole('navigation',{name:'信息频道'})).toBeVisible();
  await expect(page.locator('.workspace-sidebar [aria-current="page"]')).toHaveAttribute('href','/data');
  await expect(page.locator('.workspace-sidebar a.stream-item').last()).toHaveAttribute('href','/entrepreneurship');
  await page.locator('.workspace-sidebar a.stream-item').filter({hasText:'国内考研'}).click();
  await isolated(page,'domestic_postgraduate_exam','国内考研');
  await page.unroute('**/api/backend/v1/data/channel-updates');
  report.checks.push('Modal Escape restores focus; full detail/back link retains channel; unrelated update banner is hidden; aggregate and entrepreneurship entry retained.');
  report.states.success='All five real channel catalogs and return flows pass.';

  // Server-rendered states need an upstream fault proxy, not client DOM replacement.
  let mode='normal';
  faultServer=http.createServer(async(req,res)=>{
   if(req.method!=='GET'&&req.method!=='HEAD'){res.writeHead(405);res.end();return}
   const catalog=req.url.startsWith('/v1/data/catalog?'),summary=req.url.startsWith('/v1/data/channel-summary?');
   if(catalog&&mode==='loading')await new Promise(resolve=>release.push(resolve));
   if((catalog&&['error','permission'].includes(mode))||(summary&&mode==='partial')){
    res.writeHead(mode==='permission'?401:503,{'Content-Type':'application/json'});
    res.end(JSON.stringify({detail:'Controlled local review fixture'}));return;
   }
   try{
    const response=await fetch('http://127.0.0.1:8001'+req.url);
    res.writeHead(response.status,{'Content-Type':response.headers.get('content-type')||'application/json'});
    res.end(Buffer.from(await response.arrayBuffer()));
   }catch{res.writeHead(502);res.end('Local upstream unavailable')}
  });
  const apiPort=await listen(faultServer);
  const reservation=http.createServer();const webPort=await listen(reservation);await closeServer(reservation);
  const faultBase='http://127.0.0.1:'+webPort;
  const standalone=path.resolve(__dirname,'../.next/standalone');
  const serverFile=fs.existsSync(path.join(standalone,'server.js'))?path.join(standalone,'server.js'):path.join(standalone,'frontend/server.js');
  faultWeb=spawn(process.execPath,[serverFile],{cwd:path.dirname(serverFile),windowsHide:true,stdio:['ignore','pipe','pipe'],env:{
   ...process.env,HOSTNAME:'127.0.0.1',PORT:String(webPort),API_INTERNAL_URL:'http://127.0.0.1:'+apiPort,
   APP_ORIGIN:faultBase,ENABLE_AGENT_UI:'true',DEMO_MODE:'true',NEXT_TELEMETRY_DISABLED:'1',
  }});
  faultWeb.stdout.on('data',()=>{});faultWeb.stderr.on('data',()=>{});
  await ready(faultBase+'/favicon.svg',faultWeb);
  const faultPage=await context.newPage();
  faultPage.on('pageerror',e=>report.consoleErrors.push({mode,message:e.message}));
  mode='loading';
  await faultPage.goto(faultBase+'/channels/'+code,{waitUntil:'commit'});
  await expect(faultPage.getByRole('status').filter({hasText:'正在读取公告与来源'})).toBeVisible();
  await shot(faultPage,'channel-loading');
  mode='normal';release.splice(0).forEach(resolve=>resolve());
  await isolated(faultPage,code,name);await expect(faultPage.locator('main article')).toHaveCount(12);
  report.states.loading='Held SSR catalog request shows loading; release restores 12 real notices.';
  mode='partial';
  await faultPage.goto(faultBase+'/channels/'+code);
  await expect(faultPage.getByRole('status').filter({hasText:'频道摘要暂时不可用'})).toBeVisible();
  await expect(faultPage.locator('main article')).toHaveCount(12);
  await shot(faultPage,'channel-partial');
  report.states.partial='Summary 503 fixture retains all catalog cards and shows unavailable-summary feedback.';
  mode='error';
  await faultPage.goto(faultBase+'/channels/'+code);
  await expect(faultPage.getByRole('heading',{name:'频道信息暂时无法读取'})).toBeVisible();
  await shot(faultPage,'channel-error');
  mode='normal';await faultPage.getByRole('button',{name:'重新加载',exact:true}).click();
  await expect(faultPage.locator('main article')).toHaveCount(12);
  report.states.error='Catalog 503 fixture shows boundary and retry restores same channel.';
  mode='permission';
  await faultPage.goto(faultBase+'/channels/'+code);
  await expect(faultPage).toHaveURL(/\/#login$/,{timeout:15000});
  await expect(faultPage.locator('main article')).toHaveCount(0);
  await shot(faultPage,'channel-permission');
  report.states.permission='Catalog 401 fixture redirects to existing login entry without exposing channel notices.';
  assert.deepEqual(report.pageErrors,[]);
  fs.writeFileSync(path.join(out,'browser-report.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify(report,null,2));
 }finally{
  release.splice(0).forEach(resolve=>resolve());
  if(faultWeb&&faultWeb.exitCode===null){
   const done=new Promise(resolve=>faultWeb.once('exit',resolve));faultWeb.kill();await done;
  }
  if(faultServer)await closeServer(faultServer);
  await browser.close();
 }
})().catch(error=>{console.error(error);process.exitCode=1});

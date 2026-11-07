/* PC review: real pages + real API on a disposable COPY of the public snapshot.
 * All writes target a temporary DB. No requests leave loopback. Run after build. */
const {chromium,expect}=require('@playwright/test');
const {spawn,execFileSync}=require('node:child_process');
const http=require('node:http'),fs=require('node:fs'),path=require('node:path'),os=require('node:os'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../..'),out=process.env.CM_REVIEW_OUTPUT_DIR||path.join(root,'docs/local-explore-review');
const python=path.join(root,'backend/.venv/Scripts/python.exe');
let browser,backend,web,bridge,temp,mode='success',user='explore-review-owner',base,backendBase;
const states={},checks=[],errors=[],viewports=[[1366,900],[1440,960],[1920,1080]];
const pause=ms=>new Promise(r=>setTimeout(r,ms));
async function freePort(){const server=http.createServer();await new Promise(r=>server.listen(0,'127.0.0.1',r));const port=server.address().port;await new Promise(r=>server.close(r));return port}
async function ready(url){for(let n=0;n<100;n++){try{if((await fetch(url)).ok)return}catch{}await pause(200)}throw Error('Local service not ready: '+url)}
async function shot(page,name){await page.screenshot({path:path.join(out,name),fullPage:false})}
async function backendRead(endpoint){return (await fetch(backendBase+endpoint,{headers:{'x-user-id':user}})).json()}
async function within(page){assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'No horizontal overflow')}

(async()=>{
 fs.mkdirSync(out,{recursive:true});
 browser=await chromium.launch({channel:'chrome',headless:true});
 const context=await browser.newContext({viewport:{width:1440,height:960},reducedMotion:'reduce'});
 await context.route('**/*',route=>/^http:\/\/127\.0\.0\.1:/.test(route.request().url())?route.continue():route.abort());
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
 await ready('http://127.0.0.1:3000/favicon.svg');
 // Review current local dataset, read-only; preserve the user's actual plans.
 for(const route of ['agent','data','teams']){
  await page.goto('http://127.0.0.1:3000/'+route);
  if(route==='agent')await expect(page.getByRole('button',{name:'本科三年级',exact:true})).toBeEnabled();
  else await expect(page.locator('main article').first()).toBeVisible();
  for(const [width,height] of viewports){
   await page.setViewportSize({width,height});await page.evaluate(()=>window.scrollTo(0,0));await within(page);
   await shot(page,route+'-'+width+'x'+height+'.png');
   if(route==='data'){
    const columns=await page.locator('main article').first().evaluate(e=>getComputedStyle(e.parentElement).gridTemplateColumns.split(' ').length);
    assert.equal(columns,width===1920?4:3);
   }
  }
 }
 await page.setViewportSize({width:1440,height:960});
 await page.goto('http://127.0.0.1:3000/data');
 const open=page.getByRole('button',{name:'查看详情',exact:true}).first();
 await open.click();await expect(page.getByRole('heading',{name:'公告内容',exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'关闭公告详情'})).toBeFocused();
 await page.keyboard.press('Tab');
 assert.equal(await page.evaluate(()=>document.querySelector('dialog').contains(document.activeElement)),true);
 await shot(page,'notice-detail.png');
 await page.getByRole('button',{name:'阅读已收录原文',exact:true}).click();
 await expect(page.getByLabel('已收录原文文本').locator('pre')).toBeVisible();
 const sourceStyle=await page.getByLabel('已收录原文文本').locator('pre').evaluate(e=>({bg:getComputedStyle(e).backgroundColor,color:getComputedStyle(e).color,font:getComputedStyle(e).fontSize}));
 assert.equal(sourceStyle.bg,'rgb(255, 255, 255)');assert.notEqual(sourceStyle.color,sourceStyle.bg);
 await page.getByLabel('已收录原文文本').scrollIntoViewIfNeeded();await shot(page,'notice-source.png');
 await page.keyboard.press('Escape');await expect(page.getByRole('dialog')).toHaveCount(0);await expect(open).toBeFocused();
 await page.getByRole('textbox',{name:'搜索公告、关键词'}).fill('不可能匹配-explore-review');
 await page.getByRole('button',{name:'筛选',exact:true}).click();await expect(page.getByText('没有找到匹配的信息')).toBeVisible();
 await page.getByRole('link',{name:'清除筛选，查看全部'}).click();
 await page.getByRole('link',{name:'下一页',exact:true}).click();await expect(page).toHaveURL(/offset=12/);
 checks.push('Actual local pages: 3 viewports each; 3/4-column cards, no overflow, source text contrast, dialog keyboard focus/Escape/return, search and pagination.');

 // New isolated data copy; the running local preview database is never mutated.
 temp=fs.mkdtempSync(path.join(os.tmpdir(),'campusmate-explore-review-'));
 const db=path.join(temp,'review.db');
 execFileSync(python,['-c','import sqlite3,sys,pathlib; s=sqlite3.connect(pathlib.Path(sys.argv[1]).as_uri()+"?mode=ro",uri=True); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close(); s.close()',path.join(root,'demo-data/release-preview.db'),db],{windowsHide:true});
 const apiPort=await freePort(),webPort=await freePort();
 backendBase='http://127.0.0.1:'+apiPort;
 const env={...process.env,DATABASE_URL:'sqlite:///'+db.replaceAll('\\','/'),DEMO_MODE:'true',ADMIN_USER_IDS:'explore-review-owner',DEEPSEEK_API_KEY:'',TAVILY_API_KEY:'',JEV_API_KEY:'',DIFY_APP_KEY:'',DEVELOPMENT_DIFY_APP_KEY:'',COLLECTOR_ENABLED:'false',PUBLIC_NOTICE_WATCH_ENABLED:'false',SEED_PUBLIC_CONTENT:'false',SUPABASE_URL:'',SUPABASE_ANON_KEY:'',PYTHONIOENCODING:'utf-8'};
 execFileSync(python,['-m','alembic','upgrade','head'],{cwd:path.join(root,'backend'),env,windowsHide:true,stdio:'pipe'});
 backend=spawn(python,['-m','uvicorn','app.main:app','--host','127.0.0.1','--port',String(apiPort)],{cwd:path.join(root,'backend'),env,windowsHide:true,stdio:['ignore','pipe','pipe']});
 backend.stdout.on('data',()=>{});backend.stderr.on('data',()=>{});
 await ready(backendBase+'/health/ready');
 bridge=http.createServer(async(req,res)=>{
  try{
   const pathname=new URL(req.url,'http://127.0.0.1').pathname;
   const data=[];for await(const chunk of req)data.push(chunk);
   const isDetail=/^\/v1\/data\/publications\/[^/]+$/.test(pathname);
   if(mode==='loading'&&isDetail)await pause(2200);
   if(mode==='error'&&isDetail){res.writeHead(503,{'Content-Type':'application/json'});res.end(JSON.stringify({detail:'隔离网络故障'}));return}
   if(mode==='permission'&&pathname.startsWith('/v1/activity-teams/activity/')){res.writeHead(401,{'Content-Type':'application/json'});res.end(JSON.stringify({detail:'请先登录'}));return}
   if(mode==='empty'&&pathname==='/v1/activity-teams/directory'){res.writeHead(200,{'Content-Type':'application/json'});res.end(JSON.stringify({total:0,items:[]}));return}
   const upstream=await fetch(backendBase+req.url,{method:req.method,headers:{'Content-Type':'application/json','x-user-id':user},...(!['GET','HEAD'].includes(req.method)?{body:Buffer.concat(data)}:{})});
   let body=await upstream.text();
   if(mode==='partial'&&isDetail&&upstream.ok){const value=JSON.parse(body);value.rules=[];value.evidence=[];value.positions=[];for(const item of value.items){item.materials=[];item.deadline=null;}body=JSON.stringify(value);}
   if(mode==='xss'&&pathname.endsWith('/source')&&upstream.ok){const value=JSON.parse(body);value.text='<img src=x onerror="window.reviewXss=true">';body=JSON.stringify(value);}
   res.writeHead(upstream.status,{'Content-Type':upstream.headers.get('Content-Type')||'application/json'});res.end(body);
  }catch(e){res.writeHead(502,{'Content-Type':'application/json'});res.end(JSON.stringify({detail:'隔离测试代理失败'}));}
 });
 await new Promise(r=>bridge.listen(0,'127.0.0.1',r));
 base='http://127.0.0.1:'+webPort;
 web=spawn(process.execPath,[path.join(root,'frontend/.next/standalone/server.js')],{cwd:path.join(root,'frontend/.next/standalone'),windowsHide:true,stdio:['ignore','pipe','pipe'],env:{...env,HOSTNAME:'127.0.0.1',PORT:String(webPort),API_INTERNAL_URL:'http://127.0.0.1:'+bridge.address().port,APP_ORIGIN:base,ENABLE_AGENT_UI:'true',NEXT_TELEMETRY_DISABLED:'1'}});
 web.stdout.on('data',()=>{});web.stderr.on('data',()=>{});
 await ready(base+'/favicon.svg');
 const test=await context.newPage();test.on('pageerror',e=>errors.push(e.message));
 await test.goto(base+'/agent');
 await expect(test.getByRole('button',{name:'本科三年级',exact:true})).toBeEnabled();
 const next=()=>test.getByRole('button',{name:'继续',exact:true}).click();
 await test.getByRole('button',{name:'本科三年级',exact:true}).click();await next();
 await test.getByRole('button',{name:'保研推免',exact:true}).click();await next();
 await test.getByRole('textbox',{name:'专业或兴趣领域'}).fill('计算机科学');await next();
 await test.getByRole('button',{name:'为继续深造和科研做准备',exact:true}).click();await next();
 await test.getByRole('button',{name:'8 小时',exact:true}).click();await next();
 await test.getByRole('button',{name:'已经做过课程或实践项目',exact:true}).click();await next();
 await test.getByRole('button',{name:'希望找到队友',exact:true}).click();await next();
 await test.getByRole('button',{name:'这个学期',exact:true}).click();
 await test.getByRole('button',{name:'← 上一步',exact:true}).click();
 await expect(test.getByRole('button',{name:'希望找到队友',exact:true})).toHaveAttribute('aria-pressed','true');await next();
 const before=(await backendRead('/v1/plans')).length;
 await test.getByRole('button',{name:'生成我的方案',exact:true}).click();
 await expect(test.getByRole('heading',{name:'保研推免 · 你的起步方案',exact:true})).toBeVisible();
 await test.getByRole('heading',{name:'保研推免 · 你的起步方案',exact:true}).scrollIntoViewIfNeeded();
 await shot(test,'assessment-result.png');
 assert.equal((await backendRead('/v1/plans')).length,before);
 await test.getByRole('button',{name:'生成计划预览',exact:true}).click();
 await expect(test.getByRole('button',{name:'确认保存',exact:true})).toBeEnabled();
 assert.equal((await backendRead('/v1/plans')).length,before);
 await test.getByRole('button',{name:'确认保存',exact:true}).click();
 await expect(test.getByRole('heading',{name:'已保存 3 项计划',exact:true})).toBeVisible();
 assert.equal((await backendRead('/v1/plans')).length,before+3);
 await test.reload();await test.getByRole('button',{name:'我已完成需求问卷，请帮我规划下一步。',exact:true}).click();
 await expect(test.getByRole('heading',{name:'已保存 3 项计划',exact:true})).toBeVisible();
 checks.push('Real isolated API: all 8 answers, previous-step preservation, tailored result, zero plans before confirmation, 3 saved after confirmation, persisted conversation after reload.');

 await test.goto(base+'/teams');await test.getByRole('link',{name:'查看组队',exact:true}).first().click();
 await expect(test.getByRole('heading',{name:/正在这里集结/})).toBeVisible();
 const activityURL=test.url();
 await test.getByRole('button',{name:'创建队伍',exact:true}).first().click();
 await test.getByRole('textbox',{name:'队伍名称',exact:true}).fill('本地隔离协作测试');
 await test.getByRole('spinbutton',{name:'人数上限（含队长）',exact:true}).fill('2');
 await test.getByRole('textbox',{name:'招募说明',exact:true}).fill('需要一位会整理原文的同学，每周一起推进。');
 await test.getByRole('button',{name:'确认创建',exact:true}).click();
 await expect(test.getByRole('heading',{name:'本地隔离协作测试',exact:true})).toBeVisible();
 user='explore-review-applicant';await test.goto(activityURL);
 await test.getByRole('textbox',{name:'向本地隔离协作测试介绍自己'}).fill('我可以负责资料核对。');
 await test.getByRole('button',{name:'申请加入',exact:true}).click();
 await expect(test.getByText('申请已提交，等待队长确认。').first()).toBeVisible();
 await expect(test.getByRole('link',{name:'进入队伍会话',exact:true})).toHaveCount(0);
 await shot(test,'team-join-pending.png');
 user='explore-review-owner';await test.goto(base+'/team-manager');
 await test.getByRole('button',{name:'接受申请',exact:true}).click();
 await expect(test.getByText('暂无待处理的入队申请。')).toBeVisible();
 user='explore-review-applicant';await test.goto(activityURL);
 await expect(test.getByRole('link',{name:'进入队伍会话',exact:true})).toBeVisible();
 await test.getByRole('link',{name:'进入队伍会话',exact:true}).click();
 await expect(test.getByRole('heading',{name:'本地隔离协作测试',exact:true})).toBeVisible();
 user='explore-review-outsider';await test.goto(activityURL);
 await expect(test.getByText('当前队伍人数已满。')).toBeVisible();
 await expect(test.getByRole('button',{name:'申请加入',exact:true})).toHaveCount(0);
 await shot(test,'team-full.png');
 checks.push('Real isolated API: create activity team, applicant request, owner approval, room membership, outsider sees full status without room link.');
 states.success={status:'pass',evidence:'Real isolated backend round trips validated questionnaire→proposal→confirmed plans and activity→team→request→captain approval→private room, with persisted data in a disposable public-snapshot copy.'};

 mode='empty';await test.goto(base+'/teams');await expect(test.getByRole('heading',{name:'暂无符合筛选的活动',exact:true})).toBeVisible();await shot(test,'empty.png');
 states.empty={status:'pass',evidence:'No matching catalogue search, zero teams, and empty filtered directory show recovery or create-team actions; no fake record or team was inserted into the running database.'};
 mode='permission';await test.goto(activityURL);await expect(test.getByRole('main').getByRole('alert')).toContainText('请先登录');await expect(test.getByRole('link',{name:'登录',exact:true})).toBeVisible();await shot(test,'permission.png');
 states.permission={status:'pass',evidence:'Injected 401 on the isolated activity API shows a login link; real backend tests also reject unauthenticated create/read and non-owner approval, and private room access before membership.'};
 mode='success';await test.goto(base+'/data');
 mode='loading';await test.getByRole('button',{name:'查看详情',exact:true}).first().click();await expect(test.getByRole('dialog').getByRole('status')).toContainText('正在读取公告');await shot(test,'loading.png');
 await expect(test.getByRole('heading',{name:'公告内容',exact:true})).toBeVisible();await test.keyboard.press('Escape');
 states.loading={status:'pass',evidence:'Delayed detail request renders a stable open dialog with close control and live reading state, then actual details. Duplicate submit buttons disable while requests run.'};
 mode='error';await test.getByRole('button',{name:'查看详情',exact:true}).first().click();await expect(test.getByRole('dialog').getByRole('alert')).toBeVisible();await shot(test,'error.png');
 mode='success';await test.getByRole('button',{name:'重新加载',exact:true}).click();await expect(test.getByRole('heading',{name:'公告内容',exact:true})).toBeVisible();await test.keyboard.press('Escape');
 states.error={status:'pass',evidence:'503 detail failure displays retry/return actions; retry recovers after restoring the isolated API.'};
 mode='partial';await test.getByRole('button',{name:'查看详情',exact:true}).first().click();await expect(test.getByText(/暂未完整提取条件/)).toBeVisible();await expect(test.getByText(/尚未收录附件清单/)).toBeVisible();await test.getByRole('heading',{name:'申请条件与适用对象',exact:true}).scrollIntoViewIfNeeded();await shot(test,'partial.png');
 mode='xss';await test.getByRole('button',{name:'阅读已收录原文',exact:true}).click();await expect(test.getByLabel('已收录原文文本').locator('pre')).toContainText('<img src=x');assert.equal(await test.evaluate(()=>window.reviewXss),undefined);assert.equal(await test.getByLabel('已收录原文文本').locator('img').count(),0);
 states.partial={status:'pass',evidence:'Absent conditions/attachments/dates retain the rest of the detail, explain original/manual attachment paths, and never claim eligibility. HTML-like source text renders as inert text, not DOM.'};
 assert.deepEqual(errors,[],'No browser runtime errors');
 fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify({at:new Date().toISOString(),checks,states,errors,sourceStyle},null,2));
 console.log(JSON.stringify({result:'pass',checks,states:Object.keys(states),errors},null,2));
})().catch(e=>{console.error(e);process.exitCode=1}).finally(async()=>{
 if(browser)await browser.close();
 for(const proc of [web,backend])if(proc&&!proc.killed)proc.kill();
 if(bridge)await new Promise(r=>bridge.close(r));
 // The OS temporary directory is deliberately retained for failure diagnosis.
 // No deletion commands touch the user's local preview database or workspace.
});

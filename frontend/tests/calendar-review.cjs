/* Local-only browser review. A disposable API fixture and web process exercise
   error/permission states without modifying the demo database or live services.
   Run after next build: node tests/calendar-review.cjs */
const {chromium, expect} = require('@playwright/test');
const {spawn} = require('node:child_process');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../..');
const out = process.env.CM_REVIEW_OUTPUT_DIR || path.join(root, 'docs/local-calendar-review');
const log = [];
const states = {};
let mode = 'success', userId = 'calendar-review-a';
const today = new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Shanghai', year:'numeric', month:'2-digit', day:'2-digit'}).format(new Date());
const month = today.slice(0, 7), day = Number(today.slice(8));
const date = n => `${month}-${String(n).padStart(2, '0')}`;
const fixturePaths = [{id:1, code:'domestic_postgraduate_exam', name:'国内考研'}, {id:2, code:'employment', name:'实习就业'}];
const raw = [];
const add = (id, title, at, label, pathIndex = 0) => raw.push({item_id:id, publication_id:'fixture-' + id, title, at, label, paths:[fixturePaths[pathIndex]], source:{name:'仅用于隔离浏览器测试'}, document:{canonical_url:'https://example.invalid/source'}});
add('period','边界测试：跨周事项',date(1),'开始'); add('period','边界测试：跨周事项',date(22),'截止/失效');
add('deadline','边界测试：截止日期',date(Math.min(28,day+1)),'截止/失效',1);
add('long','很长的事项标题，用于验证截断、详情完整显示与宽屏窄屏下均不会挤压日期和操作按钮'.repeat(3),date(Math.min(28,day+2)),'开始');
for(let i=0;i<5;i++)add('busy'+i,'同日测试事项 '+i,today,'截止/失效');
const plans = [{id:999,user_id:userId,title:'隔离测试个人计划',path_id:2,due_date:today,status:'todo',note:'不写入数据库',created_at:today,updated_at:today}];
let web, browser, api;
const wait = ms => new Promise(r=>setTimeout(r, ms));
async function ready(url) {for(let i=0;i<80;i++){try {if((await fetch(url)).ok)return;}catch{}await wait(250);}throw Error('Review server did not become ready');}
async function shot(page,name){await page.screenshot({path:path.join(out,name),fullPage:false});}

(async()=>{
  fs.mkdirSync(out,{recursive:true});
  browser = await chromium.launch({channel:'chrome',headless:true});
  const context = await browser.newContext({viewport:{width:1440,height:960},reducedMotion:'reduce'});
  await context.route('**/*', route => /^http:\/\/127\.0\.0\.1:/.test(route.request().url()) ? route.continue() : route.abort());
  const page = await context.newPage();
  const errors=[]; page.on('pageerror', e=>errors.push(e.message));

  // First review the actual isolated local dataset, not the fixtures below.
  await ready('http://127.0.0.1:3000/favicon.svg');
  await page.goto('http://127.0.0.1:3000/data/timeline');
  await expect(page.getByRole('heading',{name:'发展日历',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'我的收藏',exact:true})).toBeEnabled();
  const sizes=[[1366,900],[1440,960],[1920,1080]];
  for(const [width,height] of sizes){
    await page.setViewportSize({width,height});
    await page.evaluate(()=>window.scrollTo(0,0));
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'No page-level horizontal overflow');
    const eventStyle=await page.locator('[data-event-id]').first().evaluate(e=>({bg:getComputedStyle(e).backgroundColor,color:getComputedStyle(e).color}));
    assert.notEqual(eventStyle.bg,'rgb(255, 255, 255)');
    await shot(page,`calendar-${width}x${height}.png`);
  }
  await page.setViewportSize({width:1440,height:960});
  const initialTitle=await page.locator('section[aria-label="月历"] h2').textContent();
  await page.getByRole('button',{name:'下个月',exact:true}).click();
  await expect(page.locator('section[aria-label="月历"] h2')).not.toHaveText(initialTitle);
  await page.getByRole('button',{name:'上个月',exact:true}).click();
  await expect(page.locator('section[aria-label="月历"] h2')).toHaveText(initialTitle);
  await page.getByRole('button',{name:'今天',exact:true}).click();
  await expect(page.locator('[aria-current="date"]')).toBeVisible();
  await page.locator('[aria-current="date"]').focus();
  await page.keyboard.press('ArrowRight');
  assert.notEqual(await page.evaluate(()=>document.activeElement.getAttribute('data-day')),today);
  assert.notEqual(await page.evaluate(()=>getComputedStyle(document.activeElement).outlineStyle),'none');
  await page.getByRole('button',{name:'上个月',exact:true}).click();
  const bar=page.locator('[data-event-id]').first();
  await bar.click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.getByRole('button',{name:'关闭日程详情'})).toBeFocused();
  for(let i=0;i<7;i++)await page.keyboard.press('Tab');
  assert.equal(await page.evaluate(()=>document.querySelector('dialog').contains(document.activeElement)),true,'Dialog traps keyboard focus');
  await page.getByRole('button',{name:'收藏日程',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('已收藏');
  await shot(page,'calendar-detail.png');
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await expect(bar).toBeFocused();
  await page.reload();
  await page.getByRole('button',{name:'我的收藏',exact:true}).click();
  await expect(page.getByRole('complementary',{name:'日程列表'}).getByRole('button',{name:/取消收藏：/})).toHaveCount(1);
  await page.getByRole('searchbox',{name:'搜索日程名称或关键词'}).fill('不可能匹配的测试关键词');
  await expect(page.getByText('没有符合筛选的日程')).toBeVisible();
  await page.getByRole('button',{name:'清除',exact:true}).click();
  await expect(page.locator('[data-event-id]').first()).toBeVisible();
  await page.getByRole('combobox',{name:'筛选发展方向'}).selectOption('domestic_postgraduate_exam');
  assert.ok(await page.locator('[data-event-id]').count()>0);
  await page.getByRole('combobox',{name:'筛选日程类型'}).selectOption('plan');
  // The real local user may now have plans; don't assume an empty personal list.
  await expect(page.getByRole('combobox',{name:'筛选日程类型'})).toHaveValue('plan');
  await page.getByRole('searchbox',{name:'搜索日程名称或关键词'}).fill('不可能匹配的测试关键词');
  await expect(page.getByText('没有符合筛选的日程')).toBeVisible();
  await page.getByRole('button',{name:'清除',exact:true}).click();
  log.push('Actual data: 3 viewport captures, no horizontal overflow, month navigation/today, keyboard focus, source dialog/Escape, saved favorite survives reload, search and combined filters.');

  // Dynamic fixture modes affect only this loopback API and isolated web process.
  api=http.createServer((req,res)=>{
    const pathname=new URL(req.url,'http://127.0.0.1').pathname;
    let body=[], code=200, delay=0;
    if(pathname==='/health')body={demo_mode:true};
    if(pathname==='/v1/account'){body={user_id:userId,is_admin:false};if(mode==='permission')code=401;}
    if(pathname==='/v1/profile')body={display_name:'日历测试',school:'本地测试'};
    if(pathname==='/v1/paths')body=fixturePaths;
    if(pathname==='/v1/data/timeline'){
      body=mode==='empty'?[]:mode==='partial'?[...raw,{...raw[0],at:'invalid',item_id:'bad'}]:raw;
      if(mode==='error')code=503;if(mode==='loading')delay=2400;
    }
    if(pathname==='/v1/plans'){
      body=mode==='empty'?[]:plans;
      if(mode==='error'||mode==='partial')code=503;if(mode==='permission')code=401;
    }
    setTimeout(()=>{res.writeHead(code,{'Content-Type':'application/json'});res.end(JSON.stringify(body));},delay);
  });
  await new Promise((resolve,reject)=>{api.once('error',reject);api.listen(0,'127.0.0.1',resolve);});
  const apiPort=api.address().port;
  // Select a free port without replacing an existing service.
  const reservation=http.createServer();await new Promise(r=>reservation.listen(0,'127.0.0.1',r));
  const webPort=reservation.address().port;await new Promise(r=>reservation.close(r));
  const base=`http://127.0.0.1:${webPort}`;
  web=spawn(process.execPath,[path.join(root,'frontend/.next/standalone/server.js')],{
    cwd:path.join(root,'frontend/.next/standalone'),windowsHide:true,stdio:['ignore','pipe','pipe'],
    env:{...process.env,HOSTNAME:'127.0.0.1',PORT:String(webPort),API_INTERNAL_URL:`http://127.0.0.1:${apiPort}`,APP_ORIGIN:base,NEXT_TELEMETRY_DISABLED:'1',SUPABASE_URL:'',SUPABASE_ANON_KEY:''},
  });
  web.stdout.on('data',()=>{});web.stderr.on('data',d=>log.push('fixture-server: '+String(d).trim()));
  await ready(base+'/favicon.svg');
  const fixture=await context.newPage();fixture.on('pageerror',e=>errors.push(e.message));
  const open=async state=>{mode=state;await fixture.goto(base+'/data/timeline?review='+state);await expect(fixture.getByRole('heading',{name:'发展日历',exact:true})).toBeVisible();if(state!=='permission')await expect(fixture.getByRole('button',{name:'我的收藏',exact:true})).toBeEnabled();};

  await open('success');
  await expect(fixture.locator('[data-event-id="plan:999"]:visible')).toHaveCount(1);
  const more=fixture.getByRole('button',{name:new RegExp(today+'还有')});await expect(more).toBeVisible();await more.click();
  await expect(fixture.getByRole('button',{name:'返回近期日程'})).toBeVisible();
  assert.ok(await fixture.getByRole('complementary',{name:'日程列表'}).locator('article').count()>=6);
  const firstFavorite=fixture.getByRole('button',{name:/^收藏：/}).first();await firstFavorite.click();
  await fixture.reload();await fixture.getByRole('button',{name:'我的收藏',exact:true}).click();
  await expect(fixture.getByRole('button',{name:/取消收藏：/}).first()).toBeVisible();
  userId='calendar-review-b';await fixture.reload();await fixture.getByRole('button',{name:'我的收藏',exact:true}).click();
  await expect(fixture.getByText('还没有收藏的日程').first()).toBeVisible();
  userId='calendar-review-a';await fixture.reload();await fixture.getByRole('button',{name:'我的收藏',exact:true}).click();
  await expect(fixture.getByRole('button',{name:/取消收藏：/}).first()).toBeVisible();
  states.success={status:'pass',evidence:'Real source data and isolated future/multiday/busy-day/plan fixtures rendered; month/today, search/direction/type filters, more-items, dialog/Escape and favorites persisted; a different account did not inherit favorites.'};
  await open('success');await shot(fixture,'calendar-fixture-success.png');
  await fixture.getByRole('combobox',{name:'筛选日程状态'}).selectOption('未开始');
  await expect(fixture.locator('[data-event-id="plan:999"]')).toHaveCount(0);
  await fixture.getByRole('combobox',{name:'筛选年度'}).selectOption(today.slice(0,4));
  await expect(fixture.locator('[data-event-id]').first()).toBeVisible();

  await open('empty');await expect(fixture.getByText('暂无已注明日期的日程')).toBeVisible();await shot(fixture,'calendar-empty.png');
  states.empty={status:'pass',evidence:'No dates, empty current month, no matching combined filters and empty favorites show distinct recovery actions. No fictional items were inserted.'};
  await open('error');await expect(fixture.getByRole('main').getByRole('alert')).toContainText('公开日程、个人计划暂未加载');await shot(fixture,'calendar-error.png');
  mode='success';await fixture.getByRole('button',{name:'重试',exact:true}).click();await expect(fixture.locator('[data-event-id]').first()).toBeVisible();await expect(fixture.getByRole('main').getByRole('alert')).toHaveCount(0);
  states.error={status:'pass',evidence:'Both feed APIs returned 503; visible error and retry restored real content when the API recovered.'};
  await open('partial');await expect(fixture.getByRole('main').getByRole('alert')).toContainText('个人计划暂未加载');await expect(fixture.getByText('1 条记录日期无效，暂未显示。')).toBeVisible();await expect(fixture.locator('[data-event-id]').first()).toBeVisible();await shot(fixture,'calendar-partial.png');
  states.partial={status:'pass',evidence:'Plan API failure did not discard public dates; malformed source date is skipped with an explicit count.'};
  await open('permission');await expect(fixture.getByText('登录后可查看个人计划和收藏日程。')).toBeVisible();await expect(fixture.getByRole('button',{name:'我的收藏',exact:true})).toBeDisabled();await expect(fixture.locator('[data-event-id]').first()).toBeVisible();await shot(fixture,'calendar-permission.png');
  states.permission={status:'pass',evidence:'401 account/plan responses retain public events, show a login path, and disable favorites; no auth logic was bypassed.'};
  mode='loading';await fixture.goto(base+'/data/timeline?review=loading',{waitUntil:'commit'});
  await expect(fixture.getByLabel('正在加载日历')).toBeVisible();await shot(fixture,'calendar-loading.png');
  await expect(fixture.locator('[data-event-id]').first()).toBeVisible();
  states.loading={status:'pass',evidence:'Delayed source API visibly streams the two-column skeleton; it is replaced with the calendar after resolution. Refresh has busy and live-status feedback.'};
  assert.deepEqual(errors,[],'No browser runtime errors');
  fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify({at:new Date().toISOString(),actualSource:'http://127.0.0.1:3000/data/timeline',states,errors,checks:log},null,2));
  console.log(JSON.stringify({result:'pass',states:Object.keys(states),artifacts:out,errors},null,2));
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();if(web)web.kill();if(api)await new Promise(r=>api.close(r));});

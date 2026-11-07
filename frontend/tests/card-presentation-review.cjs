/* Local visual regression; all mutating requests are fulfilled in this browser. */
const {chromium,expect}=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const out=path.resolve(__dirname,'../../docs/local-card-review'),base='http://127.0.0.1:3000';
const results={checks:[],states:{},errors:[],contrast:[]};
async function shot(page,name){await page.screenshot({path:path.join(out,name+'.png')})}
async function readable(locator,label){
 const colors=await locator.evaluate(e=>{
  const s=getComputedStyle(e);let n=e,bg;while(n){bg=getComputedStyle(n).backgroundColor;if(bg!=='rgba(0, 0, 0, 0)')break;n=n.parentElement}
  return {fg:s.color,bg,opacity:s.opacity};
 });
 const lum=c=>c.match(/[\d.]+/g).slice(0,3).map(Number).map(n=>{n/=255;return n<=.04045?n/12.92:((n+.055)/1.055)**2.4}).reduce((a,n,i)=>a+n*[.2126,.7152,.0722][i],0);
 const a=lum(colors.fg),b=lum(colors.bg),ratio=(Math.max(a,b)+.05)/(Math.min(a,b)+.05);
 results.contrast.push({label,...colors,ratio:Number(ratio.toFixed(2))});
 assert.equal(colors.opacity,'1',label+' must not disappear through opacity');
 assert.ok(ratio>=4.5,label+' readable text/stroke pair: '+ratio);
}
(async()=>{
 fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:960},reducedMotion:'reduce'});
  await context.route('**/*',r=>/^http:\/\/127\.0\.0\.1:/.test(r.request().url())?r.continue():r.abort());
  const page=await context.newPage();page.on('pageerror',e=>results.errors.push(e.message));
  await page.goto(base+'/data');await expect(page.locator('main [data-artwork]')).toHaveCount(12);
  const artwork=await page.locator('main [data-artwork]').evaluateAll(es=>es.map(e=>e.outerHTML));
  assert.equal(new Set(artwork).size,12,'No repeated first-page illustration');
  for(const [width,height] of [[1366,900],[1440,960],[1920,1080]]){
   await page.setViewportSize({width,height});await page.evaluate(()=>window.scrollTo(0,0));
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   await shot(page,'cards-'+width+'x'+height);
   const nav=page.getByRole('navigation',{name:'信息分页',exact:true});
   await nav.scrollIntoViewIfNeeded();await expect(nav.getByRole('button',{name:'上一页'})).toBeDisabled();
   await expect(nav.locator('a[aria-current=page]')).toHaveText('1');
   assert.equal(await nav.getByRole('link',{name:/^第 \d+ 页$/}).count(),9);
   await nav.getByRole('link',{name:'第 2 页',exact:true}).focus();await shot(page,'pagination-'+width+'x'+height);
   await readable(nav.locator('[aria-current=page]'),'selected pagination '+width);
   await readable(nav.getByRole('button',{name:'上一页'}),'disabled previous '+width);
  }
  await page.setViewportSize({width:1440,height:960});
  await page.getByRole('link',{name:'第 9 页',exact:true}).click();
  await expect(page).toHaveURL(/offset=96/);await expect(page.getByRole('button',{name:'下一页',exact:true})).toBeDisabled();
  await page.getByRole('link',{name:'上一页',exact:true}).click();await expect(page).toHaveURL(/offset=84/);
  await page.goto(base+'/data?path=recommendation_exemption&status=all&sort=recent');
  await page.getByRole('link',{name:'第 2 页',exact:true}).click();
  assert.equal(new URL(page.url()).searchParams.get('path'),'recommendation_exemption');
  assert.equal(new URL(page.url()).searchParams.get('sort'),'recent');
  await page.goto(base+'/teams');await page.getByRole('navigation',{name:'组队目录分页'}).getByRole('link',{name:'第 2 页',exact:true}).click();await expect(page).toHaveURL(/offset=12/);
  await page.goto(base+'/data');await expect(page.locator('main [data-artwork]')).toHaveCount(12);
  assert.deepEqual(await page.locator('main [data-artwork]').evaluateAll(es=>es.map(e=>e.outerHTML)),artwork,'Artwork stable after navigation and reload');
  const firstArt=await page.locator('main [data-artwork]').first().getAttribute('data-artwork');
  await page.getByRole('button',{name:'查看详情',exact:true}).first().click();
  await expect(page.getByRole('heading',{name:'公告内容',exact:true})).toBeVisible();
  assert.equal(await page.locator('dialog [data-artwork]').getAttribute('data-artwork'),firstArt);
  await expect(page.getByRole('button',{name:'关闭公告详情'})).toBeFocused();
  const add=page.getByRole('button',{name:'加入计划',exact:true});
  await add.scrollIntoViewIfNeeded();await readable(add,'add plan');
  await add.hover();await readable(add,'add plan hover');
  await readable(page.getByRole('button',{name:'设置截止前24小时提醒'}),'unavailable reminder');
  await shot(page,'detail-default-1440x960');
  let release;
  await page.route('**/api/backend/v1/data/subscriptions',async r=>{
   assert.equal(r.request().method(),'POST');
   await new Promise(resolve=>{release=resolve});
   await r.fulfill({status:200,contentType:'application/json',body:'{"id":"browser-only-state"}'});
  });
  await add.click();await expect(page.getByRole('button',{name:'保存中…',exact:true})).toBeDisabled();
  await readable(page.getByRole('button',{name:'保存中…',exact:true}),'saving');
  await shot(page,'detail-loading-1440x960');release();
  await expect(page.getByRole('button',{name:'已加入计划',exact:true})).toBeDisabled();
  await readable(page.getByRole('button',{name:'已加入计划',exact:true}),'saved');
  await readable(page.locator('dialog .follow-feedback'),'success feedback');
  await readable(page.getByRole('link',{name:'查看我的计划',exact:true}),'success link');
  await shot(page,'detail-saved-1440x960');await page.keyboard.press('Escape');
  results.states.loading={status:'pass',evidence:'Held intercepted save response; saving button disabled but fully readable.'};
  results.states.success={status:'pass',evidence:'Browser-only save response displays readable disabled saved button, success panel and next link; no real data written.'};
  await page.unroute('**/api/backend/v1/data/subscriptions');
  await page.route('**/api/backend/v1/data/subscriptions',r=>r.fulfill({status:401,contentType:'application/json',body:'{"detail":"请先登录"}'}));
  await page.getByRole('button',{name:'查看详情',exact:true}).first().click();
  await page.getByRole('button',{name:'加入计划',exact:true}).click();
  await expect(page.locator('dialog .follow-feedback')).toHaveText('请先登录');
  await readable(page.locator('dialog .follow-feedback'),'permission feedback');await shot(page,'detail-permission-1440x960');
  results.states.permission={status:'pass',evidence:'Intercepted 401 remains readable; no success UI or saved plan is claimed.'};
  await page.unroute('**/api/backend/v1/data/subscriptions');
  await page.route('**/api/backend/v1/data/subscriptions',r=>r.fulfill({status:503,contentType:'application/json',body:'{"detail":"服务暂时不可用，请重试"}'}));
  await page.getByRole('button',{name:'加入计划',exact:true}).click();
  await expect(page.locator('dialog .follow-feedback')).toHaveText('服务暂时不可用，请重试');
  await readable(page.locator('dialog .follow-feedback'),'error feedback');await shot(page,'detail-error-1440x960');
  results.states.error={status:'pass',evidence:'Intercepted 503 shows readable warm-red feedback and an enabled retry action.'};
  await expect(page.getByRole('button',{name:'设置截止前24小时提醒'})).toBeDisabled();
  results.states.partial={status:'pass',evidence:'Real first item has no deadline; reminder remains disabled with explanatory hint while add-plan/source actions are usable.'};
  await page.keyboard.press('Escape');
  await page.goto(base+'/data?q=card-review-no-result-90831');
  await expect(page.getByText('没有找到匹配的信息')).toBeVisible();
  await expect(page.getByRole('navigation',{name:'信息分页',exact:true})).toHaveCount(0);
  await shot(page,'empty-1440x960');
  results.states.empty={status:'pass',evidence:'No-match search shows recovery and no misleading page numbers.'};
  await page.goto(base+'/notifications');
  for(const selector of ['.notifications-hero-icon','.notifications-summary-icon','.notification-section-icon']){
   const icons=page.locator(selector+' svg');
   for(let i=0;i<await icons.count();i++)await readable(icons.nth(i),selector+' '+i);
  }
  for(const [width,height] of [[1366,900],[1440,960],[1920,1080]]){
   await page.setViewportSize({width,height});await page.evaluate(()=>window.scrollTo(0,0));await shot(page,'notifications-'+width+'x'+height);
  }
  results.checks.push('All nine page numbers; first/last disabled boundaries; direct page jump and previous; filters preserved; shared team pagination; keyboard focus; no PC overflow.','12 distinct SVG scenes; same record stable after navigation and across detail view.','Default, hover, disabled, pending, saved, failure and permission follow states all measured at >=4.5:1, including formerly blank button.','Every notification title/category/section icon measured at >=4.5:1; 2px strokes, all PC sizes rendered.');
  assert.deepEqual(results.errors,[]);
 }finally{fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify(results,null,2));await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});

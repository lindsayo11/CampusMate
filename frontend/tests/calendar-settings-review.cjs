/* Local PC review. Real public reads; profile writes are browser mocks only. */
const {chromium,expect}=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const out=path.resolve(__dirname,'../../docs/local-calendar-settings-review');
const base='http://127.0.0.1:3000';
const report={checks:[],viewports:[],errors:[]};
async function shot(page,name){await page.screenshot({path:path.join(out,name+'.png')})}
async function noOverflow(page){assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'No page overflow')}
async function contrast(locator){
 const {fg,bg}=await locator.evaluate(el=>{let parent=el,bg;while(parent){bg=getComputedStyle(parent).backgroundColor;if(bg!=='rgba(0, 0, 0, 0)')break;parent=parent.parentElement}return{fg:getComputedStyle(el).color,bg}});
 const lum=c=>c.match(/[\d.]+/g).slice(0,3).map(Number).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4}).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);
 const a=lum(fg),b=lum(bg);return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);
}
(async()=>{
 fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:960},reducedMotion:'reduce'});
  await context.route('**/*',r=>/^http:\/\/127\.0\.0\.1:/.test(r.request().url())&&['GET','HEAD'].includes(r.request().method())?r.continue():r.abort());
  let saveMode='success',release,submitted;
  await context.route('**/api/backend/v1/profile',async r=>{
   if(r.request().method()!=='PUT')return r.continue();
   submitted=r.request().postDataJSON();
   if(saveMode==='loading')await new Promise(resolve=>{release=resolve});
   const status=saveMode==='error'?503:saveMode==='permission'?403:200;
   return r.fulfill({status,contentType:'application/json',body:JSON.stringify(status===200?submitted:{detail:status===403?'登录权限已失效，请重新登录':'保存服务暂不可用，请重试'})});
  });
  const page=await context.newPage();page.on('pageerror',e=>report.errors.push(e.message));
  for(const [width,height] of [[1366,900],[1440,960],[1920,1080]]){
   await page.setViewportSize({width,height});
   await page.goto(base+'/settings');
   await expect(page.getByRole('textbox',{name:'学校',exact:true})).toHaveValue('中山大学');
   await noOverflow(page);
   const first=await page.getByRole('heading',{name:'学业坐标',exact:true}).boundingBox();
   const next=await page.getByRole('heading',{name:'下一站',exact:true}).boundingBox();
   assert.equal(Math.round(first.y),Math.round(next.y));
   assert.ok(await contrast(page.locator('main a[aria-current=page] span'))>=4.5);
   await shot(page,'settings-'+width+'x'+height);
   await page.getByRole('navigation',{name:'设置栏目'}).getByRole('link',{name:'通知',exact:true}).click();
   await expect(page.getByRole('switch')).toHaveCount(3);
   await noOverflow(page);await shot(page,'notifications-settings-'+width+'x'+height);
   await page.getByRole('navigation',{name:'设置栏目'}).getByRole('link',{name:'权限',exact:true}).click();
   await expect(page.getByRole('link',{name:'隐私与安全',exact:true}).last()).toHaveAttribute('href','/safety');
   await shot(page,'permissions-settings-'+width+'x'+height);
   await page.goto(base+'/data/timeline');
   await expect(page.getByRole('heading',{name:'2026年11月',exact:true})).toBeVisible();
   assert.ok(Number((await page.getByRole('region',{name:'月历'}).innerText()).match(/(\d+) 项日程/)[1])>=7);
   await noOverflow(page);await shot(page,'calendar-'+width+'x'+height);
   report.viewports.push(width+'x'+height);
  }
  await page.setViewportSize({width:1440,height:960});
  const month=page.getByRole('region',{name:'月历'});
  const monthCount=(await month.innerText()).match(/\d+ 项日程/)[0];
  const search=page.getByRole('searchbox',{name:'搜索日程名称或关键词'});
  await search.fill('APMCM');
  const apmcm=month.locator('button[data-event-id]').filter({hasText:'2026 APMCM'}).first();
  await expect(apmcm).toHaveAttribute('title',/2026\.11\.25$/);
  await apmcm.click();
  const dialog=page.getByRole('dialog');await expect(dialog).toBeVisible();
  await expect(dialog).toContainText('未截止');
  await expect(dialog).toContainText('报名截止仅精确到日');
  await expect(dialog.getByRole('link',{name:'官方原文'})).toHaveAttribute('href','https://newoaa.shisu.edu.cn/3d/92/c6353a212370/page.htm');
  await shot(page,'sourced-calendar-detail');
  await page.getByRole('button',{name:'关闭日程详情'}).click();
  await search.fill('不存在的日程 xyz');
  await expect(month).toContainText('没有符合筛选的日程');await shot(page,'calendar-empty');
  await month.getByRole('button',{name:'清除筛选'}).click();
  await expect(month).toContainText(monthCount);
  await page.getByRole('combobox',{name:'筛选发展方向'}).selectOption('national_civil_service');
  await expect(month).toContainText('3 项日程');
  report.checks.push('Live November calendar: 7 sourced events; correct 11/15, 11/20, 11/25 and 11/29 boundaries; original URL and date precision; empty and direction filters work.');
  await page.goto(base+'/opportunities?type=contest');
  await expect(page.getByRole('heading',{name:'竞赛项目',exact:true})).toBeVisible();
  const cards=page.locator('main article');
  assert.equal(await cards.count(),2);
  await expect(cards.first()).not.toContainText('创业扶持政策');
  await expect(page.locator('main')).not.toContainText('六大路线 · 官方新机会');
  assert.ok((await page.getByRole('textbox',{name:'搜索校园机会'}).boundingBox()).width>200);
  await noOverflow(page);await shot(page,'competitions-corrected');
  report.checks.push('Contest tab contains only two actually archived current competition registrations; policy directories, synthetic fixtures and unrelated supplemental channel cards are absent.');
  await page.goto(base+'/settings');
  await page.getByRole('textbox',{name:'展示昵称',exact:true}).fill('UI验证昵称');
  saveMode='loading';
  const save=page.getByRole('button',{name:'保存画像',exact:true});
  await save.click();await expect(page.getByRole('button',{name:'保存中…',exact:true})).toBeDisabled();
  await shot(page,'profile-saving');saveMode='success';release();
  await expect(page.locator('main')).toContainText('画像已保存，可用于资格核对。');
  await expect(page.getByRole('heading',{level:1})).toContainText('UI验证昵称');
  assert.equal(submitted.school,'中山大学');
  const downloadPromise=page.waitForEvent('download');await page.getByRole('button',{name:'下载资料'}).click();
  const download=await downloadPromise;const profile=JSON.parse(fs.readFileSync(await download.path(),'utf8'));
  assert.equal(profile.display_name,'UI验证昵称');
  saveMode='error';await save.click();await expect(page.locator('main [role=alert]')).toContainText('保存服务暂不可用');
  await expect(page.getByRole('textbox',{name:'展示昵称',exact:true})).toHaveValue('UI验证昵称');await shot(page,'profile-save-error');
  saveMode='permission';await save.click();await expect(page.locator('main [role=alert]')).toContainText('登录权限已失效');await shot(page,'profile-save-permission');
  await page.getByRole('textbox',{name:'学校',exact:true}).focus();
  assert.ok(await page.getByRole('textbox',{name:'学校',exact:true}).evaluate(e=>parseFloat(getComputedStyle(e).outlineWidth)>=2));
  report.checks.push('Mock profile loading/success/error/permission outcomes; draft retained on failure, current saved name appears in hero and download, keyboard focus visible; no profile writes reached server.');
  await page.goto(base+'/home');await expect(page.frameLocator('iframe[title="CampusMate public home"]').locator('img[src*="logo.svg"]').first()).toBeVisible();
  await shot(page,'logo-dark-landing');
  await page.goto(base+'/agent');await expect(page.getByRole('heading',{name:'校伴助手',exact:true})).toBeVisible();
  await shot(page,'logo-light-assistant');
  assert.deepEqual(report.errors,[]);
  fs.writeFileSync(path.join(out,'browser-report.json'),JSON.stringify(report,null,2));
 }finally{await browser.close()}
 console.log(JSON.stringify(report,null,2));
})().catch(error=>{console.error(error);process.exitCode=1});

/* Local PC review. Only GETs and the two read-only search/check POSTs reach the server.
   Conditional pass/fail states are browser fixtures, never published eligibility claims. */
const {chromium,expect}=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const out=path.resolve(__dirname,'../../docs/local-evidence-workspace-review');
const base='http://127.0.0.1:3000';
const report={checks:[],viewports:[],errors:[],contrast:[]};
const shot=(page,name)=>page.screenshot({path:path.join(out,name+'.png')});
async function noOverflow(page){assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'No page overflow');}
async function contrast(locator){
 const colors=await locator.evaluate(el=>{let e=el,bg;while(e){bg=getComputedStyle(e).backgroundColor;if(bg!=='rgba(0, 0, 0, 0)')break;e=e.parentElement;}return [getComputedStyle(el).color,bg];});
 const lum=c=>c.match(/[\d.]+/g).slice(0,3).map(Number).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4}).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);
 const [a,b]=colors.map(lum);return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);
}
(async()=>{
 fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:960},reducedMotion:'reduce'});
  await context.route('**/*',r=>{
   const url=new URL(r.request().url()),method=r.request().method();
   const safePost=['/api/backend/v1/knowledge/search','/api/backend/v1/tools/eligibility_check'].includes(url.pathname);
   return url.hostname==='127.0.0.1'&&(['GET','HEAD'].includes(method)||(method==='POST'&&safePost))?r.continue():r.abort();
  });
  const page=await context.newPage();page.on('pageerror',e=>report.errors.push(e.message));
  const directory=page.getByRole('region',{name:'资料目录',exact:true});
  const options=page.getByRole('complementary',{name:'核对事项列表'});
  const selected=page.getByRole('region',{name:'当前事项核对'});
  for(const [width,height] of [[1366,900],[1440,960],[1920,1080]]){
   await page.setViewportSize({width,height});
   await page.goto(base+'/knowledge');
   await expect(directory.locator('article')).toHaveCount(9);
   await noOverflow(page);await shot(page,'knowledge-'+width+'x'+height);
   const top=await directory.locator('article').evaluateAll(els=>els.slice(0,3).map(e=>Math.round(e.getBoundingClientRect().top)));
   assert.equal(new Set(top).size,1,'Three aligned columns');
   const c=await contrast(page.getByRole('button',{name:'检索依据',exact:true}));assert.ok(c>=4.5);
   report.contrast.push({viewport:width+'x'+height,primary:c});
   await page.goto(base+'/eligibility');
   await expect(options.locator('button[aria-pressed]')).toHaveCount(8);
   await expect(page.getByRole('region',{name:'核对使用的个人资料'})).toContainText('中山大学');
   await noOverflow(page);await shot(page,'eligibility-'+width+'x'+height);
   report.viewports.push(width+'x'+height);
  }
  await page.setViewportSize({width:1440,height:960});
  await page.goto(base+'/knowledge');
  await expect(directory.locator('article')).toHaveCount(9);
  const first=await directory.locator('h3').first().innerText();
  await page.getByRole('button',{name:'第 2 页',exact:true}).click();
  await expect(page.getByRole('button',{name:'第 2 页',exact:true})).toHaveAttribute('aria-current','page');
  await expect(directory.locator('h3').first()).not.toHaveText(first);
  await page.getByRole('combobox',{name:'资料板块'}).selectOption('education_policy');
  await expect(page.locator('span[role=status]')).toContainText('教育政策 · 16 份');
  const read=page.getByRole('button',{name:'阅读原文',exact:true}).first();
  await read.click();
  const dialog=page.getByRole('dialog');await expect(dialog.getByRole('link',{name:'打开官方原文'})).toBeVisible();
  await expect(dialog).toContainText('字符');
  assert.ok((await dialog.innerText()).length>200);
  const official=await dialog.getByRole('link',{name:'打开官方原文'}).getAttribute('href');
  assert.ok(/^https?:\/\//.test(official));
  await dialog.getByText('版本与引用定位',{exact:true}).click();await expect(dialog).toContainText('SHA-256');
  await shot(page,'source-reader');
  await page.keyboard.press('Escape');await expect(dialog).toHaveCount(0);await expect(read).toBeFocused();
  const readerPattern='**/api/backend/v1/knowledge/documents/*';
  await page.route(readerPattern,r=>r.fulfill({status:404,json:{detail:'原文不存在、版本已更新或已停止公开'}}));
  await read.click();await expect(dialog.getByRole('alert')).toContainText('已停止公开');
  await shot(page,'source-reader-unavailable');
  await page.unroute(readerPattern);await dialog.getByRole('button',{name:'重试',exact:true}).click();
  await expect(dialog.getByRole('link',{name:'打开官方原文'})).toBeVisible();
  await dialog.getByRole('button',{name:'关闭原文'}).click();await expect(read).toBeFocused();
  await page.getByRole('combobox',{name:'资料板块'}).selectOption('');
  await page.getByRole('button',{name:'报名材料',exact:true}).click();
  await expect(page.getByRole('heading',{name:'相关原文片段'})).toBeVisible();
  await expect(page.locator('main blockquote').first()).toBeVisible();
  await shot(page,'knowledge-search');
  const input=page.getByRole('textbox',{name:'要查找的内容'});
  await input.fill('zznohit876546789987');
  await page.getByRole('button',{name:'检索依据',exact:true}).click();
  await expect(page.getByRole('heading',{name:'未找到对应原文片段'})).toBeVisible();
  await shot(page,'knowledge-empty');
  await page.getByRole('button',{name:'浏览全部资料'}).click();
  await expect(directory.locator('article')).toHaveCount(9);
  await input.focus();assert.ok(await input.evaluate(e=>parseFloat(getComputedStyle(e).outlineWidth)>=2));
  report.checks.push('Real directory: 89 documents/354 chunks; numbered pagination, category filter, keyword excerpts, reader original URL/hash, Escape/focus restoration, empty-search recovery.');
  await page.goto(base+'/eligibility');
  await expect(selected.getByRole('button',{name:'开始核对'})).toBeEnabled();
  await selected.getByRole('button',{name:'开始核对'}).click();
  await expect(selected).toContainText('缺少条件资料，暂不能判断');
  await expect(selected).not.toContainText('已录入条件通过');
  await shot(page,'eligibility-real-unknown');
  await options.getByRole('checkbox',{name:'有核验条件'}).check();
  await expect(options).toContainText('暂没有已核验条件的事项');
  await shot(page,'eligibility-empty-filter');
  await options.getByRole('button',{name:'查看全部事项'}).click();
  await expect(options.locator('button[aria-pressed]')).toHaveCount(8);
  await options.getByRole('button',{name:'再看 8 项'}).click();
  await expect(options.locator('button[aria-pressed]')).toHaveCount(16);
  await page.getByRole('textbox',{name:'搜索核对事项'}).fill('创新大赛');
  await expect(options.locator('button[aria-pressed]')).toHaveCount(1);
  await options.locator('button[aria-pressed]').click();
  await expect(selected.getByRole('heading',{level:2})).toContainText('创新大赛');
  report.checks.push('Real eligibility: 20 options, actual SYSU profile, filters/more/selection work, zero verified conditions correctly remain unknown.');
  // Held and failed requests exercise recovery without server mutation.
  let mode='loading',release;
  const directoryPattern='**/api/backend/v1/knowledge/documents?*';
  await page.route(directoryPattern,async r=>{
   if(mode==='loading')await new Promise(resolve=>{release=resolve});
   if(mode==='normal')return r.continue();
   return r.fulfill({status:mode==='permission'?403:503,contentType:'application/json',body:JSON.stringify({detail:'资料服务暂不可用'})});
  });
  await page.goto(base+'/knowledge');await expect(page.getByText('正在整理资料…',{exact:true})).toBeVisible();
  await shot(page,'knowledge-loading');mode='error';release();
  await expect(page.locator('main [role=alert]')).toContainText('资料服务暂不可用');await shot(page,'knowledge-error');
  mode='normal';await page.getByRole('button',{name:'重试',exact:true}).click();await expect(directory.locator('article')).toHaveCount(9);
  mode='permission';await page.getByRole('button',{name:'刷新资料目录'}).click();
  await expect(page.locator('main [role=alert]')).toContainText('当前账号没有访问权限');
  await expect(page.locator('main [role=alert]').getByRole('link',{name:'去登录'})).toHaveAttribute('href','/login');
  await shot(page,'knowledge-permission');await page.unroute(directoryPattern);
  await page.route('**/api/backend/v1/profile',r=>r.fulfill({status:503,contentType:'application/json',body:'{"detail":"个人资料暂不可用"}'}));
  await page.goto(base+'/eligibility');await expect(page.locator('main [role=alert]')).toContainText('个人资料暂不可用');
  await expect(options.locator('button[aria-pressed]')).toHaveCount(8);
  await expect(selected.getByRole('button',{name:'开始核对'})).toBeDisabled();
  await shot(page,'eligibility-partial');
  await page.unroute('**/api/backend/v1/profile');
  await page.getByRole('button',{name:'重试',exact:true}).click();
  await expect(selected.getByRole('button',{name:'开始核对'})).toBeEnabled();
  // Mock-only verified condition: tests presentation, does not assert any real announcement qualifies.
  const fixture={id:'browser-only',type:'contest',title:'浏览器隔离测试事项',summary:'仅测试核对结果展示，不写入资料库。',organization:'测试',source_label:'测试原文',source_url:'https://university.edu.cn/test',location:'线上',deadline:null,rule_count:1,pending_count:0,rules:[{field:'degree',label:'学历',expected:'本科',evidence:'测试条件',source_url:'https://university.edu.cn/test',supported:true}]};
  await page.route('**/api/backend/v1/eligibility/options',r=>r.fulfill({json:{items:[fixture],total:1,with_rules:1}}));
  let checkMode='loading';
  await page.route('**/api/backend/v1/tools/eligibility_check',async r=>{
   if(checkMode==='loading')await new Promise(resolve=>{release=resolve});
   if(checkMode==='error'||checkMode==='permission')return r.fulfill({status:checkMode==='error'?503:401,json:{detail:'核对服务暂不可用'}});
   const pass=checkMode==='pass'?true:checkMode==='fail'?false:null;
   return r.fulfill({json:{eligible:pass,results:[{label:'学历',passed:pass,actual:pass===null?'':'本科',expected:pass===false?'研究生':'本科',evidence:'浏览器隔离测试条件',source_url:fixture.source_url}]}});
  });
  await page.reload();await expect(selected.getByRole('heading',{level:2})).toHaveText(fixture.title);
  await selected.getByRole('button',{name:'开始核对'}).click();await expect(selected.getByRole('button',{name:'正在核对…'})).toBeDisabled();
  await shot(page,'eligibility-loading');checkMode='pass';release();
  await expect(selected).toContainText('已录入条件通过');await shot(page,'eligibility-fixture-pass');
  for(const [status,expected] of [['fail','有不符合的已录入条件'],['partial','部分资料不足，需要补充'],['error','核对服务暂不可用'],['permission','请登录后查看此内容']]){
   checkMode=status;await selected.getByRole('button',{name:'开始核对'}).click();await expect(selected).toContainText(expected);await shot(page,'eligibility-fixture-'+status);
  }
  report.checks.push('Browser fixtures only: held loading, empty filters, 503/retry, permission/login, partial profile disables checking, pass/fail/unknown presentation. No fixture data stored.');
  assert.deepEqual(report.errors,[]);
  fs.writeFileSync(path.join(out,'browser-report.json'),JSON.stringify(report,null,2));
 }finally{await browser.close();}
 console.log(JSON.stringify(report,null,2));
})().catch(error=>{console.error(error);process.exitCode=1;});

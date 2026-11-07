/* Local browser-only fixtures. No AI calls, conversation writes, or VPS access. */
const {chromium,expect}=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const out=path.resolve(__dirname,'../../docs/local-assistant-fold-review');
const base='http://127.0.0.1:3000',endpoint='/api/backend/v1/development-agent/conversations';
const results={checks:[],contentStates:{},geometry:[],errors:[]};
const rows=Array.from({length:30},(_,i)=>({id:'history-'+i,title:i===0?'保研准备与竞赛经历：一起梳理未来一年的学习目标、材料清单和每个阶段需要核验的报名条件':'最近会话 '+(i+1)}));
const reply=[{query:'我想了解保研准备。',reply:{status:'ok',tool:'chat',message:'可以先整理成绩、经历与目标院校的官方要求。'}}];
async function screenshot(page,name){await page.screenshot({path:path.join(out,name+'.png')})}
async function foregroundContrast(locator){
 const values=await locator.evaluate(e=>{let parent=e,bg;while(parent){bg=getComputedStyle(parent).backgroundColor;if(bg!=='rgba(0, 0, 0, 0)')break;parent=parent.parentElement}return {fg:getComputedStyle(e).color,bg}});
 const luminance=c=>c.match(/[\d.]+/g).slice(0,3).map(Number).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4}).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);
 const a=luminance(values.fg),b=luminance(values.bg);return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);
}
(async()=>{
 fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:960},reducedMotion:'reduce'});
  await context.route('**/*',r=>/^http:\/\/127\.0\.0\.1:/.test(r.request().url())&&['GET','HEAD'].includes(r.request().method())?r.continue():r.abort());
  let mode='empty',initialRelease,detailRelease,holdDetail=false,detailFailure=false,moreFailure=false;
  await context.route('**'+endpoint+'**',async r=>{
   const url=new URL(r.request().url());
   const json=(status,body)=>r.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
   if(url.pathname!==endpoint){
    if(holdDetail)await new Promise(resolve=>{detailRelease=resolve});
    return detailFailure?json(503,{detail:'暂时无法读取这段对话，请重试。'}):json(200,reply);
   }
   if(url.searchParams.has('offset'))return moreFailure?json(503,{detail:'后续会话暂时无法读取，请重试。'}):json(200,[{id:'last',title:'补充会话'}]);
   if(mode==='loading')await new Promise(resolve=>{initialRelease=resolve});
   if(mode==='error')return json(503,{detail:'会话暂时无法读取，请重试。'});
   if(mode==='permission')return json(401,{detail:'登录已过期'});
   return json(200,mode==='empty'?[]:rows);
  });
  const page=await context.newPage();page.on('pageerror',e=>results.errors.push(e.message));
  const toggle=page.locator('[aria-controls="assistant-session-history"]');
  const panel=page.locator('#assistant-session-history');
  const chat=page.getByRole('region',{name:'校伴对话',exact:true});
  const newChat=page.getByRole('button',{name:'新会话',exact:true});
  async function reload(){await page.goto(base+'/agent');await expect(toggle).toHaveCount(1);await expect(toggle).toHaveAttribute('aria-expanded','false');await expect(page.getByRole('button',{name:'本科三年级',exact:true})).toBeEnabled()}
  await reload();
  await expect(panel).toBeHidden();await expect(newChat).toBeVisible();
  for(const [width,height] of [[1366,900],[1440,960],[1920,1080]]){
   await page.setViewportSize({width,height});await page.evaluate(()=>window.scrollTo(0,0));
   const closed=await chat.boundingBox();const frame=await chat.evaluate(e=>e.parentElement.getBoundingClientRect().width);
   assert.ok(Math.abs(closed.width-frame)<1,'No reserved history column');
   await screenshot(page,'closed-'+width+'x'+height);
   await toggle.click();await expect(panel).toBeVisible();
   await expect(panel).toContainText('从这里开始第一段对话。');
   const opened=await chat.boundingBox(),drawer=await panel.boundingBox();
   assert.deepEqual(opened,closed,'Opening history never squeezes or moves conversation');
   assert.ok(drawer.x>=closed.x&&drawer.x+drawer.width<=closed.x+closed.width);
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   await screenshot(page,'empty-open-'+width+'x'+height);
   await page.keyboard.press('Escape');await expect(panel).toBeHidden();await expect(toggle).toBeFocused();
   results.geometry.push({viewport:width+'x'+height,closed,opened,drawer});
  }
  results.contentStates.empty={status:'pass',evidence:'Empty drawer explains missing history; New conversation remains visible and the chat fills the whole workspace.'};
  await page.setViewportSize({width:1440,height:960});
  await page.getByRole('button',{name:'本科三年级',exact:true}).click();
  await page.getByRole('textbox',{name:'给校伴的消息'}).fill('保留这条尚未发送的草稿');
  await toggle.click();await page.keyboard.press('Escape');
  await expect(page.getByRole('button',{name:'本科三年级',exact:true})).toHaveAttribute('aria-pressed','true');
  await expect(page.getByRole('textbox',{name:'给校伴的消息'})).toHaveValue('保留这条尚未发送的草稿');
  await toggle.click();await page.getByRole('heading',{name:'校伴助手',exact:true}).click();await expect(panel).toBeHidden();
  results.checks.push('Disclosure, outside click and Escape preserve questionnaire answer and unsent draft.');
  mode='loading';await page.goto(base+'/agent');await expect(toggle).toHaveCount(1);await toggle.click();
  await expect(panel.getByRole('status')).toHaveText('正在读取…');
  await screenshot(page,'loading-1440x960');initialRelease();
  await expect(panel.locator('button[title]')).toHaveCount(30);
  mode='success';
  await page.keyboard.press('Escape');await toggle.focus();await page.keyboard.press('Enter');await page.keyboard.press('Tab');
  await expect(panel.locator('button[title]').first()).toBeFocused();
  assert.ok(await panel.locator('button[title]').first().evaluate(e=>getComputedStyle(e).outlineStyle!=='none'));
  assert.equal(await panel.evaluate(e=>getComputedStyle(e).animationName),'none');
  assert.ok(await foregroundContrast(panel.locator('button[title]').first())>=4.5);
  assert.ok(await foregroundContrast(toggle)>=3);
  assert.ok(await panel.locator('button[title] span').first().evaluate(e=>e.getBoundingClientRect().height<=parseFloat(getComputedStyle(e).lineHeight)*2+1),'Long titles stay within two lines');
  await screenshot(page,'history-keyboard-1440x960');
  holdDetail=true;await panel.locator('button[title]').first().click();
  await expect(newChat).toBeDisabled();await expect(panel.locator('[aria-busy]')).toHaveAttribute('aria-busy','true');
  detailRelease();holdDetail=false;
  await expect(panel).toBeHidden();await expect(chat).toContainText(reply[0].reply.message);await expect(toggle).toBeFocused();
  await toggle.click();await expect(panel.locator('[aria-current=true]')).toHaveText(rows[0].title);
  await screenshot(page,'selected-history-1440x960');
  await page.keyboard.press('Escape');await newChat.click();await expect(chat).toContainText('你好，我是校伴。');
  await expect(page.getByRole('progressbar',{name:'问卷进度'})).toHaveAttribute('value','1');
  results.contentStates.loading={status:'pass',evidence:'Delayed list shows live loading status; delayed history read disables duplicate actions without removing the drawer.'};
  results.contentStates.success={status:'pass',evidence:'Selecting mocked history loads its content, returns focus and collapses; reopening highlights current history. New conversation resets to the questionnaire.'};
  mode='error';await reload();await toggle.click();await expect(panel.getByRole('alert')).toContainText('会话暂时无法读取');
  await expect(panel).not.toContainText('从这里开始第一段对话。');await screenshot(page,'error-1440x960');
  mode='success';await panel.getByRole('button',{name:'重新读取'}).click();await expect(panel.locator('button[title]')).toHaveCount(30);
  detailFailure=true;await panel.locator('button[title]').first().click();await expect(panel.getByRole('alert')).toContainText('这段对话');
  await expect(chat).toContainText('你好，我是校伴。');detailFailure=false;
  results.contentStates.error={status:'pass',evidence:'List failure has a retry that recovers; failed history selection keeps the current conversation and leaves the selectable history intact.'};
  mode='permission';await reload();await toggle.click();await expect(panel.getByRole('alert')).toContainText('请登录后继续对话。');
  await expect(panel.getByRole('link',{name:'重新登录 →'})).toHaveAttribute('href','/login');
  await screenshot(page,'permission-1440x960');
  results.contentStates.permission={status:'pass',evidence:'Mocked expired-session response shows the explicit login recovery link inside history, with no fake empty/success state.'};
  mode='success';await reload();await toggle.click();moreFailure=true;
  await panel.getByRole('button',{name:'加载更多'}).click();await expect(panel.getByRole('alert')).toContainText('后续会话');
  await expect(panel.locator('button[title]')).toHaveCount(30);await screenshot(page,'partial-1440x960');
  moreFailure=false;await panel.getByRole('button',{name:'加载更多'}).click();await expect(panel.locator('button[title]')).toHaveCount(31);
  await expect(panel.getByRole('button',{name:'加载更多'})).toHaveCount(0);
  results.contentStates.partial={status:'pass',evidence:'Failed next page keeps the 30 loaded history entries and retry. Successful retry adds the last entry without duplicates.'};
  await page.keyboard.press('Escape');await toggle.focus();await page.keyboard.press('Tab');await expect(newChat).toBeFocused();
  await toggle.click();await newChat.focus();await expect(panel).toBeHidden();
  await page.emulateMedia({reducedMotion:'no-preference'});await toggle.click();await expect(panel).toBeVisible();
  assert.ok(await panel.evaluate(e=>getComputedStyle(e).animationName!=='none'));await page.keyboard.press('Escape');
  await page.getByRole('link',{name:'账号管理',exact:true}).click();await expect(page).toHaveURL(base+'/settings');
  await expect(page.getByRole('heading',{name:'设置',exact:true})).toBeVisible();
  results.checks.push('Keyboard Enter/Tab/Escape, visible focus, hidden-tab exclusion, outside-focus close, long titles, reduced motion, readable colors and real account link navigation passed.');
  assert.equal(results.errors.length,0);
  results.status='pass';
 }finally{fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify(results,null,2));await browser.close()}
 console.log(JSON.stringify(results,null,2));
})().catch(e=>{console.error(e);process.exitCode=1});

import {test,expect,type BrowserContext} from '@playwright/test';
// Test-only identity injection for DEMO_MODE. No auth bypass is added to the app.
// This exercises client-driven pages; real Supabase login remains a separate gate.
async function identity(context:BrowserContext,user:string){
 const api=process.env.E2E_API_URL||'http://127.0.0.1:8000';
 await context.route('**/api/backend/**',async route=>{
  const req=route.request();const path=new URL(req.url()).pathname.replace('/api/backend','')+new URL(req.url()).search;
  const response=await context.request.fetch(api+path,{method:req.method(),headers:{'Content-Type':'application/json','X-User-Id':user},data:req.postData()||undefined});
  await route.fulfill({response});
 });
}
test('双账号浏览器：邀请接受、任务、聊天、举报处理',async({browser,page,request})=>{
 const id=`member-${Date.now()}`;const second=await browser.newContext();await identity(second,id);const member=await second.newPage();
 const api=process.env.E2E_API_URL||'http://127.0.0.1:8000';
 await request.get(api+'/v1/profile',{headers:{'X-User-Id':id}});
 const name=`协作验收-${Date.now()}`;
 try{
  await page.goto('/team-manager');await page.getByLabel('新队伍名称').fill(name);await page.getByRole('button',{name:'创建队伍',exact:true}).click();
  const card=page.locator('article').filter({has:page.getByRole('heading',{name,exact:true})});await card.getByLabel('成员用户 ID').fill(id);await card.getByRole('button',{name:'邀请成员'}).click();
  await member.goto('/team-manager');const invitation=member.locator('article').filter({hasText:`队伍 ${name}`});await invitation.getByRole('button',{name:'接受',exact:true}).click();
  await expect(member.getByRole('heading',{name,exact:true})).toBeVisible();await page.reload();
  await card.getByLabel('任务标题').fill('双账号协作任务');await card.getByLabel('任务负责人').selectOption(id);await card.getByRole('button',{name:'创建任务',exact:true}).click();
  await expect(card.getByRole('heading',{name:'双账号协作任务',exact:true})).toBeVisible();await member.reload();
  await member.getByRole('button',{name:'进行中',exact:true}).click();await member.getByRole('button',{name:'已完成',exact:true}).click();
  await card.getByRole('link',{name:'进入队伍房间'}).click();await page.getByLabel('消息',{exact:true}).fill('等待对方举报的测试消息');await page.getByRole('button',{name:'发送',exact:true}).click();
  await member.getByRole('link',{name:'进入队伍房间'}).click();const message=member.locator('[aria-label="聊天记录"] article').filter({hasText:'等待对方举报的测试消息'});await expect(message).toBeVisible();await message.getByRole('button',{name:'举报',exact:true}).click();
  await page.goto('/admin/reports');const report=page.locator('article').filter({hasText:'等待对方举报的测试消息'});await report.getByLabel('处理理由').fill('测试举报处理');await report.getByRole('button',{name:'移除消息',exact:true}).click();
  await member.getByRole('button',{name:'刷新消息'}).click();await expect(member.getByText('[消息已由管理员移除]',{exact:false})).toBeVisible();
  await page.goto('/admin/audit');await expect(page.locator('main')).toContainText('report_remove');
 }finally{await second.close()}
});

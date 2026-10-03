import { test, expect } from '@playwright/test';
// Run against an isolated DEMO_MODE=true database. These do not test real Supabase/Dify.
test('个人行动：画像 → 机会 → 看板持久化 → 提醒', async ({page})=>{
 await page.goto('/profile');await page.getByLabel('展示昵称').fill('浏览器验收同学');await page.getByRole('button',{name:'保存画像'}).click();await expect(page.getByText('画像已保存，可立即用于资格判断。')).toBeVisible();
 await page.goto('/opportunities?type=job');await page.locator('main').getByRole('link',{name:'查看详情 →'}).first().click();
 await page.getByRole('button',{name:'加入行动看板',exact:true}).click();await expect(page.getByRole('status')).toContainText('已加入行动看板');
 await page.getByRole('button',{name:'设置提醒',exact:true}).click();await expect(page.getByRole('status')).toContainText('已设置截止前 24 小时提醒');
 await page.goto('/tracker');await page.getByRole('tab',{name:/机会行动/}).click();await expect(page.locator('main')).toContainText('实习');await page.reload();await page.getByRole('tab',{name:/机会行动/}).click();await expect(page.locator('main')).toContainText('实习');
 await page.goto('/notifications');await expect(page.getByRole('heading',{name:'已设置的提醒'})).toBeVisible();
});
test('竞赛：建队 → 邀请 → 接受 → 房间持久化', async ({ page, request }) => {
  const name = `验收队伍-${Date.now()}`;
  const api = process.env.E2E_API_URL || 'http://127.0.0.1:8000';
  expect((await request.get(`${api}/v1/profile`, { headers: { 'X-User-Id': 'demo-python' } })).ok()).toBe(true);
  await page.goto('/team-manager');
  await page.getByLabel('新队伍名称').fill(name);
  await page.getByRole('button', { name: '创建队伍', exact: true }).click();
  const card = page.locator('article').filter({ has: page.getByRole('heading', { name }) });
  await expect(card).toBeVisible();
  await card.getByLabel('成员用户 ID').fill('demo-python');
  await card.getByRole('button', { name: '邀请成员' }).click();
  await expect(page.getByRole('status')).toContainText('邀请已发送');
  const invites = await (await request.get(`${api}/v1/invitations`, { headers: { 'X-User-Id': 'demo-python' } })).json();
  const teams = await (await request.get(`${api}/v1/teams`)).json();
  const team = teams.find((t: { title: string }) => t.title === name);
  expect(invites.some((i: { team_id: string }) => i.team_id === team.id)).toBe(true);
  expect((await request.post(`${api}/v1/invitations/${team.id}/decision`, { headers: { 'X-User-Id': 'demo-python' }, data: { action: 'accept' } })).ok()).toBe(true);
  await page.reload();
  await expect(card).toContainText('2 / 5 位成员');
  await page.goto('/teams');
  await page.getByRole('button', { name, exact: true }).click();
  await page.getByLabel('消息', { exact: true }).fill('队伍已集合');
  await page.getByRole('button', { name: '发送', exact: true }).click();
  await expect(page.getByText('队伍已集合', { exact: false })).toBeVisible();
});
test('考公：规则依据 → 创建提醒 → 通知中心', async ({ page }) => {
  await page.goto('/eligibility?opportunity_id=civil-001');
  await page.getByRole('button', { name: '使用我的画像判断' }).click();
  await expect(page.getByRole('link', { name: '查看规则来源' }).first()).toBeVisible();
  await page.goto('/opportunity/civil-001');
  await page.getByRole('button', { name: '设置提醒', exact: true }).click();
  await expect(page.getByText('已设置截止前 24 小时提醒')).toBeVisible();
  await page.goto('/notifications');
  await expect(page.getByRole('heading', { name: /通知/ }).first()).toBeVisible();
  // Worker delivery and exactly-once semantics are covered by backend tests using past due records.
});
test('注册入口、举报管理与移动端无水平溢出', async ({ page }) => {
  await page.goto('/login');
  await expect(page.getByRole('heading', { name: '身份服务尚未配置' })).toBeVisible();
  await page.goto('/admin/reports');
  await expect(page.getByRole('heading', { name: '举报处理' })).toBeVisible();
  await page.goto('/safety');
  await expect(page.getByRole('heading', { name: '隐私与安全' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
});
test('来源：归档 → 审核原文 → 发布 → 资格规则', async ({ page }) => {
  const title = `归档验收职位-${Date.now()}`;
  const source = `https://example.edu/fixture-${Date.now()}`;
  await page.goto('/admin/sources');
  await page.getByLabel('公开原文').fill('本条是浏览器验收使用的虚构公告，仅限大三报名。全部信息仅用于测试，不可用于真实报名。');
  await page.getByLabel('结构化字段 JSON').fill(JSON.stringify({ type: 'civil_service', title, organization: '验收测试单位', summary: '验收数据', location: '线上', deadline: new Date(Date.now() + 7 * 86400000).toISOString(), source_url: source, source_label: '测试来源', fetched_at: new Date().toISOString(), rules: [{ field: 'grade', operator: 'in', expected: '大三', label: '年级条件', source_url: source, evidence: '仅限大三报名。' }] }));
  await page.getByRole('button', { name: '归档并提交审核' }).click();
  await expect(page.getByRole('status')).toContainText('归档成功');
  await page.goto('/admin/review');
  const row = page.locator('.review-row').filter({ has: page.getByText(title, { exact: true }) });
  await row.getByRole('button', { name: '核对字段与归档' }).click();
  await expect(page.getByRole('heading', { name: '原文归档', exact: true })).toBeVisible();
  await row.getByRole('button', { name: '通过', exact: true }).click();
  await expect(row).toHaveCount(0);
  await page.goto('/eligibility');
  await page.getByLabel('选择已发布机会').selectOption({ label: title });
  await page.getByRole('button', { name: '使用我的画像判断' }).click();
  await expect(page.locator('blockquote')).toHaveText('仅限大三报名。');
});

test('消息：自动收到对方消息，离线恢复后补齐', async ({page, request, context}) => {
 const api=process.env.E2E_API_URL||'http://127.0.0.1:8000';
 const room=await (await request.post(`${api}/v1/tools/message_connect`,{data:{target:'demo-design'}})).json();
 await page.goto('/teams');
 // Match and select the exact room even when older conversations exist.
 await page.getByText('寻找互补的队友',{exact:true}).click();
 await page.getByRole('button',{name:'匹配队友'}).click();
 await page.locator('article').filter({has:page.getByRole('heading',{name:'演示队友·设计'})}).getByRole('button',{name:'确认建立联系'}).click();
 await expect(page.getByText('已连接 · 每 3 秒自动同步')).toBeVisible();
 const body=`自动补齐-${Date.now()}`;
 await context.setOffline(true);
 expect((await request.post(`${api}/v1/rooms/${room.id}/messages`,{headers:{'X-User-Id':'demo-design'},data:{body}})).ok()).toBe(true);
 await context.setOffline(false);
 await expect(page.getByText(body,{exact:false})).toBeVisible({timeout:15000});
 await expect(page.getByText(body,{exact:false})).toHaveCount(1);
});


test('队伍任务：创建、开始、完成和刷新持久化', async ({page})=>{
 const name=`任务小队-${Date.now()}`;
 await page.goto('/team-manager');
 await page.getByLabel('新队伍名称').fill(name);
 await page.getByRole('button',{name:'创建队伍',exact:true}).click();
 const card=page.locator('article').filter({has:page.getByRole('heading',{name,exact:true})});
 await card.getByLabel('任务标题').fill('提交建模方案');
 await card.getByLabel('任务负责人').selectOption('demo-user');
 await card.getByRole('button',{name:'创建任务',exact:true}).click();
 await expect(card.getByRole('heading',{name:'提交建模方案',exact:true})).toBeVisible();
 await card.getByRole('button',{name:'进行中',exact:true}).click();
 await expect(card.getByText('负责人：demo-user · 进行中')).toBeVisible();
 await card.getByRole('button',{name:'已完成',exact:true}).click();
 await page.reload();
 await expect(card.getByRole('heading',{name:'任务分工 · 1/1 已完成'})).toBeVisible();
});

test('未配置身份服务时找回密码明确提示',async({page})=>{
 await page.goto('/recover');
 await expect(page.getByRole('heading',{name:'身份服务尚未配置'})).toBeVisible();
 await expect(page.getByRole('link',{name:'返回首页'})).toBeVisible();
});

test('原文检索：未知词不编造依据',async({page})=>{
 await page.goto('/knowledge');
 await page.getByLabel('要查找的内容').fill(`不存在的依据${Date.now()}`);
 await page.getByRole('button',{name:'检索依据'}).click();
 await expect(page.getByRole('status')).toContainText('未找到依据');
});

 test('主体导航与功能开关',async({page,isMobile})=>{
 for(const path of ['/','/opportunities','/tracker','/notifications','/team-manager','/safety']){await page.goto(path);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);}
 if(isMobile)await page.getByRole('button',{name:'展开导航'}).click();
 await expect(page.getByRole('navigation',{name:'主导航'}).getByRole('link',{name:'校园机会'})).toBeVisible();
 await page.goto('/agent');await expect(page.getByRole('heading',{name:process.env.E2E_AGENT_UI==='true'?'和校伴，一起想清楚下一步':'页面或机会不存在'})).toBeVisible();
 await page.goto('/admin/collector');await expect(page.getByRole('heading',{name:'页面或机会不存在'})).toBeVisible();
});

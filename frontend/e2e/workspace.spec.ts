import {test,expect} from '@playwright/test';
const api=process.env.E2E_API_URL||'http://127.0.0.1:8033';
const student=process.env.E2E_STUDENT_URL||'http://127.0.0.1:3034';

test('工作空间：频道筛选、移动导航和主要页面布局',async({page,isMobile})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 for(const route of ['/','/data','/opportunities','/tracker','/paths','/agent','/teams','/team-manager','/profile','/notifications','/knowledge','/eligibility','/safety','/admin','/admin/data','/admin/registry','/admin/review','/admin/sources','/admin/reports','/admin/audit','/admin/operations','/admin/source-candidates','/admin/source-changes','/admin/overseas','/admin/entrepreneurship','/login','/recover','/data/timeline']){
  await page.goto(route);await expect(page.locator('h1')).toBeVisible();
  await expect(page.getByRole('heading',{name:'暂时无法打开此页面'})).toHaveCount(0);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),route).toBe(true);
 }
 await page.goto('/');if(isMobile){await page.getByRole('button',{name:'展开导航'}).click();await expect(page.getByRole('navigation',{name:'主导航'})).toBeVisible()}
 await page.getByRole('navigation',{name:'主导航'}).getByRole('link',{name:'国内考研',exact:true}).click();
 await expect(page).toHaveURL(/path=domestic_postgraduate_exam/);await expect(page.getByRole('heading',{level:1})).toContainText('考研');
 if(isMobile){await page.getByRole('button',{name:'展开导航'}).click();await page.keyboard.press('Escape');await expect(page.getByRole('button',{name:'展开导航'})).toBeFocused()}
 expect(errors).toEqual([]);
});

test('个人计划：创建、状态更新、编辑与刷新持久化',async({page,request})=>{
 const title='UI验收计划-'+Date.now();await page.goto('/tracker');await page.getByRole('button',{name:'新建计划'}).click();await page.getByLabel('计划标题',{exact:true}).fill(title);await page.getByLabel('下一步与备注').fill('仅用于界面验收，可在独立验收数据库中清理。');await page.getByRole('button',{name:'保存计划',exact:true}).click();await expect(page.getByRole('status')).toContainText('计划已保存');
 await page.getByLabel('更新计划状态：'+title,{exact:true}).selectOption('doing');await expect(page.getByLabel('更新计划状态：'+title,{exact:true})).toHaveValue('doing');await page.reload();await expect(page.getByLabel('更新计划状态：'+title,{exact:true})).toHaveValue('doing');
 const card=page.locator('.plan-card').filter({has:page.getByRole('heading',{name:title,exact:true})});await card.getByRole('button',{name:'编辑'}).click();await page.getByLabel('下一步与备注').fill('准备进入下一步');await page.getByRole('button',{name:'保存计划',exact:true}).click();await expect(card).toContainText('准备进入下一步');
 const plans=await(await request.get(api+'/v1/plans')).json();expect(plans.find((p:{title:string})=>p.title===title).status).toBe('doing');
});

test('数据事项：查看证据、加入个人计划并打开资格助手',async({page})=>{
 await page.goto('/data?status=all');const row=page.locator('.feed-row').first();await row.getByRole('link',{name:'详情与原文依据'}).click();await expect(page.getByRole('heading',{name:'来源与版本'})).toBeVisible();await page.getByRole('button',{name:'加入我的计划',exact:true}).first().click();await expect(page.getByRole('status').first()).toContainText('已加入');
 await page.getByRole('link',{name:'请校伴核对我的资格 →'}).first().click();await expect(page.getByLabel('助手功能')).toHaveValue('eligibility');await expect(page.getByText('已选择：来源事项')).toBeVisible();await page.getByRole('button',{name:'发送',exact:true}).click();await expect(page.getByText(/条件核对：/)).toBeVisible();
});

test('助手：预览、确认写入、会话持久化及选择计划提醒',async({page,request})=>{
 const query='请给我考研准备计划 UI验收-'+Date.now();await page.goto('/agent?intent=plan&path=domestic_postgraduate_exam');await page.getByLabel('给校伴的消息').fill(query);await page.getByRole('button',{name:'发送',exact:true}).click();await expect(page.getByText('等待你确认')).toBeVisible();const before=(await(await request.get(api+'/v1/plans')).json()).length;
 await page.getByRole('button',{name:'确认保存',exact:true}).click();await expect(page.getByText(/已保存 \d+ 项计划/)).toBeVisible();expect((await(await request.get(api+'/v1/plans')).json()).length).toBeGreaterThan(before);await page.reload();await page.locator('.session-button').filter({hasText:query}).click();await expect(page.getByText(/已保存 \d+ 项计划/)).toBeVisible();
 await page.goto('/tracker');await page.getByRole('link',{name:/设置提醒：/}).first().click();await expect(page.getByLabel('助手功能')).toHaveValue('reminder');await expect(page.getByLabel('选择我的计划')).not.toHaveValue('');
});

test('画像：更新基本信息时保留发展目标与经历',async({page,request})=>{
 await page.goto('/profile');await page.getByLabel('目标方向',{exact:true}).selectOption('employment');await page.getByLabel('科研经历',{exact:true}).fill('界面验收：保留已有研究经历');await page.getByRole('button',{name:'保存画像',exact:true}).click();await expect(page.getByRole('status')).toContainText('画像已保存');await page.reload();await page.getByLabel('展示昵称',{exact:true}).fill('界面验收同学');await page.getByRole('button',{name:'保存画像',exact:true}).click();await expect(page.getByRole('status')).toContainText('画像已保存');const p=await(await request.get(api+'/v1/profile')).json();expect(p.research_exp).toBe('界面验收：保留已有研究经历');expect(p.target_path).toBe('employment');
});

test('角色隔离：学生无管理入口且伪造请求头不能访问管理接口',async({page,isMobile})=>{
 await page.goto(student+'/');if(isMobile)await page.getByRole('button',{name:'展开导航'}).click();await expect(page.getByRole('link',{name:'进入运营后台',exact:true})).toHaveCount(0);await expect(page.locator('.role-label')).toHaveText('学生');
 await page.goto(student+'/admin');await expect(page.getByRole('heading',{name:'需要管理员权限'})).toBeVisible();await expect(page.getByRole('link',{name:'数据接入与发布',exact:true})).toHaveCount(0);
 const r=await page.request.get(student+'/api/backend/v1/admin/data/overview',{headers:{'X-User-Id':'reserved-administrator'}});expect(r.status()).toBe(403);
 await page.goto('/admin');await expect(page.getByRole('heading',{name:'运营概览'})).toBeVisible();await page.getByRole('link',{name:'切回学生视图 →'}).click();await expect(page).toHaveURL(/\/$/);await expect(page.locator('.role-label')).toHaveText('管理员');
});

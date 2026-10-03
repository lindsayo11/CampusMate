import {test,expect} from "@playwright/test";

test("数据中心不使用演示机会填充，保留真实空态",async({page})=>{
  await page.goto("/data");
  await expect(page.getByRole("heading",{name:"发展信息中心"})).toBeVisible();
  await page.getByLabel("搜索信息",{exact:true}).fill("没有已发布数据的测试查询");
  await page.getByRole("button",{name:"筛选",exact:true}).click();
  await expect(page.getByText("没有找到匹配的信息",{exact:false})).toBeVisible();
  await page.goto("/data/timeline");
  await expect(page.getByRole("heading",{name:"事项时间线"})).toBeVisible();
  await expect(page.getByText("按公开事项提供的日期安排准备，未注明的日期不会被推测。")).toBeVisible();
});

test("数据工作台展示阻塞且可打开导入表单",async({page})=>{
  await page.goto("/admin/data");
  await expect(page.getByRole("heading",{name:"接入、证据与发布"})).toBeVisible();
  await page.getByText("导入官方原始 HTML / XLSX（手动导入，需审核）").click();
  await expect(page.getByLabel("Source 编码")).toBeVisible();
  await expect(page.getByLabel("官方原始 URL")).toBeVisible();
  await expect(page.getByRole("button",{name:"解析并保存草稿"})).toBeVisible();
});

test("校准未完成时不允许点击自动调度",async({page})=>{
  await page.goto("/admin/registry");
  const buttons=page.getByRole("button",{name:"核验并启用",exact:true});
  await expect(buttons.first()).toBeVisible();
  for(const button of await buttons.all())await expect(button).toBeDisabled();
  await expect(page.getByRole("button",{name:"查看校准原始依据"}).first()).toBeVisible();
});

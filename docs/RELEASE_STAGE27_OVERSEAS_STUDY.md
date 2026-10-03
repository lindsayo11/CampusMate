# Stage 27 M5 国境外升学 PoC 发布说明

版本：v0.27.0-ingestion.1  
日期：2026-09-29

## 已完成

- 新增 0018 数据库迁移以及国家、地区、院校、项目稳定 ID 与别名模型。
- 新增 OverseasRegistryAdapter，Registry 只能写入实体和公共状态，不能生成年度申请要求。
- 新增 OverseasUniversityProgramAdapter，年度 deadline、学历、GPA、语言和材料只接受目标大学第一方页面。
- 完成 Institution、Program、ApplicationCycle、DevelopmentItem、EligibilityRule、Evidence 全链路。
- Evidence 保存 DocumentVersion、SHA256、表格或 DOM 位置、审核状态；文档详情接口继续提供版本 diff。
- SourceRegistry 登记留服中心、教育涉外监管、Discover Uni、CRICOS、Study in Japan、Hochschulkompass 和 Oxford 试点来源。
- 登录、验证码、付费、商业许可和个人申请业务继续由治理门禁阻断；许可证受限来源只登记状态和 Blocker。
- 新增境外院校、项目、申请周期、规则、证据和 Blocker 管理后台入口。
- Oxford MSc Advanced Computer Science 2027 入学周期仅作为保存 Fixture 的端到端测试样例，不代表实时同步。

## 验证结果

- Alembic 0001 → 0018 升级与 schema check 通过。
- 后端 76 项测试通过。
- 前端 19 项测试通过。
- TypeScript 类型检查通过。
- Next.js production build 通过。

## 真实阻塞

- 留服中心个人学历认证需要用户登录和个人材料，不进入后台采集。
- Hochschulkompass 的免费数据使用范围不覆盖生产或商业使用，未获书面许可前禁止导入。
- Discover Uni、CRICOS、Study in Japan 的当期下载入口、字段、robots 和许可证需要在可访问环境完成首轮人工核验。
- Oxford 页面当前只完成人工复核和保存 Fixture 校准；自动调度保持关闭，未伪造实时同步。

## 下一阶段开发提示词

基于 CampusMate v0.27.0-ingestion.1 累计完整源码继续开发 M5 线上校准与 M6 创业五级接入，不得删除或降级现有功能。先在合法可访问环境对 Discover Uni、CRICOS、Study in Japan 和 2–3 所目标大学执行匿名公开页面/文件的首轮人工核验，确认 robots、条款、许可、精确下载 URL 和字段后再启用端点；所有实时版本必须保存 DocumentVersion、内容哈希、DOM/表格 Evidence、差异和审核状态。Registry 仍不得推导年度申请要求，deadline、GPA、语言、学历、材料、费用必须来自大学第一方页面。登录、验证码、付费、商业许可和个人申请页面不得进入后台采集；无法访问或未获许可的来源记录 Blocker。随后按国家→省→市/县→高校建立创业政策 SourceRegistry 和 GovernmentPolicyAdapter/OpenDataPlatformAdapter PoC，完成迁移、全量测试、类型检查和生产构建后输出下一版累计完整源码包。

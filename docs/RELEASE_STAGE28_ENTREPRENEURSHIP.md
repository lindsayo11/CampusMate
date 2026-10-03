# Stage 28 M6 创业政策五级接入 PoC 发布说明

版本：v0.28.0-ingestion.1  
日期：2026-09-29

## 已完成

- 新增 0019 数据库迁移，扩展 PolicyRecord 文号、发布机关、政策类型、辖区链、办理入口和审核状态，并为 PolicyRelation 增加 Evidence。
- 新增 GovernmentPolicyAdapter，将公开政策页确定性解析为 PolicyRecord、DevelopmentItem、EligibilityRule、DOM/表格 Evidence 和 DocumentVersion。
- 新增国家→省→市→区县→高校五级 SourceRegistry 样例与带证据的 implements 关系；稳定 ID 由来源与文号生成。
- 新增 OpenDataResource；北京公共数据端点需要 userKey，因此只登记认证、许可证状态与 Blocker，不采集有效载荷。
- 登录、验证码、API 密钥、商业许可、付费和用户个人业务页面继续被门禁拒绝。
- 新增创业政策、规则、关系、证据、版本差异和 Blocker 的管理后台审核入口。
- 补充留服中心、教育涉外监管、Discover Uni、CRICOS、Study in Japan、Oxford、Cambridge 与 Imperial 的线上校准 Blocker；所有未校准端点保持关闭。
- 固定 Fixture 覆盖五级链路和财政部财金〔2023〕75号结构化样例；Fixture 不代表实时同步或生产数据。

## 验证结果

- Alembic 0001 → 0019 升级与 schema check 通过。
- 后端 78 项测试通过。
- 前端 19 项测试通过。
- TypeScript 类型检查通过。
- Next.js production build 通过。

## 真实阻塞

- 当前执行环境不能访问目标官方站点完成 robots、条款、许可和精确 URL 的线上人工校准，因此所有相关端点保持 `scheduled=false`。
- 留服中心个人认证、大学个人申请及任何验证码页面禁止后台采集。
- 北京公共数据 API 需要数据所有者自行取得 userKey，并先确认商业/生产使用许可；项目不生成、猜测或代管未知凭据。
- Cambridge、Imperial 和深圳大学目前只登记官方目录或域名，尚未选定并校准具体当期项目/通知页。
- PostgreSQL、真实身份/邮件、域名容器部署和浏览器交互门禁仍未完成，不得标记正式 RC。

## 下一阶段开发提示词

基于 CampusMate v0.28.0-ingestion.1 累计完整源码继续开发，不得删除或降级现有功能。先在合法可访问环境逐一关闭留服中心、教育涉外监管、Discover Uni、CRICOS、Study in Japan、Oxford、Cambridge、Imperial 以及创业五级官方来源的 `live_access_unverified`/`exact_url_pending` Blocker；逐项人工记录 robots、条款、许可证、精确 URL、字段映射和校准时间，只有匿名公开、许可明确且精确页面通过审核的端点才能启用调度。随后为 M6 增加真实但最小化的省、市、区县和高校第一方样例，保留 DocumentVersion、SHA256、DOM/表格 Evidence、版本差异与双人审核；API-AUTH、登录、验证码、付费、商业许可和个人业务仍不得进入后台采集。最后补齐 PostgreSQL 迁移演练、浏览器审核链 E2E、全量测试、类型检查、生产构建，并输出下一版累计完整源码包。

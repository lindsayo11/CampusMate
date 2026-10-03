# Stage 29 线上端点校准门禁发布说明

版本：v0.29.0-ingestion.1  
日期：2026-09-29

## 已完成

- 新增 0020 迁移与 `SourceEndpointCalibration`，记录精确 URL、robots、条款、许可证、字段映射、Adapter 配置、校准时间和审核轨迹。
- 执行三方分离：提交人不能审核；第一、第二审核人必须为不同管理员。
- `live_access_unverified` 与 `exact_url_pending` 只有在双人批准后才会关闭；API Key、登录、商业许可等阻塞不受影响。
- 对仍有线上校准 Blocker 的端点，启用/恢复 API 强制要求已批准校准；启用 URL 必须与批准记录一致。
- Registry Seed 不再重新打开已解决 Blocker，也不会覆盖已批准的精确 URL、robots、许可证或 Adapter 配置。
- Registry 管理页新增开放 Blocker 数量、校准状态、提交、审核与驳回入口。

## 验证结果

- Alembic 0001 → 0020 升级、降级回放与 schema check 通过。
- 后端 79 项测试通过。
- 前端 19 项测试通过。
- TypeScript 类型检查与 Next.js production build 通过。
- 本轮变更文件 Ruff 检查通过。

## 未伪造的外部阻塞

- 当前环境没有完成留服中心、教育涉外监管、Discover Uni、CRICOS、Study in Japan、Oxford、Cambridge、Imperial 或创业省/市/区县/高校端点的实时 robots、条款与许可证核验，因此没有预填或批准任何生产校准记录。
- 北京公共数据 API 仍需要项目所有者合法取得 userKey 并确认生产/商业使用许可。
- PostgreSQL 迁移演练、真实身份/邮件、域名容器部署和浏览器交互门禁仍未完成，不得标记正式 RC。

## 下一阶段开发提示词

基于 CampusMate v0.29.0-ingestion.1 累计完整源码继续开发，不得删除、绕过或降级现有功能。优先在合法可访问环境使用新的 SourceEndpointCalibration 工作流，逐项完成留服中心、教育涉外监管、Discover Uni、CRICOS、Study in Japan、Oxford、Cambridge、Imperial 以及创业五级官方来源的真实人工校准；必须由提交人之外的两名管理员独立审核，不得用 Fixture 或推测关闭 Blocker。对通过校准且匿名公开、许可明确的 AUTO-1/AUTO-2 端点执行最小真实采集，保留 DocumentVersion、SHA256、DOM/表格 Evidence、版本差异和高风险审核。AUTO-3/manual 端点只完成校准与人工导入，不擅自改成自动调度。继续跳过 API-AUTH、登录、验证码、付费、商业许可和个人业务，并补齐 PostgreSQL、浏览器 E2E、真实身份/邮件与域名容器发布门禁。

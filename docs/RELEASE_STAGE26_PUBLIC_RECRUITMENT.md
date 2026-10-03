# Stage 26：事业单位与公共招聘接入

版本：v0.26.0-ingestion.1  
日期：2026-09-29

## 本阶段交付

- 事业单位公开招聘公告和 HTML 岗位表确定性 Adapter。
- 中国公共招聘类岗位表的受治理接入链路。
- RecruitmentCycle、Position、DevelopmentItem、Path、EligibilityRule、Evidence 完整关联。
- 官方地方招聘平台目录到 SourceRegistryCandidate 的发现链路。
- 候选批准后只生成 inactive 来源和未调度端点，避免目录发现结果直接进入生产采集。
- 地方来源候选审核 API、审计记录和管理后台页面。
- 0017 迁移与结构 Fixture 测试。

## 安全与数据状态

- 登录、密码和验证码页面拒绝解析。
- 手工导入、端点启用和重定向继续受官方域名边界约束。
- 资格规则默认 pending；复杂备注为 agent_candidate。
- 事业单位和公共招聘 Fixture 仅验证结构、数据流和证据链，不代表线上实时岗位。
- 当前执行环境无法访问目标政府域名，尚未完成在线页面抽样与结构校准。

## 验证

- Alembic 0001 → 0017 与 schema check：通过。
- 后端测试：72 项通过。
- 前端测试：19 项通过。
- Ruff、TypeScript 与 Next.js production build：通过。

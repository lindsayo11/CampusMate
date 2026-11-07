# Stage 25：国内升学公开信息接入

版本：v0.25.0-ingestion.1  
日期：2026-09-29

## 本阶段交付

- 教育部政策、研招网公开专业目录、高校公开招生通知三类确定性 Adapter。
- 从来源文档到 Institution、Program、ApplicationCycle、DevelopmentItem、Path、EligibilityRule、Evidence 的可追溯链路。
- 官方来源域名校验；登录、密码和验证码页面拒绝进入后台解析。
- 北京大学、清华大学、上海交通大学、复旦大学四个试点来源及端点；默认关闭自动调度。
- 结构 Fixture、重复导入、证据链、完整实体链和安全边界测试。

## 数据状态边界

- 政策记录写入 candidate；解析规则写入 pending。
- 只有人工核验后，规则才可标记 verified。
- Fixture 用于验证页面结构和数据流，不代表线上实时数据。
- 当前网络白名单不含目标官方域名，尚未完成在线页面抽样与结构校准。

## 验证

- Alembic 0001 → 0016：通过。
- 后端测试：68 项通过。
- Ruff：本阶段新增/修改 Python 文件通过。
- 前端测试：19 项通过。
- TypeScript 与 Next.js production build：通过。

# 当前开发状态 v0.17.0

在 v0.16.0 基础上加入持久化采集任务、来源配置、定时调度、文件解析和原文到审核链路。当前功能优先，UI 为基本可操作页面。

实测 40 项后端、15 项身份协议、TypeScript、生产构建、SQLite 0010 迁移与 metadata check 通过。
网络采集使用受控响应测试；浏览器 UI、真实官网、正式身份/邮件/Dify、PostgreSQL、容器/TLS 未验收。

下一阶段：原文切片、可溯源检索、审核及公开范围过滤。仍待完善：LLM 字段抽取、pgvector 语义检索、账号注销、Realtime、组织认证、任务提醒与成果文件、正式数据和生产部署验收。
完整采集说明见 docs/COLLECTION.md；历史进度在 docs/HISTORY_DEVELOPMENT_STATUS_v016.md。

# 当前开发状态 v0.14.0

已保留 v0.13.0 全部业务，新增消息历史分页、未读计数、已读游标和自动断线补齐。
本轮：32 项后端、8 项身份协议、类型检查和生产构建通过；浏览器受执行器 SIGTRAP 阻塞，12 项待在标准主机复验。

## 上线前仍需完成
账号找回与注销、正式身份联调；官方源自动采集与提取；RAG/pgvector；Supabase Realtime；队伍任务分工；组织身份认证；正式服务/官方内容/用户测试和生产部署验收。
PostgreSQL CI 已配置但本机无 PostgreSQL/Docker，未实际验收生产数据库。
详细历史见 docs/HISTORY_DEVELOPMENT_STATUS_v013.md。本阶段说明见 RELEASE_STAGE14.md。

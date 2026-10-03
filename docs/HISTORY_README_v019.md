# CampusMate 校伴

当前完整累计源码 **v0.19.0**。保留用户原始 v0.13.0 包及后续各阶段全部源码，只需本包即可继续开发。目标为校园机会与行动平台，目前尚未完成正式上架验收。

## 功能进度

已有六板块机会、画像、资格证据、看板、提醒、组队邀请、持久化私信、拉黑举报、人工审核、原文归档、Agent 六工具和写入确认。

- 阶段 14–16：消息分页/已读/自动补齐、队伍任务分工、邮箱找回密码。
- 阶段 17：定时来源采集、附件解析、失败重试和审核衔接，入口 /admin/collector。
- 阶段 18：原文切片、公开授权、可溯源关键词检索与助手引用，入口 /knowledge。
- 阶段 19：队伍任务站内到期通知、改期/转交处理和幂等投递，入口 /notifications。

UI 仅实现基础操作流程，便于后续重新设计。

## 启动

需要 Python 3.12、Node 22+。从项目根目录运行：

```bash
export DEMO_MODE=true
export ADMIN_USER_IDS=demo-user
bash scripts/dev.sh
```

前端 http://localhost:3000，API http://localhost:8000/docs。演示数据为虚构数据，演示身份不能用于公开部署。真实运行请按 docs/DEPLOYMENT.md 配置身份服务和数据库。

## 实际验证

后端 48 项、身份协议 15 项、TypeScript、Next.js 生产构建通过。迁移 0001→0012、旧行保留、历史审核回填和 metadata check 通过；SQLite 29 张表备份恢复全部行一致。

浏览器套件 20 项本轮未执行；真实官网采集、Supabase/SMTP/Dify/PostgreSQL/容器/TLS 尚未验收。检索是关键词模式，不是完整语义 RAG；账号注销等仍需开发，详见 DEVELOPMENT_STATUS.md。

## 使用说明

- docs/COLLECTION.md：来源白名单、Worker、解析、重跑和审核。
- docs/KNOWLEDGE.md：原文公开范围与检索。
- docs/TASK_ALERTS.md：任务通知。
- docs/PASSWORD_RECOVERY.md：找回密码与邮件模板。
- docs/DEPLOYMENT.md：启动、升级与备份；升级前备份，再运行 alembic upgrade head。

各阶段交付记录保留在 RELEASE_STAGE*.md，历史测试结果不等于当前生产验收。

# CampusMate 校伴

当前累计版本 **v0.15.0**，基于用户提供的 v0.10.0 源码继续开发，包含第 1–13 阶段的完整源码。无需叠加旧版本。目标为响应式 Web 校园机会与行动平台；当前可运行、可生产构建，但还未完成真实服务和正式上线验收。

## 本轮功能

- 阶段 11：邮箱注册、确认提示、HttpOnly 会话、自动续期与远端退出。
- 阶段 12：举报审核、消息移除/证据保留、解除拉黑、账号级频控、浏览器验收脚本。
- 阶段 13：原文归档、内容哈希、变更差异、导入去重、规则与证据审核发布、动态资格页面、Worker 健康、请求追踪、备份恢复、HTTPS 部署配置。

保留前期六板块机会、画像、看板、提醒、组队与私信、Agent 六工具及确认执行功能。

## 快速演示

需要 Python 3.12、Node 22+ 和依赖包源。仅用于本机演示：

```bash
export DEMO_MODE=true
export ADMIN_USER_IDS=demo-user
bash scripts/dev.sh
```

前端 http://localhost:3000，API http://localhost:8000/docs。演示数据是虚构测试数据，不是官方内容。公开部署必须关闭 DEMO_MODE。

## 验证与交付

本轮最新实测：30 项后端测试、8 项身份协议测试、10 项桌面/移动浏览器测试通过；TypeScript 与 Next.js 生产构建通过；SQLite 迁移及实际 21 表备份恢复通过。

完整启动、升级、环境变量、PostgreSQL/HTTPS/备份步骤见 docs/DEPLOYMENT.md；内容操作见 docs/CONTENT_INTAKE.md；每阶段变更见 RELEASE_STAGE11.md、RELEASE_STAGE12.md、RELEASE_STAGE13.md。DEVELOPMENT_STATUS.md 列明未完成项。

历史阶段说明保留在 RELEASE_STAGE3–10.md；旧 README 和进度记录移至 docs/HISTORY_*，不能将其旧状态当作当前状态。

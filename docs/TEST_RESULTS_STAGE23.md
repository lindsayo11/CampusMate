# 阶段 23 实测记录

测试日期：2026-09-29 UTC。Python 3.12.14，Node 24.19.0，Next 16.3.6，SQLite；依赖实际版本见 backend/requirements-tested.txt 和 frontend/package-lock.json。

| 验证 | 实际结果 |
| --- | --- |
| 后端全量 | 52 passed，1 条 Starlette/httpx 弃用提示 |
| 前端测试 | 16 passed，含 15 身份协议测试和 1 冻结入口回归 |
| TypeScript | 0 error |
| Next production build | 通过；云环境使用既有 restricted-node.cjs 读取内存兼容 |
| 迁移 | 空库→0012，0001/0010→head 与 metadata check 通过 |
| 运行 | API、standalone Web、Worker 在同一监督进程环境冷启动成功 |
| 页面 HTTP smoke | 18 个主体页面响应 200，无通用错误页；不证明按钮交互/布局正常 |
| 冻结入口 | /agent 和 /admin/collector HTTP 404 |
| 不存在的机会 | API 返回 404；Next 流式页面显示 not-found 内容，HTTP 可为 200 |
| Worker | 心跳健康；实际插入到期提醒，连续运行两次仍仅 1 条通知 |
| SQLite 恢复 | 29 张表逐表行数一致（包含 alembic_version）；详情见下方 |
| Playwright | 可发现 22 个用例；尝试运行桌面导航用例，在浏览器启动时 SIGTRAP，未进入交互 |
| Supabase/邮件 | 仅受控协议测试通过，未进行真实服务联调 |
| PostgreSQL | psycopg 已安装；无目标库，未执行真实迁移/恢复 |
| Docker/TLS | 无 Docker 运行服务/目标域名，未验收 |

## 环境处理记录

npm ci 已成功安装前端依赖，pip 已安装后端依赖及 psycopg。标准 Playwright Chromium 下载返回损坏归档；使用源码已有 @sparticuz/chromium 中的浏览器包解压，解决临时目录和归档属主问题后，浏览器仍以 SIGTRAP 退出。测试失败保留为阻塞，不以 typecheck、build 或 HTTP 测试替代浏览器验收。

构建初始报 uv_resident_set_memory ENOENT，使用源码已有脚本解决。构建中 API 离线时页面请求失败已通过动态渲染修复，不再把 API 错误伪装为空列表。

HTTP smoke 的程序化结果：

```json
{
  "status": "passed",
  "pages": {
    "/": 200,
    "/opportunities": 200,
    "/opportunity/job-001": 200,
    "/profile": 200,
    "/eligibility": 200,
    "/tracker": 200,
    "/notifications": 200,
    "/teams": 200,
    "/team-manager": 200,
    "/safety": 200,
    "/login": 200,
    "/recover": 200,
    "/admin": 200,
    "/admin/audit": 200,
    "/admin/review": 200,
    "/admin/reports": 200,
    "/admin/sources": 200,
    "/admin/operations": 200,
    "/agent": {
      "http_status": 404,
      "not_found_content": true
    },
    "/admin/collector": {
      "http_status": 404,
      "not_found_content": true
    },
    "/opportunity/does-not-exist": {
      "http_status": 200,
      "not_found_content": true
    }
  },
  "worker": "healthy; due reminder exactly once",
  "backup_restore_table_counts": {
    "agent_actions": 0,
    "alembic_version": 1,
    "audit_events": 0,
    "collection_runs": 0,
    "collection_sources": 0,
    "document_chunks": 0,
    "eligibility_rules": 2,
    "knowledge_access": 0,
    "knowledge_publications": 0,
    "message_reports": 0,
    "notifications": 1,
    "opportunities": 6,
    "profiles": 1,
    "reminders": 1,
    "review_items": 2,
    "room_messages": 0,
    "room_reads": 0,
    "rooms": 0,
    "social_blocks": 0,
    "social_quotas": 0,
    "source_documents": 0,
    "source_extractions": 0,
    "source_heads": 0,
    "task_alerts": 0,
    "team_invitations": 0,
    "team_tasks": 0,
    "teams": 0,
    "tracker_items": 0,
    "worker_heartbeats": 1
  },
  "browser_e2e": "not covered by HTTP smoke"
}
```

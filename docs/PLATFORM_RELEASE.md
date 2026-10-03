# 主体平台部署与发布门禁

本文件优先于历史 Agent/采集部署说明。当前版本不能标记为正式发布或已验收 RC，直到下述剩余测试真实完成。

## 配置

| 变量 | 用途 | 主体平台设置 |
| --- | --- | --- |
| DATABASE_URL | API/Worker 共用数据库 | 本地 SQLite，目标生产 PostgreSQL |
| DEMO_MODE | 演示身份与虚构数据 | 本地演示 true；公开部署 false |
| ADMIN_USER_IDS | 管理员身份 ID，逗号分隔 | 必须对应身份服务的真实用户 ID |
| SUPABASE_URL / SUPABASE_ANON_KEY | API 与 Web 身份校验 | 生产必填；密钥不进源码 |
| API_INTERNAL_URL | Web 到 API 内网地址 | 本地 http://127.0.0.1:8000；Compose http://api:8000 |
| APP_ORIGIN | 同源写请求校验 | 生产 HTTPS origin，无路径/末尾斜杠 |
| CAMPUSMATE_DOMAIN | Caddy 域名 | 与 APP_ORIGIN 一致 |
| POSTGRES_PASSWORD | Compose 数据库密码 | 至少 24 位 URL-safe 随机字符 |
| COLLECTOR_ENABLED | Worker 调度采集 | false |
| ENABLE_COLLECTOR_UI | 自动采集前台 | false |
| ENABLE_AGENT_UI | Agent 前台 | false |
| DIFY_API_BASE / DIFY_APP_KEY | 历史 Agent 服务 | 主体平台无需配置 |
| PORT / WEB_HOST | standalone Web 监听 | 默认 3000 / 127.0.0.1 |

根目录 .env 用于后端和 Compose。手工运行 Web 时需将相关变量导出到进程环境，或写入 frontend/.env.local（不要提交密钥）。

## 手工冷启动

先安装 README 所列依赖，在根目录设置环境。以下三个服务使用相同 DATABASE_URL，并分别在终端运行：

```bash
backend/.venv/bin/alembic -c backend/alembic.ini upgrade head
backend/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
backend/.venv/bin/python -m app.worker
```

```bash
cd frontend
npm run build
npm start
```

API 启动时不会自动建表，必须先迁移。DEMO_MODE=true 时自动放入六类虚构机会；正式环境必须通过人工内容导入和审核建立供给。

## Compose 目标部署

配置根目录 .env 后，先运行 `backend/.venv/bin/python scripts/preflight.py`。主体版本不要求 Dify；该检查只验证配置，不证明可上线。

```bash
docker compose -f docker-compose.yml -f docker-compose.production.yml up --build -d
```

现有 Compose 分离 PostgreSQL、迁移、API、Worker、Web 和 Caddy。当前执行环境没有 Docker 服务，因此此命令尚未实测通过，不能以文件存在代替部署验收。

## 数据库升级与恢复

当前没有 schema 变化，仍为 Alembic 0012。旧库先备份，再 `alembic upgrade head` 与 `alembic check`。回归测试覆盖 0001→head、0010→head、历史行保留与回退后重升。

```bash
backend/.venv/bin/python scripts/backup.py backup backup.sqlite
# 切换 DATABASE_URL 到不存在的新 SQLite 文件，或已验证为空的 PostgreSQL 目标库
backend/.venv/bin/python scripts/backup.py restore backup.sqlite
```

SQLite 已实测。PostgreSQL 还需目标库运行权限、迁移和 pg_dump/pg_restore 演练；脚本存在不算通过。恢复前停止写入，验证各表行数并抽样业务数据，不覆盖现有库。

## 未关闭的发布门禁

1. 在支持 Chromium 的运行环境执行全部 22 项 Playwright，覆盖桌面和 Pixel 7；修复全部失败，留存截图/trace。当前启动 SIGTRAP，不是功能通过。
2. 配置真实 Supabase 项目与邮件服务，用至少两名用户及管理员验证注册确认、登录、续期、退出、找回密码。现有 15 项协议测试使用受控响应。
3. 对目标 PostgreSQL 执行冷迁移、历史升级、备份恢复与多用户业务回归。
4. 在实际部署主机运行容器、HTTPS、请求同源校验、API/Worker 健康检查和重启恢复。
5. 由实际运营方核对真实公开内容、管理员账号、服务条款/隐私文本和域名资质；本项目不虚构这些资料。

完成后将真实结果写入 TEST_RESULTS 与 RELEASE，再确定 RC/正式版本。未通过项不得改写为已验收。

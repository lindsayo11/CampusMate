# 部署与验收

当前源码可本地运行和构建，尚未通过正式上线门槛。真实 Supabase、Dify、PostgreSQL、官方数据、域名和生产主机不在当前验收范围内。

## 本地验证

Python 3.12、Node 22+（验证环境 24.19.0）。从项目根目录执行：

```bash
python -m venv backend/.venv
backend/.venv/bin/pip install -c backend/requirements-tested.txt -e './backend[dev]'
cd frontend
npm ci
npm test
npm run typecheck
npm run build
cd ..
bash scripts/check.sh
```

浏览器验收使用隔离的 SQLite 数据库，自动启动并清理 API 和 Web：

```bash
cd frontend
npx playwright install --with-deps chromium
cd ..
backend/.venv/bin/python scripts/e2e.py
```

若云环境不允许系统安装，使用已安装的独立 Chromium，并通过 CHROMIUM_PATH 指向可执行文件。测试脚本会创建演示用户/数据，不可指向生产 API。目前 20 个浏览器场景均使用 DEMO_MODE=true 与 rules 模式，不验证真实登录或 Dify。

## 正式环境配置

复制 .env.example 为 .env，填写真实配置。要求 DEMO_MODE=false；APP_ORIGIN=https://完整域名，无结尾斜杠；CAMPUSMATE_DOMAIN 只写域名。POSTGRES_PASSWORD 至少 24 位 URL 安全随机字符。管理员 ID 必须为真实 Supabase 用户 ID，不是 demo-user。

Supabase 开启邮箱确认，配置 Site URL 和 SMTP；先验证注册邮件、登录、到期续期和退出。Auth 只有 anon key，业务数据库凭证仅给 API/Worker，不给浏览器。若将业务表放入 Supabase，请使用不对 Data API 暴露的专用 schema，或在真实项目部署并验证最小授权/RLS；当前迁移不安装 RLS 策略，不能默认认为 Supabase 公共 schema 已安全。

Dify 的 API_BASE 与 APP_KEY 按 dify/README.md 配置；使用实际模型对六个工具做正反例回归。原文与官方数据按 docs/CONTENT_INTAKE.md 归档导入并人工审核。

```bash
backend/.venv/bin/python scripts/preflight.py
# 检查通过只表示配置齐备，不表示外部服务已验收。
docker compose -f docker-compose.yml -f docker-compose.production.yml up --build -d
```

Caddy 自动申请域名 TLS 证书，需要 DNS 已指向主机并开放 80/443。API/Web 原有端口仅绑定回环，公开访问统一经 Caddy。生产 Compose/证书签发未在本次环境执行。

API /health/live 检查进程；/health/ready 检查 DB 和迁移版本。管理员 /admin/operations 查看 Worker 心跳及待发提醒。成功心跳 120 秒内为健康。日志输出请求 ID、路由模板、状态码、耗时，不记录令牌、正文或个人画像。

## 数据库升级

先停止写入并备份，再运行 alembic upgrade head。从早期版本升级会追加 0008–0012 等缺失迁移。不得修改旧 migration 或对未知生产库盲目 stamp。新增迁移降级会删除对应新功能数据；生产不执行无备份降级。

## 备份与恢复

需要已导出的 DATABASE_URL；脚本不自动加载 .env。备份目录应放在独立持久卷并由运维加密、设置保留周期，不能打入源码包。

```bash
backend/.venv/bin/python scripts/backup.py backup /secure-backups/campusmate.backup
# 先把 DATABASE_URL 指向一个新的恢复目标，绝不能仍指向在线生产库。
backend/.venv/bin/python scripts/backup.py restore /secure-backups/campusmate.backup
```

SQLite 使用在线 backup API、integrity_check，目标存在则拒绝覆盖。PostgreSQL 需要匹配服务器主版本的 pg_dump、pg_restore、psql；使用 custom 格式并检查目录，恢复只允许 public schema 无表的新库，使用单一事务。脚本目前仅支持 public schema 的 PostgreSQL 恢复目标，不适用于 Supabase 管理的完整实例恢复。真实托管库优先使用服务商的备份/PITR，并在隔离项目演练。

已验证 SQLite 29 张表备份恢复，所有行一致，包含采集、原文切片、任务提醒等记录；这不等于 PostgreSQL 生产恢复验证。PostgreSQL 命令未执行，不等同于生产灾备完成。

## 发布前仍需完成

- 真实 Supabase 注册、邮件、续期、退出和跨账号授权验收；密码找回协议已实现（配置见 PASSWORD_RECOVERY.md），注销仍需补齐。
- 真实 Dify 工作流、模型与六工具回归；当前仅适配协议测试和规则降级。
- 指定首发学校及 3–10 个官方来源，完成获准来源的采集适配、失败重跑与真实数据验收。
- PostgreSQL 并发、最小授权/RLS、备份恢复和 Compose 实测。
- Supabase Realtime、真实官网 adapter、语义 RAG 等能力尚未实现。
- 目标网络、域名、隐私条款和内容运营负责人确认后，才能进行正式上架验收。


## 受限云执行器
已实际运行后端、身份协议、生产构建和迁移测试。
无 /tmp 时设置 TMPDIR 为已创建的工作区目录；无 /proc/self 导致 Node memoryUsage ENOENT 时，可仅在此环境设置 NODE_OPTIONS=--require=/绝对路径/scripts/restricted-node.cjs。兼容脚本报告峰值 RSS/V8 堆信息，不能用于精确内存性能评估。
Chromium 当前执行器启动 SIGTRAP，即使提供独立二进制和标准无沙箱参数仍失败；这不是浏览器测试通过。普通 Linux/CI 使用标准 Chromium 运行全部浏览器用例，不要依赖该兼容配置进行上线验收。

## 当前新增功能
采集的 COLLECTOR_ALLOWED_HOSTS 同时配置 API/Worker，默认空值禁止自动抓取；见 COLLECTION.md。原文公开检索必须单独授权，见 KNOWLEDGE.md。队伍任务通知由同一 Worker 运行，见 TASK_ALERTS.md。


采集专用部署、OCR、同步与告警的开发记录见 [采集运维历史](COLLECTION_OPERATIONS_HISTORY.md)，当前整合状态见 [数据接入进度](DATA_COLLECTION_PROGRESS.md)。

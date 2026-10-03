# CampusMate 校伴

把分散在各高校、政府与公共服务网站上的升学、就业、创业信息，整理成**可核查、可执行**的个人发展计划。

每条信息都带原文出处、归档版本和证据摘录，可以追溯到官方页面；学生据此核对资格、加入个人计划、设置截止提醒。管理员侧提供从来源登记、校准、采集到审核发布的一条完整链路。

> 本项目提供本地演示与继续开发用途。**尚未完成公网生产验收**，真实 Supabase 登录、生产 PostgreSQL、Dify 模型和公网部署均未在验收范围内，详见 [待验收清单](#待验收清单)。

---

## 功能

### 发展信息中心

- 按发展路径（升学 / 就业 / 创业等）与地区、年份、类型、有效期筛选条目
- 每条信息展示来源机构、发布时间、截止时间、原文版本与证据摘录
- 覆盖度页面 `/data/coverage` 展示各来源的实际收录范围，不夸大覆盖率
- 时间线视图 `/data/timeline` 按时间轴查看信息变化

### 资格核对与原文溯源

- 规则化资格判断：学历、年级、专业、地区等条件逐条给出依据
- 判断结论必须挂接原文证据；信息不足时明确显示"未收录"，不猜测、不编造
- 原文检索 `/knowledge`，支持关键词检索已公开的原文片段并返回引用

### 个人计划与提醒

- 把信息加入个人计划，拆解准备事项清单，逐项完成
- 截止时间提醒，站内通知分页与已读管理
- 信息更新或来源变化时提示重新核对，而不是静默替换

### 发展规划助手（Agent）

- 对话式查询机会、核对资格、更新计划、设置提醒、生成材料建议
- **写操作先预览后确认**：Agent 只生成待确认动作，用户点确认才落库，重复确认复用第一次结果
- 服务端重新校验工具与参数，不接受模型给出的用户身份，不展示模型编造的自然语言结论
- 未配置模型时降级为规则检索模式，功能可用，不依赖任何模型密钥

### 团队协作

- 按互补技能匹配队友、发起与处理组队邀请
- 队伍任务分工、进度看板、任务到期提醒
- 房间与私信，含内容举报与拉黑

### 创业工作台 `/startup`

五个工作区、十个创业环节、14 类可编辑文稿，另有财务与股权测算：

| 工作区 | 内容 |
|---|---|
| 项目概况 | 名称、阶段、法域、客户市场、团队、真实运营与证据记录 |
| 商业设计 | 客户/痛点/解决方案、九要素画布、竞争位置、商业架构、MVP 验证计划 |
| 财务与股权 | 单位经济、盈亏平衡、资金期限、五年情景、期权池与稀释测算 |
| 文稿中心 | BP、用户协议、隐私告知、股权与治理等 14 类文稿，支持生成、编辑、版本保存与 Markdown 导出 |
| 创业流程 | 十环节卡片、待办提示、自评勾选 |

测算口径固定且透明（同币种、不换汇）；系统只做确定性计算，**不编造市场规模、收入、客户或履历**。所有文稿都是可编辑讨论草稿，不构成法律或投资意见。细节见 [创业工作台说明](docs/STARTUP_WORKSPACE.md)。

### 管理后台

| 入口 | 用途 |
|---|---|
| `/admin/sources` | 来源与端点登记、原文与结构化数据导入 |
| `/admin/registry` | 来源注册表、候选来源管理与端点校准门禁（robots、条款、许可证据 + 页面 SHA256） |
| `/admin/collector` | 采集任务、附件解析、来源白名单 |
| `/admin/data` | 公开信息发布、修订与下线 |
| `/admin/review` · `/admin/source-changes` | 内容审核队列与来源变化审核 |
| `/admin/notice-watch` | 高校栏目持续监测：暂停／恢复来源、排队重查 |
| `/admin/intake-document` · `/admin/source-candidates` | 导入文档与候选来源处理 |
| `/admin/operations` · `/admin/reports` · `/admin/audit` | 运行状态、报表与操作审计 |

治理约束是硬性的：采集只访问 HTTPS 白名单主机，逐跳复核重定向，检查 robots.txt，不执行网页 JavaScript；发布需要独立审核，单人环境无法绕过。采集失败不会伪装成成功。

### 账号与安全

- 支持 Supabase 邮箱注册 / 登录 / 密码找回（可选）
- 本地演示模式使用 `x-user-id` 模拟身份，**严禁用于公开部署**
- 个人画像、计划、会话、文稿按账号隔离；密钥只从服务端环境变量读取

---

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.12 · FastAPI · SQLAlchemy 2 · Alembic · Pydantic Settings |
| 数据库 | SQLite（默认，本地演示）· PostgreSQL 16（Docker / 生产） |
| 前端 | Next.js 16（App Router）· React 19 · TypeScript 5.7，无 UI 框架依赖 |
| 鉴权 | Supabase Auth（可选）· 演示模式本地身份 |
| 助手 | Dify Workflow（可选）· 默认规则检索 |
| 采集 | httpx · BeautifulSoup · pypdf · openpyxl，自带 robots 与白名单治理 |
| 测试 | pytest · node:test · Playwright |
| CI | GitHub Actions（后端测试 + 前端测试 + 浏览器 e2e） |

---

## 快速开始

前置：**Python 3.12+**、**Node.js 22+**。首次需要联网安装依赖并构建前端（仓库不含 `node_modules` 和虚拟环境）。

### macOS / Linux

```bash
git clone https://github.com/lindsayo11/CampusMate.git
cd CampusMate

python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -c backend/requirements-tested.txt -e './backend[dev]'

cd frontend && npm ci && npm run build && cd ..

backend/.venv/bin/python scripts/start_local.py
```

打开 <http://127.0.0.1:3000>。`Ctrl+C` 同时停止 API、Web、Worker 三个服务。

### Windows

```powershell
py -3.12 -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -c backend/requirements-tested.txt -e './backend[dev]'

cd frontend
npm ci
npm run build
cd ..

backend/.venv/Scripts/python.exe scripts/start_local.py
```

装好依赖并构建后，也可以直接双击 `start-windows.cmd`。

### 启动器做了什么

`scripts/start_local.py` 是本地演示启动器，它会：

1. 把公开数据快照 `demo-data/release-preview.db` 复制成 **工作副本** `local-data/demo.db`（原始快照永不被修改）
2. 为本地演示生成 `.env` / `backend/.env` / `frontend/.env.local`（已存在的文件默认保留，`--force` 才覆盖）
3. 升级数据库迁移，然后启动 API、Web、Worker

常用参数：

```bash
# 只浏览已收录内容，不请求任何外部网站
scripts/start_local.py --collector-off

# 端口冲突时指定两个不同端口
scripts/start_local.py --api-port 8001 --web-port 3001
```

启动器**不是生产入口**。要接入自己的数据库或模型，请按 [.env.example](.env.example) 单独配置并分别启动服务。

---

## 配置

复制 [.env.example](.env.example) 为 `.env` 并按需填写。全部字段都有注释，几个关键项：

| 变量 | 说明 |
|---|---|
| `DATABASE_URL` | 默认 SQLite；生产用 `postgresql+psycopg://…` |
| `DEMO_MODE` | `true` 时启用演示身份与种子数据，**只能用于隔离的本地环境** |
| `ADMIN_USER_IDS` | 管理员用户 ID，逗号分隔；演示模式用 `demo-user` |
| `SUPABASE_URL` / `SUPABASE_ANON_KEY` | 启用真实登录时填写；留空则走演示身份 |
| `DIFY_API_BASE` / `DIFY_APP_KEY` | 启用模型辅助时填写；留空则用规则检索 |
| `COLLECTOR_ALLOWED_HOSTS` | 采集白名单，留空表示禁止一切自动联网采集 |
| `PUBLIC_NOTICE_WATCH_ENABLED` | 是否开启高校栏目持续监测，默认关闭 |

`scripts/doctor.py` 会检查配置是否完整，只输出是否已配置，不打印密钥内容。

---

## 项目结构

```
CampusMate/
├── backend/                FastAPI 服务
│   ├── app/                业务模块（信息目录、采集、审核、Agent、创业等）
│   │   └── adapters/       各来源的解析适配器
│   ├── migrations/         Alembic 迁移
│   └── tests/              pytest 测试与固定样本
├── frontend/               Next.js 应用
│   ├── app/                路由与页面
│   ├── components/         组件
│   ├── lib/                接口与会话封装
│   ├── tests/              单元测试
│   └── e2e/                Playwright 浏览器测试
├── specs/                  接口契约与 JSON Schema
├── scripts/                本地启动、采集探测、验收与备份脚本
├── dify/                   Dify 工作流接入说明与提示词
├── demo-data/              公开数据快照（合成 / 已脱敏）
├── docs/                   功能与运维文档
├── infra/ · supabase/      Caddy 与邮件模板
└── docker-compose.yml      本地 PostgreSQL 编排
```

---

## 测试

```bash
# 后端测试 + 前端测试 + 类型检查 + 生产构建
bash scripts/check.sh
```

分项执行：

```bash
# 后端（需先迁移到 head）
cd backend && .venv/bin/python -m pytest tests -q

# 前端单元测试与类型检查
cd frontend && npm test && npm run typecheck

# 浏览器端到端测试（需先 npm run build 并安装 Chromium）
npx playwright install --with-deps chromium
cd .. && backend/.venv/bin/python scripts/e2e.py
```

CI 在每次 push 和 PR 时运行以上全部内容，见 [.github/workflows/ci.yml](.github/workflows/ci.yml)。

---

## 部署

Docker Compose 编排（PostgreSQL + API + Worker + Web）：

```bash
cp .env.example .env      # 填写 POSTGRES_PASSWORD、APP_ORIGIN、ADMIN_USER_IDS 等
docker compose up --build
```

生产注意事项、反向代理与 TLS、发布门禁见：

- [部署与验收](docs/DEPLOYMENT.md)
- [主体平台发布门禁](docs/PLATFORM_RELEASE.md)

---

## 文档

| 文档 | 内容 |
|---|---|
| [创业工作台](docs/STARTUP_WORKSPACE.md) | 五个工作区、14 类文稿、测算口径、Agent 接入 |
| [发展助手接入](dify/DEVELOPMENT_ASSISTANT.md) | Dify Workflow 契约与提示词 |
| [数据源接入](docs/DATA_SOURCE_INTAKE.md) | 来源登记、适配器与调度 |
| [内容采集与附件解析](docs/COLLECTION.md) | 采集治理、robots、白名单与解析边界 |
| [内容导入](docs/CONTENT_INTAKE.md) | 手动导入原文与结构化数据 |
| [原文依据检索](docs/KNOWLEDGE.md) | 检索接口与引用规则 |
| [任务到期通知](docs/TASK_ALERTS.md) | 提醒生成与投递规则 |
| [密码找回](docs/PASSWORD_RECOVERY.md) | Supabase 邮件找回的部署与验收 |
| [环境补充](ENVIRONMENT.md) | 运行环境、代理与常见问题 |

---

## 演示数据

`demo-data/release-preview.db` 是**系统导入的公开内容快照**：公开事项、原文归档、证据、版本与发布记录，以及来源配置。个人相关表（画像、计划、会话、稿件、通知、审计等）在导出时已清空。

用 `scripts/export_demo_data.py` 可以从你自己的数据库导出同样口径的公开快照：

```bash
backend/.venv/bin/python scripts/export_demo_data.py your.db --output demo-data/release-preview.db
```

脚本会硬性检查：存在非公开文档、或个人数据未清空时**直接报错退出**，不会生成不干净的快照。

`demo-data/` 里的数据全部是公开信息或合成数据，**不是真实用户数据**。演示身份（`demo-user`、`第 1–5 号模拟学生`）均为虚构，请勿当作真实账号或真实招生数据使用。

---

## 待验收清单

以下项目尚未完成真实环境验收，不应视为已就绪：

- 真实 Supabase 登录 / 邮件收发
- 生产 PostgreSQL 上的迁移与并发写入
- 真实 Dify 模型工作流
- 原生 Windows 端到端实测
- Docker + TLS 公网部署

本地 SQLite 测试与协议 mock **不能替代**以上外部服务的真实验收。

---

## 贡献

欢迎提交 Issue 和 Pull Request，请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 开源协议

[MIT](LICENSE)

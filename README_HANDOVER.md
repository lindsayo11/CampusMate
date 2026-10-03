# CampusMate 本版交接说明

版本：Stage34 · `v0.34.0-notice-watch.1`，打包日期：2026-10-01。数据库迁移到 `0027`。
这是可以继续开发、可以本地演示的完整源码包。**尚未完成公网生产上线验收。**

## 相比最初交来的原型，新增了什么

原型已经有学生／管理员工作空间、发展路径、个人计划、对话助手、数据接入与审核框架。本轮是在这些功能上继续完善，不把原型已有能力计作新增。

| 本轮改动 | 用户能看到的变化 | 主要代码 |
|---|---|---|
| UI 与使用流程优化 | 首页显示实际信息；信息行、筛选、详情、空状态更清晰；手机导航与页面布局改进 | `frontend/app/page.tsx`、`app/globals.css`、`components/app-shell.tsx`、`information-row.tsx` |
| 高校通知检索 | 按学校、年份、路径、类型、有效期筛选；按发布时间或截止时间排序；查看来源、版本、原文与证据 | `frontend/app/data/`、`backend/app/data_catalog.py` |
| 计划准备清单 | 在已有个人计划里添加、完成、删除准备事项，按本人权限保存 | `components/plan-preparation.tsx`、`backend/app/plan_steps.py` |
| 信息纠错闭环 | 用户提交针对某个版本的纠错；本人与管理员可查；管理员处理并留痕 | `components/data-correction.tsx`、`backend/app/data_feedback.py` |
| 官方栏目持续采集 | 自动从栏目发现新通知，抓取正文和 PDF，去重、归档、保留变化版本、失败重试、重启续跑 | `backend/app/notice_watch.py`、`app/adapters/notice_text.py`、`scripts/refresh_postgraduate.py` |
| 来源覆盖与运维界面 | `/data/coverage` 看实际收录范围；`/admin/notice-watch` 暂停／恢复来源及排队重查栏目 | `frontend/app/data/coverage/`、`app/admin/notice-watch/` |
| 交接可复现 | 清理个人记录的公开快照、跨平台本地启动脚本、源码差异与文件校验清单 | `demo-data/release-preview.db`、`scripts/start_handover.py`、`handover/` |

新增数据库迁移：`0025_plan_steps.py`、`0026_data_corrections.py`、`0027_notice_frontier.py`。
通知采集沿用原始归档、发布、知识检索和变化审核链路，修复重复入库、公开访问状态与日期解析等衔接问题。

## 包里有什么数据

默认演示数据为 `demo-data/release-preview.db`，包含 **94 条公开事项、95 个原文归档版本**。这两个计数含此前已接入内容，不全是本轮新增高校通知。快照保留来源配置、采集队列、原文 HTML／PDF、证据、版本与发布记录。

本轮持续采集配置是 **8 个高校来源、13 个官方栏目**。本地验收时 **6 个来源栏目正常**，发现 59 个正文／附件链接，成功解析 42 个资源；“资源”不等同于独立通知。覆盖北京大学、清华大学、复旦大学、上海交通大学、西安交通大学、电子科技大学，以及待修复的中科大和浙大材料学院来源。浙大目前仅是材料学院，不能称为覆盖全校。

当前两处明确阻塞：中科大 robots 检查遭遇网络／重定向问题；浙大材料学院栏目未发现可解析通知。部分扫描 PDF、正文结构及未知日期仍需处理。失败不会伪装成采集成功。

快照已清除对话、个人画像、个人计划、订阅、纠错、协作消息、私人通知及运行审计等记录；环境文件、密钥、依赖目录、个人运行数据库和调试日志不在包内。导出检查见 `handover/data-package-report.json`。

原型附带的 `demo-data/retained-demo.db` 仅为旧版虚构的五人测试数据，保留供历史测试；**本版默认启动不使用它**。生产请另建数据库。请勿将演示身份和历史虚构机会当成真实用户或真实招生数据。

## 首次启动：macOS / Linux

建议 Python 3.12 或 3.13、Node.js 22+。此前功能验证使用 Python 3.13；本次解压后全新安装、启动验证使用 Python 3.14.3、Node.js 25.8.1。在解压后的 `CampusMate` 根目录执行：

```bash
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -c backend/requirements-tested.txt -e './backend[dev]'
cd frontend
npm ci
npm run build
cd ..
backend/.venv/bin/python scripts/start_handover.py
```

打开 `http://127.0.0.1:3000`。启动器运行数据库迁移，启动 API、Web、Worker。`Ctrl+C` 停止三个服务。首次需要联网安装依赖及构建，不包含 node_modules 或 Python 虚拟环境。

只查看已采集内容、暂不请求高校网站：

```bash
backend/.venv/bin/python scripts/start_handover.py --collector-off
```

端口冲突时指定两个不同端口，例如 `--api-port 8001 --web-port 3001`。

## 首次启动：Windows

在项目根目录的 PowerShell 中：

```powershell
py -3.12 -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -c backend/requirements-tested.txt -e './backend[dev]'
cd frontend
npm ci
npm run build
cd ..
backend/.venv/Scripts/python.exe scripts/start_handover.py
```

也可在装好依赖、构建好前端后运行 `start-windows.cmd`；已经去掉原型里写死的 conda 和 Node 安装路径。Windows 启动路径已适配，但没有在真实 Windows 机器实测，需要队友验证。

## 配置与持续更新

启动器为**本地演示**创建 `.env`、`backend/.env`、`frontend/.env.local`；已有文件默认保留，启动器本身仍使用本地演示参数。`setup-env.py --force` 才会覆盖环境文件，请仅在确认要重置本地配置时使用。启动器不是生产入口。

首次将公开快照复制到 `local-data/teammate.db`；以后复用此文件，原始快照不变，自己的计划和后续采集数据都在工作副本里。运行目录可以包含空格。

采集入口清单为 `backend/app/postgraduate_sources.json`，配置的是**栏目 URL**。新增来源须同时登记来源／端点、更新栏目清单、设置允许的官方主机；不要手工逐条填通知 URL 作为持续采集方案。

独立运行后端或新建数据库时，先复制并修改 `.env.example`。本版的新采集开关是 `PUBLIC_NOTICE_WATCH_ENABLED=true`，`COLLECTOR_ALLOWED_HOSTS` 须包含清单内主机。原规则采集器仍用 `COLLECTOR_ENABLED`，两者独立；本地启动器默认关闭旧采集器。然后在 `backend` 中：

```bash
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m app.source_registry
.venv/bin/python ../scripts/refresh_postgraduate.py --install --actor local-operator
.venv/bin/python -m app.worker
```

Windows 将 `.venv/bin/python` 换为 `.venv/Scripts/python.exe`。全量初始化与生产操作参考原 `docs/PLATFORM_RELEASE.md`，以上只说明新栏目监测的登记与启动。

栏目通常每 12 小时检查，正文／PDF 每 24 小时复查。使用 ETag／Last-Modified 和内容哈希去重；任务与重试时间持久化；失败退避，扫描 PDF 保留待处理状态。栏目返回 304 时，正文仍独立复查。服务暂停或退出期间不会更新；本机运行不能保证全天候采集。

采集只访问已允许的官方 HTTPS 主机，验证 robots 与网络目标，限制体积与请求频率；不执行网页 JavaScript、不自动扩展到登录系统或其他域名。公开通知不等于人工核验过的资格规则。

## 接手时先看哪里

- 页面：`/`、`/data`、`/data/coverage`、`/tracker`、`/admin/data`、`/admin/notice-watch`。
- 后端：`backend/app/notice_watch.py`、`adapters/notice_text.py`、`data_catalog.py`、`plan_steps.py`、`data_feedback.py`。
- 原型对比：`handover/changes-from-original.json`；原始文件 SHA 与本版 SHA 可逐项核对。
- 数据状态：`handover/source-status-at-release.json`、`handover/data-package-report.json`。
- 验证与打包：`handover/verification.json`、`handover/file-manifest.json`。
- 页面示例：`artifacts/stage34/notice-watch-coverage.png`。

## 已验证与上线差距

此前实现阶段：167 项后端测试、19 项前端测试通过；Next 类型检查和构建通过；API＋Web＋Worker 冷启动与页面 HTTP 检查通过；手机窄屏、来源暂停／恢复／重查交互检查通过；非空 SQLite 数据库备份恢复后 64 张表内容一致。本次交接包另做公开数据清理、ZIP 完整性及解压后的启动检查，具体结果以 `handover/verification.json` 为准。

**还没有完成**真实 Supabase 登录／邮件、生产 PostgreSQL、真实 Windows、Docker／TLS 公网部署验证；这些不能用本地演示测试代替。默认 `DEMO_MODE=true` 只适合本地预览。

建议队友按以下顺序接手：

1. **数据接入**：修复中科大、浙大入口与扫描 PDF；扩展更多学校／院系；明确专业、年份、截止时间和覆盖率的验收标准。
2. **部署与身份**：正式数据库、真实登录、最小权限、持续运行 Worker、域名 HTTPS、环境密钥和进程健康告警。
3. **运维与质量**：定期备份及恢复演练、异常来源告警、解析失败人工处理、数据下线与纠错流程。
4. **产品验收**：真实学生完成“找通知→查原文→加计划→准备清单→提醒”的完整流程；补齐空栏目内容与移动端细节。

旧阶段文档在 `docs/` 中保留作历史参考。本页是本版交接入口；旧文档的版本号、手工放行数量、数据库路径或“无需配置”的结论不代表当前状态。

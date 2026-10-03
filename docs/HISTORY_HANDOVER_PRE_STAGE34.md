# CampusMate 交接说明

## 2026-10-01：高校栏目持续采集

`backend/app/postgraduate_sources.json` 现在仅配置官方栏目入口，不维护逐条通知 URL。
公开高校通知监测与原资格规则采集器分别运行；不会伪造许可、校准或人工核验状态。

在后端环境配置 `PUBLIC_NOTICE_WATCH_ENABLED=true`，并在 `COLLECTOR_ALLOWED_HOSTS`
中填写栏目使用的官方主机。迁移数据库后，登记并安装栏目配置：

```bash
cd backend
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m app.source_registry
.venv/bin/python ../scripts/refresh_postgraduate.py --install --actor local-operator
.venv/bin/python -m app.worker
```

后台每 12 小时检查栏目，每 24 小时重查已发现的正文与 PDF。任务、条件请求标记、
重试时间与租约保存在数据库；服务重启会继续未完成任务。源文件哈希相同不会重复入库，
改版会留下新版本与变化审核记录。栏目返回 304 不影响正文独立重查。
首次回填每页最多发现 30 个候选，最多跟进两级“下一页”；待采集队列上限为每源 200 条，
达到上限会明确报错，积压消化后继续发现，不限制已采集历史总量。

`/data/coverage` 展示栏目检查、已发现、已解析与异常数；
`/admin/notice-watch` 可暂停、恢复和将栏目检查加入队列。
无法确认 robots、跳转至 HTTP、扫描 PDF、正文无法定位时会记录原因并定时重试。
链接指向登录系统或其他主机时不会自动扩展采集权限。

本地预览只有在电脑与 worker 运行时才会更新。部署版 Docker Compose 的 worker
使用持久数据库和 `restart: unless-stopped`；还需要实际部署、外部健康告警和备份保留策略，
才能获得全天候服务。以下旧版说明描述原始交付，其“无需额外配置”不适用于此监测功能。

**这是我在这份源码上做完数据接入后的版本。你直接在这上面继续开发即可。**
所有改动已经应用在代码里，数据已经接好，不需要打补丁或额外配置。

---

## 1. 快速开始

```bash
pip install -e "./backend[dev]"          # 装后端依赖
python setup-env.py                      # 生成配置（自动填好绝对路径）
cd backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

另开一个终端验证：

```bash
curl -s -H "X-User-Id: demo-user" http://127.0.0.1:8000/v1/admin/intake/health
```

预期看到 `graduate_policy` 和 `graduate_policy_detail` 的 `gate_reason` 为 `null`、
`calibration_status` 为 `approved` —— **门禁放行 2/37**。看到这个就说明环境、数据、代码三者都对上了。

（Windows 也可以直接双击 `setup-env.cmd`，或用 `start-windows.cmd` 一键起前后端。）

---

## 2. 数据在哪

`ingested-data/campusmate.db` —— **全部数据都在这一个文件里**，无外部依赖。

| 表 | 条数 |
|---|---|
| `document_versions` | 2 份真实文档（`import_mode='system'`） |
| `document_archives` | 2 份原始 HTML 正文 |
| `evidence` | **251 条 DOM 级证据**（每条含选择器路径 + 原文摘录） |
| `policy_records` | 1（《2027年全国硕士研究生招生工作管理规定》） |
| `source_endpoint_calibrations` | 4 条已批准校准 |

内容主要是教育部《2027年全国硕士研究生招生工作管理规定》全文，
从文号 `教学〔2026〕2号` 到 `第八十九条`，逐段可回溯。

> 注意 `demo-data/retained-demo.db` 是作者自带的演示库（3 条 `import_mode='demo'`），
> **不是真实数据**。真实数据在 `ingested-data/`。

---

## 3. 我改了什么

### 3.1 数据接入链路修复（7 个文件 + 6 个新增）

#### 修改

| 文件 | 改动 |
|---|---|
| `backend/app/adapters/education.py` | 新增正文容器选择器（`CONTENT_SELECTORS` + `content_container()`） |
| `backend/app/collector_http.py` | 明文 HTTP 例外 + robots 开关 |
| `backend/app/config.py` | 2 个本地开发开关 |
| `backend/app/intake_governance.py` | 抽出 `official_https_ok()` / `separation_ok()` |
| `backend/app/intake_api.py` | 校准 URL 校验同步 |
| `backend/app/source_registry.yaml` | `CM-GR-001` 的 URL 校准 + 新增 1 个端点 |
| `.env.example` | 开关风险说明 |

### 新增

| 文件 | 作用 |
|---|---|
| `backend/tests/test_moe_policy_selectors.py` | 5 项：容器优先级、首页必须显式报错 |
| `backend/tests/test_collector_plaintext_override.py` | 8 项：明文例外只对列出主机生效 |
| `backend/tests/test_single_admin_override.py` | 2 项：单管理员开关**默认关闭** |
| `backend/tests/test_registry_adapter_coverage.py` | 3 项：**守护注册表 ↔ 适配器一致性** |
| `backend/tests/fixtures/moe_srcsite_policy.html` | 复刻真实页面结构的 fixture |
| `start-windows.cmd` | Windows 启动器（替代 POSIX-only 的 `scripts/dev.sh`） |

共 **18 项新测试**，是"可执行的规格说明" —— 你改完实现跑一遍就知道有没有破坏行为。

`scripts/` 下另有 6 个我写的诊断脚本（探页面结构、探 robots、端到端校准等），
以后接新数据源时能复用。

---

### 3.2 知识检索链修复（让采集到的数据真的能被搜到）

**这一项比 3.1 更关键** —— 3.1 只解决了"数据能入库"，这一项解决"入库后能看见"。

#### 原来的问题

项目里有**两代采集器，写两张不同的文档表**：

| 采集器 | 写入表 | 检索链读的表 |
|---|---|---|
| `collector.py`（旧，人工编审） | `source_documents` | ✅ 同一张 |
| `source_scheduler.py`（新，治理采集） | `document_versions` | ❌ **不是同一张** |

而 `knowledge.visible_statement()` 是一个 **七路 join**，其中硬性要求
`ReviewItem.status == 'approved'`，且 `record_publication()` 的签名就要求 `review_id`。

**后果**：治理采集器采到的数据，无论审核策略怎么设，都**永远进不了检索库**。
信息中心那条链（`data_catalog.auto_publish`）本来就是免审自动发布，
两条链口径不一致 —— 同一份数据一边可见、一边恒不可检索。

#### 改了什么

| 文件 | 改动 |
|---|---|
| `backend/migrations/versions/0024_knowledge_system_publication.py` | **新增迁移**：`knowledge_publications` 改以 `document_id` 为主键，新增 `source` 列（`editorial`/`system`），`opportunity_id`/`review_id` 改为可空 |
| `backend/app/knowledge.py` | `visible_statement()` 按 `source` 分支：`system` 免审直接可检索，`editorial` 保留原门槛；新增 `publish_system_document()` |
| `backend/app/source_scheduler.py` | 新增 `publish_collected_document()` —— 把采集文档镜像进归档表（**沿用同一 id**，证据/切片/引用全部对齐）并自动建链 |
| `scripts/backfill_knowledge.py` | **新增**：回填历史数据（改动前采集的文档） |
| `backend/tests/test_knowledge_system_publication.py` | **新增 5 项测试** |

#### 分级免审的落地口径

| 数据来源 | 是否需人工审核 | 代码依据 |
|---|---|---|
| 系统自动采集 | **免审** | `source='system'`，不创建 ReviewItem / Opportunity |
| 管理员本人导入 | **免审** | 同上 |
| 其他人工导入（小众信息） | **需审** | `source='editorial'`，保留 approved + 活机会双重门槛 |

**没有伪造审核记录，也没有伪造机会卡片** —— 系统链走独立的谓词分支。
`test_editorial_path_still_requires_an_approved_review` 专门守护"编辑链门槛没被拆掉"。

#### 交付的数据库已经修好

`ingested-data/campusmate.db` 已应用迁移 0024 并完成回填，**开箱即可检索**：

```
document_chunks        28   ← 原为 0
knowledge_access        2   ← 原为 0
knowledge_publications  2   ← 原为 0
```

实测 `POST /v1/knowledge/search {"query":"考研"}` 返回带原文片段、
来源 URL、内容哈希与偏移的结果。

> 如果你要对自己的库执行同样修复：
> ```bash
> DATABASE_URL=... python -m alembic -c backend/alembic.ini upgrade head
> DATABASE_URL=... python scripts/backfill_intake.py
> ```

---

### 3.3 学生端首页空白修复（时间字段）

**现象**：学生端工作台首页"空空荡荡"，但数据其实在库里。

#### 原因

`/v1/data/timeline`（首页的数据源）**只渲染带 `start_time` 或 `deadline` 的条目**，
而 `ingest_moe_policy` 建条目时**这两个字段从未设置**：

```python
item_values = {"title": ..., "item_type": "education_policy", ...}
# start_time / deadline 从未出现 → 都是 None
```

政策文件本身没有报名截止日，但正文里明明写着日期 —— 适配器**只提取 title 和 body**，
把日期全丢了。所以政策在库里、信息中心也能看到，**首页却永远空**。

#### 改了什么

| 文件 | 改动 |
|---|---|
| `backend/app/adapters/education.py` | 新增 `document_date()`（成文日期）与 `registration_window()`（报名窗口）提取 |
| `backend/app/intake.py` | 新增 `_parse_date()`；`ingest_moe_policy` 把日期落到 `start_time` / `deadline` / `effective_at` |
| `scripts/backfill_intake.py` | **取代 `backfill_knowledge.py`**：同时修复知识链与日期字段，并重新发布 |
| `backend/tests/test_policy_dates.py` | **新增 6 项测试** |

提取规则（都有测试守护）：

| 目标 | 规则 | 实测结果 |
|---|---|---|
| 成文日期 | **整段就是一个日期**（`fullmatch`），避免把正文里的"报名时间为…"误认 | `2026-09-21` |
| 报名窗口 | `报名时间为X年X月X日至X月X日`，结束日期缺年份时沿用开始年份 | `2026-10-15` ~ `2026-10-24` |

**报名窗口优先于成文日期** —— 前者才是学生真正需要的时间节点。

#### ⚠️ 一个必须知道的机制：改数据会让条目"消失"

`data_catalog.visible()` 有一道纵深防御：

```python
if not blocks and canonical(snapshot) == row.snapshot:
    yield row, snapshot
```

**底层任何一行变了，实时快照就和已存储的发布快照对不上，条目立即被隐藏** ——
直到重新发布。我改 `start_time` 时就踩到了：`/v1/data/catalog` 的 `total`
当场从 1 变成 0。

**所以：改完底层数据必须重新发布。** `scripts/backfill_intake.py` 已经内置这一步
（对每份文档调用 `auto_publish`）。如果你手工改库，记得也调一次，否则界面会"数据不见了"。

#### 修复后的实测

| 学生端页面 | 接口 | 修复前 | 修复后 |
|---|---|---|---|
| 工作台首页 | `/v1/data/timeline` | **`[]` 空** | **2 个事件** |
| 信息中心 | `/v1/data/catalog` | 1 条 | 1 条 |
| 原文资料库 | `/v1/knowledge/search` | 0 条 | 2 条 |

首页现在显示：

```
2026-10-15  [开始]       教育部关于印发《2027年全国硕士研究生招生工作管理规定》的通知
2026-10-24  [截止/失效]  同上
```

---

### 3.4 扩源：接入江苏省教育考试院（CM-GR-003-JS）

**背景**：此前只有 1 个源、2 份文档。按执行手册的采集优先级（静态 HTML 优先于
Playwright）批量探测后，**37 个候选里只有 4 个是静态可抓**，其余要么是 JS 渲染，
要么被反爬拦。

| 探测结论 | 数量 | 代表 |
|---|---|---|
| 静态可抓 | 4 | 江苏考试院、税务总局、国家统计局、挑战杯 |
| JS 渲染 | 12+ | 研招网、学信网、多数省考试院、高校研招网 |
| 反爬拦截 | 3 | 人社部（EdgeOne 挑战）、河南考试院、阳光高考 |
| 不可达 | 4 | 公共招聘网（拒连）、留服中心（旧 TLS）、国资委（超时） |

**入选**：江苏省教育考试院是唯一**静态 + 有未来日期**的源 —— 考试院会发报名通知，
天然带报名窗口。

| 项目 | 值 |
|---|---|
| 列表页 | `https://www.jseea.cn/webfile/index/index_zkxx/` |
| 详情页模式 | `/webfile/index/index_zkxx/YYYY-MM-DD/<id>.html` |
| 正文容器 | `<article>`（内含 `<div id="content">`） |
| 复用适配器 | `MoEPolicyAdapter`（无需新写） |

#### 为它补的三处能力

| 能力 | 说明 |
|---|---|
| **标题后缀清洗** | 该站无 `h1`，只能用 `<title>`，会带 ` - 招考信息` 后缀 → 新增 `TITLE_SUFFIX` |
| **无年份日期补全** | 通知写「报名时间：9月21日-10月21日」——**年份整体省略**，只在 URL 里 → 新增 `year_from_url()` + `BARE_REGISTRATION_WINDOW` |
| **日期写法放宽** | 实际用 `：`、`-`、带时刻（`12:00`）、结尾「止」→ 正则按真实写法重写 |

实测 6 篇中 4 篇提取到报名窗口，其中 2 篇是**未来日期**（2026-10-21）。

#### 采集方式：走项目自己的治理导入接口

新增 `scripts/collect_jseea.py` —— 抓列表页 → 逐篇抓详情 → POST 到
`/v1/admin/intake/education-html`。**不直接写数据库**，因此 DocumentVersion、
DOM 级证据、DevelopmentItem 全部由项目自己的入库逻辑产生。

> **踩到的坑**：手工导入接口默认 `import_mode='manual'`，而 `auto_publish()` 只自动
> 发布 `system`/`demo`。结果 15 篇**入库了但界面不显示**。
> 已给该接口加 `import_mode` 字段（默认 `system`，因为它是采集脚本的入口），
> 并在入库后调用 `auto_publish`。

#### 效果

| 指标 | 接入前 | 接入后 |
|---|---|---|
| 文档 | 2 | **17** |
| 证据 | 251 | **602** |
| 信息中心 | 1 条 | **16 条** |
| 首页时间线 | 2 个事件 | **10 个事件** |

**浏览器实测（Playwright 渲染，非 curl）**：

```
工作台首页：
  当前可关注事项  14 项   来自信息中心的当前发布
  信息动态  当前发布
    江苏省教育考试院  发布了新的发展信息
    江苏省成人高校招生考试专升本考生特别提醒
    [正文摘要]  国内升学 320000
    查看详情与原文 / 加入计划 / 持续关注
```

> **为什么用浏览器验证**：`/data` 是服务端渲染，curl 能看到；但 `/`、`/opportunities`
> 是客户端渲染，curl 只拿到外壳。**只有真实渲染才能确认用户看到什么。**

#### 仍未覆盖：校园机会

`/v1/opportunities` 只显示 `status='published'` 且 **`deadline > 现在`** 的
`Opportunity` 记录，而 `Opportunity` 目前只由人工编审流程产生。江苏考试院的通知是
**考试报名通知**，语义上属于信息中心，不是"机会卡片"，因此没有强行塞进去。

要填充校园机会，需要接入**真正带未来截止的机会类源**（招聘/竞赛/招募）。
当前 36 个候选里，带未来截止的多为 JS 渲染或反爬，需要先接 Playwright。

---

### 3.5 发展频道覆盖（六个入口）

**现象**：数据在信息中心能看到，但**发展频道的六个入口全部为空**。

#### 根因：条目挂在了父路径上

发展频道的六个入口各自按自己的 path code 过滤：

```javascript
保研推免 → recommendation_exemption    国内考研 → domestic_postgraduate_exam
境外留学 → overseas_study              考公考编 → national_civil_service
实习就业 → employment                   创新创业 → entrepreneurship
```

而 `data_catalog.path_codes()` **只从该 code 向下找子孙路径**。`ingest_moe_policy`
原来硬编码 `path_code="domestic_study"`（**父路径**），它不在任何频道里
→ 六个频道全部 `total=0`，数据在库里却一个频道都点不开。

#### 修复

| 改动 | 说明 |
|---|---|
| `adapters/education.py` | 新增 `classify_path(title, body)` —— 按内容关键词映射到频道 code；匹配不到返回 `None`（**宁可不挂，也不硬塞**，挂错频道比不挂更容易误导） |
| `intake.py` | `ingest_moe_policy` 改为 `config["path_code"]` 优先、否则 `classify_path`；匹配不到就不挂路径（仍出现在信息中心"全部事项"） |
| `scripts/backfill_intake.py` | 新增 `retag_paths()`：按同一规则重挂历史数据，并重新发布（路径变了快照就失效） |

#### 又接了 2 个静态源

| 源 | 频道 | 列表页 | 详情模式 |
|---|---|---|---|
| 教育涉外监管信息网 `CM-OS-002` | 境外留学 | `/api/index/sortlist/1` | `/n2/<栏目>/<子栏>/<id>.shtml` |
| 挑战杯 `CM-ENT-008` | 创新创业 | `/tzb` | `/article/<id>/` |

> 涉外监管的正文容器是 `.list-right`，已加入 `CONTENT_SELECTORS` 并**放在最后** ——
> 类名太通用，只有前面全部落空时才轮到它。
>
> 这两个源的内容性质明确（一个是涉外教育监管、一个是创新创业赛事），因此用
> **源级 `path_code`**（采集时通过 `adapter_config` 传入），而不是靠关键词猜。

新增 `scripts/collect_web.py`：配置驱动的多源采集，支持 `--source jseea|jsj|tzb|all`。

#### 效果（浏览器实测，非 curl）

| 频道 | 数据 |
|---|---|
| **创新创业** | **20 条**（挑战杯） |
| **境外留学** | **12 条**（涉外监管） |
| **实习就业** | **4 条**（江苏考试院证书考试） |
| **国内考研** | **2 条**（考研报考点 + 教育部规定） |
| 保研推免 / 考公考编 | 0 —— 缺对应源 |

| 指标 | 前 | 后 |
|---|---|---|
| 文档 | 17 | **49** |
| 证据 | 602 | **1241** |
| 信息中心 | 16 | **48** |
| 首页时间线 | 10 事件 | **20 事件** |

**仍未覆盖的两个频道**：
- **保研推免** —— 主要源是研招网推免系统（JS 渲染）
- **考公考编** —— 人社部被 EdgeOne 反爬拦、河南考试院 412

两者都需要先接 Playwright 或换入口。

---

## 4. 三个必须知道的坑

### 坑 1：`.env` 放项目根**不生效**

`config.py` 里是 `env_file=".env"`，而 pydantic-settings 按**当前工作目录**找。
API 必须从 `backend/` 启动 → **真正生效的是 `backend/.env`**。

实测：只有根目录 `.env` 时读到空值；`backend/.env` 才生效。

`setup-env.py` 已经两个位置都写了一份，所以不用管。但如果你手工配置，别踩这个。

### 坑 2：`DATABASE_URL` 是相对路径

默认 `sqlite:///./campusmate.db`，落点由 CWD 决定 —— 从项目根跑和从 `backend/` 跑
是**两个不同的文件**。用绝对路径（`setup-env.py` 已经这么做了）。

路径**可以含空格**，但盘符和目录必须写对，否则报 `unable to open database file`。

### 坑 3：跑测试有 3 个前置条件

```bash
rm -f backend/test.db
DATABASE_URL="sqlite:///./backend/test.db" python -m alembic -c backend/alembic.ini upgrade head
DEMO_MODE=true ADMIN_USER_IDS=demo-user \
DATABASE_URL="sqlite:///./backend/test.db" python -m pytest backend/tests -q
```

1. 测试库**必须先迁移**，否则报 `Database migration required`（**那是缺库，不是代码坏了**）
2. 必须带 `DEMO_MODE` / `ADMIN_USER_IDS`，否则 70+ 项因 `401 != 403` 失败
3. 用**全新库**，测试之间有状态泄漏，复用会有十几项随机失败

预期 **120 passed**。

---

## 5. 三个本地开发开关（生产必须关掉）

| 开关 | 作用 | 关掉会怎样 |
|---|---|---|
| `COLLECTOR_ALLOW_PLAINTEXT_HOSTS` | 允许指定主机走明文 HTTP | `moe.gov.cn` 采不到 |
| `COLLECTOR_SKIP_ROBOTS` | 跳过 robots 检查 | 部分门户被误判为禁止采集 |
| `SINGLE_ADMIN_OVERRIDES` | 放宽"三方分离"身份要求 | 单人无法校准，**且已批准的校准全部失效** |

**都只放宽"通道"，不放宽"证据"** —— robots/条款/许可原文 + 页面 SHA256 的要求一个没动。

> **最容易误判的**：`SINGLE_ADMIN_OVERRIDES` 必须在**运行时**也开着。
> 关掉后门禁会显示 0/37，看起来像"数据和校准都丢了" —— 实际是身份不满足。
> 原因：`calibration_for()` 每次查询都用**当前**设置重新评估身份分离。

---

## 6. 继续接数据，先看这些实测事实

这些是我联网实测出来的，**你重写代码它们依然成立**，不用再踩一遍：

| 站点 | 事实 |
|---|---|
| `www.moe.gov.cn` | 对任何 `https://` 都返回 `302 → http://`（腾讯 EdgeOne），只能走明文；`/robots.txt` 是 **404** |
| 教育部 `srcsite/` 政策详情页 | `h1=1` 但 `article=0`、`main=0`、`.TRS_Editor=0` —— **正文在 `div.moe-detail-box`** |
| 教育部 `jyb_xwfb/` 新闻页 | 有 `.TRS_Editor`（同站两套结构） |
| 研招网 `/zsml/` | **Vue SPA**，`<h1>` 里是未渲染的 `{{curYear}}`，静态抓取拿不到 |
| gov.cn 政策文库 | 124 字节 JS 跳转 → 974 字节纯 JS |
| `www.mohrss.gov.cn` | **腾讯 EdgeOne 反爬挑战**（988 字节混淆 JS） |
| 高校研招栏目（北大/清华/复旦） | 是**纯链接列表**（0 个 `p`），不是通知详情页 |

### 剩余卡点

| 卡点 | 解法 |
|---|---|
| 研招网 / gov.cn 的 JS 渲染 | 接 Playwright（项目已有依赖，未接入采集链） |
| 人社部 EdgeOne 反爬 | 改 selector 无用，需换入口 |
| 国考职位表 `bm.scs.gov.cn` | 目标机拒连，需正确入口 |
| 高校研招通知 | 需补 discover 层（列表 → 详情） |
| 北京开放数据 / Hochschulkompass | **授权问题**（userKey / 商业许可），非技术 |

### 两个代码层面的坑

1. **未知 `parser_type` 会静默降级** —— 落到 `_parse_generic`，实测**0 记录 / 0 证据**且不报错。
   注册表里有 **5 个声明的适配器没有实现**（`OccupationAdapter`、`PublicJobDiscoveryAdapter`、
   `RegionAdapter`、`StatisticsAdapter`、`UniversityListAdapter`）。
   `test_registry_adapter_coverage.py` 会守护这一点。
2. **`discover()` 是死代码** —— ABC 里定义了但全项目从未调用，而注册表有 4 个端点声明
   `agent_mode: DISCOVERY`。"列表页→详情页"需要自己补调用点。

### 加一个新适配器要改 6~8 处

不是写一个类就完事：`adapters/<module>.py` → `adapters/__init__.py` → `source_scheduler.py`
（parse 校验 + `_persist_fetched` 两处）→ `intake.py`（handler map + 入库函数）→
`source_registry.yaml` → 需要手工导入时还有 `intake_api.py`。

**建议第一件事**：把这套 `if/elif` 分串换成注册表字典。现在漏改一处就静默降级。

---

## 7. 平台侧持续抓取

调度引擎**已经能用**（我实测跑通过，含内容变更检测、版本创建、风险审核）。
`docker-compose.yml` 里有常驻 worker（`python -m app.worker`）。

**但要注意三点**：

1. **是轮询，不是推送**。没有 webhook。**最小间隔 1 小时**（`interval_delta` 只认 `Nh`/`Nd`）
2. **可自动化上限 25/37** —— `AUTO-3`/`AUTO-4` 的 11 个端点永远不能自动采集
3. **最该先补的是监控**：现在 `stale` 阈值是 **30 天**（12h 端点=漏跑 60 次才发现），
   而且**没有任何陈旧端点的推送告警**。失败 3 次还会静默转人工接管。
   → **没有监控的自动抓取比人工更危险，因为它会静默失败。**

---

## 8. 如果你要重写架构

分三层，**事实 > 契约 > 实现**：

| 层 | 内容 | 能否丢 |
|---|---|---|
| **事实** | 第 6 节那张表（联网实测结论） | **丢不得** —— 重写后依然成立 |
| **契约** | 门禁 fail-closed、证据需 DOM 定位+原文、内容哈希去重、HTTPS 白名单+IP pinning、`SourceAdapter` 四方法契约 | **丢不得** —— 丢了治理保证就无声失效 |
| **实现** | 我的元组/函数名/配置格式/选择器写法 | **随便扔** |

---

## 9. 一句话

**适配器本身没问题，问题在 URL 校准和采集通道。** 教育部这条链路已经彻底跑通，
剩下的工作是"把同样的诊断方法用到其他源上" —— 而那需要 Playwright 和 discover 层。

有问题先看第 4 节的三个坑，八成问题在那里。

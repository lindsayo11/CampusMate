> 最新累计版本 v0.10.0，详见 RELEASE_STAGE10.md。包含阶段 1–10 全部代码；生产构建与外部联调尚未通过。

> 最新累计版本 v0.9.0，见 RELEASE_STAGE9.md；包含 v0.8.0 全部改动。

> 最新累计版本 v0.8.0。新环境先运行 Alembic 迁移；验证与限制见 RELEASE_STAGE8.md。下文历史启动说明以新发布说明为准。

# CampusMate 校伴

CampusMate 是面向高校学生的统一机会与行动平台。本仓库是阶段 2 完整源码，包含阶段 1 的全部成果，并新增画像、行动看板、资格判断、提醒、Agent Tool API 与内容审核。

## 已完成

- 六板块统一首页与机会浏览（就业、竞赛、考公、志愿、社团、升学）
- 类型、关键词筛选与机会详情页
- 来源、截止日期、可信度和适配标签
- FastAPI `/v1/opportunities`、详情与统计 API
- 用户画像读取与编辑
- 确定性资格规则逐条判断与来源证据
- 行动看板与幂等写入
- 截止提醒与重复请求去重
- `opportunity_search`、`eligibility_check`、`tracker_write`、`deadline_remind` 四个 Tool API
- 低置信度和高风险内容审核队列
- SQLite 本地零配置运行；通过 `DATABASE_URL` 可切 PostgreSQL
- OpenAPI、种子数据、后端测试、Docker Compose

## 本地运行

### 后端

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
uvicorn app.main:app --reload --port 8000
```

### 前端

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

访问 http://localhost:3000；API 文档位于 http://localhost:8000/docs。

### Docker

```bash
cp .env.example .env
docker compose up --build
```

## 验证

```bash
cd backend && pytest
cd frontend && npm run typecheck && npm run build
```

## 下一阶段

阶段 3 将增加 `team_match`、`message_connect`、队伍房间、消息持久化、举报与 Agent 对话编排。

# Stage 24 — 毕业发展路径迁移改造

本阶段将 CampusMate 从校园机会发现底座迁移为毕业发展路径与信息整合系统。

## 已完成

- 新增 `development_paths`、`timeline_nodes`、`user_plans` 数据表及 Alembic `0013`/`0014` 迁移；`0014` 补齐路径状态索引，消除 ORM 与迁移漂移。
- 新增保研、国内考研、留学、考公考编、就业、创业六条内置路径与时间线节点。
- 扩展用户画像：学历层次、目标年份、目标方向、目标地区、语言成绩、科研/实习/竞赛/创业经历。
- 新增 API：`GET /v1/paths`、`GET /v1/paths/{id}/timeline`、`GET/POST /v1/plans`、`PATCH /v1/plans/{id}`。
- 保留既有机会、资格判断、提醒和追踪接口，确保迁移期间兼容旧页面。
- 首页入口、行动区和前端 API 类型更新为毕业发展路径语义。

## 发布步骤

```bash
alembic upgrade head
python -m app.seed
```

首次启动演示模式会自动写入路径和时间线种子数据。

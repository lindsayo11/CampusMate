# 当前开发状态 v0.30.0-ingestion.1

Stage30 已实现原文归档→证据审核→独立双人发布→数据中心/时间线→个人计划与站内提醒的核心链路。迁移到 0021 后旧端点调度自动暂停，必须补充校准依据后重新审核启用。当前验收结果与剩余边界以 `docs/RELEASE_STAGE30_DATA_CLOSURE.md` 为准。

以下为截至 Stage29 的历史记录，不代表 Stage30 本轮结果。

已按 v2.1 主体平台方案在 v0.19.0 上增量开发并逐阶段交付完整累计源码。当前为预发布验收包，阶段 23 的最终发布门禁尚未关闭。

| 阶段 | 本轮源码成果 | 验收状态 |
| --- | --- | --- |
| 20 | 平台首页/导航、基础状态与响应式、Agent/采集默认关闭 | 构建/API通过；浏览器布局待验收 |
| 21 | 通用资格入口、主看板编辑、机会状态筛选、提醒取消、通知分页 | 后端/类型/构建通过；浏览器链待验收 |
| 22 | 角色后台、审计/下线、邀请队名/状态、队伍房间入口 | 权限/并发/消息/治理后端通过；双账号浏览器链待验收 |
| 23 | standalone 启动、配置门禁、冷启动/迁移/恢复脚本、22项 E2E | 本地 SQLite 与 HTTP/Worker 通过；浏览器/真实生产服务受阻 |

实测通过 79 后端、19 前端测试（含身份协议、范围开关、来源、M5 境外升学、M6 创业政策、端点校准门禁与恢复流程）、TypeScript、生产构建和迁移 schema check。

Chromium 已安装但运行 SIGTRAP，22 项浏览器用例未验收。没有真实身份/邮件项目、PostgreSQL 目标库和域名容器部署环境，因此不得声称完整上架。恢复测试仅证明 SQLite。本轮不开发 Agent 编排、自动信息采集、Realtime、语义 RAG、原生 App 或六板块专属重业务。

下一步是关闭 docs/PLATFORM_RELEASE.md 的实际发布门禁，再标记 RC。历史版本记录保留，不把历史结果当本次测试结果。

## 数据源接入增量

已完成 M0、M1、M2、M3 与 M4 的本地可运行链路：0015–0017 迁移、SourceRegistry YAML Seed、DocumentVersion/Evidence、周期与岗位实体、Path 层级与多对多关系、公务员工作簿、国内升学、事业单位公告、公共招聘岗位与地方招聘平台目录适配器。端到端链路支持 XLSX 单元格证据、HTML DOM 证据、去重、版本 diff、高风险字段待审和人工确认。另提供 Source Health、Registry、来源变化和地方来源候选审核页面。

本轮后端 79 项、前端 19 项测试、Alembic 0001→0020 schema check、TypeScript 与 production build 通过。新增 SourceEndpointCalibration 三方分离审核：提交人不得审核，两名审核人必须不同；批准后才关闭 `live_access_unverified`/`exact_url_pending`，Registry Seed 不会重新打开已解决 Blocker，也不会覆盖已批准的精确 URL 与配置。当前环境未执行任何官方站点线上校准，因此原有真实 Blocker 保持开放。北京开放数据 userKey 端点仍只登记许可证/认证状态，不导入数据。

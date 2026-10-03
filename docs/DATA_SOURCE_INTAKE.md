# 数据源接入运行说明

## 初始化

先执行数据库迁移，再导入 Registry：

```bash
cd backend
python -m alembic -c alembic.ini upgrade head
python -m app.source_registry
```

Seed 可重复运行。它以 `app/source_registry.yaml` 为声明源，更新同一 `source_code` 和端点，不保存 API Key、Token 或用户凭证。

## 公务员职位工作簿

管理员调用 `POST /v1/admin/intake/civil-service-workbook`，提交官方 XLSX 的原始公开 URL、年度批次和文件内容。系统会：

1. 校验端点属于 `CM-CS-001` 且为匿名官方文件端点；
2. 拒绝宏、公式事实字段、超限文件和缺少关键列的工作簿；
3. 建立或更新 RecruitmentCycle 和 Position；
4. 为每个确定性字段保留 `sheet + cell` Evidence；
5. 生成带 Evidence 的 EligibilityRule；
6. 将备注保留为 `agent_candidate`，不直接发布；
7. 用 SHA256 去重，变化时创建新的 DocumentVersion 和 diff。

高风险字段初始 `review_status=pending`。管理员使用 `PATCH /v1/admin/intake/rules/{id}` 确认、修改、拒绝或标记过期。确认结果会记录核验人和核验时间。

## 合规边界

- `[LOGIN-USER]` 端点不进入后台采集。
- `secret_ref` 只引用外部 Secret；数据库和前端不保存密钥。
- 公式、模型猜测和无 Evidence 的高风险值不能进入已确认事实。
- 外部网站测试不进入 CI；Parser 使用保存的 Fixture。
- 真实抓取必须配置官方域名白名单，并遵守 robots、条款、限流和许可证。

## SourceEndpoint 调度

Registry Seed 只登记来源，不会自动开始采集。管理员必须在数据源治理页面核验精确 URL 后显式启用。系统会拒绝登录、商业授权、许可证受限、`USER_ACTION` 和 `AUTO-4` 端点。

启用后的端点进入 `source_endpoint_runs` 队列。Worker 使用租约和 fencing 防止重复处理；发送 ETag 与 Last-Modified 条件请求；304 只更新最后发现时间。429、503 优先遵守 Retry-After，其余失败采用指数退避。连续失败达到阈值后自动暂停并切换为人工接管。

内容变化会创建新的 DocumentVersion 和 SourceChangeReview。变化审核页提供官方原文、版本差异、确认、拒绝和待后续处理操作；变化不会直接覆盖已确认事实。
# 数据发布与使用

当前入口：`/admin/data` 为导入与发布工作台，`/admin/registry` 为来源校准，`/data` 为已审核数据中心，`/data/timeline` 只展示有明确日期的事项。

1. 管理员上传受支持的 HTML/XLSX 原始文件并选择适配器。导入仅生成草稿，不自动公开。
2. 核验精确官方 URL、robots、条款与许可证，填写原文摘录和页面 SHA256；提交人与两名校准审核人必须不同。
3. 检查原文归档、规则与证据；政策关联批准必须提供当前原文中实际存在的引用和位置。
4. 在工作台提交发布，由两名不同于提交人的管理员复核。原文缺失、hash 不符、测试文件、开放阻断或待审规则会阻止发布。
5. 用户在数据详情保存个人计划；仅有未来明确截止日期时可添加截止提醒。通知页显示截止或来源失效提醒。取消订阅不删除用户计划。

迁移 0021 会暂停旧调度，因为旧校准记录没有完整依据。补充依据并重新审核后，管理员才能显式恢复调度。旧文档缺失原文时需重新导入真实原文件；不能用重新生成的摘要替代。

新版本到达、来源停用、校准失效或规则修改会使旧发布不再可见。复杂自然语言资格仍需人工判断；数据中心不会猜测日期或资格结论。更多边界见 `docs/PLATFORM_RELEASE.md`。

---

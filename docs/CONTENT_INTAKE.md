# 真实内容接入

管理员登录 /admin/sources，粘贴允许归档的公开原文和下列结构化 JSON（全部例值必须换成实际信息）。不自动联网抓取、不自行生成官方事实。原文长度 20–200000 字；规则 evidence 必须存在于原文中。

```json
{
  "type": "civil_service",
  "title": "实际公告标题",
  "organization": "实际发布单位",
  "summary": "人工核对后的摘要",
  "location": "实际地区",
  "deadline": "2027-01-01T17:00:00+08:00",
  "source_url": "https://example.edu/notice",
  "source_label": "实际官方来源名称",
  "fetched_at": "2026-09-28T09:00:00+08:00",
  "tags": ["招录"],
  "rules": [{"field":"grade","operator":"in","expected":"大三","label":"年级条件","source_url":"https://example.edu/notice","evidence":"仅限大三报名。"}]
}
```

rules 可为空，未录入规则时资格判断返回信息不足，不推断合格。支持字段 school/college/grade/major；operator 为 in（逗号分隔精确匹配）或 contains_any（任一文字包含）。人工审核需确认规则足够完整，不能将通过已录入条件等同于获得报名资格。

来源 URL 下原文相同则沿用归档；字段也相同则复用审核单。原文变化追加不可变版本并保留前序 ID，可在页面查看文本 diff。重复导入忽略 fetched_at 差异，不制造多份审核任务。

管理员到 /admin/review 点击“核对字段与归档”，核对原文、规则与来源后批准；新机会与资格规则在同一事务落库。变更后的内容仍需审核，不自动覆盖已发布内容。若替代旧公告，管理员需要显式下线旧机会（POST /v1/admin/opportunities/{id}/unpublish），避免误覆盖一个公告下的多个职位。

当前是运营辅助导入流水线，不包含官方爬虫、PDF/Excel 抽取、自动内容变更推送或 RAG。首发学校和获准使用的官方来源确定后才能配置并验收这些能力。

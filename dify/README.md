# Dify 路由工作流接入

本仓库实现的是后端 Workflow API 适配器，不是已部署的 Dify 服务。契约依据 Dify 官方源代码 /workflows/run：
https://github.com/langgenius/dify/blob/main/api/controllers/service_api/app/workflow.py

创建并发布 Workflow（不是 Chatflow），用户输入节点声明 query、opportunity_id 两个字符串；LLM 节点使用 prompts/router.md。结构化输出遵循 specs/agent-decision.schema.json。结束节点输出名必须为 decision，值为对象或 JSON 字符串。

服务端环境变量：DIFY_API_BASE=https://你的服务/v1，DIFY_APP_KEY 为该 Workflow 的 API key。只配置在 API 容器，禁止放入 NEXT_PUBLIC_*。调用采用 blocking，20 秒超时；超时/输出非法返回 502，不自动尝试写操作。生产部署需根据实际 Dify 版本导出、版本控制并回归工作流；此包未伪造 DSL 导出文件。

没有配置时 /v1/agent/chat 使用明确标记为 rules 的规则检索；已选机会支持“资格”“能报”“提醒”“看板”“收藏”关键词。降级模式不具备通用自然语言理解。

后端重新验证 tool/arguments，不接受模型给出的用户身份，也不展示模型编造的自然语言结论。读取结果来自业务库；3 种写操作先持久化待确认动作，有效期 10 分钟。confirm 在同一事务中锁定动作、执行工具、记录结果与审计。重复确认返回第一次结果。原始用户问题不写入审计；传给 Dify 的用户 ID 为哈希，但问题本身会发送给所配置的 Dify 服务。

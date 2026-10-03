# 数据源接入实施状态

更新日期：2026-09-29

## Stage30 当前增量

已打通归档、证据审核、不可变发布快照、双人复核、公开检索/详情/时间线、个人计划和站内数据提醒。人工导入、后台排队、调度执行、发布可见性采用一致的来源与授权阻断条件；Worker 增加抓取前后检查、租约过期阻断及失败事务回滚。校准须附 robots/条款/许可原文摘录、URL 和页面 SHA256。

以下 M0–M6 是累计实现范围；文末“本轮实测”为 Stage29 历史结果。Stage30 的最新测试和尚未完成事项见 `docs/RELEASE_STAGE30_DATA_CLOSURE.md`。本轮新增真实线上校准来源数为 0。

## M0 信息源底座

已完成：

- Source、SourceEndpoint、DocumentVersion、Evidence 数据模型与 0015 迁移。
- Institution、Program、ApplicationCycle、RecruitmentCycle、ExamCycle、Position、DevelopmentItem 数据层。
- Path 父子层级和 DevelopmentItemPath 多对多关系。
- EligibilityRule 支持通用目标、Evidence、解析器、置信度和审核状态。
- DocumentVersion 支持 SHA256、附件 hash、版本号、首次/末次发现、变更时间、上一版本和 diff。

## M1 SourceRegistry Seed

已完成：

- YAML 与数据库幂等 Seed。
- 累计 33 个来源、36 个端点，保留 CM-GR、CM-TM、CM-CS、CM-PI、CM-JOB、CM-OS、CM-ENT 编码。
- Access、Auth、Automation、Agent、许可证说明与刷新频率。
- 按路径、地区、学校过滤 API；来源详情包含端点边界。
- 研招网登录业务标为 LOGIN-USER、AUTO-4、USER_ACTION，不作为后台采集通道。

## M2 文件型数据 PoC

已完成：

- CivilServiceWorkbookAdapter 确定性 XLSX 解析。
- Sheet + Cell Evidence、公式拒绝、字段标准化、岗位与资格规则生成。
- 未变更内容不重复生成版本；变更生成新 DocumentVersion 和 diff。
- 备注只生成 agent_candidate，默认待审核；高风险字段带 Evidence 并保持 pending。
- 保存的 Fixture 与端到端、去重、版本变化、Evidence 测试。

## M3 国内升学公开信息接入

已完成可运行链路：

- MoEPolicyAdapter：教育部公开政策标题、正文段落、文档版本与 DOM Evidence。
- YZChsiAdapter：研招网公开专业目录表，生成 Institution、Program、ApplicationCycle、DevelopmentItem、DevelopmentItemPath 与日期规则。
- UniversityNoticeAdapter：高校公开招生通知中的时间、学历、GPA、排名、语言和材料字段，生成待审规则并关联 Evidence。
- 四所试点高校 SourceRegistry：北京大学、清华大学、上海交通大学、复旦大学；Seed 后默认不启用调度。
- 手工导入严格限定公开匿名端点与官方域名；登录、密码、验证码页面明确拒绝解析。
- 高风险规则保持 pending，政策保持 candidate，未人工确认前不作为最终事实。

当前执行环境不能访问所列政府/高校域名，因此本阶段只以保存的结构 Fixture 验证解析和落库链路；未声称已完成线上真实数据同步。

## M4 公务员、事业单位与公共招聘 PoC

已完成可运行链路：

- 公务员职位 XLSX PoC 延续使用 CivilServiceWorkbookAdapter。
- InstitutionRecruitmentAdapter：解析事业单位公告时间、附件和 HTML 岗位表。
- MohrssPublicJobAdapter：将公开岗位表接入市场化就业路径，并复用同一版本和证据治理机制。
- RecruitmentCycle → Position / DevelopmentItem → DevelopmentItemPath → EligibilityRule → Evidence 完整链路。
- 年龄、学历、学位、专业、资格、应届、政治面貌、考试科目等规则默认 pending；复杂备注为 agent_candidate。
- RegionalRecruitmentDirectoryAdapter：从官方地方平台目录生成 SourceRegistryCandidate，不直接启用来源。
- 候选人工批准后只创建 inactive 省级 Source 和未调度 Endpoint；启用前仍需复核精确栏目、robots 与条款。
- 新增候选审核 API、审计记录与管理后台页面。

当前只使用保存的结构 Fixture 验证事业单位和公共招聘链路；未声称已同步线上实时岗位。

## M5 国（境）外升学 PoC

已完成可运行链路：

- 0018 迁移新增 GeographicEntity、EntityAlias、RegistryAssertion、SourceBlocker，并扩展 Institution、Program、ApplicationCycle、Evidence 和 SourceEndpoint。
- 以 ISO 国家/地区代码和 Registry 官方 ID 生成稳定 ID；国家、地区、院校、项目支持多语言别名并检测别名冲突。
- OverseasRegistryAdapter 只导入院校、项目发现和公共状态；检测到 deadline、GPA、语言、学历或材料列时拒绝解析。
- OverseasUniversityProgramAdapter 只允许 foreign university 第一方来源写入年度申请要求。
- 完成 Institution → Program → ApplicationCycle → DevelopmentItem → EligibilityRule → Evidence 全链路，deadline、学历、GPA、语言、GRE/GMAT、材料和申请费均绑定表格/DOM Evidence。
- SourceRegistry 增加留服中心、教育涉外监管、Discover Uni、CRICOS、Study in Japan、Hochschulkompass 和 Oxford 试点大学端点。
- 留服个人认证端点标为 LOGIN-USER/AUTO-4/USER_ACTION；Hochschulkompass 标为 LICENSE/restricted/AUTO-4，均不允许进入后台采集。
- 保存 Oxford MSc Advanced Computer Science 2027 入学周期和 Discover Uni 院校实体 Fixture，验证版本哈希、去重、别名、RegistryAssertion、规则和证据链。
- 管理后台新增境外院校、项目、申请周期、规则、证据与 Blocker 审核入口，并提供确认、拒绝、过期 API。

Fixture 只用于确定性端到端测试；未把其表述为 2026-09-29 的实时同步结果。

## M6 创业政策五级接入 PoC

已完成可运行链路：

- 0019 迁移扩展 PolicyRecord 文号、发布机关、政策类型、辖区链、办理入口和审核状态，并为 PolicyRelation 增加 Evidence。
- GovernmentPolicyAdapter 将公开政策结构确定性转换为 PolicyRecord、DevelopmentItem、EligibilityRule、表格/DOM Evidence 和 DocumentVersion。
- Fixture 覆盖国家→省→市→区县→高校五级 PolicyRelation 链，关系与每条规则均保留 Evidence；所有规则默认 pending。
- OpenDataPlatformAdapter 明确拒绝认证有效载荷；OpenDataResource 只登记 API 认证、许可证状态、导入状态与 Blocker。
- 北京公共数据端点标为 API-AUTH/api_key/AUTO-4/USER_ACTION，缺少 userKey 时不进入调度、不导入生产数据。
- 管理后台新增政策、规则、关系、文档版本、差异与 Blocker 审核入口。

财政部样例使用保存的官方政策结构；省、市、区县和高校样例明确标记为 synthetic offline test fixture，只验证链路，不声称对应真实现行政策或实时同步。

## M7 自动调度与健康监测

- ETag 与 Last-Modified 条件请求，支持 304 不变更结果。
- SourceEndpoint 成功时间、连续失败数和健康状态 API。
- 管理员可确认、修改、拒绝或标记资格规则过期；确认者和确认时间写回 Evidence。
- 管理后台 SourceRegistry 与端点健康页面。
- 0016 迁移新增端点调度开关、下次运行时间、任务租约、人工接管和来源变化审核。
- Seed 端点默认不调度；管理员必须核验精确 URL 后显式启用。
- 登录、商业、许可证受限、USER_ACTION、AUTO-4 端点不能进入后台调度。
- Worker 支持条件请求、租约 fencing、失败重试、Retry-After 和连续失败自动暂停。
- 版本变化创建 SourceChangeReview，高风险关键词变化进入高风险审核。
- 管理后台支持启用、暂停、立即采集、人工接管、恢复和版本差异审核。
- 0020 迁移新增 SourceEndpointCalibration，完整记录精确 URL、robots、条款、许可证、字段映射、Adapter 配置和校准时间。
- 校准采用提交人 + 两名不同管理员的三方分离；未双人批准的线上校准 Blocker 不能被启用操作绕过。
- 校准批准后只关闭 `live_access_unverified`/`exact_url_pending`；API Key、登录、商业许可等 Blocker 不会被误关闭。
- Registry Seed 保留已解决 Blocker，并保留已批准校准的精确 URL、robots、许可证和 Adapter 配置。
- 管理后台 Registry 页面显示开放 Blocker 和校准状态，支持提交、审核与驳回。

## 尚未执行

- M3 官方站点在线抽样、页面结构校准和人工首轮验真。
- M3/M4 官方站点在线抽样、页面结构校准与首轮人工验真。
- M5 官方 Registry 与三所大学页面的线上抽样、页面结构校准和首轮人工验真。
- M6 省、市、区县与高校第一方政策的真实最小样例校准；当前只有隔离 Fixture 链路。

## 外部阻塞

- 当前未使用政府开放平台账号、API Key、商业授权或用户登录。
- 未伪造开放数据平台凭证；正式 API PoC 需合法 userKey 或选择无需凭证的官方接口。
- 当前执行环境未通过应用采集器完成官方 Registry/大学页实时同步；只完成保存 Fixture 测试并登记待线上校准 Blocker。
- Discover Uni、CRICOS、Study in Japan 的当期下载格式、robots/条款和许可证仍需人工核验后才能启用调度。
- Hochschulkompass 商业/生产使用许可未取得，仅登记限制和 Blocker，不导入生产数据。
- 本阶段以保存的官方字段结构 Fixture 验证解析与证据链，未把模拟文件声称为线上真实数据。

## 本轮实测

- Alembic 0001 到 0020 升级和 schema check 通过。
- 后端 79 项测试通过；新增覆盖三方分离校准、未批准禁用、Seed 防重开和审核后启用。
- 前端 19 项测试通过，TypeScript 通过。
- Next.js production build 通过；当前受限运行环境需要项目已有的 `restricted-node.cjs` 兼容脚本。
- 新增文件 Ruff 检查通过；项目全量 Ruff 仍有既有代码告警，未借本次需求批量改写无关历史代码。

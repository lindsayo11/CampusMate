"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import { Icon, PageHeading } from "@/components/ui";

type Output = { title: string; detail: string };
type Prompt = { label: string; hint: string };
type Force = { id: string; title: string; detail: string; evidence: string; risk: string; prompts: Prompt[] };
type Step = {
  code: string;
  label: string;
  short: string;
  title: string;
  description: string;
  phase: string;
  input: string;
  action: string;
  prompts: Prompt[];
  outputs: Output[];
  gate: string;
  decisions: string[];
  special?: "entry" | "validation";
};

type StepCopy = Pick<Step, "label" | "short" | "title" | "description" | "phase" | "input" | "action" | "prompts" | "outputs" | "gate" | "decisions"> & {
  aiRole: string;
  aiTasks: string[];
  humanCheck: string;
};

const STEP_ICONS = ["search", "book", "hash", "file", "users", "arrow", "clock", "link", "shield", "users", "arrow", "file", "spark"] as const;

const FORCES: Force[] = [
  {
    id: "demand", title: "需求驱动", detail: "从反复出现的用户痛点开始。",
    evidence: "访谈、问卷、桌面研究、ITBD、沉浸式观察、用户日志、行为数据、社群讨论、搜索词、投诉和差评。",
    risk: "伪需求：用户说出了问题，却没有改变行为或付费。",
    prompts: [
      { label: "谁在什么具体场景经历这个痛点？", hint: "写出可触达的人群、触发时机、任务和环境。" },
      { label: "痛点多久发生一次，严重到什么程度？", hint: "估算损失的时间、金钱、精力、收入、效率或体验。" },
      { label: "用户现在怎么解决，已经付出了什么？", hint: "记录替代方案、成本，以及为什么仍不满意。" },
      { label: "什么证据说明这是真实需求而不是口头偏好？", hint: "优先使用观察、访谈、日志、搜索或投诉数据。" },
      { label: "如何把具体痛点写成可验证的需求？", hint: "先写用户要完成的任务，不要先写产品。" },
    ],
  },
  {
    id: "market", title: "市场驱动", detail: "从已被验证的市场缺口开始。",
    evidence: "市场规模与增长、竞品方案、用户不满、评价、产品与服务缺口、价格、渠道、人群、地域、场景和技术覆盖。",
    risk: "同质化竞争：缺口明显，却没有可守住的差异。",
    prompts: [
      { label: "你在研究哪个已被验证的市场和人群？", hint: "说明市场成熟度、增长、购买者和使用场景。" },
      { label: "龙头或替代方案在哪些地方没有服务好用户？", hint: "检查产品、服务、价格、渠道、人群、地域、场景和技术缺口。" },
      { label: "用户不喜欢现有方案的什么地方？", hint: "使用评价、访谈、转用行为和竞品对比。" },
      { label: "你能触达这个缺口并守住独特位置吗？", hint: "记录进入成本、竞争者反应和可持续优势。" },
    ],
  },
  {
    id: "product", title: "产品驱动", detail: "从一个小产品测试开始。",
    evidence: "原型使用、任务完成、观察到的行为、反馈、重复使用、替代操作和付费意愿。",
    risk: "没人需要：产品有趣，却没有在真实场景中产生价值。",
    prompts: [
      { label: "现在能让用户试用哪个小产品或原型？", hint: "把测试范围收窄到一个核心任务。" },
      { label: "谁在什么场景试用了，实际做了什么？", hint: "观察行为和任务完成，不用客套话代替结果。" },
      { label: "用户认可、拒绝或绕开了什么？", hint: "把直接反馈和观察到的摩擦分别记录。" },
      { label: "有人回来、推荐或付费吗？", hint: "寻找重复使用和真实承诺，而不是口头意向。" },
    ],
  },
  {
    id: "other", title: "其他驱动", detail: "从技术、政策或产业变化开始。",
    evidence: "技术、AI 能力、基础设施、产业链、平台、政策、法规、人口、消费习惯、贸易和商业基础设施信号。",
    risk: "时机或依赖风险：变化是真的，但采用条件还没准备好。",
    prompts: [
      { label: "哪个外部变化创造了新可能？", hint: "说清技术、政策、法规或产业变化及其来源。" },
      { label: "谁的需求、行为或成本结构因此改变？", hint: "把变化连接到可识别的用户和使用场景。" },
      { label: "可能出现什么新需求或市场缺口？", hint: "写可验证的假设，不要只写趋势总结。" },
      { label: "哪些依赖、监管或采用条件可能阻碍它？", hint: "检查时机、基础设施、供应商、许可和付费意愿。" },
    ],
  },
];

const VALIDATION_MODULES: Output[] = [
  { title: "用户需求研究报告", detail: "用户、场景、痛点频率与严重程度、当前方案、付出成本、不满原因、替代方案与支付行为。" },
  { title: "用户问题地图", detail: "把用户 → 场景 → 问题 → 原因 → 后果 → 当前方案连起来。" },
  { title: "STP 分析", detail: "完成市场细分、目标市场选择和初步定位。" },
  { title: "V1 消费者画像", detail: "基本特征、场景、核心任务、痛点、行为、频率、支付能力与获客渠道。" },
  { title: "TAM / SAM / SOM 测算", detail: "用户数量、市场规模、增长率、客单价与渗透率假设。" },
  { title: "行业分析报告", detail: "波特五力、市场集中度、龙头、新进入者、替代品、壁垒、生命周期与利润率。" },
  { title: "产业链 / 价值链地图", detail: "上游、供应商、技术、平台、渠道、产品、客户、下游与关键依赖。" },
  { title: "政策与监管清单", detail: "准入、许可、限制、补贴、税收、政府采购、产业基金与园区政策。" },
  { title: "技术经济可行性报告", detail: "技术路径、难点、周期、人力、基础设施、供应链、单位成本与毛利。" },
  { title: "机会可行性评估表", detail: "汇总需求 × 市场 × 竞争 × 产业 × 政策 × 技术 × 经济。" },
];

const STEPS: Step[] = [
  {
    code: "ENTRY", label: "Opportunity discovery", short: "Discover", title: "Find the opportunity before building the company", phase: "Discovery",
    description: "Keep an opportunity pool. Explore demand, market, product and external forces before committing to a venture.",
    input: "Signals from users, markets, products, technology, industry and policy.", action: "Collect signals, compare alternatives and write a falsifiable opportunity hypothesis.", special: "entry",
    prompts: [
      { label: "Who do you believe has this problem?", hint: "Name a reachable user group, not a broad population." },
      { label: "In what scene does the problem appear?", hint: "Describe the trigger, task and context." },
      { label: "What is the current solution and why is it insufficient?", hint: "Name the workaround, cost and dissatisfaction." },
      { label: "Why does this opportunity appear now?", hint: "Record market, technology, policy or industry changes." },
    ],
    outputs: [
      { title: "Opportunity Pool", detail: "A continuously updated list of potential opportunities and their evidence." },
      { title: "Opportunity Card", detail: "User, scene, pain, current solution, why now, competition, business opportunity and risk." },
      { title: "Initial opportunity hypothesis", detail: "I believe [user] in [scene] has [problem], current solutions are [gap], so [opportunity] may exist." },
    ],
    gate: "Is this opportunity worth investigating further?", decisions: ["Enter demand and environment validation", "Hold for observation", "Drop", "Keep in opportunity pool"],
  },
  {
    code: "VALIDATE", label: "Demand and environment validation", short: "Validate", title: "Turn the opportunity into evidence", phase: "Validation",
    description: "This is the investigation center. Test the user problem and the surrounding market, industry, policy, technology and economics.",
    input: "The opportunity hypothesis, primary research and reliable public sources.", action: "Interview, observe, measure, compare and attach evidence to every conclusion.", special: "validation",
    prompts: [
      { label: "What evidence would prove the pain is real?", hint: "Define observable behavior, not only opinions." },
      { label: "Which user segment and target market are you testing first?", hint: "State the segment, targeting logic and initial position." },
      { label: "What assumptions drive your market and unit economics?", hint: "List user count, growth, price, penetration and cost assumptions." },
    ],
    outputs: VALIDATION_MODULES,
    gate: "Is this opportunity worth allocating resources to validate?", decisions: ["GO to positioning", "Change direction", "Continue investigation", "Pause", "Drop"],
  },
  {
    code: "POSITION", label: "Value proposition and positioning", short: "Position", title: "Define who receives what value", phase: "Validation",
    description: "Make the user, scene, problem, solution and value explicit. If the team cannot say why users choose it, do not build the MVP.", input: "Validated user problem, target segment and competitor evidence.", action: "Compare alternatives and choose a differentiated position.",
    prompts: [{ label: "For whom, in which scene, what problem do you solve?", hint: "Keep the sentence narrow enough to test." }, { label: "Why would the user choose you over current options?", hint: "Describe a concrete, durable difference." }, { label: "What will you deliberately not solve?", hint: "State the boundary of the position." }],
    outputs: [{ title: "Value proposition canvas", detail: "User + scene + problem + solution + value." }, { title: "Competitive positioning map", detail: "Choose two meaningful axes and identify the open position." }, { title: "Differentiation table", detail: "Compare your offer, competitors and the user's current solution." }, { title: "Core value proposition", detail: "One sentence that a target user can understand and act on." }, { title: "Product positioning statement", detail: "Service object, core scene, core value and core difference." }],
    gate: "Do we clearly solve a valuable problem, and should users choose us?", decisions: ["Enter MVP", "Reposition", "Continue research", "Stop"],
  },
  {
    code: "MVP", label: "Solution and MVP", short: "MVP", title: "Deliver the smallest complete value loop", phase: "Validation",
    description: "Define only the core value, its user flow, delivery method, cost and measurable validation indicators.", input: "Positioning statement and the highest-risk assumptions.", action: "Scope, prototype, deliver and instrument the smallest useful experience.",
    prompts: [{ label: "What is the core function and what is explicitly out of scope?", hint: "Protect the value loop from feature creep." }, { label: "What is the user flow from acquisition to feedback?", hint: "Acquisition -> registration -> use -> core action -> value -> feedback." }, { label: "What must be true for the MVP to work?", hint: "List people, technology, time, cost and delivery dependencies." }, { label: "How will you charge and measure value?", hint: "Draft pricing and activation, completion, time-to-value and feedback metrics." }],
    outputs: [{ title: "MVP product plan", detail: "Core and non-core features, user flow, product flow, technical path and delivery." }, { title: "MVP user flow", detail: "Acquisition -> registration -> use -> core behavior -> value -> feedback." }, { title: "MVP development plan", detail: "Tasks, people, time, cost and technical dependencies." }, { title: "MVP cost budget", detail: "Development, server, people, channel, operations and support." }, { title: "Pricing hypothesis V0", detail: "Free, paid, package, subscription, usage or enterprise authorization." }, { title: "MVP validation metrics", detail: "Registration, activation, core use, completion, time to first value and feedback." }],
    gate: "Does the MVP actually deliver the core value?", decisions: ["Run first customer acquisition", "Revise MVP", "Continue prototype", "Stop"],
  },
  {
    code: "FIRST_USERS", label: "First customer acquisition", short: "First users", title: "Earn the first real usage", phase: "Traction",
    description: "Find a reachable first cohort, make the offer understandable, observe use and turn feedback into a real consumer profile.", input: "MVP, target user and a clear success event.", action: "Recruit, demonstrate, support, observe and record every friction point.",
    prompts: [{ label: "Who are the first users and where can you reach them?", hint: "Name people or organizations, not only channels." }, { label: "Why would they try now?", hint: "State the trigger and the trust mechanism." }, { label: "Where did the first user fail or succeed?", hint: "Record behavior rather than compliments." }, { label: "What changed in the real user profile and price hypothesis?", hint: "Update assumptions from observed usage." }],
    outputs: [{ title: "First user acquisition plan", detail: "Who, where, when, how and owner." }, { title: "First user pool", detail: "A real list of potential users with status and next action." }, { title: "Messaging and marketing kit", detail: "Product intro, demo, copy, case, FAQ and presentation." }, { title: "First user test report", detail: "Why they used it, how they used it, failure, delight and dissatisfaction." }, { title: "Feedback database", detail: "Bugs, feature requests, usage barriers, price, value and service issues." }, { title: "V2 consumer profile", detail: "The people who actually use the product, not the imagined audience." }, { title: "Pricing hypothesis V1", detail: "Update price, package, free boundary and payment point from feedback." }],
    gate: "Are real users willing to actively try the product?", decisions: ["Enter growth tests", "Return to positioning", "Revise MVP", "Stop"],
  },
  {
    code: "GROWTH", label: "Growth and distribution", short: "Growth", title: "Find a repeatable way to reach users", phase: "Traction", description: "Test channels and the reason people share. Track the full funnel instead of celebrating exposure alone.", input: "First-user evidence and an activation event.", action: "Run controlled channel and message experiments.", prompts: [{ label: "Which channels can reach the target user at a known cost?", hint: "Consider SEO, social, communities, campus, KOL, partnerships, agents and ads." }, { label: "Why would a user share or invite another user?", hint: "Design a real propagation mechanism." }, { label: "What experiment will you run this week?", hint: "Write one hypothesis, one audience and one success metric." }],
    outputs: [{ title: "Channel matrix", detail: "Channel, cost, volume, conversion and suitable scene." }, { title: "Growth experiment backlog", detail: "A/B, referral, content, ad and channel tests." }, { title: "Propagation mechanism", detail: "The reason users voluntarily share, invite or recommend." }, { title: "Growth funnel", detail: "Exposure -> click -> registration -> activation -> core behavior -> retention -> payment." }, { title: "Channel test report", detail: "Acquisition, cost, conversion, retention and payment by channel." }],
    gate: "Is there at least one channel that can acquire users repeatedly?", decisions: ["Enter PMF analysis", "Change channel", "Change positioning", "Pause"],
  },
  {
    code: "PMF", label: "Data analysis and PMF", short: "PMF", title: "Test whether the need persists", phase: "Traction", description: "Use behavior data to distinguish a one-time trial from sustained need, retention, payment and recommendation.", input: "Instrumented funnel and cohort data.", action: "Analyze retention, behavior, churn, recommendation and a data-based user profile.", prompts: [{ label: "Where do users drop out of the funnel?", hint: "Attach counts and rates for every transition." }, { label: "Who retains, pays and recommends?", hint: "Compare cohorts and usage depth." }, { label: "What should change if PMF is partial or absent?", hint: "Name the return point: positioning or MVP." }],
    outputs: [{ title: "User funnel report", detail: "Exposure, click, registration, activation, core behavior, retention, payment, repurchase and referral." }, { title: "Retention analysis", detail: "Next-day, 7-day, 30-day and long-term retention." }, { title: "Behavior analysis", detail: "Frequency, depth, feature use, core behavior and user path." }, { title: "Churn report", detail: "Who churns, why and at which step." }, { title: "Recommendation analysis", detail: "Recommendation, sharing, NPS and recommendation source." }, { title: "V3 data-based profile", detail: "A profile built from real behavior data." }, { title: "PMF validation report", detail: "Whether users continue to need the product and why." }],
    gate: "Do users continue to need this product?", decisions: ["PMF established", "Partially established; iterate", "PMF not established; return to positioning", "PMF not established; return to MVP"],
  },
  {
    code: "BUSINESS", label: "Business model validation", short: "Business", title: "Prove this can become a durable business", phase: "Enterprise", description: "Connect customers, value, channels, revenue, costs, risks, IP and compliance into one operating model.", input: "PMF evidence, pricing experiments and operating costs.", action: "Model, test and stress the unit economics and cash requirements.", prompts: [{ label: "Who pays, what do they pay for and through which channel?", hint: "Separate user, buyer and payer when they differ." }, { label: "What are CAC, LTV, gross margin and payback assumptions?", hint: "Use observed data where available and label estimates." }, { label: "What legal, policy, data or IP risk blocks scale?", hint: "Record owner and resolution deadline." }],
    outputs: [{ title: "Business model canvas", detail: "Customers, value, channels, relationship, revenue, resources, activities, partners and costs." }, { title: "Pricing experiment report", detail: "Price, package, payment method, conversion and average order value." }, { title: "Unit economics model", detail: "CAC -> LTV -> gross margin -> payback, plus ARPU, repurchase and churn." }, { title: "Channel economics report", detail: "Which channel actually makes money." }, { title: "Revenue model", detail: "Where revenue comes from and how it compounds." }, { title: "Cost model and cash forecast", detail: "Monthly revenue, costs, cash balance and break-even." }, { title: "Risk matrix", detail: "Probability x impact across market, tech, finance, legal, policy, supply, data and people." }, { title: "IP strategy", detail: "Patent, trademark, copyright, trade secret, disclosure and licensing decisions." }, { title: "Compliance pre-check", detail: "Legal and regulatory issues to resolve before scale." }],
    gate: "Is this a business system that can make money sustainably?", decisions: ["Enter company formation", "Change business model", "Continue experiments", "Pause"],
  },
  {
    code: "COMPANY", label: "Company formation and governance", short: "Company", title: "Turn the project into a governable company", phase: "Enterprise", description: "Formalize founder rights, capital, governance, assets, finance, contracts and compliance only when the evidence supports it.", input: "Validated business model, founders and financing needs.", action: "Document ownership, authority, controls, assets and legal operating boundaries.", prompts: [{ label: "Who owns which work, asset and decision?", hint: "Separate contribution, ownership and authority." }, { label: "What financing or exit terms create unacceptable risk?", hint: "Review dilution, control, liquidation and performance commitments." }, { label: "Which assets, contracts, financial and compliance controls must exist now?", hint: "Set an owner and review date." }],
    outputs: [{ title: "Founder agreement", detail: "Equity, contribution, responsibilities, decisions, exit, departure and vesting." }, { title: "Cap table", detail: "Founders, employees, investors, ESOP, ownership and dilution by round." }, { title: "Articles and governance architecture", detail: "Shareholder, board, management, rights and decision mechanisms." }, { title: "Authorization matrix", detail: "Who can decide finance, hiring, contracts, procurement, investment and financing." }, { title: "Financing document pack", detail: "Valuation, term sheet, investment agreement and investor rights." }, { title: "Exit and commitment risk list", detail: "Targets, triggers, compensation, repurchase and worst case." }, { title: "Enterprise asset inventory", detail: "Code, data, IP, domains, contracts, customers, accounts, brand and secrets." }, { title: "Finance and contract template pack", detail: "Accounting, reimbursement, budget, payment, employment, customer, supplier, NDA, IP and data." }, { title: "Compliance checklist", detail: "Network, data, privacy, consumer rights, IP, advertising and licences." }],
    gate: "Has the personal project become a governable, financeable and sustainable company?", decisions: ["Enter organization", "Fix governance gaps", "Remain a project", "Pause"],
  },
  {
    code: "ORG", label: "Organization", short: "Organize", title: "Make the work repeatable without the founder", phase: "Enterprise", description: "Define people, roles, processes, incentives and management visibility before adding complexity.", input: "Company responsibilities, operating bottlenecks and recurring work.", action: "Build the smallest organization and operating system that can deliver consistently.", prompts: [{ label: "Which roles and decisions are needed next?", hint: "Tie each role to an outcome, authority and reporting line." }, { label: "Which recurring work needs an SOP?", hint: "Start with product, sales, service, finance, legal and people workflows." }, { label: "What numbers tell leaders whether the system is healthy?", hint: "Define KPI/OKR and a review cadence." }],
    outputs: [{ title: "Organization chart", detail: "CEO -> departments -> roles with reporting lines." }, { title: "Role descriptions", detail: "Responsibility, authority, KPI/OKR, requirements and reporting." }, { title: "Hiring and training system", detail: "Recruiting, interview, offer, onboarding and role training." }, { title: "SOP handbook", detail: "Product, sales, service, finance, legal, HR and customer success processes." }, { title: "Performance system", detail: "KPI, OKR, promotion, compensation and incentives." }, { title: "Department policies", detail: "Operating rules for product, tech, market, sales, support, finance and HR." }, { title: "Management dashboard", detail: "Revenue, cost, users, retention, sales, cash and project progress." }],
    gate: "Could the company operate normally if the founder were away for one day?", decisions: ["Enter scale", "Continue organization building", "Reduce scope", "Pause"],
  },
  {
    code: "SCALE", label: "Scale", short: "Scale", title: "Prove the model can be copied at lower cost", phase: "Enterprise", description: "Expand only the parts that are already understood: channels, regions, product, enterprise sales, partners and operations.", input: "Validated channel economics, SOPs and operating capacity.", action: "Replicate with controlled expansion and explicit cost and risk limits.", prompts: [{ label: "What are you scaling, why now and at what cost?", hint: "State the repeatable unit and the expansion threshold." }, { label: "Which new channel, region or customer group comes next?", hint: "Name the dependency and learning plan." }, { label: "What breaks first when volume doubles?", hint: "Test people, product, supply, partner and cash constraints." }],
    outputs: [{ title: "Scale strategy", detail: "What to scale, why, when, expansion cost and risk." }, { title: "Channel and region expansion plan", detail: "Verified channel -> new channel -> new region -> new audience." }, { title: "Product matrix", detail: "Core product -> derivative product -> value service -> ecosystem." }, { title: "Brand strategy", detail: "Positioning, assets, communication and recognition." }, { title: "Enterprise customer system", detail: "B2B sales, key accounts, business cooperation and strategic customers." }, { title: "Strategic partner map", detail: "Channel, platform, technology, supply, capital and enterprise partners." }, { title: "Internationalization plan", detail: "Market, localization, law, channel, payment, tax and data." }],
    gate: "Can the business model be copied with materially lower marginal cost?", decisions: ["Enter capital-market assessment", "Fix the replication bottleneck", "Scale selectively", "Stop expansion"],
  },
  {
    code: "CAPITAL", label: "Capital markets (optional)", short: "Capital", title: "Decide whether capital markets serve the strategy", phase: "Capital", description: "Listing is optional. Compare the strategic need, cost, risk and alternatives before preparing for an IPO or other capital event.", input: "Scale metrics, governance, financial records and strategic objectives.", action: "Assess readiness and choose the least risky capital route.", prompts: [{ label: "Why would a capital-market event help this company?", hint: "Growth, liquidity, credibility or something else?" }, { label: "What must be corrected before external scrutiny?", hint: "Review equity, finance, governance, disclosure and internal control." }, { label: "What is the best alternative if listing is not necessary?", hint: "Compare private financing, strategic investment, M&A or continued operation." }],
    outputs: [{ title: "Listing feasibility report", detail: "Need, basic conditions, cost, risk and alternatives." }, { title: "Equity and financial normalization reports", detail: "Historical equity, audit, tax, internal controls and disputes." }, { title: "Governance normalization report", detail: "Board, committees, disclosure and internal controls." }, { title: "Listing preparation plan", detail: "Counsel, filing, review, issuance and post-listing operation." }, { title: "Post-listing capital plan", detail: "Refinancing, M&A, private placement and rights issue." }, { title: "Investor relations system", detail: "Disclosure calendar, investor communication and accountability." }],
    gate: "Does entering the capital market serve the company's long-term strategy?", decisions: ["Prepare capital route", "Choose a private alternative", "Continue operating", "Do not pursue listing"],
  },
  {
    code: "ITERATE", label: "Strategic iteration", short: "Iterate", title: "Close the loop and start the next opportunity pool", phase: "Strategy", description: "Review users, market, product, industry, policy, technology and finance; then update the opportunity pool rather than treating the path as finished.", input: "The full evidence tree, operating metrics and external changes.", action: "Review assumptions, map opportunities and risks, then choose the next deliberate move.", prompts: [{ label: "What did we get right and wrong?", hint: "Separate results from stories." }, { label: "Which assumptions were falsified and what changed outside the company?", hint: "Include user, competitor, policy, technology and industry changes." }, { label: "What is the next opportunity or product decision?", hint: "Turn the review into an owned, time-bound experiment." }],
    outputs: [{ title: "Annual strategy report", detail: "Users, market, product, industry, competition, value chain, policy, technology and finance." }, { title: "Strategic opportunity map", detail: "New market, product, technology, user, business model and value-chain position." }, { title: "Strategic risk map", detail: "Technology replacement, new competition, policy, user, industry chain and macro changes." }, { title: "Product iteration roadmap", detail: "Current product -> next version -> new product -> product matrix." }, { title: "Strategy review report", detail: "What worked, what failed, which assumptions were falsified and what emerged." }, { title: "Next opportunity pool", detail: "The next cycle returns to opportunity discovery with new evidence." }],
    gate: "What is the next evidence-backed strategic move?", decisions: ["Start a new opportunity cycle", "Double down on the current model", "Change direction", "Pause"],
  },
];

const STEP_COPY: StepCopy[] = [
  {
    label: "机会发现", short: "发现机会", title: "先找到值得验证的机会", phase: "发现",
    description: "从需求、市场、产品、技术、产业和政策信号建立机会池，不急着把第一个想法变成公司。",
    input: "用户反馈、市场变化、产品试用、技术进展、产业链和政策信号。", action: "收集信号、比较现有方案，写出可以被证伪的机会假设。",
    prompts: [
      { label: "谁在什么场景遇到了什么问题？", hint: "写出可触达的人群、触发时机、任务和环境。" },
      { label: "用户现在怎样解决，为什么仍然不满意？", hint: "记录替代方案、已付出的时间、金钱和精力。" },
      { label: "为什么这个机会现在出现？", hint: "说明市场、技术、政策或产业变化。" },
      { label: "有哪些证据支持这是机会，而不是偏好？", hint: "优先填写观察、访谈、搜索、投诉或行为数据。" },
    ],
    outputs: [
      { title: "机会池", detail: "持续记录所有潜在机会、来源、用户、痛点、市场与证据。" },
      { title: "机会卡", detail: "机会名称、目标用户、场景、痛点、现有方案、为什么现在、竞争与风险。" },
      { title: "初步机会假设", detail: "我认为某类用户在某场景下有某问题，现有方案存在某缺口，因此可能存在某机会。" },
    ],
    gate: "这个机会值得进一步调查吗？", decisions: ["进入需求与环境验证", "暂缓观察", "放弃", "加入机会池持续观察"],
    aiRole: "AI 研究助理先把零散想法整理成可比较的机会卡。",
    aiTasks: ["归并重复痛点并标注来源", "补全机会卡与反例", "根据公开信息列出竞品和变化信号"],
    humanCheck: "你要确认用户、场景和证据是否真实，并决定是否投入调查。",
  },
  {
    label: "需求与环境验证", short: "验证需求", title: "把机会变成可核验的证据", phase: "验证",
    description: "这是信息调查中心：同时验证用户问题、市场、行业、产业链、政策、技术和经济条件。",
    input: "机会假设、访谈与观察记录、问卷数据和可靠公开来源。", action: "访谈、观察、测算、比较，并为每个结论挂上证据。",
    prompts: [
      { label: "什么证据可以证明痛点真实且足够严重？", hint: "定义可观察行为，不只记录观点。" },
      { label: "先验证哪一类用户和目标市场？", hint: "写出细分、目标选择和初步定位逻辑。" },
      { label: "市场规模和单位经济依赖哪些假设？", hint: "列出用户数、增长率、价格、渗透率和成本。" },
      { label: "哪一项事实还需要一手调研或官方原文确认？", hint: "把不确定性变成下一次调查任务。" },
    ],
    outputs: VALIDATION_MODULES,
    gate: "这个机会值得投入资源验证吗？", decisions: ["GO，进入价值主张", "改变方向", "继续调查", "暂停", "放弃"],
    aiRole: "AI 信息分析师负责整理材料、计算假设和暴露证据缺口。",
    aiTasks: ["从访谈和资料提取主题与矛盾", "生成 STP、TAM/SAM/SOM 初稿", "整理行业、产业链、政策和技术风险"],
    humanCheck: "你要核对一手访谈、官方来源和关键数字，不能把 AI 推测当成事实。",
  },
  {
    label: "价值主张与定位", short: "定位价值", title: "说清楚为谁创造什么价值", phase: "验证",
    description: "把用户、场景、问题、解决方案和价值写成一句可测试的话；说不清就不进入 MVP。",
    input: "已验证的问题、目标细分市场和竞争证据。", action: "比较替代方案，选择清晰且可持续的差异化位置。",
    prompts: [
      { label: "为谁、在什么场景下解决什么问题？", hint: "范围要足够窄，才能被验证。" },
      { label: "为什么用户会选择你，而不是现有方案？", hint: "写出具体、可感知、能持续的差异。" },
      { label: "你明确不解决什么？", hint: "给产品定位划出边界，避免功能泛化。" },
    ],
    outputs: [
      { title: "价值主张画布", detail: "用户 + 场景 + 问题 + 解决方案 + 价值。" },
      { title: "竞争定位地图", detail: "选择两个有意义的维度，找到可进入的位置。" },
      { title: "竞争差异化表", detail: "比较我方、竞争者和用户现有方案。" },
      { title: "核心价值主张", detail: "形成目标用户能理解并愿意行动的一句话。" },
      { title: "产品定位声明", detail: "明确服务对象、核心场景、核心价值和核心差异。" },
    ],
    gate: "我们是否解决了有价值的问题，用户为什么要选我们？", decisions: ["进入 MVP", "重新定位", "继续研究", "停止"],
    aiRole: "AI 策略顾问负责把研究证据改写成定位选项和竞争比较。",
    aiTasks: ["生成价值主张画布初稿", "根据竞品提炼差异化假设", "提出定位表述的反例和验证问题"],
    humanCheck: "你要选择最终定位，并用真实用户语言确认价值，而不是只选最顺耳的文案。",
  },
  {
    label: "方案与 MVP", short: "设计 MVP", title: "交付最小但完整的价值闭环", phase: "验证",
    description: "只保留核心价值，明确用户流程、交付方式、成本、收费假设和可观测指标。",
    input: "定位声明和最高风险的产品假设。", action: "确定范围、制作原型、交付最小可用体验并埋点验证。",
    prompts: [
      { label: "核心功能是什么，哪些内容明确不做？", hint: "保护价值闭环，避免功能蔓延。" },
      { label: "用户如何从获客走到获得价值？", hint: "获客 → 注册 → 使用 → 核心行为 → 价值 → 反馈。" },
      { label: "MVP 成功依赖哪些人、技术、时间和成本？", hint: "把依赖写成可执行任务。" },
      { label: "如何收费，如何判断用户得到价值？", hint: "先写价格假设、激活率、完成率和首次价值时间。" },
    ],
    outputs: [
      { title: "MVP 产品方案", detail: "核心与非核心功能、用户流程、产品流程、技术路径和交付方式。" },
      { title: "MVP 用户流程图", detail: "获客 → 注册 → 使用 → 核心行为 → 获得价值 → 反馈。" },
      { title: "MVP 开发计划", detail: "开发任务、人员、时间、成本和技术依赖。" },
      { title: "MVP 成本预算", detail: "开发、服务器、人员、渠道、运营和客服成本。" },
      { title: "收费假设 V0", detail: "免费、Freemium、订阅、一次性、按量或企业授权。" },
      { title: "MVP 验证指标", detail: "注册、激活、核心使用、完成率、首次价值时间和反馈。" },
    ],
    gate: "MVP 是否真正交付了核心价值？", decisions: ["开始第一次获客", "修改 MVP", "继续原型验证", "停止"],
    aiRole: "AI 产品经理负责把定位拆成范围、流程、任务和预算初稿。",
    aiTasks: ["生成 MVP 功能优先级和用户流程", "拆解开发任务与依赖", "模拟成本、收费和验证指标场景"],
    humanCheck: "你要确认核心价值、交付质量和预算，不让 AI 替你承诺做不到的功能。",
  },
  {
    label: "第一次获客", short: "首批用户", title: "获得第一批真实使用", phase: "获客",
    description: "找到可触达的首批用户，讲清楚产品，观察使用过程，把反馈变成真实消费者画像。",
    input: "MVP、目标用户和一个明确的成功事件。", action: "招募、演示、陪伴、观察，记录每个摩擦点。",
    prompts: [
      { label: "首批用户是谁，在哪里可以找到？", hint: "写出具体的人或组织，而不只是渠道名称。" },
      { label: "为什么他们现在愿意尝试？", hint: "明确触发点和信任机制。" },
      { label: "用户在哪一步成功或放弃？", hint: "记录行为，不用赞美代替证据。" },
      { label: "真实画像和收费假设发生了什么变化？", hint: "根据实际使用更新定位、客户和价格。" },
    ],
    outputs: [
      { title: "首批用户获取计划", detail: "用户是谁、去哪里找、何时接触、如何沟通、谁负责。" },
      { title: "首批用户池", detail: "真实潜在用户名单、状态和下一步行动。" },
      { title: "获客话术与营销素材包", detail: "产品介绍、Demo、文案、案例、FAQ 和演示材料。" },
      { title: "第一次用户测试报告", detail: "为什么使用、如何使用、失败点、喜欢点和不满点。" },
      { title: "用户反馈数据库", detail: "Bug、功能需求、使用障碍、价格、价值和服务问题。" },
      { title: "V2 真实消费者画像", detail: "实际使用产品的人，而不是想象中的受众。" },
      { title: "收费假设 V1", detail: "依据反馈调整价格、套餐、免费边界和付费点。" },
    ],
    gate: "有没有真实用户愿意主动尝试？", decisions: ["进入增长测试", "回到价值定位", "修改 MVP", "停止"],
    aiRole: "AI 获客教练负责准备沟通材料、记录反馈并找出流失节点。",
    aiTasks: ["按用户类型生成邀请话术和 Demo 讲稿", "把测试记录归类为问题、需求和障碍", "生成 V2 画像与收费假设初稿"],
    humanCheck: "你要亲自观察用户和确认反馈，不能用 AI 生成的名单或好评替代真实用户。",
  },
  {
    label: "增长与传播", short: "增长传播", title: "找到可以重复的获客方式", phase: "获客",
    description: "测试渠道和用户愿意传播的原因，追踪完整漏斗，而不是只看曝光量。",
    input: "首批用户证据和激活事件。", action: "用可比较的实验测试渠道、信息和传播机制。",
    prompts: [
      { label: "哪些渠道能以已知成本触达目标用户？", hint: "考虑 SEO、社交、社群、校园、KOL、合作、代理和广告。" },
      { label: "用户为什么愿意分享或邀请别人？", hint: "设计真实的传播动机，而不是只写口号。" },
      { label: "本周要跑哪一个增长实验？", hint: "写一个假设、一个人群和一个成功指标。" },
    ],
    outputs: [
      { title: "渠道矩阵", detail: "渠道、成本、用户量、转化率和适用场景。" },
      { title: "增长实验清单", detail: "A/B 测试、推荐奖励、裂变、内容、广告和渠道测试。" },
      { title: "传播机制设计", detail: "用户主动分享、邀请或推荐的具体原因。" },
      { title: "增长漏斗", detail: "曝光 → 点击 → 注册 → 激活 → 核心行为 → 留存 → 付费。" },
      { title: "渠道测试报告", detail: "分渠道记录获客量、成本、转化、留存和付费。" },
    ],
    gate: "是否至少有一个可以重复获客的渠道？", decisions: ["进入 PMF 分析", "更换渠道", "调整定位", "暂停"],
    aiRole: "AI 增长分析师负责设计实验、生成内容变体和比较渠道数据。",
    aiTasks: ["生成渠道矩阵和实验假设", "改写不同渠道的内容与落地页文案", "计算漏斗转化并提示异常"],
    humanCheck: "你要确认渠道数据口径、预算边界和用户同意，不把虚假曝光算成增长。",
  },
  {
    label: "数据分析与 PMF", short: "验证 PMF", title: "验证用户是否持续需要", phase: "获客",
    description: "用行为数据区分一次性尝试和持续需求，分析留存、付费、流失与推荐。",
    input: "已埋点的漏斗数据和用户分群数据。", action: "分析留存、行为、流失、推荐，形成数据化消费者画像。",
    prompts: [
      { label: "用户在漏斗的哪一步流失？", hint: "为每个转化节点填写人数和比例。" },
      { label: "谁在留存、付费并主动推荐？", hint: "比较不同批次、场景和使用深度。" },
      { label: "如果 PMF 只部分成立，下一步改什么？", hint: "明确回到定位还是回到 MVP。" },
    ],
    outputs: [
      { title: "用户漏斗数据报告", detail: "曝光、点击、注册、激活、核心行为、留存、付费、复购和推荐。" },
      { title: "用户留存分析", detail: "次日、7 日、30 日和长期留存。" },
      { title: "用户行为分析", detail: "使用频率、深度、功能使用率、核心行为和用户路径。" },
      { title: "流失分析报告", detail: "谁流失、为什么流失、在哪一步流失。" },
      { title: "推荐分析", detail: "推荐率、自发分享、NPS 和推荐来源。" },
      { title: "V3 数据化消费者画像", detail: "由真实行为数据而不是市场假设构成的画像。" },
      { title: "PMF 验证报告", detail: "用户是否持续需要产品，以及证据和反证。" },
    ],
    gate: "用户是否持续需要这个产品？", decisions: ["PMF 成立", "部分成立，继续迭代", "不成立，回到定位", "不成立，回到 MVP"],
    aiRole: "AI 数据分析师负责计算指标、分群和解释异常，帮助团队找到证据。",
    aiTasks: ["计算漏斗、留存、流失和推荐指标", "比较用户 cohort 与关键行为", "生成 PMF 报告初稿与待验证假设"],
    humanCheck: "你要确认埋点和样本质量，结合访谈解释数据，不让 AI 代替产品判断。",
  },
  {
    label: "商业模式验证", short: "验证商业", title: "证明这可以成为可持续的生意", phase: "企业化",
    description: "把客户、价值、渠道、收入、成本、风险、知识产权和合规连成一个经营模型。",
    input: "PMF 证据、定价实验和运营成本。", action: "建模、测试并压力测试单位经济和现金需求。",
    prompts: [
      { label: "谁付费，为什么付费，通过什么渠道付费？", hint: "区分使用者、购买者和付款人。" },
      { label: "CAC、LTV、毛利和回本周期的假设是什么？", hint: "能用实测数据就不用猜测，并标注估算。" },
      { label: "什么法律、政策、数据或 IP 风险会阻碍规模化？", hint: "写明责任人和解决期限。" },
    ],
    outputs: [
      { title: "商业模式画布", detail: "客户、价值、渠道、关系、收入、资源、活动、伙伴和成本。" },
      { title: "定价实验报告", detail: "不同价格、套餐、支付方式、转化率和客单价。" },
      { title: "单位经济模型", detail: "CAC → LTV → 毛利 → 回本周期，以及 ARPU、复购和流失。" },
      { title: "渠道经济学报告", detail: "比较渠道成本、获客、激活、留存、付费和毛利。" },
      { title: "收入模型", detail: "明确收入来源、收费逻辑和增长方式。" },
      { title: "成本模型与现金流预测", detail: "月度收入、成本、现金余额和盈亏平衡点。" },
      { title: "风险矩阵", detail: "按概率 × 影响评估市场、技术、财务、法律、政策、供应链、数据和人员。" },
      { title: "知识产权战略", detail: "决定专利、商标、软著、商业秘密、公开和授权。" },
      { title: "合规预审清单", detail: "规模化前必须解决的法律、监管和资质问题。" },
    ],
    gate: "这是一个可以持续赚钱的商业系统吗？", decisions: ["进入公司化", "调整商业模式", "继续实验", "暂停"],
    aiRole: "AI 财务与合规助理负责做情景测算、风险归类和文件清单。",
    aiTasks: ["生成商业模式画布与收入成本模型", "比较价格、CAC、LTV 和回本场景", "整理 IP、隐私和合规预审问题"],
    humanCheck: "你要确认财务口径和法律边界，重要合同、税务和合规事项需要专业人士复核。",
  },
  {
    label: "公司化与治理", short: "公司治理", title: "把项目变成可治理的企业", phase: "企业化",
    description: "在证据支持正式化之后，明确创始人、资本、治理、资产、财务、合同和合规边界。",
    input: "已验证的商业模式、创始团队和融资需求。", action: "把所有权、授权、控制、资产和法律运营边界写成制度。",
    prompts: [
      { label: "谁拥有哪项工作成果、资产和决策权？", hint: "分开贡献、股权和授权。" },
      { label: "融资或退出条款中有哪些不可接受的风险？", hint: "检查稀释、控制权、清算优先和业绩承诺。" },
      { label: "现在必须建立哪些资产、财务和合规控制？", hint: "为每项控制指定负责人和复核日期。" },
    ],
    outputs: [
      { title: "创始人协议", detail: "股权、出资、职责、决策、退出、离职和归属期。" },
      { title: "股权结构表 Cap Table", detail: "创始人、员工、投资人、ESOP、持股比例和各轮稀释。" },
      { title: "公司章程与治理架构", detail: "股东会、董事会、管理层、权利和决策机制。" },
      { title: "授权矩阵", detail: "财务、招聘、合同、采购、投资和融资由谁决定。" },
      { title: "资本融资文件包", detail: "估值、Term Sheet、投资协议和投资人权利安排。" },
      { title: "对赌与业绩承诺风险清单", detail: "目标、触发条件、补偿、回购、责任主体和最坏情况。" },
      { title: "并购与退出预案", detail: "股权出售、资产出售、公司出售、管理层收购、清算和整合。" },
      { title: "企业资产清单", detail: "代码、数据、商标、专利、软著、域名、合同、客户、账号和商业秘密。" },
      { title: "财务制度文件包", detail: "会计、报销、预算、付款、发票和现金管理。" },
      { title: "法律合同模板库", detail: "劳动、客户、供应商、保密、IP、数据、用户和隐私协议。" },
      { title: "业务合规清单", detail: "网络、数据、隐私、消费者权益、知识产权、广告和行业许可。" },
      { title: "公司注册清单", detail: "注册资本、股权登记、章程、税务、银行、印章和基础财务。" },
    ],
    gate: "项目是否已经成为可治理、可融资、可持续运营的企业？", decisions: ["进入组织化", "补齐治理缺口", "保持项目形态", "暂停"],
    aiRole: "AI 企业法务助理负责生成治理文件初稿、情景表和缺口清单。",
    aiTasks: ["模拟不同股权与融资结构", "生成协议、授权矩阵和资产清单模板", "按业务类型整理合规与合同待办"],
    humanCheck: "你要和创始人、投资人及律师确认权利义务，AI 不能替代签署或法律意见。",
  },
  {
    label: "组织化", short: "组织运行", title: "让工作离开创始人也能重复", phase: "企业化",
    description: "在扩大复杂度前，先把人员、岗位、流程、激励和管理可见性建立起来。",
    input: "公司职责、运营瓶颈和重复发生的工作。", action: "建立能稳定交付的最小组织和运营系统。",
    prompts: [
      { label: "下一阶段需要哪些岗位和决策？", hint: "每个岗位都写出结果、权限和汇报关系。" },
      { label: "哪些重复工作必须形成 SOP？", hint: "从产品、销售、客服、财务、法务和 HR 开始。" },
      { label: "哪些数字能说明组织是否健康？", hint: "定义 KPI/OKR 和固定复盘节奏。" },
    ],
    outputs: [
      { title: "组织架构图", detail: "CEO → 部门 → 岗位，以及汇报关系。" },
      { title: "岗位说明书", detail: "职责、权限、KPI/OKR、要求和汇报对象。" },
      { title: "招聘与培训体系", detail: "招聘、面试、Offer、入职和岗位培训。" },
      { title: "SOP 手册", detail: "产品、销售、客服、财务、法务、HR 和客户成功流程。" },
      { title: "绩效体系", detail: "KPI、OKR、晋升、薪酬和激励。" },
      { title: "部门制度", detail: "产品、技术、市场、销售、客服、财务和 HR 的运行规则。" },
      { title: "管理数据看板", detail: "收入、成本、用户、留存、销售、现金流和项目进度。" },
      { title: "授权与复盘节奏", detail: "明确例会、审批、升级和持续改进机制。" },
    ],
    gate: "创始人离开一天，公司还能正常运行吗？", decisions: ["进入规模化", "继续组织建设", "缩小范围", "暂停"],
    aiRole: "AI 运营教练负责把重复工作标准化，并生成岗位和看板初稿。",
    aiTasks: ["生成组织架构和岗位说明书", "把流程拆成 SOP、检查表和培训材料", "汇总经营指标并准备周/月报"],
    humanCheck: "你要授权真实负责人并试跑流程，不能只在文档里完成组织化。",
  },
  {
    label: "规模化", short: "规模复制", title: "证明模型可以低成本复制", phase: "企业化",
    description: "只复制已经理解的部分：渠道、区域、产品、企业销售、伙伴和运营。",
    input: "已验证的渠道经济、SOP 和运营产能。", action: "控制扩张节奏，明确每次复制的成本、门槛和风险。",
    prompts: [
      { label: "扩什么、为什么现在扩、扩张成本是多少？", hint: "写清可复制的最小单元和扩张阈值。" },
      { label: "下一步进入哪个渠道、区域或人群？", hint: "写出依赖条件和学习计划。" },
      { label: "规模翻倍时最先会坏在哪里？", hint: "测试人员、产品、供应、伙伴和现金约束。" },
    ],
    outputs: [
      { title: "规模化战略", detail: "扩什么、为什么扩、什么时候扩、扩张成本和风险。" },
      { title: "渠道与区域扩张计划", detail: "已验证渠道 → 新渠道 → 新区域 → 新人群。" },
      { title: "产品矩阵", detail: "核心产品 → 衍生产品 → 增值服务 → 产品生态。" },
      { title: "品牌战略", detail: "品牌定位、品牌资产、传播和认知。" },
      { title: "企业客户开发体系", detail: "B 端销售、大客户、商务合作和战略客户。" },
      { title: "战略合作伙伴地图", detail: "渠道、平台、技术、供应链、资本和企业伙伴。" },
      { title: "国际化方案", detail: "市场、本地化、法律、渠道、支付、税务和数据。" },
      { title: "复制单元验收表", detail: "用统一指标验收新区域、新渠道或新产品是否可复制。" },
    ],
    gate: "商业模型是否可以用更低的边际成本复制？", decisions: ["进入资本市场评估", "修复复制瓶颈", "选择性扩张", "停止扩张"],
    aiRole: "AI 规模化顾问负责做扩张情景、伙伴匹配和复制单元检查。",
    aiTasks: ["生成区域、渠道和产品扩张方案", "比较新增成本、收入和风险", "整理伙伴候选与尽调问题"],
    humanCheck: "你要先用小范围试点验证可复制性，再决定投入更多资金和组织。",
  },
  {
    label: "上市与资本市场（可选）", short: "资本市场", title: "判断资本市场是否服务战略", phase: "资本",
    description: "上市不是必经终点。先比较战略需要、成本、风险和替代方案，再决定 IPO 或其他资本事件。",
    input: "规模指标、治理文件、财务记录和长期战略目标。", action: "评估准备度，选择风险最低且与战略匹配的资本路径。",
    prompts: [
      { label: "资本市场事件会为公司带来什么？", hint: "区分增长、流动性、信誉和创始人退出需求。" },
      { label: "接受外部审查前必须修正什么？", hint: "检查股权、财务、治理、披露和内控。" },
      { label: "如果不上市，什么替代方案更合适？", hint: "比较私募融资、战略投资、并购和继续经营。" },
    ],
    outputs: [
      { title: "上市可行性报告", detail: "上市目的、基本条件、成本、风险和替代方案。" },
      { title: "股权规范报告", detail: "历史股权、代持、纠纷和股权结构问题。" },
      { title: "财务规范报告", detail: "财务制度、审计、税务和内部控制。" },
      { title: "公司治理规范报告", detail: "董事会、专门委员会、信息披露和内控。" },
      { title: "上市辅导计划", detail: "中介机构、申报、审核、发行和上市准备。" },
      { title: "IPO 申报材料体系", detail: "按目标市场整理申报资料、证据和责任人。" },
      { title: "上市后资本运作计划", detail: "再融资、并购、定增和配股等安排。" },
      { title: "投资者关系体系", detail: "披露日历、投资者沟通和责任追踪。" },
    ],
    gate: "进入资本市场是否符合企业长期战略？", decisions: ["准备资本路径", "选择非上市方案", "继续经营", "不追求上市"],
    aiRole: "AI 资本分析师负责整理准备度、情景和材料索引，不替代中介机构意见。",
    aiTasks: ["生成上市准备度与缺口清单", "比较融资、并购和上市的情景", "整理披露、审计和投资者沟通材料目录"],
    humanCheck: "你要由董事会、股东和专业中介决定是否上市，并承担真实披露责任。",
  },
  {
    label: "战略迭代", short: "战略迭代", title: "复盘并开始下一轮机会", phase: "战略",
    description: "持续回看用户、市场、产品、行业、政策、技术和财务，把新发现放回机会池。",
    input: "完整证据树、经营指标和外部变化。", action: "复盘假设、绘制机会与风险地图，选择下一项有证据的行动。",
    prompts: [
      { label: "哪些事情做对了，哪些做错了？", hint: "把结果和故事分开写。" },
      { label: "哪些假设被证伪，外部发生了什么变化？", hint: "包括用户、竞争者、政策、技术和产业链。" },
      { label: "下一项机会或产品决策是什么？", hint: "转成有负责人、有期限的实验。" },
    ],
    outputs: [
      { title: "年度战略报告", detail: "用户、市场、产品、行业、竞争、产业链、政策、技术和财务。" },
      { title: "战略机会地图", detail: "新市场、新产品、新技术、新用户、新商业模式和新产业链位置。" },
      { title: "战略风险地图", detail: "技术替代、新竞争、政策、用户、产业链和宏观变化。" },
      { title: "产品迭代路线图", detail: "当前产品 → 下一版本 → 新产品 → 产品矩阵。" },
      { title: "战略复盘报告", detail: "做对什么、做错什么、哪些假设被证伪、出现了什么新机会。" },
      { title: "下一轮机会池", detail: "把战略发现带回第 1 步，开始新的机会循环。" },
    ],
    gate: "下一项有证据支持的战略动作是什么？", decisions: ["开始新的机会循环", "加倍投入当前模型", "改变方向", "暂停"],
    aiRole: "AI 战略复盘师负责汇总长期证据、发现变化并提出下一轮选项。",
    aiTasks: ["生成年度战略与经营复盘", "绘制机会地图、风险地图和产品路线图", "把新机会登记回第 1 步机会池"],
    humanCheck: "你要对战略取舍负责，并确认新机会是否值得重新投入验证。",
  },
];

const WORKFLOW_STEPS = STEPS.map((step, index) => ({ ...step, ...STEP_COPY[index] }));

type DraftState = {
  current: number;
  force: string;
  answers: Record<string, string>;
  outputNotes: Record<string, string>;
  outputDone: Record<string, boolean>;
  validationDone: Record<string, boolean>;
  validationNotes: Record<string, string>;
  files: string[];
  gates: Record<string, string>;
  reviewed: Record<string, boolean>;
};

const storageKey = "campusmate.entrepreneurship";
const initialDraft: DraftState = { current: 0, force: "demand", answers: {}, outputNotes: {}, outputDone: {}, validationDone: {}, validationNotes: {}, files: [], gates: {}, reviewed: {} };

function routeStep(value: string | null) {
  if (!value) return null;
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= 1 && parsed <= WORKFLOW_STEPS.length ? parsed - 1 : null;
}

function safeDraft(value: unknown): DraftState {
  if (!value || typeof value !== "object") return initialDraft;
  const parsed = value as Partial<DraftState>;
  return {
    ...initialDraft,
    ...parsed,
    current: typeof parsed.current === "number" && Number.isFinite(parsed.current) ? Math.max(0, Math.min(WORKFLOW_STEPS.length - 1, parsed.current)) : 0,
    force: typeof parsed.force === "string" && FORCES.some((item) => item.id === parsed.force) ? parsed.force : initialDraft.force,
    answers: parsed.answers && typeof parsed.answers === "object" ? parsed.answers : {},
    outputNotes: parsed.outputNotes && typeof parsed.outputNotes === "object" ? parsed.outputNotes : {},
    outputDone: parsed.outputDone && typeof parsed.outputDone === "object" ? parsed.outputDone : {},
    validationDone: parsed.validationDone && typeof parsed.validationDone === "object" ? parsed.validationDone : {},
    validationNotes: parsed.validationNotes && typeof parsed.validationNotes === "object" ? parsed.validationNotes : {},
    files: Array.isArray(parsed.files) ? parsed.files.filter((item): item is string => typeof item === "string").slice(0, 8) : [],
    gates: parsed.gates && typeof parsed.gates === "object" ? parsed.gates : {},
    reviewed: parsed.reviewed && typeof parsed.reviewed === "object" ? parsed.reviewed : {},
  };
}

export default function EntrepreneurshipPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const fileInput = useRef<HTMLInputElement>(null);
  const [draft, setDraft] = useState<DraftState>(initialDraft);
  const [expandedOutput, setExpandedOutput] = useState("");
  const [expandedValidation, setExpandedValidation] = useState(VALIDATION_MODULES[0].title);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    document.body.classList.add("venture-black");
    return () => document.body.classList.remove("venture-black");
  }, []);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(storageKey);
      if (raw) setDraft(safeDraft(JSON.parse(raw)));
    } catch {
      // Local progress is optional.
    } finally {
      setHydrated(true);
    }
  }, []);

  // URL navigation is authoritative for the visible stage, even when an older
  // local draft exists. This keeps copied/shared stage links deterministic.
  useEffect(() => {
    if (!hydrated) return;
    const nextStep = routeStep(searchParams.get("step"));
    const nextForce = FORCES.some((item) => item.id === searchParams.get("force")) ? searchParams.get("force")! : null;
    if (nextStep === null && nextForce === null) return;
    setDraft((previous) => {
      const current = nextStep ?? previous.current;
      const force = nextForce ?? previous.force;
      return current === previous.current && force === previous.force ? previous : { ...previous, current, force };
    });
  }, [hydrated, searchParams]);

  useEffect(() => {
    if (!hydrated) return;
    try { window.localStorage.setItem(storageKey, JSON.stringify(draft)); } catch {
      // Local progress is optional.
    }
  }, [draft, hydrated]);

  useEffect(() => {
    if (!hydrated) return;
    document.querySelector<HTMLElement>(`[data-step-index="${draft.current}"]`)?.scrollIntoView({ behavior: "instant", block: "nearest", inline: "center" });
  }, [draft.current, hydrated]);

  const step = WORKFLOW_STEPS[draft.current];
  const selectedForce = FORCES.find((item) => item.id === draft.force) || FORCES[0];
  const prompts = step.special === "entry" ? selectedForce.prompts : step.prompts;
  const completedSteps = useMemo(() => WORKFLOW_STEPS.filter((_, index) => Boolean(draft.gates[String(index)])).length, [draft.gates]);
  const progress = Math.round((completedSteps / WORKFLOW_STEPS.length) * 100);
  const update = (change: Partial<DraftState>) => setDraft((previous) => ({ ...previous, ...change }));
  const answerKey = (index: number) => draft.current === 0 ? `s0:${draft.force}:${index}` : `s${draft.current}:${index}`;
  const outputKey = (title: string) => `s${draft.current}:${title}`;

  function updateAnswer(index: number, value: string) {
    update({ answers: { ...draft.answers, [answerKey(index)]: value }, reviewed: { ...draft.reviewed, [String(draft.current)]: false } });
  }

  function syncRoute(index: number, force = draft.force) {
    const query = new URLSearchParams();
    query.set("step", String(index + 1));
    if (index === 0) query.set("force", force);
    router.push(`/entrepreneurship?${query.toString()}`, { scroll: false });
  }

  function chooseForce(id: string) {
    update({ force: id, reviewed: { ...draft.reviewed, "0": false } });
    syncRoute(0, id);
  }
  function chooseStep(index: number) {
    const next = Math.max(0, Math.min(WORKFLOW_STEPS.length - 1, index));
    setDraft((previous) => ({ ...previous, current: next }));
    setExpandedOutput("");
    setExpandedValidation(next === 1 ? VALIDATION_MODULES[0].title : "");
    syncRoute(next);
  }

  function updateOutput(title: string, note: string) {
    update({ outputNotes: { ...draft.outputNotes, [outputKey(title)]: note }, reviewed: { ...draft.reviewed, [String(draft.current)]: false } });
  }

  function toggleOutput(title: string, done: boolean) { update({ outputDone: { ...draft.outputDone, [outputKey(title)]: done }, reviewed: { ...draft.reviewed, [String(draft.current)]: false } }); }
  function updateValidation(title: string, note: string) { update({ validationNotes: { ...draft.validationNotes, [title]: note }, reviewed: { ...draft.reviewed, "1": false } }); }
  function toggleValidation(title: string, done: boolean) { update({ validationDone: { ...draft.validationDone, [title]: done }, reviewed: { ...draft.reviewed, "1": false } }); }
  function chooseGate(decision: string) { update({ gates: { ...draft.gates, [String(draft.current)]: decision }, reviewed: { ...draft.reviewed, [String(draft.current)]: false } }); }
  function markStageReady() { update({ reviewed: { ...draft.reviewed, [String(draft.current)]: true } }); }
  function onFiles(event: ChangeEvent<HTMLInputElement>) {
    const names = Array.from(event.target.files || []).map((file) => file.name).slice(0, 8);
    if (names.length) update({ files: Array.from(new Set([...draft.files, ...names])).slice(0, 8) });
    event.target.value = "";
  }

  return <div className="shell venture-shell">
    <PageHeading eyebrow="创业操作系统" title="创新创业路径" description="从机会发现到战略迭代，把每一步的输入、证据、产出和决策都沉淀下来。">
      <Link className="button secondary" href="/data?path=entrepreneurship&view=sources" title="查看创业政策与参考来源"><Icon name="book" size={15} /><span>来源库</span></Link>
    </PageHeading>

    <section className="venture-journey" aria-label="创新创业十三步">
      <div className="venture-journey-head"><div><p className="eyebrow">13 个步骤</p><h2><Icon name="arrow" size={18} />创业工作流</h2></div><span className="venture-progress" title={`${completedSteps} / ${WORKFLOW_STEPS.length} 个决策闸门已完成`}><strong>{progress}%</strong><small>{completedSteps}/{WORKFLOW_STEPS.length}</small></span></div>
      <div className="venture-steps-scroll" tabIndex={0} aria-label="选择创业步骤">
        <div className="venture-steps" role="list">
         {WORKFLOW_STEPS.map((item, index) => <button type="button" role="listitem" key={item.code} data-step-index={index} className={`venture-step ${index === draft.current ? "active" : ""} ${draft.gates[String(index)] ? "done" : ""}`} onClick={() => chooseStep(index)} aria-current={index === draft.current ? "step" : undefined} aria-label={`前往第 ${index + 1} 步：${item.label}`}>
          <span className="venture-step-node" title={`第 ${index + 1} 步`}><Icon name={draft.gates[String(index)] ? "check" : STEP_ICONS[index]} size={14} /></span><span className="venture-step-label">{item.short}</span>
        </button>)}
        </div>
      </div>
    </section>

    <section className="venture-framework" aria-label="阶段框架">
      <div title={step.input}><span><Icon name="book" size={14} /></span><strong>输入</strong></div>
      <div title={step.action}><span><Icon name="spark" size={14} /></span><strong>行动</strong></div>
      <div title={`${step.outputs.length} 项证据产出`}><span><Icon name="file" size={14} /></span><strong>产出 <em>{step.outputs.length}</em></strong></div>
      <div className="is-gate" title={step.gate}><span><Icon name="check" size={14} /></span><strong>闸门 {draft.current + 1}</strong></div>
    </section>

    <div className="venture-workspace">
      <section className="venture-main-panel" aria-labelledby="venture-step-title">
        <header className="venture-panel-header"><div><p className="eyebrow"><Icon name={STEP_ICONS[draft.current]} size={13} /> 第 {String(draft.current + 1).padStart(2, "0")} 步 / {step.code} · {step.phase}</p><h2 id="venture-step-title">{step.title}</h2></div><span className="venture-current-mark"><Icon name="spark" size={15} />当前步骤</span></header>

        {step.special === "entry" && <section className="venture-entry-section"><div className="venture-section-label"><span><Icon name="search" size={14} />切入路径</span><small>选择一个起点</small></div><div className="venture-entry-grid">{FORCES.map((item) => <button type="button" key={item.id} className={`venture-entry-card ${selectedForce.id === item.id ? "active" : ""}`} onClick={() => chooseForce(item.id)} aria-pressed={selectedForce.id === item.id} title={`${item.detail} ${item.risk}`}><span className="venture-force-icon"><Icon name={item.id === "demand" ? "users" : item.id === "market" ? "search" : item.id === "product" ? "file" : "spark"} size={16} /></span><span><strong>{item.title}</strong></span><Icon name="chevron" size={14} /></button>)}</div><div className="venture-entry-brief"><div title={selectedForce.evidence}><span className="settings-label"><Icon name="book" size={13} />证据</span></div><div title={selectedForce.risk}><span className="settings-label"><Icon name="shield" size={13} />风险</span></div></div></section>}

        {step.special === "validation" && <section className="venture-validation-section"><div className="venture-section-label"><span><Icon name="check" size={14} />验证清单</span><small>{Object.values(draft.validationDone).filter(Boolean).length} / {VALIDATION_MODULES.length}</small></div><div className="venture-validation-grid">{VALIDATION_MODULES.map((item, index) => { const open = expandedValidation === item.title; return <article className={`venture-validation-card ${draft.validationDone[item.title] ? "complete" : ""}`} key={item.title} title={item.detail}><div className="venture-output-head"><label><input type="checkbox" checked={Boolean(draft.validationDone[item.title])} onChange={(event) => toggleValidation(item.title, event.target.checked)} /><span><strong><Icon name={index % 2 ? "file" : "search"} size={13} />{String(index + 1).padStart(2, "0")} {item.title}</strong></span></label><button type="button" className="icon-button" aria-label={`${open ? "收起" : "展开"} ${item.title}`} aria-expanded={open} onClick={() => setExpandedValidation(open ? "" : item.title)}><Icon name={open ? "close" : "chevron"} size={14} /></button></div>{open && <textarea value={draft.validationNotes[item.title] || ""} onChange={(event) => updateValidation(item.title, event.target.value)} placeholder="记录证据、结论与待核验项…" maxLength={2000} />}</article>; })}</div></section>}

        <div className="venture-prompt-head"><div><span className="venture-kicker"><Icon name="file" size={13} />{step.short}</span><h3>{step.special === "entry" ? `${selectedForce.title}问题` : "关键问题"}</h3></div><span className="venture-required"><Icon name="clock" size={12} />草稿</span></div>
        <div className="venture-prompts">{prompts.map((prompt, index) => <label className="venture-prompt" key={prompt.label} title={prompt.hint}><span><Icon name="chevron" size={12} />{prompt.label}</span><small>{prompt.hint}</small><textarea value={draft.answers[answerKey(index)] || ""} onChange={(event) => updateAnswer(index, event.target.value)} placeholder="写下你的判断、数据或链接…" maxLength={1600} /></label>)}</div>

        <section className="venture-ai-section"><div className="venture-section-label"><span><Icon name="spark" size={14} />AI 协助</span><small>AI 先整理，你来确认</small></div><div className="venture-ai-card"><div><strong>{step.aiRole}</strong><p>适合先交给 AI 的工作：</p><ul>{step.aiTasks.map((task) => <li key={task}>{task}</li>)}</ul></div><div className="venture-ai-footer"><span><Icon name="shield" size={13} />你需要确认：{step.humanCheck}</span><Link className="button secondary" href={`/agent?intent=paths&path=entrepreneurship&step=${draft.current + 1}`} title="让 AI 继续整理本步骤">让 AI 继续起草<Icon name="arrow" size={14} /></Link></div></div></section>

        <section className="venture-output-section"><div className="venture-section-label"><span><Icon name="file" size={14} />本步产出</span><small>{step.outputs.length} 项</small></div><div className="venture-output-grid">{step.outputs.map((item, index) => { const key = outputKey(item.title); const open = expandedOutput === key; return <article className={`venture-output-card ${draft.outputDone[key] ? "complete" : ""}`} key={item.title} title={item.detail}><div className="venture-output-head"><label><input type="checkbox" checked={Boolean(draft.outputDone[key])} onChange={(event) => toggleOutput(item.title, event.target.checked)} /><span><strong><Icon name={index % 3 === 0 ? "file" : index % 3 === 1 ? "link" : "check"} size={13} />{String(index + 1).padStart(2, "0")} {item.title}</strong></span></label><button type="button" className="icon-button" aria-label={`${open ? "收起" : "展开"} ${item.title}`} aria-expanded={open} onClick={() => setExpandedOutput(open ? "" : key)}><Icon name={open ? "close" : "chevron"} size={14} /></button></div>{open && <textarea value={draft.outputNotes[key] || ""} onChange={(event) => updateOutput(item.title, event.target.value)} placeholder="记录证据、结论与待核验项…" maxLength={2400} />}</article>; })}</div></section>

        <section className="venture-upload-section"><div className="venture-section-label"><span><Icon name="file" size={14} />参考材料</span><small>DOCX · XLSX · TXT · PDF</small></div><div className="venture-upload" title="仅保存文件名，文件不会被上传或读取。"><Icon name="file" size={21} /><div><strong>添加参考材料</strong></div><input ref={fileInput} className="sr-only" type="file" multiple accept=".doc,.docx,.xls,.xlsx,.txt,.pdf" onChange={onFiles} /><button type="button" className="button secondary" onClick={() => fileInput.current?.click()}><Icon name="plus" size={14} />添加</button></div>{draft.files.length > 0 && <ul className="venture-files" aria-label="已添加的参考材料">{draft.files.map((file) => <li key={file}><Icon name="file" size={14} /><span>{file}</span><button type="button" className="venture-file-remove" onClick={() => update({ files: draft.files.filter((item) => item !== file) })} aria-label={`移除 ${file}`}><Icon name="close" size={13} /></button></li>)}</ul>}</section>

        <section className="venture-gate"><div><p className="eyebrow"><Icon name="check" size={13} />决策闸门 {draft.current + 1}</p><h3>{step.gate}</h3></div><div className="venture-decisions">{step.decisions.map((decision) => <button type="button" key={decision} className={draft.gates[String(draft.current)] === decision ? "selected" : ""} onClick={() => chooseGate(decision)}><Icon name={draft.gates[String(draft.current)] === decision ? "check" : "chevron"} size={13} />{decision}</button>)}</div>{draft.gates[String(draft.current)] && <p className="venture-gate-result" role="status"><Icon name="check" size={13} />{draft.gates[String(draft.current)]}</p>}</section>

        <footer className="venture-actions"><button type="button" className="button primary" onClick={markStageReady}><Icon name="check" size={15} />标记为待复核</button>{draft.reviewed[String(draft.current)] && <span className="venture-review-status" role="status"><Icon name="check" size={14} />草稿已标记为待复核</span>}<div className="venture-step-actions"><button type="button" className="button quiet" onClick={() => chooseStep(draft.current - 1)} disabled={draft.current === 0}><Icon name="arrow" size={14} />上一步</button><button type="button" className="button secondary" onClick={() => chooseStep(draft.current + 1)} disabled={draft.current === WORKFLOW_STEPS.length - 1} title={draft.current === WORKFLOW_STEPS.length - 1 ? "已经是最后一步" : "Next step：前往下一步"}>下一步<Icon name="arrow" size={14} /></button></div></footer>
      </section>

      <aside className="venture-aside" aria-label="步骤工具"><section className="venture-guide"><span className="venture-guide-icon"><Icon name="book" size={18} /></span><p className="eyebrow">使用指南</p><h3>{step.short}</h3><ol><li title="记录本步输入"><Icon name="book" size={14} /><span>输入</span></li><li title="附上证据"><Icon name="file" size={14} /><span>证据</span></li><li title="选择下一步动作"><Icon name="check" size={14} /><span>闸门</span></li></ol></section><section className="venture-help"><div><Icon name="spark" size={17} /><h3>让 AI 协助</h3></div><p>AI 可以先整理材料、测算和文案，你保留事实核验与关键决策。</p><Link href={`/agent?intent=paths&path=entrepreneurship&step=${draft.current + 1}`} className="section-link" title="让 AI 提供第二视角">打开 AI 助手<Icon name="arrow" size={14} /></Link></section><section className="venture-source"><span className="eyebrow"><Icon name="check" size={13} />当前决策</span><strong>{draft.gates[String(draft.current)] || "尚未选择"}</strong><Link href="/knowledge" className="section-link" title="打开来源库">查找原文<Icon name="arrow" size={14} /></Link></section></aside>
    </div>
  </div>;
}

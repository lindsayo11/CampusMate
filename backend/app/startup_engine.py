"""Deterministic startup planning: user facts, explicit assumptions, reviewable drafts."""
from decimal import Decimal, ROUND_CEILING, localcontext
from .startup_schemas import Brief

TITLES={
    'business_model':'商业模式画布','architecture':'商业架构与业务链路','equity':'股权与治理设计',
    'bp':'商业计划书 BP','user_agreement':'用户服务协议草稿','privacy':'隐私告知与数据处理草稿',
    'exit':'合伙人进入与退出机制','ipo':'资本化与 IPO 准备建议','compliance':'主体与经营合规清单',
    'ip':'知识产权与壁垒规划','finance':'财务假设与现金流规划','fundraising':'融资准备与尽调清单',
    'organization':'人才与组织设计','validation':'MVP 与市场验证计划',
}
SOURCES=[
    {'id':'company','title':'中华人民共和国公司法（2023 修订）','url':'https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/fgs/art/2023/art_067c072db6ef4679a2e0180996be4cf8.html','scope':'中国大陆公司治理、出资及股权事项'},
    {'id':'privacy','title':'中华人民共和国个人信息保护法（人大英文全文）','url':'https://en.npc.gov.cn.cdurl.cn/2021-12/29/c_694559.htm','scope':'中国大陆个人信息处理；适用性需核对'},
    {'id':'ipo','title':'证监会首次公开发行股票注册管理办法','url':'https://www.csrc.gov.cn/csrc/c101953/c7121923/content.shtml','scope':'中国大陆 IPO 注册规则入口'},
    {'id':'sse','title':'上海证券交易所主板上市规则入口','url':'https://www.sse.com.cn/lawandrules/sselawsrules/stocks/mainipo/','scope':'具体版本、板块标准需在申请时核对'},
    {'id':'szse','title':'深圳证券交易所股票发行规则入口','url':'https://www.szse.cn/lawrules/rule/stock/issue/index.html','scope':'具体版本、板块标准需在申请时核对'},
]
REFERENCE_DATE='2026-10-02'
ROADMAP=[
    ('s01','商业顶层设计','business_model',['写清客户痛点与购买理由','完成九要素画布','用真实访谈和付费实验验证假设']),
    ('s02','公司主体与经营合规','compliance',['选择主体和经营地区','核对注册资本、出资计划与住所','核对行业许可和登记要求']),
    ('s03','股权与公司治理','equity',['记录贡献与现有股权','测算期权池和融资稀释','确认决策规则、成熟条件和退出机制']),
    ('s04','知识产权与核心壁垒','ip',['确认职务成果和代码权属','梳理专利、商标、著作权及商业秘密','发布前核对保密及申请策略']),
    ('s05','财务与税务','finance',['建立收支与现金台账','测算盈亏平衡和资金可维持时间','核对税务身份与优惠适用条件']),
    ('s06','融资全流程','fundraising',['准备 BP 和证据材料','明确融资目标及资金用途','比较条款并准备尽调资料']),
    ('s07','人才与组织','organization',['确认核心岗位和责任人','核对劳动合同与社保安排','设计薪酬、绩效与激励条件']),
    ('s08','市场与业务落地','validation',['定义 MVP 最小交付范围','执行客户访谈和付费测试','记录获客成本、留存与竞品差异']),
    ('s09','合规与风险防控','user_agreement',['核对合同、用户协议和隐私告知','建立数据及权限流程','演练现金流、人员及业务中断预案']),
    ('s10','资本化与退出','ipo',['比较并购、转让、回购和 IPO','整理治理、财务与合规证据','按目标市场最新规则逐项核验']),
]
FIELDS=[
    ('overview','summary','项目一句话与目标'),('overview','industry','行业'),('overview','target_market','目标市场与地区'),
    ('overview','team','团队真实经历'),('overview','traction','已有验证与运营数据'),('overview','evidence','证据记录与来源'),
    ('business','customers','客户细分'),('business','problem','客户痛点'),('business','solution','价值主张与解决方案'),
    ('business','revenue_model','收入来源与定价方式'),('business','costs','成本结构'),('business','channels','获客渠道'),
    ('business','resources','关键资源'),('business','activities','关键业务'),('business','partners','重要合作'),
    ('business','moat','壁垒设计'),('business','competitors','竞品与差异'),
    ('documents','entity_name','经营主体名称'),('documents','service_scope','服务范围与交付内容'),
    ('documents','data_practices','实际收集的数据、目的、保存和共享方式'),('documents','refund_policy','费用与退款规则'),
    ('documents','contact','客服与权利请求联系方式'),('documents','funding_use','融资用途与里程碑'),
]


def number(value):
    return float(value.quantize(Decimal('0.000001')))


def calculations(brief:Brief):
    f=brief.finance
    with localcontext() as ctx:
        ctx.prec=60
        missing=[name for name in ['price','monthly_units','variable_cost','fixed_cost','cash'] if getattr(f,name) is None]
        economics={'missing_fields':missing,'currency':'用户统一输入的同一币种；不自动换汇',
            'assumptions':['销量和价格固定的单产品模型','单位变动成本不含固定支出','不含税费、折旧、应收应付与营运资本变化；不等于会计利润或真实现金流']}
        if not missing:
            contribution=f.price-f.variable_cost
            revenue=f.price*f.monthly_units
            result=contribution*f.monthly_units-f.fixed_cost
            burn=max(-result,Decimal(0))
            economics.update(monthly_revenue=number(revenue),unit_contribution=number(contribution),
                contribution_margin_pct=number(contribution/f.price*100) if f.price>0 else None,
                monthly_operating_result=number(result),monthly_burn=number(burn),
                runway_months=number(f.cash/burn) if burn>0 else None,
                break_even_units=int((f.fixed_cost/contribution).to_integral_value(rounding=ROUND_CEILING)) if contribution>0 else None,
                runway_note='净消耗为零，简化模型不计算有限资金期限' if burn==0 else '现金 / 月净消耗，未计融资和额外资本支出')
            projections=[]
            for label,factor in [('销量下降20%',Decimal('.8')),('基准',Decimal(1)),('销量上升20%',Decimal('1.2'))]:
                units=f.monthly_units*12*factor
                fixed=f.fixed_cost*12
                for year in range(1,6):
                    revenue=units*f.price;cost=units*f.variable_cost+fixed
                    projections.append({'scenario':label,'year':year,'revenue':number(revenue),
                        'cost':number(cost),'operating_result':number(revenue-cost)})
                    units*=1+f.annual_volume_growth_pct/100
                    fixed*=1+f.annual_cost_growth_pct/100
            economics['projections']=projections
        cap={'rows':[], 'assumptions':['单轮新增普通权益资金；没有老股转让、可转债、SAFE、优先股特殊权利',
            '新期权池先由现有股东同比例稀释，再按投前估值融资；现有持股须合计100%',
            '表中是经济持股测算，不推导实际表决权、董事席位或控制权']}
        if brief.founders:
            if f.investment and f.pre_money is None:
                cap['missing_fields']=['pre_money']
            else:
                investment=f.investment or Decimal(0)
                investor=investment/(f.pre_money+investment) if investment else Decimal(0)
                pool=f.new_pool_pct/100
                rows=[{'name':x.name,'role':x.role,'before_pct':number(x.percent),
                    'after_pct':number(x.percent*(1-pool)*(1-investor))} for x in brief.founders]
                if pool: rows.append({'name':'新增期权池（未分配）','role':'激励预留','before_pct':0,'after_pct':number(pool*(1-investor)*100)})
                if investor: rows.append({'name':'本轮投资人','role':'新增投资','before_pct':0,'after_pct':number(investor*100)})
                # Display rounding adjustment only; no change to economic formulas.
                total=sum(Decimal(str(r['after_pct'])) for r in rows)
                rows[-1]['after_pct']=number(Decimal(str(rows[-1]['after_pct']))+100-total)
                cap.update(rows=rows,total_pct=100,post_money=number(f.pre_money+investment) if f.pre_money is not None else None)
        else:cap['missing_fields']=['founders']
        return {'economics':economics,'cap_table':cap}


def field(brief,key):
    value=getattr(brief,key,'')
    return value if value else f'【待填写：{next((label for _,name,label in FIELDS if name==key),key)}】'


def section(title,*parts):
    return '## '+title+'\n\n'+'\n\n'.join(parts)+'\n'


def sources_for(kind):
    ids={'equity':['company'],'exit':['company'],'compliance':['company'],'user_agreement':['company','privacy'],
        'privacy':['privacy'],'ipo':['company','ipo','sse','szse'],'organization':['company']}.get(kind,[])
    return [{**s,'reference_date':REFERENCE_DATE} for s in SOURCES if s['id'] in ids]


def build_draft(brief:Brief,kind):
    """Generate a usable, editable draft; no unsupplied market/legal fact is invented."""
    title=f'{brief.name} · {TITLES[kind]}'
    F=lambda key:field(brief,key)
    relevant={
        'business_model':{'customers','problem','solution','revenue_model','costs','channels','resources','activities','partners','moat'},
        'architecture':{'solution','activities','resources','partners','moat','team'},
        'bp':{'summary','customers','target_market','problem','solution','revenue_model','channels','costs','competitors','moat','team','traction','evidence','funding_use'},
        'equity':{'team','entity_name','evidence'},'exit':{'entity_name','team','evidence'},
        'user_agreement':{'entity_name','service_scope','revenue_model','refund_policy','data_practices','contact'},
        'privacy':{'entity_name','data_practices','contact'},'ipo':{'entity_name','target_market','traction','evidence'},
        'compliance':{'entity_name','service_scope','target_market','evidence'},
        'ip':{'resources','moat','evidence'},'finance':{'costs','revenue_model','evidence'},
        'fundraising':{'funding_use','traction','team','evidence'},'organization':{'team','activities'},
        'validation':{'customers','problem','solution','traction','competitors'},
    }
    missing=[label for _,key,label in FIELDS if key in relevant[kind] and not getattr(brief,key)]
    calc=calculations(brief)
    sections=[]
    if kind=='business_model':
        for label,key in [('价值主张','solution'),('客户细分','customers'),('收入来源','revenue_model'),('成本结构','costs'),('获客渠道','channels'),('关键资源','resources'),('关键业务','activities'),('重要合作','partners'),('壁垒设计','moat')]:
            sections.append(section(label,'项目输入：'+F(key),'验证问题：这项安排是否有可核验的成本、责任人、交付结果或客户证据？记录证据与下一次实验。'))
        sections.append(section('备选商业模式与取舍','设计候选（待验证）：订阅收费关注持续使用与留存；按次收费关注触发频率和单次价值；企业服务包关注交付成本、销售周期和回款。根据客户与产品选择，不能只凭行业名称决定。','当前收费设计：'+F('revenue_model'),'先比较付费对象、收费单位、渠道成本和扩张瓶颈，再做小规模付费试验。'))
    elif kind=='architecture':
        for label,role,cost,output in [('获客','市场/渠道负责人','投放、人力与渠道分成','有效需求'),('评估与转化','销售/产品负责人','销售时间、试用和咨询','明确范围的订单'),('交付','产品/技术/服务负责人','人工、云服务与履约成本','可验收的服务结果'),('售后与留存','客服/客户成功负责人','支持、退款与维护','问题关闭与复购'),('结算与复盘','财务/运营负责人','收款费用、坏账及复盘时间','现金回款和业务改进')]:
            sections.append(section(label,f'建议责任角色：{role}（实际人员待指定）。成本项：{cost}。交接产物：{output}。',f'项目服务：{F("solution")}','待决定：输入材料、服务时限、验收条件、异常升级路径与指标负责人。'))
        sections.append(section('资源、合作与组织边界','关键资源：'+F('resources'),'重要合作：'+F('partners'),'壁垒：'+F('moat'),'将核心能力、外包能力和合作能力分别登记；明确知识产权、客户数据和质量责任归属。'))
    elif kind=='bp':
        sections=[section('项目概述',F('summary'),f'目标客户：{F("customers")}；目标地区：{F("target_market")}。'),
            section('市场痛点与规模',F('problem'),'市场规模【待核验】：采用客户数量 × 年均支出的自下而上测算，区分总市场、可服务市场和近期可获得市场；必须附出处、统计口径与日期。'),
            section('解决方案与产品',F('solution'),'阶段：'+brief.stage+'；功能范围、演示链接和交付边界【待补充】。'),
            section('商业模式','收入：'+F('revenue_model'),'渠道：'+F('channels'),'成本：'+F('costs')),
            section('竞品与差异化',F('competitors'),'壁垒：'+F('moat'),'竞品价格、用户和能力由可核验材料支持，不声称“无竞品”。'),
            section('核心团队',F('team'),'角色、投入时间、贡献与真实成果待逐人核对；不编造履历。'),
            section('运营验证与规划',F('traction'),'证据：'+F('evidence'),'建议里程碑：客户问题访谈 → 小范围付费交付 → 复购/留存验证；数量与日期由项目负责人填写。'),
            section('财务预测',finance_text(calc),'五年预测是简化情景测算；补充税费、资产投入、回款和融资后才能编制正式报表。'),
            section('融资与资金用途',F('funding_use'),'融资金额假设：'+str(brief.finance.investment if brief.finance.investment is not None else '待填写'),'资金用途按研发、获客、交付和储备拆分，分别对应里程碑和证据；市场估值未由系统验证。'),
            section('风险与附件','列出市场验证、现金流、人员、知识产权、数据及监管风险。附经营与财务证据、股权表和版本日期。')]
    elif kind=='equity':
        rows=calc['cap_table'].get('rows',[])
        table='\n'.join(f'- {x["name"]}：当前 {x["before_pct"]}% → 场景测算后 {x["after_pct"]}%' for x in rows) or '【待填写股东比例，合计100%】'
        sections=[section('现有贡献与股权',table,'\n'.join(f'- {f.name} / {f.role or "角色待填"} / 贡献：{f.contribution or "待记录"}' for f in brief.founders)),
            section('融资与激励安排','\n'.join(calc['cap_table']['assumptions']),f'新增池假设：{brief.finance.new_pool_pct}%；投前估值：{brief.finance.pre_money or "待填"}；本轮资金：{brief.finance.investment if brief.finance.investment is not None else "待填"}。'),
            section('治理选择与僵局处理','备选设计：集中决策、共同决策或职责分层。比较效率、监督和僵局成本。均分比例可能增加僵局风险，但不作为违法或不可用的结论。','经济持股不等于全部控制权。逐项记录股东会表决、董事席位、保留事项、利益冲突及争议升级规则；按主体类型和适用法审查。'),
            section('成熟与进入退出','成熟周期、悬崖期、服务贡献、离职分类和未成熟部分处理均待协商；四年/一年仅为可讨论的商业例子，不是强制规则。','回购义务主体、合法资金来源、批准程序和税务不能由持股计算推定；详见退出机制文稿。')]
    elif kind=='user_agreement':
        sections=[section('协议主体与服务范围',f'本协议拟由 {F("entity_name")} 与使用服务的用户订立。服务范围：{F("service_scope")}。','生效日期、用户类别、服务地区和签订方式：【待填写】。'),
            section('账号与使用规则','用户应提供必要且真实的信息，妥善保管账号，不从事侵权、欺诈或违法活动。适用年龄、未成年人安排及账号注销流程：【待核验并填写】。'),
            section('费用、交付与退款','收费方式：'+F('revenue_model'),'拟定退款规则：'+F('refund_policy'),'付款前显著展示价格、交付标准、续费与取消条件；退款和消费者法定权利的适用性须核验。'),
            section('内容与知识产权','各方已有知识产权不因使用服务当然转移。用户提交内容应具有合法权利。授权范围、期限、用途及撤回机制：【待填写】，避免超过履约所需范围。'),
            section('个人信息','实际数据处理说明：'+F('data_practices'),'隐私告知应单独明确处理主体、数据类型、目的、期限、接收方、用户权利与联系方式；用户协议不能代替必要的隐私告知或合法处理依据。'),
            section('服务变更、暂停与责任','仅在具体、合理且依法允许的情况下暂停服务；记录通知、申诉、纠错和退款处理程序。责任限制及免责条款：【待结合强制性法律审查】，不预填“全部免责”。'),
            section('争议解决与联系','联系：'+F('contact'),'适用法与争议解决方式：【待协商并核验】。重大变更应作醒目说明，依法完成通知或其他必要程序。')]
    elif kind=='privacy':
        sections=[section('处理主体和联系',F('entity_name'),F('contact')),
            section('真实的数据处理活动',F('data_practices'),'逐项登记：数据类型、来源、用途、处理依据、必要性、保存期限、接收方、删除方式。尚未确定的活动不要描述成已实施的保护能力。'),
            section('权利与操作流程','建立查询、复制、更正、删除、撤回、注销及投诉的适用流程，说明入口、身份验证方式和处理安排；具体范围依适用法核验。'),
            section('需要单独审查的场景','敏感个人信息、未成年人、第三方提供、跨境处理及自动化决策需逐项判断是否触发专门义务，不以统一勾选代替。'),
            section('安全、保存与变更','实际安全措施、供应商约束、事件处置、保存期限与到期删除：【待补全实际实现】。法规参考与业务实现均需在正式发布前核对。')]
    elif kind=='exit':
        sections=[section('进入条件与出资','参与方及当前比例：'+'；'.join(f'{x.name} {x.percent}%' for x in brief.founders),'出资金额、期限、非货币成果权属、工作投入和交付标准：【待协商】。出资义务与劳动报酬分别记录。'),
            section('成熟与离职分类','商业选项：按持续服务或里程碑成熟，设置起算时间、悬崖期和成熟周期。主动离职、协商退出、失能及严重违约分别定义，避免单方无限裁量。'),
            section('未成熟与已成熟权益','未成熟权益的处理方案、已成熟权益是否保留、是否可转让及是否存在购买选择权：【待协商】。回购主体可以是合法条件下的公司或其他股东，不能默认由公司无条件回购。'),
            section('价格与程序','为各退出场景记录估值基准、独立评估方式、折扣上限、付款期限和争议解决。核对优先购买权、批准/通知程序、登记、出资责任、劳动和税务事项。'),
            section('业务交接与争议','资料、客户、代码、权限和未完事项按清单交接；合理约定保密及知识产权事项。竞业限制需另行核验适用主体、期限、补偿和地域。'),
            section('投资人及公司层面的退出','并购、老股转让、合法回购与清算分别安排触发条件、义务人和资金来源。退出时间为协商目标，不能承诺必然流动性或收益。')]
    elif kind=='ipo':
        sections=[section('先确认资本化目标',f'经营地区代码：{brief.jurisdiction}；当前阶段：{brief.stage}；市场：{F("target_market")}。','在完成客户与经营验证前，优先整理治理和财务证据。IPO、并购、股权转让和持续独立经营是不同选项。'),
            section('路径比较','中国大陆：按主板、创业板、科创板、北交所各自定位和当期标准核验，不笼统判断允许未盈利或一定适合。香港及美国：另核对适用上市规则、证券监管、跨境及行业限制。','未给出董事会决定、具体板块和经审计数据，不判断是否具备上市资格或估计成功率。'),
            section('准备资料与缺口','整理主体沿革、真实股权及出资、业务与知识产权、收入确认、审计、税务、关联交易、诉讼/处罚、数据与行业许可、内控和人员材料。','已提供证据：'+F('evidence'),'完成清单只表示用户记录进度，不能证明满足上市条件。'),
            section('阶段推进','建议路径：明确市场与板块 → 由适格专业机构完成差距分析 → 整理治理及审计证据 → 按现行程序推进必要辅导、申报及审查。各市场程序不同，不预设固定年限。'),
            section('当前阶段建议',{'idea':'先验证客户问题和付费意愿，建立主体与资金基本记录；暂不据想法推定上市适配。','mvp':'先核验交付、留存和回款，整理团队及知识产权资料，记录融资与治理缺口。','growth':'建立可复核的财务和内控记录，比较融资及并购选项，再开展上市差距分析。','scale':'在已验证业务基础上明确目标市场，组织审计、法律和保荐等适用专业评估。'}[brief.stage]),
            section('下一步问题','目标上市市场与板块？是否完成审计？收入与盈利数据的期间和口径？股权代持、特殊投资条款和重大合规问题是否清理？跨境安排与备案义务是否适用？')]
    elif kind=='compliance':
        sections=[section('主体与地区','经营主体：'+F('entity_name'),f'地区代码：{brief.jurisdiction}；业务：{F("service_scope")}。','比较有限公司、个体经营、个人独资及合伙结构时，分别确认责任、融资、税务和管理需求，不默认统一最优主体。'),
            section('登记与出资','登记住所、经营范围、法定代表人、治理和出资计划逐项核对。认缴不是免除缴付责任；应按适用公司法、登记规则及主体沿革核验期限和例外。'),
            section('行业与经营许可','针对教育、食品、金融、医疗、互联网及其他受监管业务，按具体服务与经营地核对许可/备案。不能以“科技公司”名称推定可直接经营。'),
            section('财税、用工与合同','建立账户、票据、账簿、申报和授权流程。劳动、社保、采购、服务及合作合同分别审查。税务优惠须有期间、主体条件和官方依据。'),
            section('需要专业确认的事项','服务地区、消费者类型、特殊许可、数据处理、知识产权、出资与税务记录：【待逐项确认】。')]
    elif kind=='ip':
        sections=[section('资产与权属盘点','资源：'+F('resources'),'壁垒：'+F('moat'),'列出代码、算法、作品、名称/标识、技术方案、客户与供应链资料的作者、合同、职务关系和权利归属。'),
            section('保护方式与取舍','比较专利、商标、著作权和商业秘密的保护对象、公开成本、维护费用及可执行性。不是所有软件或商业方案都适合申请专利。'),
            section('发布与申请安排','在公开或销售前评估新颖性、申请策略和保密措施；公开后的例外与救济按具体法域核验，不作“一经公开绝对不能申请”的结论。'),
            section('合同与内部控制','核对员工/外包成果转让、开源许可、供应商权利保证、保密分级、权限和离职交接。保存原创及交付证据。')]
    elif kind=='finance':
        sections=[section('假设和简化测算',finance_text(calc),'数值为输入假设，不是已发生的业绩或审计报表。'),
            section('五年情景与现金流','销量按用户设置的年增长率变化，固定成本按成本增长率变化；单价与单位成本保持不变。另做销量上下20%的敏感性比较。','建立应收、应付、税费、资产投入和融资台账，再复核实际资金可维持时间；不将未承诺融资计入可用资金。'),
            section('税务及财务管理','核对纳税身份、申报周期、抵扣及优惠条件；不预填统一税率或自动宣称符合优惠。建立月度收入、成本、现金和预测偏差复盘。')]
    elif kind=='fundraising':
        sections=[section('目标、用途和里程碑','项目阶段：'+brief.stage,'资金用途：'+F('funding_use'),'先确认本轮应解决的业务验证或扩张瓶颈，再确定融资金额与缓冲。'),
            section('投资人和融资路径','比较股权融资、经营现金、补贴和适当债务的成本与约束。股权融资对象应结合行业、阶段和资源匹配，不承诺找到或获得投资。'),
            section('尽调资料目录','BP；客户及收入证据；月度财务与资金台账；股权及出资历史；知识产权；核心合同；人员；诉讼/监管与数据事项。每份材料记录负责人、日期和版本。'),
            section('条款比较','比较投前/投后估值、融资金额、期权池口径、董事席位、保留事项、清算优先、反稀释、赎回/对赌和退出。测算只覆盖普通权益单轮增资，不替代特殊条款分析。')]
    elif kind=='organization':
        sections=[section('核心能力与角色','已有团队：'+F('team'),'业务：'+F('activities'),'先指定产品/技术、获客、交付、财务与合规的责任人，一人兼多岗时写清授权边界和备用负责人。'),
            section('进入与绩效','记录岗位交付、投入时间、试用/评价流程、薪酬与激励条件。用工合同、社保和劳动权利按经营地核验，不用期权代替法定义务。'),
            section('组织迭代','先围绕业务链路协作；出现稳定工作量或管理跨度后再拆部门。例会关注客户反馈、现金、交付质量和风险，不只关注人数扩张。')]
    elif kind=='validation':
        sections=[section('要验证的客户问题','客户：'+F('customers'),'痛点：'+F('problem'),'方案：'+F('solution')),
            section('最小可行产品与实验','只交付解决核心问题所需的一条流程。记录假设、招募渠道、访谈问题、成本上限、付费方式和停止条件。具体样本量与阈值由项目设置。'),
            section('指标与证据','分别记录使用者和付费者、转化、单客获客成本、交付成本、复购/留存、退款及回款。避免把注册量等同于有效需求。','已有证据：'+F('traction'),'竞品：'+F('competitors')),
            section('复盘与决策','对照事前阈值决定继续、改变定位或停止；区分真实结果与推测。将新证据同步到商业模式、BP 和财务假设。')]
    sources=sources_for(kind)
    scope='本稿参考中国大陆框架。' if brief.jurisdiction=='CN' else '所选法域并非中国大陆；下列中国大陆资料只作比较参考，不视为当地适用规则。'
    intro=f'# {title}\n\n**可编辑讨论草稿，未完成商业验证或法律/投资审查。**\n\n项目输入按用户记录呈现，未由平台独立验证。设计选项和预测均为假设；“待填写”不能视为已满足条件。{scope}\n\n'
    appendix=section('资料缺口与核验',('待补充：'+'、'.join(missing)) if missing else '项目资料已填写；真实性与专业适用性仍须核验。')
    if sources:appendix+=section('官方参考入口',*(f'- [{s["title"]}]({s["url"]})：{s["scope"]}。参考日期 {REFERENCE_DATE}；使用时核对现行版本。' for s in sources))
    return {'kind':kind,'title':title[:200],'markdown':intro+'\n'.join(sections)+appendix,
        'sources':sources,'missing_fields':missing,'mode':'structured_template','calculations':calc,
        'notice':'草稿可继续修改；未提供的市场规模、履历、业绩或法律资格不会自动补造。'}


def finance_text(calc):
    e=calc['economics']
    if e['missing_fields']:return '【财务输入待补充：'+', '.join(e['missing_fields'])+'】'
    summary=(f'月收入假设 {e["monthly_revenue"]}；月经营结果（未计税费及营运资本）{e["monthly_operating_result"]}；'
        f'月资金净消耗 {e["monthly_burn"]}；资金可维持月数 {e["runway_months"] if e["runway_months"] is not None else "简化模型不计算有限期限"}；'
        f'盈亏平衡销量 {e["break_even_units"] if e["break_even_units"] is not None else "单位贡献不为正，不能达到该模型的盈亏平衡"}。')
    projections='\n'.join(f'- {p["scenario"]} · 第 {p["year"]} 年：收入 {p["revenue"]}；成本 {p["cost"]}；经营结果 {p["operating_result"]}。' for p in e['projections'])
    return summary+'\n\n五年简化情景预测（与测算面板相同；未计税费、资产投入、回款及融资）：\n\n'+projections


def kind_from_query(query):
    q=query.lower()
    for kind,words in [('ipo',['ipo','上市','资本化']),('exit',['退出','回购','成熟']),('privacy',['隐私','数据合规']),
        ('user_agreement',['用户协议','服务协议']),('bp',['bp','商业计划书','创业计划书']),('equity',['股权','期权','治理']),
        ('architecture',['商业架构','业务链路']),('finance',['现金流','财务','盈亏']),('fundraising',['融资','尽调']),
        ('organization',['人才','组织','用工']),('ip',['知识产权','专利','商标']),('compliance',['注册','主体','合规']),
        ('validation',['mvp','市场验证']),('business_model',['商业模式','商业画布'])]:
        if any(w in q for w in words):return kind
    return 'business_model'

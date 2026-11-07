"""Curated first-party reference content used by the production seed.

The entries below are deliberately small, dated extracts from official pages.
They are not presented as live crawls: every card keeps the original URL and
the source-library copy tells the user to open that page before applying.
The same stable records feed the opportunity list, information centre and
source library so those surfaces cannot drift apart.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .intake_models import (
    DevelopmentItem,
    DevelopmentItemPath,
    DocumentArchive,
    DocumentVersion,
    Evidence,
    Source,
    SourceEndpoint,
)
from .knowledge import DocumentChunk, KnowledgeAccess, KnowledgePublication, split_text
from .models import Opportunity, Path
from .sources import SourceDocument, SourceHead


def _id(value: str) -> str:
    return str(uuid5(NAMESPACE_URL, "campusmate:real-content:" + value))


def _entry(
    key: str,
    source_code: str,
    path_code: str | None,
    item_type: str,
    opportunity_type: str,
    title: str,
    organization: str,
    url: str,
    source_label: str,
    summary: str,
    location: str,
    deadline: str | None,
    published: str,
    excerpt: str,
    tags: str,
    trust: float = 0.94,
    start: str | None = None,
) -> dict[str, str | float | None]:
    raw = (
        f"标题：{title}\n来源单位：{source_label}\n来源页面：{url}\n"
        f"页面发布时间：{published}\n\n原文摘录：\n{excerpt}\n\n"
        "校伴标注：这是从公开第一方页面保存的资料摘录，不替代当年完整公告。"
        "报名资格、时间和材料请打开来源页面核对；页面未给出明确截止日时，"
        "卡片只作为入口，不推断截止时间。"
    )
    return {
        "key": key,
        "source_code": source_code,
        "path_code": path_code,
        "item_type": item_type,
        "opportunity_type": opportunity_type,
        "title": title,
        "organization": organization,
        "url": url,
        "source_label": source_label,
        "summary": summary,
        "location": location,
        "deadline": deadline,
        "published": published,
        "start": start,
        "excerpt": excerpt,
        "raw_text": raw,
        "tags": tags,
        "trust": trust,
    }


# Search was run against Tavily on 2026-10-07 and the URLs below were checked
# as official university/government/platform pages.  Expired notices remain
# published so users can switch the opportunity filter to “已截止” and inspect
# the original record. Directory pages without a verified deadline stay in the
# information centre/source library and are not shown as actionable openings.
REAL_CONTENT = [
    _entry(
        "pku-2026-recommendation",
        "CM-GR-004-PKU",
        "recommendation_exemption",
        "university_notice",
        "graduate",
        "北京大学信息工程学院2026年接收推荐免试研究生说明",
        "北京大学信息工程学院",
        "https://www.ece.pku.edu.cn/info/1025/3011.htm",
        "北京大学信息工程学院",
        "学院页面说明了2026年接收推免研究生的校级办法入口，适合核对推免材料、时间和院系要求。",
        "北京",
        None,
        "2025-09-02",
        "北京大学2026年接收推荐免试研究生办法（校本部）已发布；学院页面提示申请人查看学校办法与院系后续说明。",
        "保研,推免,北京大学,研究生",
        0.98,
        None,
    ),
    _entry(
        "pku-recommendation-portal",
        "CM-GR-004-PKU",
        "recommendation_exemption",
        "reference",
        "graduate",
        "北京大学研究生招生网推免与研究生招生信息入口",
        "北京大学研究生院",
        "https://admission.pku.edu.cn/xxgk/index2.htm",
        "北京大学研究生招生网",
        "北京大学研究生招生网公开发布研究生招生、推免和院系通知入口；具体年度办法、申请时间和材料要求以对应原文为准。",
        "北京",
        None,
        "2026-10-07",
        "北京大学研究生招生网提供研究生招生信息公开栏目和院系通知入口。当前条目不推断2027年度时间，申请前应核对当届原文。",
        "保研,推免,北京大学,研究生招生,官方入口",
        0.98,
    ),
    _entry(
        "fudan-2027-masters",
        "CM-GR-004-FDU",
        "domestic_postgraduate_exam",
        "university_notice",
        "graduate",
        "复旦大学2027年招收攻读硕士研究生章程",
        "复旦大学研究生院",
        "https://gsao.fudan.edu.cn/15015/list.htm",
        "复旦大学研究生院",
        "复旦研究生院简章目录已列出2027年硕士研究生章程和专业目录，报考条件、报名流程以原文为准。",
        "上海",
        None,
        "2026-09-30",
        "简章目录列出“2027年招收攻读硕士学位研究生章程”和“2027年招收攻读硕士研究生专业目录”；页面还提供各院系咨询联系方式。",
        "考研,硕士,复旦大学,招生章程",
        0.98,
        None,
    ),
    _entry(
        "moe-2027-graduate-policy",
        "CM-GR-001",
        "domestic_postgraduate_exam",
        "policy",
        "graduate",
        "教育部2027年全国硕士研究生招生考试政策原文入口",
        "中华人民共和国教育部",
        "https://www.moe.gov.cn/srcsite/A15/moe_778/s3261/202609/t20260923_1451734.html",
        "教育部研究生招生政策栏目",
        "保存教育部研究生招生政策页面入口，用于核对考试管理、报名和资格要求，不把搜索摘要当作完整政策。",
        "全国",
        None,
        "2026-09-23",
        "教育部研究生招生政策栏目提供2027年研究生招生考试管理相关原文页面；报名前应回到页面查看完整条款和附件。",
        "考研,教育部,政策,报名",
        0.99,
    ),
    _entry(
        "oxford-2027-social-policy",
        "CM-OS-003-OXF",
        "overseas_masters",
        "application_cycle",
        "graduate",
        "牛津大学MSc Evidence-Based Social Intervention and Policy Evaluation 2027-28申请截止",
        "University of Oxford",
        "https://www.ox.ac.uk/admissions/graduate/courses/msc-social-intervention-and-policy-evaluation",
        "Oxford Graduate Admissions",
        "课程页面给出2027-28入学的具体截止时点，申请人还需查看课程页面的语言、推荐信和材料要求。",
        "英国·英格兰",
        "2027-01-07T12:00:00+00:00",
        "2026-09-24",
        "Upcoming application deadline for 2027-28 entry: 12:00 midday UK time on Thursday 7 January 2027。课程页面同时提供课程时长、英语要求和申请说明。",
        "留学,英国,牛津,硕士,申请截止",
        0.99,
        None,
    ),
    _entry(
        "melbourne-2027-data-science",
        "CM-OS-011-MEL",
        "overseas_masters",
        "application_cycle",
        "graduate",
        "墨尔本大学Master of Data Science 2027入学申请日期",
        "The University of Melbourne",
        "https://study.unimelb.edu.au/find/courses/graduate/master-of-data-science/how-to-apply",
        "University of Melbourne Study",
        "课程申请页列出2027年Start Year（3月）申请截止日，申请按课程和学生类别可能不同。",
        "澳大利亚·墨尔本",
        "2026-11-30T23:59:59+11:00",
        "2026-09-30",
        "2027 Start Year (March intake) applications due 30 November 2026；页面提醒申请人先核对入学要求、英语要求和申请步骤。",
        "留学,澳大利亚,墨尔本大学,数据科学",
        0.98,
        None,
    ),
    _entry(
        "scs-2027-national-exam",
        "CM-CS-001",
        "national_civil_service",
        "recruitment_cycle",
        "civil_service",
        "中央机关及其直属机构2027年度考试录用公务员官方入口",
        "国家公务员局",
        "https://www.scs.gov.cn/",
        "国家公务员局",
        "这是国家公务员局官方入口。2027年度公告发布前，卡片只用于跟踪，不推断报名和考试日期。",
        "全国",
        None,
        "2026-10-07",
        "国家公务员局网站是国考公告、职位表、考试大纲和报考指南的权威发布渠道。公告未发布前，不应把往年日期当作本年度安排。",
        "国考,公务员,职位表,公告入口",
        0.99,
    ),
    _entry(
        "guangdong-2026-civil-service",
        "CM-ENT-101-GD",
        "national_civil_service",
        "recruitment_cycle",
        "civil_service",
        "广东省2026年考试录用公务员公告",
        "广东省人民政府门户网站",
        "https://www.gz.gov.cn/zwfw/zxfw/jyfw/content/post_10497463.html",
        "广州市人民政府门户网站",
        "政府门户页面转载广东省2026年省考公告要点，记录招录规模与基本报考条件，完整职位表需回到原公告核对。",
        "广东",
        None,
        "2025-10-19",
        "广东省2026年考试录用公务员公告发布，计划招考公务员11779名；页面摘要列出报考年龄和应届硕士、博士研究生相关说明。",
        "广东省考,公务员,招录,职位表",
        0.96,
    ),
    _entry(
        "ncss-2027-autumn-hiring",
        "CM-JOB-001",
        "enterprise_employment",
        "job",
        "job",
        "2027届高校毕业生“金秋启航”校园招聘月活动",
        "国家大学生就业服务平台（24365）",
        "https://www.ncss.cn/ncss/zt/2027jqqh.shtml",
        "国家大学生就业服务平台",
        "24365专题页提供招聘会、实习岗位和重点领域入口，岗位信息会随平台更新，申请前应打开专题页核对。",
        "全国·线上",
        None,
        "2026-09-01",
        "国家大学生就业服务平台专题页列出2027届高校毕业生“金秋启航”校园招聘月，包含职位信息、专场招聘、实习岗位和风险提示入口。",
        "秋招,实习,就业,24365",
        0.96,
    ),
    _entry(
        "guangdong-2026-public-institutions",
        "CM-JOB-003-GD",
        "enterprise_employment",
        "recruitment_cycle",
        "job",
        "广东省事业单位2026年集中公开招聘高校毕业生公告",
        "广东省人力资源和社会保障厅",
        "https://rsj.gz.gov.cn/ywzt/rszdgg/sydwgkzp/sydwzpgg/content/post_10667246.html",
        "广州市人力资源和社会保障局",
        "广东省集中公开招聘高校毕业生，公告说明岗位查询、报名条件和统一报名时间，具体岗位表需回到官方系统核对。",
        "广东",
        "2026-02-06T16:00:00+08:00",
        "2026-01-29",
        "本次招聘实行网络报名；网上报名时间为2026年2月2日9:00至2月6日16:00，应聘人员只能选择一个岗位报名。岗位、人数和资格条件以广东省事业单位公开招聘信息管理系统及公告附件为准。",
        "事业单位,广东,高校毕业生,招聘,岗位",
        0.98,
    ),
    _entry(
        "shanghai-government-research-intern-2026",
        "CM-JOB-003-SH",
        "enterprise_employment",
        "internship_notice",
        "job",
        "上海市人民政府发展研究中心关于招收2026—2027年度实习生的通知",
        "上海市人民政府发展研究中心",
        "https://www.fzzx.sh.gov.cn/qtl/20260525/24a1bfbada5c4d469e5840a50c8196ac.html",
        "上海市人民政府发展研究中心",
        "上海市政府发展研究中心面向国内外重点高校本科高年级及研究生招收实习生，页面给出实习时间、地点、岗位能力要求和简历投递方式。",
        "上海",
        None,
        "2026-05-25",
        "招募对象为国内外重点高校本科高年级或硕士、博士在读学生；要求善于收集、整理、分析信息，具备文字写作和数据处理能力。实习时间为2026年暑假、2027年寒假，原则上每周到岗4天及以上，地点为上海市黄浦区大沽路100号。页面未给出统一截止日期，请按原文联系方式咨询。",
        "实习,上海,政府研究,岗位,学生",
        0.98,
    ),
    _entry(
        "mohrss-public-recruitment",
        "CM-JOB-002",
        "enterprise_employment",
        "job",
        "job",
        "中国公共招聘网岗位与招聘活动入口",
        "人力资源和社会保障部相关体系",
        "https://job.mohrss.gov.cn/cjobs/jobinfolist/listJobinfolist",
        "中国公共招聘网",
        "公共招聘网按地区和岗位提供职位信息，适合作为实习、就业和公共岗位的补充检索入口。",
        "全国·线上",
        None,
        "2026-10-07",
        "中国公共招聘网提供岗位信息查询与公共招聘服务；具体岗位、用人单位和截止时间以页面实时结果为准。",
        "招聘,就业,岗位,公共招聘",
        0.95,
    ),
    _entry(
        "innovation-contest-2026",
        "CM-ENT-008",
        "entrepreneurship",
        "application_cycle",
        "contest",
        "教育部关于举办中国国际大学生创新大赛（2026）的通知",
        "中华人民共和国教育部",
        "https://www.moe.gov.cn/srcsite/A08/s5672/202607/t20260731_1445670.html",
        "教育部高等教育司",
        "教育部通知明确大赛在2026年7月至11月举办，并给出报名截止、赛制和赛道要求。",
        "全国·线上与各校",
        "2026-09-25T12:00:00+08:00",
        "2026-07-23",
        "教高函〔2026〕26号：大赛定于2026年7月至11月举办；参赛报名开放时间为2026年8月10日，报名截止时间为9月25日12时；校级初赛、省级复赛、总决赛三级赛制。",
        "创新创业,竞赛,教育部,团队",
        0.99,
        "2026-08-10T00:00:00+08:00",
    ),
    _entry(
        "guangdong-entrepreneurship-policy-2026",
        "CM-ENT-101-GD",
        "entrepreneurship",
        "policy",
        "policy",
        "广东省创业扶持政策与公共服务入口",
        "广东省人民政府",
        "https://www.gd.gov.cn/",
        "广东省人民政府门户网站",
        "广东省人民政府门户网站创业政策与公共服务入口，适合查询创业扶持、营商服务和各地政策发布；具体申报条件以对应政策原文为准。",
        "广东",
        None,
        "2026-10-07",
        "广东省人民政府门户网站提供省级政策、政务服务和各地市政府信息公开入口。校伴仅保存官方入口，不推断补贴金额、申报期限或资格条件。",
        "创业政策,广东,招商,扶持,政务服务",
        0.94,
    ),
    _entry(
        "shenzhen-entrepreneurship-policy-2026",
        "CM-ENT-102-SZ",
        "entrepreneurship",
        "policy",
        "policy",
        "深圳市创业与就业扶持政策入口",
        "深圳市人力资源和社会保障局",
        "https://hrss.sz.gov.cn/",
        "深圳市人力资源和社会保障局",
        "深圳市人社部门官方入口，适合查询高校毕业生创业、就业服务和创业扶持政策；申报对象与办理流程以具体政策页面为准。",
        "深圳",
        None,
        "2026-10-07",
        "深圳市人力资源和社会保障局网站提供就业创业政策、公共服务和办事指南入口。申请前应核对最新政策正文、有效期和办理部门。",
        "创业政策,深圳,招商,就业创业,办事指南",
        0.94,
    ),
    _entry(
        "nanshan-entrepreneurship-policy-2026",
        "CM-ENT-103-NS",
        "entrepreneurship",
        "policy",
        "policy",
        "深圳市南山区创业政策与招商服务入口",
        "深圳市南山区人民政府",
        "https://www.szns.gov.cn/",
        "深圳市南山区人民政府门户网站",
        "南山区政府官方入口，适合查询产业招商、创业扶持、孵化载体和企业服务政策；具体项目需回到对应公告核对。",
        "深圳·南山",
        None,
        "2026-10-07",
        "深圳市南山区人民政府网站提供招商引资、产业发展和企业服务信息入口。页面未统一给出申报期限，校伴不推断截止时间。",
        "创业政策,招商,南山,深圳,孵化",
        0.93,
    ),
    _entry(
        "challenge-cup-portal",
        "CM-ENT-008",
        "entrepreneurship",
        "policy",
        "contest",
        "挑战杯全国大学生系列科技学术竞赛官方信息入口",
        "挑战杯全国大学生系列科技学术竞赛",
        "https://www.tiaozhanbei.net/tzb",
        "挑战杯官方站点",
        "官方站点用于查看竞赛新闻和后续通知；站点历史文章不等于当前报名时间，参赛前需核对当届通知。",
        "全国·线上与各校",
        None,
        "2026-10-07",
        "挑战杯官方站点提供竞赛信息和通知文章。当前页面主要是信息入口，具体赛程和报名条件以当届正式通知为准。",
        "挑战杯,竞赛,科技学术,创新",
        0.93,
    ),
    _entry(
        "west-plan-2026",
        "CM-ENT-001",
        "employment",
        "application_notice",
        "volunteer",
        "2026年大学生志愿服务西部计划报名通知",
        "共青团中央、教育部、财政部",
        "https://xibu.youth.cn/",
        "西部计划官方平台",
        "西部计划面向应届毕业生和在读研究生，服务方向包括乡村教育、基层治理、新疆和西藏等专项。",
        "西部地区",
        "2026-05-10T23:59:59+08:00",
        "2026-03-01",
        "2026年报名通道于3月1日起开启至5月10日；计划预计新招募约6万人，服务期1至3年。具体报名入口和资格以西部计划官方平台为准。",
        "志愿服务,西部计划,基层,毕业生",
        0.94,
    ),
    _entry(
        "shenzhen-volunteer-oct-2026",
        "CM-ENT-101-GD",
        "employment",
        "application_notice",
        "volunteer",
        "志愿深圳2026年10月社区志愿服务活动",
        "志愿深圳",
        "https://www.sva.org.cn/",
        "志愿深圳信息平台",
        "志愿深圳活动页展示社区文明实践、生态环保等项目，活动地点和报名截止随项目更新。",
        "深圳",
        None,
        "2026-10-01",
        "平台活动摘要显示2026年10月份大康社区文明园山行志愿活动，报名截止为2026年10月25日；报名资格和服务安排以活动详情页为准。",
        "志愿,深圳,社区,环保",
        0.91,
    ),
    _entry(
        "tsinghua-club-spring-2026",
        "CM-BASE-UNIVERSITIES",
        None,
        "campus_activity",
        "club",
        "清华大学2026年春季学期学生社团联合招新活动",
        "清华大学校团委",
        "https://www.tsinghua.edu.cn/info/1660/124895.htm",
        "清华大学新闻网",
        "清华新闻网记录2026年春季学生社团联合招新，适合了解社团活动和跨兴趣交流机会。",
        "北京·清华大学",
        None,
        "2026-03-25",
        "清华大学2026年春季学期学生社团联合招新活动举行；报道提到同学通过社团培养兴趣、探索校园生活并认识志同道合伙伴。",
        "社团,校园活动,清华大学,交流",
        0.96,
    ),
    _entry(
        "pku-club-autumn-2026",
        "CM-BASE-UNIVERSITIES",
        None,
        "campus_activity",
        "club",
        "北京大学2026—2027学年秋季学期学生社团集体招新活动",
        "北京大学党委宣传部（融媒体中心）",
        "https://news.pku.edu.cn/info/7921/3218831.htm",
        "北京大学新闻网",
        "北京大学新闻网发布秋季学期学生社团集体招新信息，具体摊位、时间和报名方式以学校后续通知为准。",
        "北京·北京大学",
        None,
        "2026-09-01",
        "北京大学新闻网发布“2026—2027学年秋季学期学生社团集体招新活动”报道，并提供学校新闻网和社团相关栏目入口。",
        "社团,校园活动,北京大学,招新",
        0.95,
    ),
]


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    stamp = datetime.fromisoformat(value)
    # SQLite drops timezone offsets. Store UTC before it does so, otherwise
    # 23:59 Beijing time is reinterpreted as UTC and the calendar shows tomorrow.
    return stamp.astimezone(UTC) if stamp.tzinfo else stamp.replace(tzinfo=UTC)


def _endpoint(db: Session, source_code: str):
    source = db.scalar(select(Source).where(Source.source_code == source_code))
    if not source:
        return None, None
    endpoint = db.scalar(select(SourceEndpoint).where(
        SourceEndpoint.source_id == source.id, SourceEndpoint.active.is_(True)
    ).order_by(SourceEndpoint.id))
    return source, endpoint


def _ensure_melbourne_source(db: Session) -> None:
    """Register the university source used by the curated Melbourne record."""
    source_code = "CM-OS-011-MEL"
    if db.scalar(select(Source).where(Source.source_code == source_code)):
        return
    now = datetime.now(UTC)
    source = Source(
        id=_id("source:" + source_code), source_code=source_code,
        name="墨尔本大学研究生招生", publisher="The University of Melbourne",
        authority_level="A+", source_class="university", official=True,
        jurisdiction_level="foreign", region_code="AU-VIC", school_id="MEL-001",
        supported_paths=json.dumps(["overseas_masters"]),
        supported_item_types=json.dumps(["program", "application_cycle"]),
        base_url="https://study.unimelb.edu.au/", active=True, verified_at=now,
    )
    endpoint = SourceEndpoint(
        id=_id("endpoint:" + source_code), source_id=source.id,
        name="master_data_science_apply", endpoint_type="html",
        url="https://study.unimelb.edu.au/find/courses/graduate/master-of-data-science/how-to-apply",
        access_tags=json.dumps(["DIRECT"]), auth_type="none", format="html",
        parser_type="OverseasUniversityProgramAdapter", automation_level="AUTO-2",
        agent_mode="REVIEW", active=True, scheduled=False,
    )
    db.add_all([source, endpoint])
    db.flush()


def _ensure_extra_sources(db: Session) -> None:
    """Register the two official employment notices added after the first seed."""
    now = datetime.now(UTC)
    specs = [
        (
            "CM-JOB-003-GD", "广东省事业单位公开招聘", "广东省人力资源和社会保障厅",
            "https://rsj.gz.gov.cn/", "government", "province", "CN-GD",
            "public_institution_recruitment",
            "https://rsj.gz.gov.cn/ywzt/rszdgg/sydwgkzp/sydwzpgg/content/post_10667246.html",
        ),
        (
            "CM-JOB-003-SH", "上海市人民政府发展研究中心实习", "上海市人民政府发展研究中心",
            "https://www.fzzx.sh.gov.cn/", "government", "city", "CN-SH",
            "internship_notice",
            "https://www.fzzx.sh.gov.cn/qtl/20260525/24a1bfbada5c4d469e5840a50c8196ac.html",
        ),
    ]
    for code, name, publisher, base_url, source_class, jurisdiction, region, endpoint_name, url in specs:
        source = db.scalar(select(Source).where(Source.source_code == code))
        if source:
            continue
        source = Source(
            id=_id("source:" + code), source_code=code, name=name, publisher=publisher,
            authority_level="A+", source_class=source_class, official=True,
            jurisdiction_level=jurisdiction, region_code=region, school_id=None,
            supported_paths=json.dumps(["enterprise_employment"]),
            supported_item_types=json.dumps(["recruitment_cycle", "internship_notice"]),
            base_url=base_url, active=True, verified_at=now,
        )
        endpoint = SourceEndpoint(
            id=_id("endpoint:" + code), source_id=source.id, name=endpoint_name,
            endpoint_type="html", url=url, access_tags=json.dumps(["DIRECT"]),
            auth_type="none", format="html", parser_type="GovernmentNoticeAdapter",
            automation_level="AUTO-2", agent_mode="REVIEW", active=True, scheduled=False,
        )
        db.add_all([source, endpoint])
    db.flush()


def seed_real_content(db: Session, entries: list[dict] | None = None) -> dict[str, int]:
    """Upsert curated first-party cards into all three public read models."""
    # Importing here avoids a module cycle during application construction.
    from .data_catalog import auto_publish

    _ensure_melbourne_source(db)
    _ensure_extra_sources(db)
    now = datetime.now(UTC)
    opportunities = 0
    catalog_items = 0
    knowledge_documents = 0
    chunks = 0

    for item in REAL_CONTENT if entries is None else entries:
        key = str(item["key"])
        url = str(item["url"])
        title = str(item["title"])
        source, endpoint = _endpoint(db, str(item["source_code"]))
        if not source or not endpoint:
            # A registry seed can be temporarily incomplete during a rolling
            # deployment; skip this item and let the next startup retry it.
            continue

        deadline = _parse(item.get("deadline") if isinstance(item.get("deadline"), str) else None)
        values = {
            "type": str(item["opportunity_type"]),
            "title": title,
            "organization": str(item["organization"]),
            "summary": str(item["summary"]),
            "location": str(item["location"]),
            "deadline": deadline,
            "source_url": url,
            "source_label": str(item["source_label"]),
            "trust_score": float(item["trust"]),
            "tags": str(item["tags"]),
            "status": "published",
            "fetched_at": now,
        }
        opportunity_id = "real-" + key[:35]
        # Keep deadline-less official portals and campus activities visible;
        # the UI labels them as requiring source verification.
        opportunity = db.get(Opportunity, opportunity_id)
        if not opportunity:
            db.add(Opportunity(id=opportunity_id, **values))
            opportunities += 1
        else:
            for field, value in values.items():
                setattr(opportunity, field, value)

        document_id = _id("document:" + key)
        curated_text = str(item["raw_text"])
        raw_text = curated_text
        archive = db.get(DocumentArchive, document_id)
        existing_source_doc = db.get(SourceDocument, document_id)
        archive_content = curated_text.encode("utf-8")
        archive_type = "text/plain; charset=utf-8"
        # A one-time source archival job may have stored the complete official
        # HTML/PDF.  Keep that richer snapshot on every subsequent startup;
        # the seed must never replace original material with the short card
        # excerpt used as a fallback when a source is unreachable.
        if (
            not item.get("archive_bytes")
            and
            archive
            and existing_source_doc
            and archive.content
            and archive.content_type
            and (archive.content_type.startswith("text/html") or archive.content_type.startswith("application/pdf"))
            and len(existing_source_doc.raw_text or "") > len(curated_text)
        ):
            raw_text = existing_source_doc.raw_text
            archive_content = bytes(archive.content)
            archive_type = archive.content_type
        if item.get("archive_bytes"):
            archive_content = item["archive_bytes"]
            archive_type = str(item.get("content_type", "text/html; charset=utf-8"))
        # The integrity gate validates the exact archived bytes, not the
        # normalized extracted text. This must remain stable across restarts.
        digest = hashlib.sha256(archive_content).hexdigest()
        version = db.get(DocumentVersion, document_id)
        version_values = {
            "source_endpoint_id": endpoint.id,
            "canonical_url": url,
            "source_item_id": key,
            "publish_time": _parse(str(item["published"])),
            "last_modified": str(item["published"]),
            "content_hash": digest,
            "first_seen_at": now,
            "last_seen_at": now,
            "last_changed_at": now,
            "version_no": 1,
            "fetched_at": now,
            "raw_storage_uri": "db://document-archives/" + document_id,
            "raw_text": raw_text,
            "import_mode": "system",
            "test_batch": None,
            "deleted_at": None,
        }
        if not version:
            version = DocumentVersion(id=document_id, **version_values)
            db.add(version)
            db.flush()
        else:
            for field, value in version_values.items():
                setattr(version, field, value)
        if not archive:
            db.add(DocumentArchive(document_id=document_id, content=archive_content,
                                    content_type=archive_type, is_fixture=False))
        elif item.get("archive_bytes") or not (archive.content_type and (archive.content_type.startswith("text/html") or archive.content_type.startswith("application/pdf"))
                  and existing_source_doc and len(existing_source_doc.raw_text or "") > len(curated_text)):
            archive.content = archive_content
            archive.content_type = archive_type
            archive.is_fixture = False

        # The direct/system publication path is intentionally used here: the
        # page has been selected from a first-party URL and is retained with a
        # hash, while the UI still shows the source and verification notice.
        development_id = _id("development-item:" + key)
        development = db.get(DevelopmentItem, development_id)
        item_values = {
            "title": title,
            "item_type": str(item["item_type"]),
            "cycle_type": "application" if str(item["opportunity_type"]) in {"graduate", "civil_service", "job"} else "event",
            "cycle_id": None,
            "description": str(item["summary"]),
            "start_time": _parse(item.get("start") if isinstance(item.get("start"), str) else None),
            "deadline": deadline,
            "location": str(item["location"]),
            "materials": json.dumps(["打开官方原文", "核对当年资格与时间", "保存申请凭据"], ensure_ascii=False),
            "status": "published",
            "source_document_id": document_id,
        }
        if not development:
            development = DevelopmentItem(id=development_id, **item_values)
            db.add(development)
            db.flush()
            catalog_items += 1
        else:
            for field, value in item_values.items():
                setattr(development, field, value)

        path_code = item.get("path_code")
        if isinstance(path_code, str) and path_code:
            path = db.scalar(select(Path).where(Path.code == path_code))
            if path and not db.scalar(select(DevelopmentItemPath.id).where(
                    DevelopmentItemPath.development_item_id == development_id,
                    DevelopmentItemPath.path_id == path.id)):
                db.add(DevelopmentItemPath(development_item_id=development_id, path_id=path.id))

        evidence_id = _id("evidence:" + key)
        evidence = db.get(Evidence, evidence_id)
        if not evidence:
            db.add(Evidence(id=evidence_id, document_version_id=document_id, source_id=source.id,
                            evidence_location="原文摘录", quote_or_normalized_fact=str(item["excerpt"]),
                            extractor="verified-fetch" if item.get("archive_bytes") else "editorial-seed", evidence_type="dom",
                            review_status="verified", verified_by="system-ingestion",
                            verified_at=now))

        # Legacy source library used by the assistant and /knowledge.
        source_doc = db.get(SourceDocument, document_id)
        if not source_doc:
            source_doc = SourceDocument(id=document_id, source_url=url, content_hash=digest,
                                        raw_text=raw_text, fetched_at=now, archived_at=now)
            db.add(source_doc)
            knowledge_documents += 1
        else:
            source_doc.source_url, source_doc.content_hash = url, digest
            source_doc.raw_text, source_doc.fetched_at = raw_text, now
            source_doc.archived_at = now
        head_id = hashlib.sha256(url.encode("utf-8")).hexdigest()
        head = db.get(SourceHead, head_id)
        if not head:
            db.add(SourceHead(url_hash=head_id, source_url=url, document_id=document_id))
        else:
            head.source_url, head.document_id = url, document_id
        db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
        for ordinal, start, end, chunk_text in split_text(raw_text):
            chunk_id = hashlib.sha256(f"{document_id}:real:{start}:{end}:{digest}".encode()).hexdigest()
            db.add(DocumentChunk(id=chunk_id, document_id=document_id, ordinal=ordinal,
                                 start_offset=start, end_offset=end, text=chunk_text))
            chunks += 1
        publication = db.get(KnowledgePublication, document_id)
        if not publication:
            publication = KnowledgePublication(document_id=document_id)
            db.add(publication)
        publication.source = "system"
        publication.title = title[:160]
        publication.item_type = str(item["opportunity_type"])[:20]
        publication.opportunity_id = opportunity_id if deadline is not None else None
        publication.review_id = None
        access = db.get(KnowledgeAccess, document_id)
        if not access:
            db.add(KnowledgeAccess(document_id=document_id, public=True))
        else:
            access.public = True

        db.flush()
        auto_publish(db, version)

    db.flush()
    return {"opportunities": opportunities, "catalog_items": catalog_items,
            "knowledge_documents": knowledge_documents, "chunks": chunks}

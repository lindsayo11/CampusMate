import hashlib
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .models import EligibilityRule, Opportunity, Path, PlanStep, ReviewItem, TimelineNode, UserPlan
from .sources import SourceDocument, SourceHead
from .knowledge import DocumentChunk, KnowledgeAccess, KnowledgePublication, split_text

PATH_SEEDS = [
    ("保研", "本科阶段通过推免进入研究生阶段", "本科生", "大一至大四"),
    ("国内考研", "通过全国硕士研究生招生考试继续深造", "本科生", "大三至大四"),
    ("留学", "申请海外高校研究生项目", "本科生", "大二至大四"),
    ("考公考编", "参加公务员或事业单位招录考试", "应届毕业生", "大三至毕业"),
    ("就业", "通过实习、校招进入目标行业", "本科生/研究生", "大二至毕业"),
    ("创业", "将想法发展为可持续的创业项目", "在校学生", "全年"),
]

SEEDS = [
    (
        "job-001",
        "job",
        "2027 届产品实习生",
        "星河科技",
        "参与校园产品调研、需求拆解与版本复盘。",
        "上海 / 远程",
        8,
        "产品,实习,应届",
    ),
    (
        "contest-001",
        "contest",
        "全国大学生人工智能创新赛",
        "高校创新联盟",
        "围绕真实校园问题完成 AI 应用原型，支持跨专业组队。",
        "线上 + 北京决赛",
        16,
        "AI,竞赛,组队",
    ),
    (
        "civil-001",
        "civil_service",
        "某市 2027 选调生招录",
        "市委组织部",
        "面向符合专业、学历与学生干部条件的应届毕业生。",
        "某市",
        12,
        "考公,选调,应届",
    ),
    (
        "volunteer-001",
        "volunteer",
        "迎新志愿者招募",
        "校团委",
        "协助新生报到、路线指引与物资发放，可开具志愿证明。",
        "校内",
        5,
        "志愿,校内,证明",
    ),
    (
        "club-001",
        "club",
        "开源技术协会秋季招新",
        "开源技术协会",
        "面向开发、设计和运营同学，参与校园开源项目共建。",
        "大学生活动中心",
        20,
        "社团,开源,技术",
    ),
    (
        "graduate-001",
        "graduate",
        "计算机学院推免宣讲与实验室开放日",
        "计算机学院",
        "介绍推免政策、导师方向与实验室申请流程。",
        "线上 + 学院报告厅",
        10,
        "升学,推免,计算机",
    ),
]

# These are deliberately labelled reference entries.  They give a new account
# useful material immediately while the assistant still tells the user to
# verify current dates and requirements in the linked official notice.
PUBLIC_OPPORTUNITY_SEEDS = [
    ("notice-grad-gateway", "graduate", "研究生招生信息公开入口（预置参考）", "中国研究生招生信息网",
     "用于查找招生单位公告、招生简章和推免/统考相关通知。具体年度安排以研招网及招生单位最新公告为准。",
     "线上", 365, "https://yz.chsi.com.cn/", "研招网官方入口", 0.98, "研究生,招生,公告,预置"),
    ("notice-recommendation-gateway", "graduate", "全国推免服务系统入口（预置参考）", "中国研究生招生信息网",
     "用于了解推免服务系统与公开说明。开放时间、填报流程和资格要求必须以当年官方通知为准。",
     "线上", 330, "https://yz.chsi.com.cn/tm/", "研招网官方入口", 0.98, "推免,保研,公告,预置"),
    ("notice-edu-policy-gateway", "graduate", "教育部研究生招生政策栏目（预置参考）", "中华人民共和国教育部",
     "提供研究生招生政策公开入口。页面内容可能更新，校伴不会把预置资料当作当年截止日期。",
     "线上", 365, "https://www.moe.gov.cn/jyb_xwfb/xfb/2024/", "教育部公开栏目", 0.96, "政策,研究生,公告,预置"),
    ("notice-campus-contest", "contest", "大学生创新创业竞赛信息整理（预置参考）", "校伴资料库",
     "用于建立竞赛准备清单和时间线；具体赛项、组别与截止日期需要打开主办方公告核对。",
     "线上", 180, "https://www.gov.cn/", "公开政策入口", 0.82, "竞赛,创新创业,预置"),
    ("notice-civil-service-gateway", "civil_service", "国家公务员考试公告入口（预置参考）", "国家公务员局",
     "用于定位国考公告与职位表。报名时间、学历专业和应届要求以当年公告及职位表为准。",
     "线上", 365, "https://www.scs.gov.cn/", "国家公务员局公开入口", 0.96, "国考,公告,预置"),
    ("notice-employment-gateway", "job", "高校毕业生就业信息服务入口（预置参考）", "教育部学生服务与素质发展中心",
     "用于查找就业服务与招聘信息。岗位条件、招聘批次和截止日期以招聘单位原文为准。",
     "线上", 365, "https://24365.smartedu.cn/", "国家大学生就业服务平台", 0.94, "就业,实习,招聘,预置"),
]

PUBLIC_DOCUMENT_SEEDS = [
    (
        "研究生招生与推免公开信息检索指南（预置文档）",
        "graduate",
        "https://yz.chsi.com.cn/",
        "中国研究生招生信息网",
        """这是一份 CampusMate 预置参考文档，不是某一年度招生公告。

使用建议：
1. 先在研招网查找招生单位公告、招生简章和推免相关通知。
2. 再打开目标院校研究生院或学院官网，核对报名时间、材料、成绩和专业要求。
3. 任何时间线都要记录公告发布日期和原文链接；预置内容不提供当年截止日期。
4. 向校伴提问“保研时间和要求”时，系统会联网检索并列出可核对的来源。""",
    ),
    (
        "国考与选调公告核对清单（预置文档）",
        "civil_service",
        "https://www.scs.gov.cn/",
        "国家公务员局公开入口",
        """这是一份 CampusMate 预置参考文档，不构成报考资格结论。

核对顺序：公告发布日期 → 报名与缴费时间 → 职位表专业和学历条件 → 应届身份与基层经历 → 笔试、面试及体检安排。
每项要求都应回到国家公务员局或招录机关发布的当年原文确认。""",
    ),
    (
        "校园机会时间线使用说明（预置文档）",
        "campus",
        "https://www.gov.cn/",
        "校伴资料库",
        """预置时间线用于安排准备动作，不等同于官方日程。

建议把每条机会拆成：查看公告、整理材料、资格核对、提交申请、复盘记录。
校伴只会在检索到来源时展示具体日期；如果找不到官方依据，会明确标注信息不足。""",
    ),
]

TIMELINE_SEEDS = {
    "recommendation_exemption": [
        ("大一-大二", "建立成绩与科研档案", "记录核心课程成绩、排名口径和可验证的项目成果。", "high"),
        ("大二-大三", "核对院系推免规则", "查看本校和目标院校当年公开规则，整理材料缺口。", "high"),
        ("大三", "关注夏令营与预推免公告", "以目标院校研究生院原文为准，记录开放时间和材料要求。", "high"),
    ],
    "domestic_postgraduate_exam": [
        ("大二-大三", "确定专业与院校范围", "记录信息来源、考试科目与时间假设，不把假设当作官方安排。", "high"),
        ("大三", "完成初试准备", "按周拆解科目练习、复盘和资料整理。", "high"),
        ("大四", "核对报名与复试公告", "回到研招网和招生单位原文确认报名、考试和复试节点。", "high"),
    ],
    "overseas_masters": [
        ("大二-大三", "准备语言与标化考试", "根据目标项目要求建立考试和成绩单清单。", "high"),
        ("大三", "整理申请材料", "准备个人陈述、推荐信和成绩单，并逐项核对项目官网要求。", "high"),
    ],
    "national_civil_service": [
        ("公告发布后", "核对公告与职位表", "确认学历、专业、应届身份和地区条件，保留原文链接。", "high"),
        ("报名后", "安排笔试与面试准备", "按公告节点拆解练习、材料和复盘任务。", "high"),
    ],
    "employment": [
        ("大二-大三", "积累项目与实习证据", "把经历整理为可展示的项目成果和复盘记录。", "high"),
        ("大三-大四", "跟踪实习与校招公告", "记录岗位原文、截止日期和投递状态。", "high"),
    ],
    "entrepreneurship": [
        ("全年", "验证问题与需求", "访谈用户，记录问题、证据和仍待验证的假设。", "high"),
        ("全年", "组建团队与试运营", "明确分工，完成最小产品并记录真实反馈。", "normal"),
    ],
}


def _stable_seed_id(value: str) -> str:
    return str(uuid5(NAMESPACE_URL, "campusmate:public-seed:" + value))


def seed_public_content(db: Session) -> dict[str, int]:
    """Upsert public paths, reference notices, timeline nodes and documents.

    This function is safe to run on every API start.  It never creates a
    user-owned plan and it updates only rows carrying the stable seed IDs.
    """
    from .source_registry import seed_registry

    seed_registry(db)
    # The old six-card fixture set and generated "reference" cards are kept
    # for the local SQLite/demo test harness only.  Production uses the
    # curated first-party records in ``real_content.py``; it must never create
    # synthetic deadlines or example.edu links on a fresh PostgreSQL database.
    from .config import settings
    legacy_fixtures = settings.demo_mode or settings.database_url.startswith("sqlite")
    now = datetime.now(UTC)
    paths_by_code: dict[str, Path] = {}
    path_metadata = {
        "recommendation_exemption": ("保研", "通过推免进入研究生阶段", "本科生", "大一至大三"),
        "domestic_postgraduate_exam": ("国内考研", "通过全国硕士研究生招生考试继续深造", "本科生", "大二至大四"),
        "overseas_masters": ("境外硕士", "申请海外高校硕士项目", "本科生", "大二至大四"),
        "national_civil_service": ("国考", "参加国家公务员考试", "应届毕业生", "大三至毕业"),
        "employment": ("就业", "通过实习、校招进入目标行业", "本科生/研究生", "大二至毕业"),
        "entrepreneurship": ("创业", "将想法发展为可持续的创业项目", "在校学生", "全年"),
    }
    for code, (name, description, group, duration) in path_metadata.items():
        row = db.scalar(select(Path).where(Path.code == code))
        if not row:
            row = db.scalar(select(Path).where(Path.name == name))
        if not row:
            row = Path(code=code, name=name, description=description,
                       target_group=group, duration=duration, status="published")
            db.add(row)
            db.flush()
        else:
            row.code, row.description, row.target_group, row.duration, row.status = (
                code, description, group, duration, "published")
        paths_by_code[code] = row

    timeline_count = 0
    for code, nodes in TIMELINE_SEEDS.items():
        path = paths_by_code.get(code)
        if not path:
            continue
        for grade, title, description, importance in nodes:
            row = db.scalar(select(TimelineNode).where(
                TimelineNode.path_id == path.id, TimelineNode.title == title))
            if not row:
                db.add(TimelineNode(path_id=path.id, title=title, month=grade,
                                    grade=grade, description=description, importance=importance))
                timeline_count += 1

    opportunity_count = 0
    if legacy_fixtures:
        for oid, kind, title, organization, summary, location, days, source_url, source_label, trust, tags in PUBLIC_OPPORTUNITY_SEEDS:
            row = db.get(Opportunity, oid)
            values = dict(type="reference", title=title, organization=organization, summary=summary,
                          location=location, deadline=None, source_url=source_url,
                          source_label=source_label, trust_score=trust, tags=tags,
                          status="published", fetched_at=now)
            if not row:
                db.add(Opportunity(id=oid, **values))
                opportunity_count += 1
            elif row.source_label in {"研招网官方入口", "教育部公开栏目", "国家公务员局公开入口",
                                      "国家大学生就业服务平台", "公开政策入口"}:
                for key, value in values.items():
                    setattr(row, key, value)

    document_count = 0
    chunk_count = 0
    for title, item_type, source_url, source_label, raw_text in PUBLIC_DOCUMENT_SEEDS:
        document_id = _stable_seed_id(source_url)
        digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        doc = db.get(SourceDocument, document_id)
        if not doc:
            doc = SourceDocument(id=document_id, source_url=source_url, content_hash=digest,
                                 raw_text=raw_text, fetched_at=now, archived_at=now)
            db.add(doc)
            document_count += 1
        else:
            doc.source_url, doc.content_hash, doc.raw_text, doc.fetched_at = source_url, digest, raw_text, now
        head_id = hashlib.sha256(source_url.encode("utf-8")).hexdigest()
        head = db.get(SourceHead, head_id)
        if not head:
            db.add(SourceHead(url_hash=head_id, source_url=source_url, document_id=document_id))
        else:
            head.source_url, head.document_id = source_url, document_id
        db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
        for ordinal, start, end, chunk_text in split_text(raw_text):
            chunk_id = hashlib.sha256(f"{document_id}:seed:{start}:{end}:{digest}".encode()).hexdigest()
            db.add(DocumentChunk(id=chunk_id, document_id=document_id, ordinal=ordinal,
                                 start_offset=start, end_offset=end, text=chunk_text))
            chunk_count += 1
        publication = db.get(KnowledgePublication, document_id)
        if not publication:
            publication = KnowledgePublication(document_id=document_id)
            db.add(publication)
        publication.source, publication.title, publication.item_type = "system", title[:160], item_type[:20]
        publication.opportunity_id, publication.review_id = None, None
        access = db.get(KnowledgeAccess, document_id)
        if not access:
            db.add(KnowledgeAccess(document_id=document_id, public=True))
        else:
            access.public = True
    # Curated first-party notices share the same public opportunity, catalog
    # and source-library records.  Keep this call inside the idempotent seed so
    # a rolling restart can retry a source that was not registered yet.
    from .real_content import seed_real_content
    real = seed_real_content(db)
    db.flush()
    return {"paths": len(paths_by_code), "timeline": timeline_count,
            "opportunities": opportunity_count + real["opportunities"],
            "documents": document_count + real["knowledge_documents"],
            "chunks": chunk_count + real["chunks"],
            "catalog_items": real["catalog_items"]}


STARTER_PLAN_SEEDS = [
    ("保研准备：核对年度政策与目标院校要求", "recommendation_exemption", 21,
     "先打开研招网和目标院校研究生院公告，记录发布日期、来源链接和仍待确认的条件。",
     ["查找当年推免/招生公告", "整理成绩与科研材料清单", "记录需要向学院确认的问题"]),
    ("每周一次机会与公告核对", "employment", 7,
     "每周用校伴搜索一次目标方向，把截止日期和下一步动作放入自己的计划。",
     ["搜索公开机会", "打开原文核对日期", "写下下一步行动"]),
    ("建立个人材料与证据清单", "entrepreneurship", 14,
     "把经历、项目和成果拆成可验证的证据，不编造缺失经历。",
     ["列出已有材料", "标记缺口", "安排一次复盘"]),
]


def ensure_starter_plans(db: Session, user_id: str) -> None:
    """Create private starter plans once for a new account when explicitly enabled."""
    from .config import settings

    if not settings.seed_starter_plans or db.scalar(select(UserPlan.id).where(UserPlan.user_id == user_id)):
        return
    now = datetime.now(UTC)
    for title, path_code, days, note, steps in STARTER_PLAN_SEEDS:
        path = db.scalar(select(Path).where(Path.code == path_code))
        plan = UserPlan(user_id=user_id, path_id=path.id if path else None, title=title,
                        due_date=now + timedelta(days=days), status="todo", note=note,
                        created_at=now, updated_at=now)
        db.add(plan)
        db.flush()
        for step in steps:
            db.add(PlanStep(plan_id=plan.id, title=step, done=False, created_at=now))
    db.commit()


def seed_if_empty(db: Session) -> None:
    now = datetime.now(UTC)
    # Keep demo fixtures compatible with the production public seed.  The
    # latter is idempotent and also supplies the timeline/document tables.
    seed_public_content(db)
    if not db.scalar(select(Path.id).limit(1)):
        for name, desc, group, duration in PATH_SEEDS:
            path = Path(name=name, description=desc, target_group=group, duration=duration)
            db.add(path); db.flush()
            for title, grade, desc2, importance in {
                "保研": [("提升成绩与排名", "大一-大二", "保持核心课程成绩，了解院系推免规则", "high"), ("准备科研与材料", "大二-大三", "积累项目、论文与推荐信", "high"), ("夏令营与预推免", "大三", "关注院校通知并完成申请", "high")],
                "国内考研": [("确定专业与院校", "大二-大三", "完成信息收集和择校", "high"), ("完成初试准备", "大三-大四", "制定科目学习计划", "high")],
                "留学": [("准备语言考试", "大二-大三", "制定语言与标化考试计划", "high"), ("整理申请材料", "大三", "准备文书、推荐信和成绩单", "high")],
                "考公考编": [("了解招考政策", "大三", "跟踪公告与岗位条件", "normal"), ("笔试面试准备", "大三-大四", "按考试大纲分阶段训练", "high")],
                "就业": [("积累项目与实习", "大二-大三", "形成可展示的项目成果", "high"), ("参加秋招", "大四", "准备简历、面试与签约", "high")],
                "创业": [("验证问题与需求", "全年", "访谈用户并验证可行性", "high"), ("组建团队与试运营", "全年", "明确分工，完成最小产品", "normal")],
            }[name]:
                db.add(TimelineNode(path_id=path.id, title=title, grade=grade, description=desc2, importance=importance))
        db.commit()
    from .config import settings
    legacy_fixtures = settings.demo_mode or settings.database_url.startswith("sqlite")
    if legacy_fixtures:
        for oid, kind, title, org, summary, location, days, tags in SEEDS:
            if not db.get(Opportunity, oid):
                db.add(
                    Opportunity(
                        id=oid,
                        type=kind,
                        title=title,
                        organization=org,
                        summary=summary,
                        location=location,
                        deadline=now + timedelta(days=days),
                        source_url=f"https://example.edu/opportunities/{oid}",
                        source_label="校园官方来源",
                        trust_score=0.94,
                        tags=tags,
                        fetched_at=now,
                    )
                )
        db.flush()
        civil = "civil-001"
        if not db.scalar(select(EligibilityRule.id).limit(1)):
            db.add_all(
                [
                    EligibilityRule(
                        opportunity_id=civil,
                        field="grade",
                        operator="in",
                        expected="大四,应届生",
                        label="须为应届毕业年级",
                        source_url=f"https://example.edu/opportunities/{civil}",
                        review_status="verified",
                    ),
                    EligibilityRule(
                        opportunity_id=civil,
                        field="major",
                        operator="contains_any",
                        expected="计算机,软件,电子信息",
                        label="专业须在计算机相关目录",
                        source_url=f"https://example.edu/opportunities/{civil}",
                        review_status="verified",
                    ),
                ]
            )
        if not db.scalar(select(ReviewItem.id).limit(1)):
            db.add_all(
                [
                    ReviewItem(
                        title="学院创新创业训练计划申报",
                        source_url="https://example.edu/review/1",
                        risk_level="medium",
                        confidence=0.73,
                        extracted_payload='{"type":"contest","deadline":"待复核"}',
                        created_at=now,
                    ),
                    ReviewItem(
                        title="企业校园招聘补录通知",
                        source_url="https://example.edu/review/2",
                        risk_level="high",
                        confidence=0.58,
                        extracted_payload='{"type":"job","organization":"待认证"}',
                        created_at=now,
                    ),
                ]
            )
    db.commit()
    # Registry seeding is idempotent and keeps demo/test environments aligned
    # with the same governed source metadata used in production migrations.
    from .source_registry import seed_registry
    seed_registry(db)

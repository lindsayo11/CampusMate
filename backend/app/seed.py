from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import EligibilityRule, Opportunity, Path, ReviewItem, TimelineNode

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


def seed_if_empty(db: Session) -> None:
    now = datetime.now(UTC)
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
    if not db.scalar(select(Opportunity.id).limit(1)):
        for oid, kind, title, org, summary, location, days, tags in SEEDS:
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
        db.commit()
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
                ),
                EligibilityRule(
                    opportunity_id=civil,
                    field="major",
                    operator="contains_any",
                    expected="计算机,软件,电子信息",
                    label="专业须在计算机相关目录",
                    source_url=f"https://example.edu/opportunities/{civil}",
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

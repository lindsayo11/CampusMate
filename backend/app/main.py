from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import actor_id, require_admin
from .config import settings
from .database import SessionLocal, get_db
from .models import (
    EligibilityRule,
    Opportunity,
    Path,
    Profile,
    Reminder,
    ReviewItem,
    TimelineNode,
    TrackerItem,
    UserPlan,
)
from .schemas import (
    EligibilityCheckIn,
    EligibilityOut,
    OpportunityList,
    OpportunityOut,
    PathOut,
    PlanIn,
    PlanOut,
    ProfileIn,
    ProfileOut,
    ReminderIn,
    ReminderOut,
    ReviewOut,
    RuleResult,
    StatsOut,
    TimelineNodeOut,
    TrackerItemOut,
    TrackerWriteIn,
)
from .seed import seed_if_empty
from .notification_models import Notification


def to_out(row: Opportunity) -> OpportunityOut:
    data = {c.name: getattr(row, c.name) for c in row.__table__.columns}
    data["tags"] = [x for x in row.tags.split(",") if x]
    return OpportunityOut.model_validate(data)


@asynccontextmanager
async def lifespan(_: FastAPI):
    from .migrate import check_schema
    check_schema()
    if settings.demo_mode:
        import logging
        logging.getLogger("uvicorn.error").warning(
            "\n%s\nDEMO_MODE=true: 演示身份可通过 x-user-id 切换，包含管理员。"
            "仅供隔离环境测试，严禁公网部署！\n%s", "=" * 72, "=" * 72)
    with SessionLocal() as db:
        if settings.demo_mode:
            seed_if_empty(db)
    yield


app = FastAPI(title="CampusMate API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


from .social import router_for

app.include_router(router_for(actor_id))
from .plan_steps import router as plan_steps_router
app.include_router(plan_steps_router)
from .data_feedback import router as corrections_router, admin as corrections_admin
app.include_router(corrections_router)
app.include_router(corrections_admin)
from .teams import router as teams_router

app.include_router(teams_router)
from .team_tasks import router as team_tasks_router

app.include_router(team_tasks_router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "campusmate-api", "demo_mode": settings.demo_mode}


@app.get("/v1/notifications")
def notifications(user: str = Depends(actor_id), db: Session = Depends(get_db),
                  before: int | None = Query(None, ge=1), limit: int = Query(100, ge=1, le=100)):
    stmt = select(Notification).where(Notification.user_id == user)
    if before is not None:
        stmt = stmt.where(Notification.id < before)
    return db.scalars(stmt.order_by(Notification.id.desc()).limit(limit)).all()


@app.get("/v1/opportunities", response_model=OpportunityList)
def list_opportunities(
    type: str | None = None,
    q: str | None = Query(default=None, max_length=80),
    db: Session = Depends(get_db),
    status: Literal["active", "expired", "all"] = "active",
):
    stmt = select(Opportunity).where(Opportunity.status == "published")
    if status == "active":
        stmt = stmt.where(Opportunity.deadline > datetime.now(UTC))
    elif status == "expired":
        stmt = stmt.where(Opportunity.deadline <= datetime.now(UTC))
    if type:
        stmt = stmt.where(Opportunity.type == type)
    if q:
        term = f"%{q}%"
        stmt = stmt.where(
            or_(
                Opportunity.title.ilike(term),
                Opportunity.summary.ilike(term),
                Opportunity.tags.ilike(term),
            )
        )
    rows = db.scalars(stmt.order_by(Opportunity.deadline)).all()
    return OpportunityList(items=[to_out(row) for row in rows], total=len(rows))


@app.get("/v1/opportunities/{opportunity_id}", response_model=OpportunityOut)
def get_opportunity(opportunity_id: str, db: Session = Depends(get_db)):
    row = db.get(Opportunity, opportunity_id)
    if not row or row.status != "published":
        raise HTTPException(404, "机会不存在或已下线")
    return to_out(row)


@app.get("/v1/stats", response_model=StatsOut)
def stats(db: Session = Depends(get_db)):
    counts = dict(
        db.execute(
            select(Opportunity.type, func.count())
            .where(Opportunity.status == "published")
            .group_by(Opportunity.type)
        ).all()
    )
    soon = (
        db.scalar(
            select(func.count())
            .select_from(Opportunity)
            .where(
                Opportunity.status == "published",
                Opportunity.deadline <= datetime.now(UTC) + timedelta(days=7),
            )
        )
        or 0
    )
    return StatsOut(total=sum(counts.values()), by_type=counts, closing_soon=soon)


@app.get("/v1/account")
def account(user: str = Depends(actor_id)):
    return {"user_id": user, "is_admin": user in {x.strip() for x in settings.admin_user_ids.split(",") if x.strip()}}


@app.get("/v1/profile", response_model=ProfileOut)
def get_profile(user_id: str = Depends(actor_id), db: Session = Depends(get_db)):
    row = db.get(Profile, user_id)
    if not row:
        now = datetime.now(UTC)
        row = Profile(
            user_id=user_id,
            college="计算机学院" if settings.demo_mode else "",
            grade="大四" if settings.demo_mode else "",
            major="计算机科学与技术" if settings.demo_mode else "",
            interests="AI,开源" if settings.demo_mode else "",
            skills="Python,产品设计" if settings.demo_mode else "",
            weekly_hours=8,
            updated_at=now,
        )
        db.add(row)
        db.commit()
    return ProfileOut(
        user_id=row.user_id,
        display_name=row.display_name,
        discoverable=row.discoverable,
        school=row.school,
        college=row.college,
        grade=row.grade,
        major=row.major,
        interests=[x for x in row.interests.split(",") if x],
        skills=[x for x in row.skills.split(",") if x],
        weekly_hours=row.weekly_hours,
        degree=row.degree, target_year=row.target_year, target_path=row.target_path,
        target_region=row.target_region, language_score=row.language_score,
        research_exp=row.research_exp, internship_exp=row.internship_exp,
        competition_exp=row.competition_exp, startup_exp=row.startup_exp,
        updated_at=row.updated_at,
    )


@app.put("/v1/profile", response_model=ProfileOut)
def update_profile(
    payload: ProfileIn, user_id: str = Depends(actor_id), db: Session = Depends(get_db)
):
    row = db.get(Profile, user_id) or Profile(user_id=user_id)
    for field in ("school", "college", "grade", "major", "weekly_hours", "display_name", "discoverable",
                  "degree", "target_year", "target_path", "target_region", "language_score",
                  "research_exp", "internship_exp", "competition_exp", "startup_exp"):
        setattr(row, field, getattr(payload, field))
    row.interests, row.skills, row.updated_at = (
        ",".join(payload.interests),
        ",".join(payload.skills),
        datetime.now(UTC),
    )
    db.add(row)
    db.commit()
    return get_profile(user_id, db)


@app.get("/v1/paths", response_model=list[PathOut])
def list_paths(db: Session = Depends(get_db)):
    return db.scalars(select(Path).where(Path.status == "published").order_by(Path.id)).all()


@app.get("/v1/paths/{path_id}/timeline", response_model=list[TimelineNodeOut])
def path_timeline(path_id: int, db: Session = Depends(get_db)):
    if not db.get(Path, path_id):
        raise HTTPException(404, "发展路径不存在")
    return db.scalars(select(TimelineNode).where(TimelineNode.path_id == path_id).order_by(TimelineNode.id)).all()


@app.get("/v1/plans", response_model=list[PlanOut])
def list_plans(user_id: str = Depends(actor_id), db: Session = Depends(get_db)):
    return db.scalars(select(UserPlan).where(UserPlan.user_id == user_id).order_by(UserPlan.due_date, UserPlan.id)).all()


@app.post("/v1/plans", response_model=PlanOut)
def create_plan(payload: PlanIn, user_id: str = Depends(actor_id), db: Session = Depends(get_db)):
    if payload.path_id is not None and not db.get(Path, payload.path_id):
        raise HTTPException(404, "发展路径不存在")
    now = datetime.now(UTC)
    row = UserPlan(user_id=user_id, created_at=now, updated_at=now, **payload.model_dump())
    db.add(row); db.commit(); db.refresh(row)
    return row


@app.patch("/v1/plans/{plan_id}", response_model=PlanOut)
def update_plan(plan_id: int, payload: PlanIn, user_id: str = Depends(actor_id), db: Session = Depends(get_db)):
    row = db.scalar(select(UserPlan).where(UserPlan.id == plan_id, UserPlan.user_id == user_id))
    if not row: raise HTTPException(404, "计划不存在")
    if payload.path_id is not None and not db.get(Path, payload.path_id):
        raise HTTPException(404, "发展路径不存在")
    for key, value in payload.model_dump().items(): setattr(row, key, value)
    row.updated_at = datetime.now(UTC); db.commit(); db.refresh(row)
    return row


@app.post("/v1/tools/opportunity_search", response_model=OpportunityList)
def opportunity_search(
    type: str | None = None, q: str | None = None, db: Session = Depends(get_db)
):
    return list_opportunities(type, q, db)


@app.post("/v1/tools/eligibility_check", response_model=EligibilityOut)
def eligibility_check(
    payload: EligibilityCheckIn, user_id: str = Depends(actor_id), db: Session = Depends(get_db)
):
    opportunity = db.get(Opportunity, payload.opportunity_id)
    if not opportunity or opportunity.status != "published":
        raise HTTPException(404, "机会不存在或已下线")
    profile = get_profile(user_id, db)
    rules = db.scalars(
        select(EligibilityRule).where(EligibilityRule.opportunity_id == payload.opportunity_id)
    ).all()
    results: list[RuleResult] = []
    for rule in rules:
        actual = str(getattr(profile, rule.field, ""))
        from .eligibility_engine import evaluate
        passed = evaluate(actual, rule.expected, rule.operator)
        results.append(
            RuleResult(
                label=rule.label,
                evidence=rule.evidence,
                passed=passed,
                actual=actual,
                expected=rule.expected,
                source_url=rule.source_url,
            )
        )
    return EligibilityOut(
        eligible=False if any(x.passed is False for x in results) else (None if not results or any(x.passed is None for x in results) else True),
        opportunity_id=payload.opportunity_id,
        results=results,
    )


def tracker_out(row: TrackerItem, db: Session) -> TrackerItemOut:
    opportunity = db.get(Opportunity, row.opportunity_id)
    if not opportunity:
        raise HTTPException(404, "关联机会不存在")
    return TrackerItemOut(
        id=row.id,
        opportunity=to_out(opportunity),
        stage=row.stage,
        note=row.note,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@app.get("/v1/tracker/items", response_model=list[TrackerItemOut])
def tracker_items(user_id: str = Depends(actor_id), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(TrackerItem)
        .where(TrackerItem.user_id == user_id)
        .order_by(TrackerItem.updated_at.desc())
    ).all()
    return [tracker_out(row, db) for row in rows]


@app.post("/v1/tools/tracker_write", response_model=TrackerItemOut)
def tracker_write(payload: TrackerWriteIn, user_id: str = Depends(actor_id), db: Session = Depends(get_db)):
    return write_tracker(payload, user_id, db)


def write_tracker(payload: TrackerWriteIn, user_id: str, db: Session, commit: bool = True):
    opportunity = db.get(Opportunity, payload.opportunity_id)
    if not opportunity or opportunity.status != "published":
        raise HTTPException(404, "机会不存在或已下线")
    row = db.scalar(
        select(TrackerItem).where(
            TrackerItem.user_id == user_id, TrackerItem.opportunity_id == payload.opportunity_id
        )
    )
    now = datetime.now(UTC)
    if not row:
        row = TrackerItem(
            user_id=user_id, opportunity_id=payload.opportunity_id, created_at=now, updated_at=now
        )
    transitions = {"saved": {"saved", "preparing", "applied"}, "preparing": {"preparing", "applied"},
                   "applied": {"applied", "interview", "completed"}, "interview": {"interview", "completed"},
                   "completed": {"completed"}}
    if payload.stage not in transitions.get(row.stage or "saved", set()):
        raise HTTPException(409, "不能跳过或回退当前看板阶段")
    row.stage, row.note, row.updated_at = payload.stage, payload.note, now
    db.add(row)
    db.flush()
    if commit:
        db.commit()
    return tracker_out(row, db)


@app.get("/v1/reminders", response_model=list[ReminderOut])
def reminders(user_id: str = Depends(actor_id), db: Session = Depends(get_db)):
    return db.scalars(
        select(Reminder).where(Reminder.user_id == user_id).order_by(Reminder.due_at)
    ).all()


@app.post("/v1/tools/deadline_remind", response_model=ReminderOut)
def deadline_remind(payload: ReminderIn, user_id: str = Depends(actor_id), db: Session = Depends(get_db)):
    return create_reminder(payload, user_id, db)


def create_reminder(payload: ReminderIn, user_id: str, db: Session, commit: bool = True):
    opportunity = db.get(Opportunity, payload.opportunity_id)
    if not opportunity or opportunity.status != "published":
        raise HTTPException(404, "机会不存在或已下线")
    due_at = opportunity.deadline - timedelta(hours=max(1, min(payload.hours_before, 720)))
    aware_due = due_at.replace(tzinfo=UTC) if due_at.tzinfo is None else due_at
    if aware_due <= datetime.now(UTC):
        raise HTTPException(422, "提醒时间已过，请选择更短的提前量")
    row = db.scalar(
        select(Reminder).where(
            Reminder.user_id == user_id,
            Reminder.opportunity_id == payload.opportunity_id,
            Reminder.due_at == due_at,
        )
    )
    if not row:
        row = Reminder(
            user_id=user_id,
            opportunity_id=payload.opportunity_id,
            due_at=due_at,
            created_at=datetime.now(UTC),
        )
        db.add(row)
        db.flush()
        if commit:
            db.commit()
    return row


@app.get("/v1/admin/reviews", response_model=list[ReviewOut], dependencies=[Depends(require_admin)])
def reviews(status: str = "pending", db: Session = Depends(get_db)):
    return db.scalars(
        select(ReviewItem).where(ReviewItem.status == status).order_by(ReviewItem.confidence)
    ).all()


from .governance import router as governance_router

app.include_router(governance_router)


@app.get("/health/live")
def live():
    return {"status": "ok"}


@app.get("/health/ready")
def ready(db: Session = Depends(get_db)):
    try:
        from .migrate import check_schema
        check_schema()
        db.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(503, "数据库尚未就绪")
    return {"status": "ready"}

from .agent import router as agent_router

app.include_router(agent_router)


@app.exception_handler(IntegrityError)
async def integrity_conflict(request, exc):
    return JSONResponse(status_code=409, content={"detail": "数据已由其他请求修改，请刷新后重试"})

from .moderation import router as moderation_router

app.include_router(moderation_router)

from .sources import router as sources_router

app.include_router(sources_router)

from .operations import install_request_logging
from .operations import router as operations_router

app.include_router(operations_router)
install_request_logging(app)

from .collector import router as collector_router

app.include_router(collector_router)

from .knowledge import router as knowledge_router

app.include_router(knowledge_router)

from .task_alerts import router as task_alerts_router

app.include_router(task_alerts_router)

from .source_registry import router as source_registry_router

app.include_router(source_registry_router)

from .intake_api import router as intake_router

app.include_router(intake_router)

from .data_catalog import admin as data_admin_router, router as data_router

app.include_router(data_admin_router)
app.include_router(data_router)
from .notice_watch import router as notice_watch_router
app.include_router(notice_watch_router)
from .development_agent import router as development_agent_router
app.include_router(development_agent_router)

from .startup import router as startup_router
app.include_router(startup_router)

from .collection_page import router as collection_page_router
app.include_router(collection_page_router)
from .collection_exchange import router as collection_exchange_router
app.include_router(collection_exchange_router)

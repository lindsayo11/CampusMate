"""Personal preparation checklist and in-app reminders, scoped to the owning plan."""
from datetime import UTC, datetime
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from .auth import actor_id
from .database import get_db
from .models import UserPlan, PlanStep
from .agent_state import PlanReminder

router = APIRouter(prefix='/v1/plans')


def own_plan(db, plan_id, user):
    plan = db.scalar(select(UserPlan).where(UserPlan.id == plan_id, UserPlan.user_id == user))
    if not plan:
        raise HTTPException(404, '计划不存在')
    return plan


class StepIn(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=300)


class StepUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    done: bool


class ReminderIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    due_at: datetime


@router.get('/{plan_id}/steps')
def steps(plan_id: int, user: str = Depends(actor_id), db: Session = Depends(get_db)):
    own_plan(db, plan_id, user)
    return db.scalars(select(PlanStep).where(PlanStep.plan_id == plan_id).order_by(PlanStep.id)).all()


@router.post('/{plan_id}/steps', status_code=201)
def add_step(plan_id: int, body: StepIn, user: str = Depends(actor_id), db: Session = Depends(get_db)):
    own_plan(db, plan_id, user)
    rows = db.scalars(select(PlanStep).where(PlanStep.plan_id == plan_id)).all()
    for row in rows:
        if row.title == body.title:
            return row
    if len(rows) >= 50:
        raise HTTPException(422, '每项计划最多保存 50 条清单')
    row = PlanStep(plan_id=plan_id, title=body.title, done=False, created_at=datetime.now(UTC))
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        row = db.scalar(select(PlanStep).where(PlanStep.plan_id == plan_id, PlanStep.title == body.title))
        if row is None:
            raise
    db.refresh(row)
    return row


@router.patch('/{plan_id}/steps/{step_id}')
def update_step(plan_id: int, step_id: int, body: StepUpdate, user: str = Depends(actor_id), db: Session = Depends(get_db)):
    own_plan(db, plan_id, user)
    row = db.scalar(select(PlanStep).where(PlanStep.id == step_id, PlanStep.plan_id == plan_id))
    if not row:
        raise HTTPException(404, '清单条目不存在')
    row.done = body.done; db.commit(); db.refresh(row)
    return row


@router.delete('/{plan_id}/steps/{step_id}')
def remove_step(plan_id: int, step_id: int, user: str = Depends(actor_id), db: Session = Depends(get_db)):
    own_plan(db, plan_id, user)
    row = db.scalar(select(PlanStep).where(PlanStep.id == step_id, PlanStep.plan_id == plan_id))
    if not row:
        raise HTTPException(404, '清单条目不存在')
    db.delete(row); db.commit()
    return {'deleted': True}


@router.post('/{plan_id}/reminders', status_code=201)
def remind(plan_id: int, body: ReminderIn, user: str = Depends(actor_id), db: Session = Depends(get_db)):
    plan = own_plan(db, plan_id, user)
    if body.due_at.tzinfo is None or body.due_at <= datetime.now(UTC):
        raise HTTPException(422, '请选择带时区的未来提醒时间')
    if plan.status == 'done':
        raise HTTPException(422, '已完成的计划无需提醒')
    due = body.due_at.astimezone(UTC)
    row = db.scalar(select(PlanReminder).where(PlanReminder.user_id == user,
        PlanReminder.plan_id == plan_id, PlanReminder.due_at == due, PlanReminder.status == 'pending'))
    if not row:
        row = PlanReminder(id=str(uuid4()), user_id=user, plan_id=plan_id, due_at=due, status='pending')
        db.add(row); db.commit(); db.refresh(row)
    return {'id':row.id, 'due_at':due.isoformat(), 'status':row.status}

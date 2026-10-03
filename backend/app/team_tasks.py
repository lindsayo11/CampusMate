"""Small team task board. Every operation is authorized against current membership."""
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import DateTime, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .auth import actor_id
from .database import Base, get_db
from .teams import lock_team


class TeamTask(Base):
    __tablename__ = "team_tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[str] = mapped_column(String(36), index=True)
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    assignee: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="todo")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(default=1)
    created_by: Mapped[str] = mapped_column(String(80))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=4000)
    assignee: str | None = Field(default=None, max_length=80)
    due_at: datetime | None = None

    @field_validator("title")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("任务标题不能为空")
        return value.strip()

    @field_validator("due_at")
    @classmethod
    def timezone_required(cls, value):
        if value and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("截止时间必须含时区")
        return value.astimezone(UTC) if value else None


class TaskEdit(TaskCreate):
    version: int = Field(ge=1)


class TaskStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["todo", "doing", "done", "cancelled"]
    version: int = Field(ge=1)


router = APIRouter(prefix="/v1/teams")


def authorized(db, team_id, user):
    team, room = lock_team(db, team_id)
    if user not in room.members:
        raise HTTPException(404, "队伍不存在或已退出")
    return team, room


def task_for(db, team_id, task_id, version):
    task = db.get(TeamTask, task_id, populate_existing=True)
    if not task or task.team_id != team_id:
        raise HTTPException(404, "任务不存在")
    if task.version != version:
        raise HTTPException(409, "任务已被更新，请刷新后重试")
    return task


def task_out(task):
    return {c.name: (getattr(task, c.name).replace(tzinfo=UTC)
                    if c.name in {"due_at", "updated_at"} and getattr(task, c.name)
                    and getattr(task, c.name).tzinfo is None else getattr(task, c.name))
            for c in task.__table__.columns}


@router.get("/{team_id}/tasks")
def listing(team_id: str, user: str = Depends(actor_id), db: Session = Depends(get_db)):
    authorized(db, team_id, user)
    return [task_out(t) for t in db.scalars(select(TeamTask).where(
        TeamTask.team_id == team_id).order_by(TeamTask.id))]


@router.post("/{team_id}/tasks", status_code=201)
def create(team_id: str, body: TaskCreate, user: str = Depends(actor_id),
           db: Session = Depends(get_db)):
    team, room = authorized(db, team_id, user)
    if team.owner != user:
        raise HTTPException(403, "只有队长可以创建和分配任务")
    if body.assignee is not None and body.assignee not in room.members:
        raise HTTPException(422, "负责人必须是当前队伍成员")
    task = TeamTask(team_id=team_id, **body.model_dump(), status="todo", version=1,
                    created_by=user, updated_at=datetime.now(UTC))
    db.add(task)
    db.commit()
    return task_out(task)


@router.put("/{team_id}/tasks/{task_id}")
def edit(team_id: str, task_id: int, body: TaskEdit, user: str = Depends(actor_id),
         db: Session = Depends(get_db)):
    team, room = authorized(db, team_id, user)
    if team.owner != user:
        raise HTTPException(403, "只有队长可以编辑和分配任务")
    task = task_for(db, team_id, task_id, body.version)
    if body.assignee is not None and body.assignee not in room.members:
        raise HTTPException(422, "负责人必须是当前队伍成员")
    for key, value in body.model_dump(exclude={"version"}).items():
        setattr(task, key, value)
    task.version += 1
    task.updated_at = datetime.now(UTC)
    db.commit()
    return task_out(task)


@router.post("/{team_id}/tasks/{task_id}/status")
def change_status(team_id: str, task_id: int, body: TaskStatus,
                  user: str = Depends(actor_id), db: Session = Depends(get_db)):
    team, _ = authorized(db, team_id, user)
    task = task_for(db, team_id, task_id, body.version)
    if user != team.owner and (user != task.assignee or body.status == "cancelled"
                               or task.status == "cancelled"):
        raise HTTPException(403, "只有队长或当前负责人可以更新进度；取消和恢复由队长操作")
    task.status = body.status
    task.version += 1
    task.updated_at = datetime.now(UTC)
    db.commit()
    return task_out(task)

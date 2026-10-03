"""Durable task deadline reminders with current-membership visibility checks."""
import hashlib
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import DateTime, String, select, update
from sqlalchemy.orm import Mapped, Session, mapped_column

from .auth import actor_id
from .database import Base, SessionLocal, get_db
from .social import Room
from .team_tasks import TeamTask
from .teams import Team, lock_team


class TaskAlert(Base):
    __tablename__ = "task_alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    dedup_key: Mapped[str] = mapped_column(String(64), unique=True)
    task_id: Mapped[int] = mapped_column(index=True)
    user_id: Mapped[str] = mapped_column(String(80), index=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def active_alerts(db, user):
    rows = db.execute(select(TaskAlert, TeamTask, Team, Room)
        .join(TeamTask, TaskAlert.task_id == TeamTask.id)
        .join(Team, Team.id == TeamTask.team_id)
        .join(Room, Room.id == Team.room_id)
        .where(TaskAlert.user_id == user, TeamTask.assignee == user,
               TeamTask.status.in_(["todo", "doing"]), Team.status == "active",
               TeamTask.due_at == TaskAlert.due_at)
        .order_by(TaskAlert.id.desc()))
    for alert, task, team, room in rows:
        if user in room.members:
            yield {"id": alert.id, "task_id": task.id, "title": task.title,
                   "team_id": team.id, "team_title": team.title, "due_at": utc(task.due_at),
                   "overdue": utc(task.due_at) <= datetime.now(UTC),
                   "created_at": utc(alert.created_at), "read_at": utc(alert.read_at) if alert.read_at else None}


router = APIRouter(prefix="/v1/task-alerts")


@router.get("")
def listing(before: int | None = Query(None, ge=1), user: str = Depends(actor_id),
            db: Session = Depends(get_db)):
    result = []
    for row in active_alerts(db, user):
        if before is None or row["id"] < before:
            result.append(row)
        if len(result) == 51:
            break
    return {"items": result[:50], "has_more": len(result) > 50}


@router.post("/{alert_id}/read")
def mark_read(alert_id: int, user: str = Depends(actor_id), db: Session = Depends(get_db)):
    # Do not allow marking (or learning about) another user's or withdrawn task alert.
    found = next((r for r in active_alerts(db, user) if r["id"] == alert_id), None)
    if not found:
        raise HTTPException(404, "通知不存在或任务状态已变更")
    db.execute(update(TaskAlert).where(TaskAlert.id == alert_id, TaskAlert.user_id == user,
        TaskAlert.read_at.is_(None)).values(read_at=datetime.now(UTC)))
    db.commit()
    return {"read": True}


def deliver_task_alerts():
    now, delivered = datetime.now(UTC), 0
    # Match the team's established lock order: team -> room -> task.
    # Per-team transactions prevent one bad/deleted team from holding all deliveries open.
    with SessionLocal() as db:
        team_ids = list(db.scalars(select(Team.id).join(TeamTask, TeamTask.team_id == Team.id).where(
            Team.status == "active", TeamTask.status.in_(["todo", "doing"]),
            TeamTask.assignee.is_not(None), TeamTask.due_at <= now + timedelta(hours=24)).distinct().order_by(Team.id)))
    for team_id in team_ids:
        with SessionLocal.begin() as db:
            try:
                _, room = lock_team(db, team_id)
            except HTTPException as exc:
                if exc.status_code == 404:
                    continue
                raise
            tasks = db.scalars(select(TeamTask).where(TeamTask.team_id == team_id,
                TeamTask.status.in_(["todo", "doing"]), TeamTask.assignee.is_not(None),
                TeamTask.due_at <= now + timedelta(hours=24))).all()
            for task in tasks:
                if task.assignee not in room.members:
                    continue
                due = utc(task.due_at)
                # Edits to the description/status do not generate new reminders.
                # Changing deadline or owner creates a new effective notification.
                key = hashlib.sha256(f"{task.id}:{task.assignee}:{due.isoformat()}".encode()).hexdigest()
                if db.scalar(select(TaskAlert.id).where(TaskAlert.dedup_key == key)):
                    continue
                db.add(TaskAlert(dedup_key=key, task_id=task.id, user_id=task.assignee,
                                  due_at=due, created_at=now))
                db.flush()
                delivered += 1
    return delivered

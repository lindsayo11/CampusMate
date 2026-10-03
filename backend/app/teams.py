from typing import Literal
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import String, Integer, select, update
from sqlalchemy.orm import Mapped, Session, mapped_column
from .auth import actor_id
from .database import Base, get_db
from .models import Profile
from .social import Room, Block


class Team(Base):
    __tablename__ = "teams"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(100))
    capacity: Mapped[int] = mapped_column(Integer, default=5, server_default="5")
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active")
    room_id: Mapped[str] = mapped_column(String(36), unique=True)


class Invitation(Base):
    __tablename__ = "team_invitations"
    team_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    target: Mapped[str] = mapped_column(String(80), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")


class CreateTeam(BaseModel):
    capacity: int = Field(default=5, ge=2, le=20)
    title: str = Field(min_length=1, max_length=100)


class Invite(BaseModel):
    target: str = Field(min_length=1, max_length=80)


class Decision(BaseModel):
    action: Literal["accept", "reject"]


router = APIRouter(prefix="/v1")


@router.post("/teams")
def create(body: CreateTeam, user: str = Depends(actor_id), db: Session = Depends(get_db)):
    if not body.title.strip():
        raise HTTPException(422, "队名不能为空")
    room = Room(id=str(uuid4()), title=body.title.strip(), members=[user])
    team = Team(id=str(uuid4()), owner=user, title=room.title, room_id=room.id, capacity=body.capacity)
    db.add_all([room, team])
    db.commit()
    return team


@router.get("/teams")
def listing(user: str = Depends(actor_id), db: Session = Depends(get_db)):
    rows = db.execute(select(Team, Room).join(Room, Team.room_id == Room.id)).all()
    return [{"id": t.id, "title": t.title, "owner": t.owner, "room_id": r.id, "members": r.members, "capacity": t.capacity, "is_owner": t.owner == user} for t, r in rows if user in r.members and t.status == "active"]


@router.post("/teams/{team_id}/invitations")
def invite(team_id: str, body: Invite, user: str = Depends(actor_id), db: Session = Depends(get_db)):
    team, room = lock_team(db, team_id)
    if team.owner != user:
        raise HTTPException(404, "队伍不存在或不是队长")
    if not db.get(Profile, body.target):
        raise HTTPException(422, "目标用户尚未建立画像")
    if len(room.members) >= team.capacity:
        raise HTTPException(409, "队伍已满")
    if body.target in room.members:
        raise HTTPException(409, "用户已经在队伍中")
    if db.get(Block, (user, body.target)) or db.get(Block, (body.target, user)):
        raise HTTPException(403, "双方存在拉黑关系")
    row = db.get(Invitation, (team_id, body.target))
    if row and row.status != "pending":
        row.status = "pending"
        db.commit()
    if not row:
        row = Invitation(team_id=team_id, target=body.target, status="pending")
        db.add(row)
        db.commit()
    return row


@router.get("/invitations")
def incoming(user: str = Depends(actor_id), db: Session = Depends(get_db)):
    rows = db.execute(select(Invitation, Team).join(Team, Invitation.team_id == Team.id)
                      .where(Invitation.target == user)).all()
    return [{"team_id": i.team_id, "target": i.target, "status": i.status,
             "title": t.title, "team_status": t.status} for i, t in rows]


@router.post("/invitations/{team_id}/decision")
def decide(team_id: str, body: Decision, user: str = Depends(actor_id), db: Session = Depends(get_db)):
    team, room = lock_team(db, team_id)
    row = db.get(Invitation, (team_id, user))
    if not row:
        raise HTTPException(404, "邀请不存在")
    if row.status != "pending":
        raise HTTPException(409, "邀请已处理")
    if body.action == "accept" and (db.get(Block, (user, team.owner)) or db.get(Block, (team.owner, user))):
        raise HTTPException(403, "双方存在拉黑关系")
    if body.action == "accept" and len(room.members) >= team.capacity:
        raise HTTPException(409, "队伍已满")
    claimed = db.execute(update(Invitation).where(Invitation.team_id == team_id, Invitation.target == user, Invitation.status == "pending").values(status="accepted" if body.action == "accept" else "rejected"))
    if not claimed.rowcount:
        db.rollback()
        raise HTTPException(409, "邀请已处理")
    if body.action == "accept":
        room.members = sorted(set(room.members + [user]))
    db.commit()
    return {"status": "accepted" if body.action == "accept" else "rejected"}


def lock_team(db, team_id):
    # All team changes lock team then room in a consistent order.
    changed = db.execute(update(Team).where(Team.id == team_id, Team.status == "active").values(title=Team.title))
    if not changed.rowcount:
        raise HTTPException(404, "队伍不存在或已解散")
    team = db.get(Team, team_id, populate_existing=True)
    db.execute(update(Room).where(Room.id == team.room_id).values(title=Room.title))
    return team, db.get(Room, team.room_id, populate_existing=True)


@router.post("/teams/{team_id}/leave")
def leave(team_id: str, user: str = Depends(actor_id), db: Session = Depends(get_db)):
    team, room = lock_team(db, team_id)
    if user not in room.members:
        raise HTTPException(404, "不是队伍成员")
    if user == team.owner:
        raise HTTPException(409, "队长不能直接退出，请解散队伍")
    room.members = [m for m in room.members if m != user]
    unassign_tasks(db, team_id, user)
    invitation = db.get(Invitation, (team_id, user))
    if invitation:
        invitation.status = "left"
    db.commit()
    return {"status": "left"}


@router.post("/teams/{team_id}/remove")
def remove(team_id: str, body: Invite, user: str = Depends(actor_id), db: Session = Depends(get_db)):
    team, room = lock_team(db, team_id)
    if team.owner != user:
        raise HTTPException(404, "不是队长")
    if body.target == user:
        raise HTTPException(409, "不能移除队长")
    if body.target not in room.members:
        raise HTTPException(404, "目标不是队伍成员")
    room.members = [m for m in room.members if m != body.target]
    unassign_tasks(db, team_id, body.target)
    invitation = db.get(Invitation, (team_id, body.target))
    if invitation:
        invitation.status = "removed"
    db.commit()
    return {"status": "removed"}


@router.post("/teams/{team_id}/dissolve")
def dissolve(team_id: str, user: str = Depends(actor_id), db: Session = Depends(get_db)):
    team, room = lock_team(db, team_id)
    if team.owner != user:
        raise HTTPException(404, "不是队长")
    team.status = "dissolved"
    room.members = []
    db.execute(update(Invitation).where(Invitation.team_id == team_id, Invitation.status == "pending").values(status="cancelled"))
    db.commit()
    return {"status": "dissolved"}


def unassign_tasks(db, team_id, target):
    from datetime import UTC, datetime
    from .team_tasks import TeamTask
    # Preserve completed history; active work must not stay assigned to an ex-member.
    db.execute(update(TeamTask).where(TeamTask.team_id == team_id,
        TeamTask.assignee == target, TeamTask.status.in_(["todo", "doing"])).values(
        assignee=None, version=TeamTask.version + 1, updated_at=datetime.now(UTC)))

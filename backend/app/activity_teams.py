"""Published-activity team directory; membership stays captain-approved."""
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Boolean, DateTime, String, Text, or_, select
from sqlalchemy.orm import Mapped, Session, mapped_column
from .auth import actor_id
from .database import Base, get_db
from .data_catalog import visible, path_codes, information_state, publication
from .models import Profile
from .social import Block, Room
from .teams import Team, lock_team
from .rate_limits import consume


class ActivityTeam(Base):
    __tablename__ = "activity_teams"
    team_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    publication_id: Mapped[str] = mapped_column(String(36), index=True)
    item_id: Mapped[str] = mapped_column(String(64), index=True)
    recruiting: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TeamJoinRequest(Base):
    __tablename__ = "team_join_requests"
    team_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    id: Mapped[str] = mapped_column(String(36), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    message: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class NewActivityTeam(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    publication_id: str = Field(min_length=1, max_length=36)
    item_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=100)
    capacity: int = Field(default=5, ge=2, le=20)
    description: str = Field(default="", max_length=600)


class JoinBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    message: str = Field(default="", max_length=300)


class JoinDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["accept", "reject"]


class Recruitment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recruiting: bool


router = APIRouter(prefix="/v1/activity-teams")


def activity(db, publication_id, item_id):
    data = publication(publication_id, db)
    item = next((i for i in data["items"] if i["id"] == item_id), None)
    if not item:
        raise HTTPException(404, "该公告中不存在这个活动")
    return {**item, "publication_id": publication_id, "source": data["source"], "document": data["document"]}


def blocked(db, a, b):
    return bool(db.get(Block, (a, b)) or db.get(Block, (b, a)))


def activity_rows(db):
    return db.execute(select(ActivityTeam, Team, Room).join(Team, Team.id == ActivityTeam.team_id)
        .join(Room, Room.id == Team.room_id).where(Team.status == "active")).all()


def state_of(rows, user):
    if any(user in room.members for _, _, room in rows):
        return "joined"
    if any(link.recruiting and len(room.members) < team.capacity for link, team, room in rows):
        return "recruiting"
    if rows and all(len(room.members) >= team.capacity for _, team, room in rows):
        return "full"
    return "closed" if rows else "none"


@router.get("/directory")
def directory(q: str = Query("", max_length=100), path: str | None = Query(None, max_length=80),
        state: Literal["all", "none", "recruiting", "full", "closed", "joined"] = "all",
        offset: int = Query(0, ge=0), limit: int = Query(12, ge=1, le=50),
        user: str = Depends(actor_id), db: Session = Depends(get_db)):
    groups = {}
    excluded = {b.target if b.owner == user else b.owner for b in db.scalars(
        select(Block).where(or_(Block.owner == user, Block.target == user)))}
    # Respect block relationships without exposing private room members.
    for link, team, room in activity_rows(db):
        if team.owner not in excluded:
            groups.setdefault((link.publication_id, link.item_id), []).append((link, team, room))
    codes = path_codes(db, path) if path else set()
    items = []
    for row, data in visible(db):
        for item in data["items"]:
            if q and q.casefold() not in (item["title"] + item["description"]).casefold():
                continue
            if path and not any(p["code"] in codes for p in item["paths"]):
                continue
            teams = groups.get((row.id, item["id"]), [])
            status = state_of(teams, user)
            if state != "all" and state != status:
                continue
            items.append({**item, "publication_id": row.id, "source": data["source"],
                "document": data["document"], "availability": information_state(item),
                "team_state": status, "team_count": len(teams),
                "open_slots": sum(max(0, t.capacity-len(r.members)) for l,t,r in teams if l.recruiting)})
    items.sort(key=lambda i: (i["document"]["fetched_at"], i["id"]), reverse=True)
    return {"total": len(items), "items": items[offset:offset+limit]}


@router.get("/activity/{publication_id}/{item_id}")
def activity_detail(publication_id: str, item_id: str,
        user: str = Depends(actor_id), db: Session = Depends(get_db)):
    item = activity(db, publication_id, item_id)
    requests = {r.team_id: r for r in db.scalars(select(TeamJoinRequest).where(TeamJoinRequest.user_id == user))}
    teams = []
    for link, team, room in activity_rows(db):
        if (link.publication_id, link.item_id) != (publication_id, item_id) or blocked(db, user, team.owner):
            continue
        member = user in room.members
        request = requests.get(team.id)
        teams.append({"id": team.id, "title": team.title, "description": link.description,
            "capacity": team.capacity, "member_count": len(room.members),
            "is_member": member, "is_owner": team.owner == user,
            "state": state_of([(link, team, room)], user),
            "recruiting": link.recruiting, "request_status": request.status if request else None,
            **({"room_id": room.id} if member else {})})
    return {"activity": item, "teams": teams}


@router.post("")
def create(body: NewActivityTeam, user: str = Depends(actor_id), db: Session = Depends(get_db)):
    activity(db, body.publication_id, body.item_id)
    consume(db, user, "activity-team-create", 10, 3600)
    room = Room(id=str(uuid4()), title=body.title, members=[user])
    team = Team(id=str(uuid4()), owner=user, title=body.title, room_id=room.id, capacity=body.capacity)
    link = ActivityTeam(team_id=team.id, publication_id=body.publication_id, item_id=body.item_id,
        description=body.description, recruiting=True, created_at=datetime.now(UTC))
    db.add_all([room, team, link])
    db.commit()
    return {"id": team.id, "room_id": room.id, "status": "created"}


@router.post("/{team_id}/request")
def join(team_id: str, body: JoinBody, user: str = Depends(actor_id), db: Session = Depends(get_db)):
    consume(db, user, "activity-team-request", 30, 3600)
    team, room = lock_team(db, team_id)
    link = db.get(ActivityTeam, team_id)
    if not link:
        raise HTTPException(404, "该队伍未开放活动组队")
    activity(db, link.publication_id, link.item_id)
    if user in room.members:
        return {"status": "joined"}
    if blocked(db, user, team.owner):
        raise HTTPException(403, "当前无法申请此队伍")
    if not link.recruiting or len(room.members) >= team.capacity:
        raise HTTPException(409, "队伍已满或暂停招募")
    row = db.get(TeamJoinRequest, (team_id, user))
    if row and row.status == "pending":
        return {"status": "pending"}
    if row:
        row.status, row.message, row.created_at = "pending", body.message, datetime.now(UTC)
    else:
        db.add(TeamJoinRequest(id=str(uuid4()), team_id=team_id, user_id=user,
            status="pending", message=body.message, created_at=datetime.now(UTC)))
    db.commit()
    return {"status": "pending"}


@router.get("/requests")
def incoming(user: str = Depends(actor_id), db: Session = Depends(get_db)):
    rows = db.execute(select(TeamJoinRequest, Team).join(Team, Team.id == TeamJoinRequest.team_id)
        .where(Team.owner == user, Team.status == "active", TeamJoinRequest.status == "pending")
        .order_by(TeamJoinRequest.created_at)).all()
    result = []
    for request, team in rows:
        profile = db.get(Profile, request.user_id)
        result.append({"id": request.id, "team_id": team.id, "team_title": team.title,
            "display_name": profile.display_name if profile else "同学",
            "message": request.message, "created_at": request.created_at})
    return result


@router.post("/requests/{request_id}/decision")
def decide(request_id: str, body: JoinDecision, user: str = Depends(actor_id), db: Session = Depends(get_db)):
    request = db.scalar(select(TeamJoinRequest).where(TeamJoinRequest.id == request_id))
    if not request:
        raise HTTPException(404, "申请不存在")
    team, room = lock_team(db, request.team_id)
    if team.owner != user:
        raise HTTPException(404, "申请不存在")
    db.refresh(request)
    if request.status != "pending":
        raise HTTPException(409, "申请已处理")
    if body.action == "accept":
        link = db.get(ActivityTeam, team.id)
        if not link:
            raise HTTPException(404, "活动关联不存在")
        activity(db, link.publication_id, link.item_id)
        if blocked(db, user, request.user_id):
            raise HTTPException(403, "当前无法接受此申请")
        if request.user_id not in room.members and len(room.members) >= team.capacity:
            raise HTTPException(409, "队伍已满")
        room.members = sorted(set(room.members + [request.user_id]))
    request.status = "accepted" if body.action == "accept" else "rejected"
    db.commit()
    return {"status": request.status}


@router.post("/{team_id}/recruitment")
def recruitment(team_id: str, body: Recruitment, user: str = Depends(actor_id), db: Session = Depends(get_db)):
    team, _ = lock_team(db, team_id)
    link = db.get(ActivityTeam, team_id)
    if team.owner != user or not link:
        raise HTTPException(404, "队伍不存在")
    link.recruiting = body.recruiting
    db.commit()
    return {"recruiting": link.recruiting}

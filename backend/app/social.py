"""Demo social slice. Identity headers are not production authentication."""

from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import JSON, Boolean, String, Text, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from .auth import actor_id
from .config import settings
from .database import Base, get_db
from .models import Profile
from .rate_limits import consume


class Room(Base):
    __tablename__ = "rooms"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(100))
    members: Mapped[list] = mapped_column(JSON)


class Message(Base):
    __tablename__ = "room_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[str] = mapped_column(String(36), index=True)
    sender: Mapped[str] = mapped_column(String(80))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40))
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")


class RoomRead(Base):
    __tablename__ = "room_reads"
    room_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    last_message_id: Mapped[int] = mapped_column(default=0)


class ReadInput(BaseModel):
    message_id: int = Field(ge=1)


def message_out(m):
    return {"id": m.id, "room_id": m.room_id, "sender": m.sender,
            "body": "[消息已由管理员移除]" if m.hidden else m.body,
            "created_at": m.created_at, "hidden": m.hidden}


class Block(Base):
    __tablename__ = "social_blocks"
    owner: Mapped[str] = mapped_column(String(80), primary_key=True)
    target: Mapped[str] = mapped_column(String(80), primary_key=True)


class Report(Base):
    __tablename__ = "message_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    reporter: Mapped[str] = mapped_column(String(80))
    message_id: Mapped[int]
    reason: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    resolved_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class Connect(BaseModel):
    target: str = Field(min_length=1, max_length=80)


class Send(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class ReportInput(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


CANDIDATES = [
    {"user_id": "demo-python", "name": "演示队友·开发", "skills": ["Python", "AI"], "hours": 10},
    {"user_id": "demo-design", "name": "演示队友·设计", "skills": ["设计", "产品"], "hours": 6},
]


def router_for(actor):
    router = APIRouter(prefix="/v1")

    def require_room(db, room_id, user):
        room = db.get(Room, room_id)
        if not room or user not in room.members:
            raise HTTPException(404, "会话不存在")
        return room

    router.add_api_route("/tools/team_match", match_candidates, methods=["POST"])

    @router.post("/tools/message_connect")
    def connect(body: Connect, user: str = Depends(actor), db: Session = Depends(get_db)):
        return connect_user(body, user, db)

    @router.get("/rooms")
    def rooms(user: str = Depends(actor), db: Session = Depends(get_db)):
        items = []
        for r in db.scalars(select(Room)).all():
            if user not in r.members:
                continue
            read = db.get(RoomRead, (r.id, user))
            last = read.last_message_id if read else 0
            unread = db.scalar(select(func.count()).select_from(Message).where(
                Message.room_id == r.id, Message.id > last, Message.sender != user,
                Message.hidden.is_(False)))
            items.append({"id": r.id, "title": r.title, "members": r.members,
                          "unread_count": unread, "last_read_message_id": last})
        return items

    @router.get("/rooms/{room_id}/messages")
    def messages(
        room_id: str, after: int = 0, user: str = Depends(actor), db: Session = Depends(get_db)
    ):
        require_room(db, room_id, user)
        rows = db.scalars(
            select(Message)
            .where(Message.room_id == room_id, Message.id > after)
            .order_by(Message.id)
            .limit(100)
        ).all()
        return [message_out(m) for m in rows]

    @router.get("/rooms/{room_id}/history")
    def history(room_id: str, before: int | None = Query(None, ge=1),
                after: int | None = Query(None, ge=0), limit: int = Query(50, ge=1, le=100),
                user: str = Depends(actor), db: Session = Depends(get_db)):
        require_room(db, room_id, user)
        if before is not None and after is not None:
            raise HTTPException(422, "不能同时使用前向和后向游标")
        stmt = select(Message).where(Message.room_id == room_id)
        if before is not None:
            stmt = stmt.where(Message.id < before)
        if after is not None:
            stmt = stmt.where(Message.id > after)
        rows = list(db.scalars(stmt.order_by(
            Message.id.asc() if after is not None else Message.id.desc()).limit(limit + 1)))
        has_more = len(rows) > limit
        rows = rows[:limit]
        if after is None:
            rows.reverse()
        return {"items": [message_out(m) for m in rows], "has_more": has_more,
                "oldest_id": rows[0].id if rows else None,
                "newest_id": rows[-1].id if rows else None}

    @router.post("/rooms/{room_id}/read")
    def mark_read(room_id: str, body: ReadInput, user: str = Depends(actor),
                  db: Session = Depends(get_db)):
        # Same lock as membership changes/sends: serialize initial insert and monotonic updates.
        db.execute(update(Room).where(Room.id == room_id).values(title=Room.title))
        require_room(db, room_id, user)
        message = db.get(Message, body.message_id)
        if not message or message.room_id != room_id:
            raise HTTPException(422, "已读位置不属于当前会话")
        row = db.get(RoomRead, (room_id, user))
        if not row:
            row = RoomRead(room_id=room_id, user_id=user, last_message_id=body.message_id)
            db.add(row)
        else:
            row.last_message_id = max(row.last_message_id, body.message_id)
        db.commit()
        return {"last_read_message_id": row.last_message_id}

    @router.post("/rooms/{room_id}/messages")
    def send(room_id: str, body: Send, user: str = Depends(actor), db: Session = Depends(get_db)):
        # Serialize sends and membership changes on this room, across API processes.
        db.execute(update(Room).where(Room.id == room_id).values(title=Room.title))
        room = require_room(db, room_id, user)
        since = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
        count = db.scalar(select(func.count()).select_from(Message).where(Message.room_id == room_id, Message.sender == user, Message.created_at >= since))
        if count >= 20:
            raise HTTPException(429, "每个会话每分钟最多发送 20 条消息", headers={"Retry-After": "60"})
        if not body.body.strip():
            raise HTTPException(422, "消息不能为空")
        if any(
            db.get(Block, (user, other)) or db.get(Block, (other, user))
            for other in room.members
            if other != user
        ):
            raise HTTPException(403, "已拉黑，不能发送消息")
        consume(db, user, "message-minute", 60, 60)
        consume(db, user, "message-day", 200, 86400)
        msg = Message(
            room_id=room_id,
            sender=user,
            body=body.body.strip(),
            created_at=datetime.now(UTC).isoformat(),
        )
        db.add(msg)
        db.commit()
        return msg

    @router.post("/blocks")
    def block(body: Connect, user: str = Depends(actor), db: Session = Depends(get_db)):
        if body.target == user:
            raise HTTPException(422, "不能拉黑自己")
        db.merge(Block(owner=user, target=body.target))
        db.commit()
        return {"blocked": True}

    @router.post("/messages/{message_id}/report")
    def report(
        message_id: int,
        body: ReportInput,
        user: str = Depends(actor),
        db: Session = Depends(get_db),
    ):
        msg = db.get(Message, message_id)
        if not msg:
            raise HTTPException(404, "消息不存在")
        require_room(db, msg.room_id, user)
        if not body.reason.strip():
            raise HTTPException(422, "举报原因不能为空")
        db.execute(update(Message).where(Message.id == message_id).values(hidden=Message.hidden))
        existing = db.scalar(select(Report).where(Report.reporter == user, Report.message_id == message_id))
        if existing:
            return {"id": existing.id, "status": existing.status}
        consume(db, user, "report-day", 20, 86400)
        db.add(Report(reporter=user, message_id=message_id, reason=body.reason.strip()))
        db.commit()
        return {"status": "pending_review"}

    return router


def match_candidates(skills: list[str], user: str = Depends(actor_id), db: Session = Depends(get_db)):
    if len(skills) > 20 or any(not s.strip() or len(s) > 40 for s in skills):
        raise HTTPException(422, "技能数量或长度无效")
    wanted = {s.strip().casefold() for s in skills}
    me = db.get(Profile, user)
    candidates = []
    if me and me.school.strip():
        rows = db.scalars(select(Profile).where(Profile.discoverable.is_(True), Profile.school == me.school, Profile.user_id != user)).all()
        for p in rows:
            if db.get(Block, (user, p.user_id)) or db.get(Block, (p.user_id, user)):
                continue
            candidates.append({"user_id": p.user_id, "name": p.display_name, "skills": [v for v in p.skills.split(',') if v], "hours": p.weekly_hours})
    if settings.demo_mode:
        candidates += [c for c in CANDIDATES if c['user_id'] != user and not db.get(Block, (user, c['user_id'])) and not db.get(Block, (c['user_id'], user))]
    items = []
    for c in candidates:
        matched = sorted(wanted & {s.casefold() for s in c['skills']})
        score = round(100 * len(matched) / max(1, len(wanted)))
        items.append(dict(c, score=score, matched_skills=matched, score_breakdown={"skill_coverage": score}))
    return {"demo": settings.demo_mode, "items": sorted(items, key=lambda c: (-c['score'], c['user_id']))[:50]}

def connect_user(body: Connect, user: str, db: Session, commit: bool = True):
    target = db.get(Profile, body.target)
    me = db.get(Profile, user)
    demo_target = settings.demo_mode and body.target in {c['user_id'] for c in CANDIDATES}
    visible = target and target.discoverable and me and me.school.strip() and target.school == me.school
    if body.target == user or not (demo_target or visible):
        raise HTTPException(422, "目标用户未开放同校联系")
    if db.get(Block, (user, body.target)) or db.get(Block, (body.target, user)):
        raise HTTPException(403, "已拉黑，无法建立联系")
    members = sorted([user, body.target])
    import json
    room_id = str(uuid5(NAMESPACE_URL, 'campusmate:direct:' + json.dumps(members)))
    existing = db.get(Room, room_id)
    if existing:
        return existing
    consume(db, user, "contact-day", 10, 86400)
    # Recheck after the account lock so an idempotent concurrent contact costs no second slot.
    existing = db.get(Room, room_id)
    if existing:
        return existing
    room = Room(id=room_id, title="同学交流", members=members)
    try:
        with db.begin_nested():
            db.add(room)
            db.flush()
        if commit:
            db.commit()
    except IntegrityError:
        room = db.get(Room, room_id)
        if not room:
            raise
    return room


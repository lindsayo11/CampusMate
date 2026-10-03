"""Report decisions retain evidence; ordinary readers see a removal placeholder."""
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .auth import actor_id, require_admin
from .database import get_db
from .governance import audit
from .social import Block, Message, Report

router = APIRouter(prefix="/v1")


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    action: Literal["dismiss", "remove"]
    note: str = Field(min_length=1, max_length=1000)


@router.get("/admin/reports")
def reports(status: Literal["pending", "dismissed", "removed"] = "pending",
            after: int = Query(0, ge=0), user: str = Depends(require_admin),
            db: Session = Depends(get_db)):
    rows = db.scalars(select(Report).where(Report.status == status, Report.id > after)
                      .order_by(Report.id).limit(100)).all()
    items = []
    for row in rows:
        msg = db.get(Message, row.message_id)
        items.append({"id": row.id, "message_id": row.message_id, "reason": row.reason,
                      "status": row.status, "decision_note": row.decision_note,
                      "resolved_at": row.resolved_at,
                      "evidence": {"body": msg.body, "sender": msg.sender,
                                   "created_at": msg.created_at} if msg else None})
    return {"items": items, "next_after": rows[-1].id if len(rows) == 100 else None}


@router.post("/admin/reports/{report_id}/decision")
def decide(report_id: int, body: Decision, user: str = Depends(require_admin),
           db: Session = Depends(get_db)):
    # A conditional update makes competing reviewers mutually exclusive.
    row = db.get(Report, report_id)
    if not row:
        raise HTTPException(404, "举报不存在")
    status = "removed" if body.action == "remove" else "dismissed"
    if row.status != "pending":
        if row.status == status:
            return {"id": row.id, "status": row.status}
        raise HTTPException(409, "举报已处理，不能覆盖原决定")
    changed = db.execute(update(Report).where(Report.id == report_id, Report.status == "pending")
                         .values(status=status, decision_note=body.note, resolved_by=user,
                                 resolved_at=datetime.now(UTC).isoformat()))
    if not changed.rowcount:
        raise HTTPException(409, "举报已由其他管理员处理")
    if body.action == "remove":
        db.execute(update(Message).where(Message.id == row.message_id).values(hidden=True))
    audit(db, user, "report_" + body.action, f"report:{report_id}",
          {"message_id": row.message_id})
    db.commit()
    return {"id": row.id, "status": status}


@router.get("/reports/mine")
def own_reports(user: str = Depends(actor_id), db: Session = Depends(get_db)):
    rows = db.scalars(select(Report).where(Report.reporter == user)
                      .order_by(Report.id.desc()).limit(100)).all()
    return [{"id": row.id, "message_id": row.message_id, "reason": row.reason,
             "status": row.status, "resolved_at": row.resolved_at} for row in rows]


@router.get("/blocks")
def blocks(user: str = Depends(actor_id), db: Session = Depends(get_db)):
    return [{"target": row.target} for row in db.scalars(select(Block).where(Block.owner == user))]


@router.delete("/blocks/{target}")
def unblock(target: str, user: str = Depends(actor_id), db: Session = Depends(get_db)):
    row = db.get(Block, (user, target))
    if row:
        db.delete(row)
        db.commit()
    return {"blocked": False}

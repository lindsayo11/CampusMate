"""Operational visibility without exposing credentials or private message content."""
import json
import logging
import time
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends
from sqlalchemy import DateTime, String, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .auth import require_admin
from .database import Base, SessionLocal, get_db
from .models import Opportunity, Reminder


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"
    name: Mapped[str] = mapped_column(String(40), primary_key=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    state: Mapped[str] = mapped_column(String(20))


def heartbeat(state):
    with SessionLocal.begin() as db:
        db.merge(WorkerHeartbeat(name="reminders", observed_at=datetime.now(UTC), state=state))


def install_request_logging(app):
    logger = logging.getLogger("campusmate.requests")
    if not logger.handlers:
        logger.addHandler(logging.StreamHandler())
    logger.setLevel(logging.INFO)
    logger.propagate = False

    @app.middleware("http")
    async def trace_request(request, call_next):
        trace_id = str(uuid4())
        started = time.monotonic()
        response = await call_next(request)
        response.headers["X-Request-ID"] = trace_id
        route = request.scope.get("route")
        logger.info(json.dumps({"trace_id": trace_id, "method": request.method,
                                "route": getattr(route, "path", "unmatched"),
                                "status": response.status_code,
                                "latency_ms": round((time.monotonic() - started) * 1000, 1)}))
        return response


router = APIRouter(prefix="/v1/admin")


@router.get("/operations")
def operations(user: str = Depends(require_admin), db: Session = Depends(get_db)):
    worker = db.get(WorkerHeartbeat, "reminders")
    now = datetime.now(UTC)
    age = (now - worker.observed_at.replace(tzinfo=UTC)).total_seconds() if worker else None
    return {"worker": {"state": worker.state if worker else "missing", "age_seconds": age,
                       "healthy": bool(worker and worker.state == "ok" and age < 120)},
            "pending_reminders": db.scalar(select(func.count()).select_from(Reminder).where(Reminder.sent.is_(False))),
            "published_opportunities": db.scalar(select(func.count()).select_from(Opportunity).where(Opportunity.status == "published", Opportunity.deadline > now))}

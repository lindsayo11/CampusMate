from datetime import UTC, datetime, timedelta
from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.database import SessionLocal
from app.models import Reminder
from app.worker import deliver_due


def test_identity_fail_closed(monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", False)
    with TestClient(app) as c:
        assert c.get("/v1/profile", headers={"X-User-Id":"admin"}).status_code == 401
        assert c.get("/v1/admin/reviews").status_code == 401


def test_admin_and_notifications():
    user = str(uuid4())
    with TestClient(app) as c:
        assert c.get("/v1/admin/reviews", headers={"X-User-Id":user}).status_code == 403
        with SessionLocal.begin() as db:
            db.add(Reminder(user_id=user, opportunity_id="job-001", due_at=datetime.now(UTC)-timedelta(hours=1), created_at=datetime.now(UTC)))
        deliver_due()
        deliver_due()
        rows = c.get("/v1/notifications", headers={"X-User-Id":user}).json()
        assert len(rows) == 1
        assert c.get("/v1/notifications", headers={"X-User-Id":str(uuid4())}).json() == []

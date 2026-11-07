from datetime import UTC, datetime, timedelta
from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.database import SessionLocal
from app.models import Reminder
from app.worker import deliver_due
from app.intake_models import DataSubscription
from app.notification_models import NotificationPreference


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


def test_source_update_notification_preference_is_saved_per_user():
    user=str(uuid4())
    headers={"X-User-Id":user}
    with TestClient(app) as c:
        assert c.get("/v1/notification-preferences",headers=headers).json()=={"source_updates":True}
        saved=c.put("/v1/notification-preferences",headers=headers,json={"source_updates":False})
        assert saved.status_code==200 and saved.json()=={"source_updates":False}
        assert c.get("/v1/notification-preferences",headers=headers).json()=={"source_updates":False}


def test_disabled_source_updates_suppress_change_and_deadline_alerts(monkeypatch):
    from types import SimpleNamespace
    from app import data_catalog

    user=str(uuid4())
    now=datetime.now(UTC)
    with SessionLocal.begin() as db:
        db.add(NotificationPreference(user_id=user,source_updates=False,updated_at=now))
        db.add_all([
            DataSubscription(id=str(uuid4()),user_id=user,item_id="changed-item",
                publication_id="withdrawn-publication",plan_id=90001,title="来源变更",
                status="active",message="",remind_at=None,alerted_at=None,read_at=None),
            DataSubscription(id=str(uuid4()),user_id=user,item_id="due-item",
                publication_id="live-publication",plan_id=90002,title="截止提醒",
                status="active",message="",remind_at=now-timedelta(hours=1),alerted_at=None,read_at=None),
        ])
    monkeypatch.setattr(data_catalog,"visible",lambda _db:[(SimpleNamespace(id="live-publication"),{})])
    assert data_catalog.deliver_data_alerts()==0
    with SessionLocal() as db:
        rows=db.query(DataSubscription).filter(DataSubscription.user_id==user).all()
        assert len(rows)==2
        assert all(row.status=="active" and row.alerted_at is None and not row.message for row in rows)

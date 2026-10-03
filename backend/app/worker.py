import time
from datetime import UTC, datetime
from sqlalchemy import select, update
from .database import SessionLocal
from .models import Reminder
from .notification_models import Notification


def deliver_due():
    delivered = 0
    with SessionLocal.begin() as db:
        ids = db.scalars(select(Reminder.id).where(Reminder.sent.is_(False), Reminder.due_at <= datetime.now(UTC))).all()
        for rid in ids:
            claimed = db.execute(update(Reminder).where(Reminder.id == rid, Reminder.sent.is_(False)).values(sent=True))
            if claimed.rowcount:
                reminder = db.get(Reminder, rid)
                db.add(Notification(reminder_id=rid, user_id=reminder.user_id, opportunity_id=reminder.opportunity_id, created_at=datetime.now(UTC).isoformat()))
                delivered += 1
    from .operations import heartbeat
    heartbeat("ok")
    return delivered


def run_cycle():
    from .config import settings
    from .task_alerts import deliver_task_alerts
    from .operations import heartbeat
    deliver_due()
    deliver_task_alerts()
    from .data_catalog import deliver_data_alerts
    deliver_data_alerts()
    from .development_agent import deliver_plan_reminders
    deliver_plan_reminders()
    from .notice_watch import run_cycle as watch_cycle
    watch_cycle()
    if settings.collector_enabled:
        from .collector import schedule_due, process_one
        from .source_scheduler import process_endpoint_once, schedule_due_endpoints
        schedule_due()
        process_one()
        schedule_due_endpoints()
        process_endpoint_once()
    heartbeat("ok")


def main():
    from .migrate import check_schema
    check_schema()
    while True:
        try:
            run_cycle()
        except Exception:
            import logging
            logging.error("Worker cycle failed; retry in 30s")
            try:
                from .operations import heartbeat
                heartbeat("error")
            except Exception:
                logging.error("Worker heartbeat unavailable")
        time.sleep(30)


if __name__ == "__main__":
    main()

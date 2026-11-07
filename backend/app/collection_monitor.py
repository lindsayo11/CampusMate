"""Independent durable alerts; stays alive when the collection worker stops."""
from datetime import UTC, datetime, timedelta
import time
from uuid import uuid4
import hashlib

from sqlalchemy import select
from .database import SessionLocal
from .intake_models import CollectionAlert, CollectionAttempt, NoticeResource, Source
from .operations import WorkerHeartbeat
from .coverage_quality import utc


def record_attempt(db, row, outcome, response=None, error=''):
    response=response or {}
    content=response.get('data',b'')
    # Store at most one copy of an identical failed response for a resource.
    digest=hashlib.sha256(content).hexdigest() if content else ''
    saved=None
    if content and outcome in {'failed','pending_attachment'} and not db.scalar(select(CollectionAttempt.id).where(
            CollectionAttempt.resource_id==row.id,CollectionAttempt.content_hash==digest,
            CollectionAttempt.content.is_not(None))):
        saved=content
    db.add(CollectionAttempt(id=str(uuid4()),resource_id=row.id,endpoint_id=row.endpoint_id,
        observed_at=row.checked_at,outcome=outcome,error=error[:500],content_hash=digest,
        content_type=response.get('content_type','')[:160],content=saved))


def check_alerts(db, now=None):
    from .notice_watch import monitor_status
    now=now or datetime.now(UTC)
    problems={}
    from .collection_exchange import status as sync_status
    sync=sync_status(db)
    if sync['state'] in {'error','partial','stale'}:
        pending_label='待处理' if sync['state']=='partial' else '上次清点待处理'
        problems['collection-sync']=(None,(sync.get('error') or '官方原文同步检查超时')+
            '；'+pending_label+' '+str(sync['pending'])+' 条')
    heartbeat=db.get(WorkerHeartbeat,'reminders')
    if not heartbeat or heartbeat.state!='ok' or now-utc(heartbeat.observed_at)>timedelta(minutes=4):
        problems['worker']=(None,'持续采集 Worker 心跳异常或超过 4 分钟未更新')
    for monitor in monitor_status(db):
        if not monitor['enabled']:continue
        eid=monitor['endpoint_id']
        if monitor.get('success_freshness') in {'stale','never_succeeded'}:
            problems['source:'+eid]=(eid,f"{monitor['name']}：超过两轮间隔未成功检查，或尚未成功检查")
        failures=db.scalars(select(NoticeResource).where(NoticeResource.endpoint_id==eid,
            NoticeResource.status!='retired',NoticeResource.failures>=3)).all()
        if failures:
            problems['failures:'+eid]=(eid,f"{monitor['name']}：{len(failures)} 个资源连续失败至少 3 次")
    for key,(eid,message) in problems.items():
        alert=db.get(CollectionAlert,key)
        if not alert:
            alert=CollectionAlert(key=key,endpoint_id=eid,status='active',message=message,
                first_seen_at=now,last_seen_at=now);db.add(alert)
        else:
            if alert.status=='resolved':alert.first_seen_at=now
            alert.status='active';alert.message=message;alert.last_seen_at=now;alert.resolved_at=None
    for alert in db.scalars(select(CollectionAlert).where(CollectionAlert.status=='active')).all():
        # Independent cloud watchdog alerts have their own recovery observations.
        # A local poll cannot resolve them and start a new outage every 5 minutes.
        owned=alert.key in {'worker','collection-sync'} or alert.key.startswith(('source:','failures:'))
        if owned and alert.key not in problems:
            alert.status='resolved';alert.resolved_at=now;alert.last_seen_at=now
    db.merge(WorkerHeartbeat(name='collection-monitor',observed_at=now,state='ok'))
    from .alert_delivery import queue_alerts
    queue_alerts(db,now)
    return len(problems)


def main():
    from .migrate import check_schema
    check_schema()
    while True:
        try:
            with SessionLocal.begin() as db:check_alerts(db)
            from .alert_delivery import deliver_once
            deliver_once()
        except Exception:
            import logging
            logging.exception('Collection monitor failed')
        time.sleep(30)


if __name__=='__main__':main()

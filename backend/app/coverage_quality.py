"""Observed collection quality, kept separate from candidate/probe counts."""
from collections import Counter
from datetime import UTC, datetime, timedelta

from .public_source_catalog import TOPIC_LABELS


def utc(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return value.replace(tzinfo=UTC) if value and value.tzinfo is None else value


def error_category(message):
    if 'robots' in message and '不允许' in message:
        return 'access_denied'
    if any(x in message for x in ('登录','验证码','白名单','HTTPS','不允许','权限限制')):
        return 'access_denied'
    if any(x in message for x in ('HTTP','超时','网络','解析失败','404','限流','域名解析')):
        return 'network'
    if 'OCR' in message:
        return 'ocr_required'
    if any(x in message for x in ('主题','标题')):
        return 'title_or_topic'
    return 'body_or_structure'


def summarize(monitors, sources, worker=None, now=None):
    now = now or datetime.now(UTC)
    by_code = {s['source_code']:s for s in sources}
    topics = []
    for key, label in TOPIC_LABELS.items():
        rows = [m for m in monitors if m['topic'] == key]
        codes = {m['source_code'] for m in rows}
        content = [s for code,s in by_code.items() if code in codes]
        topics.append({'topic':key,'label':label,'enabled_sources':sum(m['enabled'] for m in rows),
            'healthy_sources':sum(m['enabled'] and m['index_healthy'] for m in rows),
            'public_items':sum(s['items'] for s in content),
            'application_notices':sum(s['notices'] for s in content),
            'open':sum(s.get('availability',{}).get('open',0) for s in content),
            'upcoming':sum(s.get('availability',{}).get('upcoming',0) for s in content),
            'needs_confirmation':sum(s.get('availability',{}).get('needs_confirmation',0) for s in content)})
    configured = {m['source_code'] for m in monitors}
    count = sum(m.get('details_discovered',0) for m in monitors)
    collected = sum(m.get('details_collected',0) for m in monitors)
    notices = sum(s['notices'] for s in sources)
    dated = sum(s.get('dated_notices',0) for s in sources)
    states = Counter()
    errors = Counter()
    for m in monitors:
        errors.update(m.get('error_categories',{}))
    for s in sources:
        states.update(s.get('availability',{}))
    age = (now-utc(worker.observed_at)).total_seconds() if worker else None
    return {'topics':topics,'unmonitored_items':sum(s['items'] for s in sources if s['source_code'] not in configured),
        'details_discovered':count,'details_collected':collected,
        'detail_success_rate':round(collected/count*100,1) if count else None,
        'application_notices':notices,'dated_notices':dated,
        'deadline_completeness':round(dated/notices*100,1) if notices else None,
        'availability':dict(states),
        'error_categories':dict(errors),
        'enabled_sources':sum(m['enabled'] for m in monitors),
        'stale_sources':sum(m['enabled'] and m.get('freshness')=='stale' for m in monitors),
        'unsuccessful_sources':sum(m['enabled'] and m.get('success_freshness') in {'stale','never_succeeded'} for m in monitors),
        'regions':dict(sorted(Counter(m.get('region') or '未标注' for m in monitors if m['enabled']).items())),
        'worker':{'status':'unknown' if not worker else 'stale' if age > 180 else worker.state,
                  'observed_at':utc(worker.observed_at).isoformat() if worker else None}}


def recent_attempts(db, now=None):
    from sqlalchemy import select, func
    from .intake_models import CollectionAttempt, CollectionAlert,CollectionAlertDelivery,NoticeResource,DocumentVersion,Evidence
    from .config import settings
    import json
    from .operations import WorkerHeartbeat
    now=now or datetime.now(UTC)
    counts=dict(db.execute(select(CollectionAttempt.outcome,func.count()).where(
        CollectionAttempt.observed_at>=now-timedelta(hours=24)).group_by(CollectionAttempt.outcome)).all())
    total=sum(counts.values());succeeded=counts.get('success',0)
    sensor=db.get(WorkerHeartbeat,'collection-monitor')
    from .collection_exchange import status as sync_status
    formats=Counter()
    for doc in db.scalars(select(DocumentVersion).join(NoticeResource,NoticeResource.document_id==DocumentVersion.id).where(
        NoticeResource.kind=='support_file',NoticeResource.status!='retired',DocumentVersion.deleted_at.is_(None))).all():
        try:formats[json.loads(doc.raw_text)['format']]+=1
        except (ValueError,KeyError,TypeError):continue
    backups={}
    for name,key in [('collection-backup','railway'),('offsite-backup','offsite')]:
        row=db.get(WorkerHeartbeat,name)
        backups[key]={'state':'not_observed' if not row else 'ok' if row.state=='ok' and now-utc(row.observed_at)<timedelta(hours=36) else 'stale',
            'last_verified_at':utc(row.observed_at).isoformat() if row else None}
    deliveries=dict(db.execute(select(CollectionAlertDelivery.state,func.count()).group_by(CollectionAlertDelivery.state)).all())
    channel=settings.collection_alert_channel
    return {'attempts_24h':total,'successful_attempts_24h':succeeded,
        'sync':sync_status(db),
        'attachments':{'archived':sum(formats.values()),'formats':dict(formats),
            'waiting':db.scalar(select(func.count()).select_from(NoticeResource).where(NoticeResource.kind=='support_file',
                NoticeResource.status!='retired',NoticeResource.document_id.is_(None))),
            'ocr_documents':db.scalar(select(func.count(func.distinct(Evidence.document_version_id))).join(
                NoticeResource,NoticeResource.document_id==Evidence.document_version_id).where(
                Evidence.extractor=='ocr',NoticeResource.status!='retired'))},
        'alert_delivery':{'channel':channel if channel=='desktop' or settings.collection_alert_webhook else 'not_configured',
            'pending':deliveries.get('queued',0)+deliveries.get('retry',0),'delivered':deliveries.get('sent',0)},
        'backups':backups,
        'attempt_success_rate_24h':round(succeeded/total*100,1) if total else None,
        'active_alerts':db.scalar(select(func.count()).select_from(CollectionAlert).where(CollectionAlert.status=='active')),
        'monitor_status':'ok' if sensor and sensor.state=='ok' and now-utc(sensor.observed_at)<timedelta(minutes=4) else 'stale'}

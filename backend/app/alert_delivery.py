"""Notify only meaningful alert changes; retries survive monitor restarts."""
import hashlib
import ipaddress
import subprocess
from datetime import UTC,datetime,timedelta
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select,update

from .collector_http import public_ip
from .config import settings
from .database import SessionLocal
from .intake_models import CollectionAlert,CollectionAlertDelivery


def queue_alerts(db,now=None):
    if not settings.collection_alert_webhook and settings.collection_alert_channel!='desktop':return 0
    now=now or datetime.now(UTC);count=0
    for alert in db.scalars(select(CollectionAlert)).all():
        # last_seen_at changes every poll; it is deliberately absent from this key.
        first=alert.first_seen_at.replace(tzinfo=UTC) if alert.first_seen_at.tzinfo is None else alert.first_seen_at.astimezone(UTC)
        identity=f'{alert.key}\0{first.isoformat()}\0{alert.status}'
        key=hashlib.sha256(identity.encode()).hexdigest()
        existing=db.get(CollectionAlertDelivery,key)
        if not existing:
            legacy_key=hashlib.sha256((identity+'\0'+alert.message).encode()).hexdigest()
            existing=db.get(CollectionAlertDelivery,legacy_key)
            if existing:existing.key=key  # Preserve successful deliveries across the episode-key upgrade.
        if existing:
            if existing.state in {'queued','retry','superseded'}:
                existing.message=alert.message
                if existing.state=='superseded':existing.state='queued';existing.next_attempt_at=now
            continue
        # Avoid sending historic resolved alerts when the channel is first configured.
        if alert.status=='resolved' and not db.scalar(select(CollectionAlertDelivery.key).where(
            CollectionAlertDelivery.alert_key==alert.key)):continue
        db.add(CollectionAlertDelivery(key=key,alert_key=alert.key,status=alert.status,message=alert.message,
            state='queued',attempts=0,created_at=now,next_attempt_at=now,error=''));count+=1
    db.flush()
    return count


def send_alert(message,status):
    if settings.collection_alert_channel=='desktop':
        script='on run argv\ndisplay notification (item 1 of argv) with title (item 2 of argv)\nend run'
        result=subprocess.run(['osascript','-e',script,message[:450],'CampusMate 采集状态'],
            capture_output=True,timeout=10)
        if result.returncode:raise ValueError('desktop notification rejected')
        return
    parts=urlsplit(settings.collection_alert_webhook)
    if parts.scheme!='https' or not parts.hostname or parts.username or parts.password or parts.port not in (None,443):
        raise ValueError('invalid webhook')
    address=public_ip(parts.hostname)
    host=f'[{address}]' if ipaddress.ip_address(address).version==6 else address
    url=f'https://{host}{parts.path or "/"}'+('?' + parts.query if parts.query else '')
    text=('CampusMate 采集恢复：' if status=='resolved' else 'CampusMate 采集告警：')+message
    channel=settings.collection_alert_channel
    if channel=='feishu':payload={'msg_type':'text','content':{'text':text}}
    elif channel=='wecom':payload={'msgtype':'text','text':{'content':text}}
    elif channel=='telegram':payload={'chat_id':settings.collection_alert_chat_id,'text':text}
    elif channel=='generic':payload={'service':'CampusMate','status':status,'message':text}
    else:raise ValueError('unknown channel')
    with httpx.Client(trust_env=False,follow_redirects=False,timeout=8) as client:
        response=client.post(url,headers={'Host':parts.hostname},json=payload,
            extensions={'sni_hostname':parts.hostname})
        response.raise_for_status()
        if len(response.content)>65536:raise ValueError('oversized receipt')
        if channel!='generic':
            receipt=response.json()
            accepted=receipt.get('ok') is True if channel=='telegram' else receipt.get('errcode',receipt.get('code'))==0
            if not accepted:raise ValueError('channel rejected delivery')


def deliver_once(limit=4):
    if settings.collection_alert_channel=='desktop':return deliver_desktop()
    if not settings.collection_alert_webhook:return {'state':'not_configured','sent':0}
    sent=failed=0
    for _ in range(limit):
        now=datetime.now(UTC)
        with SessionLocal.begin() as db:
            row=db.scalar(select(CollectionAlertDelivery).where(CollectionAlertDelivery.state.in_(['queued','retry']),
                CollectionAlertDelivery.next_attempt_at<=now,
                (CollectionAlertDelivery.lease_until.is_(None))|(CollectionAlertDelivery.lease_until<=now))
                .order_by(CollectionAlertDelivery.created_at).limit(1))
            if not row:break
            alert=db.get(CollectionAlert,row.alert_key)
            if not alert or alert.status!=row.status or alert.message!=row.message:
                row.state='superseded';continue
            claimed=db.execute(update(CollectionAlertDelivery).where(CollectionAlertDelivery.key==row.key,
                (CollectionAlertDelivery.lease_until.is_(None))|(CollectionAlertDelivery.lease_until<=now)).values(
                lease_until=now+timedelta(minutes=2),attempts=CollectionAlertDelivery.attempts+1)
                .execution_options(synchronize_session=False))
            if not claimed.rowcount:continue
            key,message,status=row.key,row.message,row.status
        error=''
        try:send_alert(message,status)
        except Exception:error='外部告警发送失败，已安排重试'  # Never expose webhook credentials or provider bodies.
        with SessionLocal.begin() as db:
            row=db.get(CollectionAlertDelivery,key);row.lease_until=None
            if error:
                row.state='retry';row.error=error
                row.next_attempt_at=datetime.now(UTC)+timedelta(seconds=min(21600,60*2**min(row.attempts,8)))
                failed+=1
            else:
                row.state='sent';row.error='';row.delivered_at=datetime.now(UTC);sent+=1
    return {'state':'retry' if failed else 'ok','sent':sent,'failed':failed}


def deliver_desktop():
    now=datetime.now(UTC);events=[]
    with SessionLocal.begin() as db:
        rows=db.scalars(select(CollectionAlertDelivery).where(CollectionAlertDelivery.state.in_(['queued','retry']),
            CollectionAlertDelivery.next_attempt_at<=now,
            (CollectionAlertDelivery.lease_until.is_(None))|(CollectionAlertDelivery.lease_until<=now))
            .order_by(CollectionAlertDelivery.created_at).limit(200)).all()
        for row in rows:
            alert=db.get(CollectionAlert,row.alert_key)
            if not alert or alert.status!=row.status or alert.message!=row.message:
                row.state='superseded';continue
            claimed=db.execute(update(CollectionAlertDelivery).where(CollectionAlertDelivery.key==row.key,
                (CollectionAlertDelivery.lease_until.is_(None))|(CollectionAlertDelivery.lease_until<=now)).values(
                lease_until=now+timedelta(minutes=2),attempts=CollectionAlertDelivery.attempts+1)
                .execution_options(synchronize_session=False))
            if claimed.rowcount:events.append((row.key,row.status,row.message))
    if not events:return {'state':'ok','sent':0}
    errors=sum(status=='active' for _,status,_ in events)
    body=f'{len(events)} 项状态变化：{errors} 项告警，{len(events)-errors} 项恢复。\n'+'\n'.join(message for _,_,message in events[:3])
    error=''
    try:send_alert(body,'active' if errors else 'resolved')
    except Exception:error='桌面告警发送失败，已安排重试'
    with SessionLocal.begin() as db:
        for key,_,_ in events:
            row=db.get(CollectionAlertDelivery,key);row.lease_until=None;row.error=error
            row.state='retry' if error else 'sent'
            if error:row.next_attempt_at=now+timedelta(minutes=5)
            else:row.delivered_at=datetime.now(UTC)
    return {'state':'retry' if error else 'ok','sent':0 if error else len(events),'failed':len(events) if error else 0}

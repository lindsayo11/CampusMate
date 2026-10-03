"""Keep an independent Mac watchdog on Railway API, worker and monitor heartbeats."""
import sys
from datetime import UTC,datetime,timedelta
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))

from app.collection_exchange import peer_request,utc
from app.database import SessionLocal
from app.intake_models import CollectionAlert
from app.operations import WorkerHeartbeat
from app.alert_delivery import queue_alerts,deliver_once


def run():
    now=datetime.now(UTC);problems={};remote=None
    try:
        remote=peer_request('GET','/health')
        for name,label in [('reminders','云端采集 Worker'),('collection-monitor','云端独立监控')]:
            heartbeat=remote['heartbeats'].get(name)
            if not heartbeat or heartbeat['state']!='ok' or now-utc(datetime.fromisoformat(heartbeat['observed_at']))>timedelta(minutes=5):
                problems['cloud:'+name]=label+'心跳异常或超过 5 分钟未更新'
        for name,label in [('collection-backup','Railway 每日备份'),('offsite-backup','加密异地副本')]:
            heartbeat=remote['heartbeats'].get(name)
            if not heartbeat or heartbeat['state']!='ok' or now-utc(datetime.fromisoformat(heartbeat['observed_at']))>timedelta(hours=36):
                problems['cloud:'+name]=label+'验证记录缺失或超过 36 小时；请检查备份任务'
        if remote['active_alerts']:
            problems['cloud:sources']='云端存在持续采集故障：部分来源或附件连续失败，请查看云端采集状态页'
    except Exception:problems['cloud:api']='云端采集 API 无法连接；本机独立监控将继续重试'
    with SessionLocal.begin() as db:
        if remote and remote['heartbeats'].get('collection-backup'):
            row=remote['heartbeats']['collection-backup']
            db.merge(WorkerHeartbeat(name='collection-backup',state=row['state'],observed_at=datetime.fromisoformat(row['observed_at'])))
        for key,message in problems.items():
            alert=db.get(CollectionAlert,key)
            if not alert:
                alert=CollectionAlert(key=key,status='active',message=message,first_seen_at=now,last_seen_at=now);db.add(alert)
            else:
                if alert.status=='resolved':alert.first_seen_at=now
                alert.status='active';alert.message=message;alert.last_seen_at=now;alert.resolved_at=None
        for key in ('cloud:api','cloud:reminders','cloud:collection-monitor','cloud:collection-backup','cloud:offsite-backup','cloud:sources'):
            alert=db.get(CollectionAlert,key)
            if alert and key not in problems and alert.status=='active':
                alert.status='resolved';alert.last_seen_at=now;alert.resolved_at=now
        db.flush();queue_alerts(db,now)
    delivery=deliver_once()
    return {'state':'alert' if problems else 'ok','problems':len(problems),'delivery':delivery}


if __name__=='__main__':
    import json
    print(json.dumps(run()))

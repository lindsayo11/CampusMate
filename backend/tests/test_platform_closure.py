from datetime import UTC, datetime, timedelta
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import Opportunity
from app.worker import Notification


def test_notification_cursor_is_private_and_exhaustive():
    with TestClient(app) as client:
        with SessionLocal.begin() as db:
            for i in range(105):
                db.add(Notification(reminder_id=900000+i, user_id='cursor-owner', opportunity_id='job-001', created_at=datetime.now(UTC).isoformat()))
            db.add(Notification(reminder_id=900200, user_id='cursor-other', opportunity_id='job-001', created_at=datetime.now(UTC).isoformat()))
        headers={'X-User-Id':'cursor-owner'}
        first=client.get('/v1/notifications',headers=headers).json()
        assert len(first)==100
        second=client.get('/v1/notifications',params={'before':first[-1]['id']},headers=headers).json()
        assert len(second)==5
        assert len({x['id'] for x in first+second})==105
        assert all(x['user_id']=='cursor-owner' for x in first+second)
        assert client.post(f"/v1/notifications/{first[0]['id']}/read",headers={'X-User-Id':'cursor-other'}).status_code==404
        assert client.get('/v1/notifications?limit=101',headers=headers).status_code==422
        assert client.get('/v1/notifications?before=0',headers=headers).status_code==422


def test_public_status_filter_never_exposes_unpublished():
    with TestClient(app) as client:
        with SessionLocal.begin() as db:
            row=db.get(Opportunity,'job-001')
            for oid,status in [('closure-expired','published'),('closure-hidden','unpublished')]:
                db.add(Opportunity(id=oid,type='job',title=oid,organization=row.organization,summary='fixture',location='online',deadline=datetime.now(UTC)-timedelta(days=1),source_url=row.source_url,source_label='fixture',trust_score=.8,tags='',status=status,fetched_at=datetime.now(UTC)))
        active=client.get('/v1/opportunities').json()['items']
        expired=client.get('/v1/opportunities?status=expired').json()['items']
        all_rows=client.get('/v1/opportunities?status=all').json()['items']
        assert 'closure-expired' not in {x['id'] for x in active}
        assert 'closure-expired' in {x['id'] for x in expired}
        assert 'closure-hidden' not in {x['id'] for x in all_rows}
        assert client.get('/v1/opportunities?status=unpublished').status_code==422


def test_account_role_and_invitation_titles_are_scoped():
    from uuid import uuid4
    a,b,other=[{'X-User-Id':str(uuid4())} for _ in range(3)]
    with TestClient(app) as c:
        assert c.get('/v1/account').json()['is_admin'] is True
        assert c.get('/v1/account',headers=a).json()=={'user_id':a['X-User-Id'],'is_admin':False}
        c.get('/v1/profile',headers=b)
        team=c.post('/v1/teams',headers=a,json={'title':'真实邀请名称'}).json()
        c.post(f"/v1/teams/{team['id']}/invitations",headers=a,json={'target':b['X-User-Id']})
        received=c.get('/v1/invitations',headers=b).json()
        assert received[0]['title']=='真实邀请名称'
        assert received[0]['team_status']=='active'
        assert c.get('/v1/invitations',headers=other).json()==[]
        assert c.get('/v1/admin/audit',headers=b).status_code==403
        c.post(f"/v1/teams/{team['id']}/dissolve",headers=a)
        received=c.get('/v1/invitations',headers=b).json()
        assert received[0]['status']=='cancelled'


def test_worker_cycle_does_not_run_frozen_collector(monkeypatch):
    from app import collector, worker
    from app.config import settings
    monkeypatch.setattr(settings,'collector_enabled',False)
    def forbidden():
        raise AssertionError('Frozen collector must never run')
    monkeypatch.setattr(collector,'schedule_due',forbidden)
    monkeypatch.setattr(collector,'process_one',forbidden)
    worker.run_cycle()
    with TestClient(app) as c:
        assert c.get('/v1/admin/operations').json()['worker']['healthy'] is True

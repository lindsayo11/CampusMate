from datetime import UTC, datetime, timedelta
from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import Reminder
from app.worker import deliver_due


def content():
    return dict(type='job', title='人工复核测试岗位', organization='测试单位', summary='测试内容', location='线上',
                deadline=(datetime.now(UTC)+timedelta(days=5)).isoformat(), source_url='https://example.edu/verified',
                source_label='测试来源', fetched_at=datetime.now(UTC).isoformat(), tags=['Python'])


def test_atomic_publish_and_unpublish():
    with TestClient(app) as c:
        denied = c.post('/v1/admin/imports', json=content(), headers={'X-User-Id': 'outsider'})
        assert denied.status_code == 403
        row = c.post('/v1/admin/imports', json=content())
        assert row.status_code == 201
        rid = row.json()['id']
        approved = c.post(f'/v1/admin/reviews/{rid}/approve')
        assert approved.status_code == 200
        assert c.post(f'/v1/admin/reviews/{rid}/approve').status_code == 200
        assert c.post(f'/v1/admin/reviews/{rid}/reject').status_code == 409
        events = [e for e in c.get('/v1/admin/audit').json() if e['resource']==f'review:{rid}' and e['action']=='approve']
        assert len(events) == 1
        import json
        oid = json.loads(events[0]['detail'])['opportunity_id']
        assert c.get('/v1/opportunities/'+oid).json()['tags'] == ['Python']
        assert c.post('/v1/admin/opportunities/'+oid+'/unpublish').status_code == 200
        assert c.get('/v1/opportunities/'+oid).status_code == 404


def test_editorial_validation_and_expiry():
    with TestClient(app) as c:
        bad = content(); bad['source_url'] = 'javascript:alert(1)'
        assert c.post('/v1/admin/imports', json=bad).status_code == 422
        bad = content(); bad['deadline'] = '2020-01-01T00:00:00+00:00'
        rid = c.post('/v1/admin/imports', json=bad).json()['id']
        assert c.post(f'/v1/admin/reviews/{rid}/approve').status_code == 422
        bad = content(); bad['deadline'] = '2030-01-01T00:00:00'
        assert c.post('/v1/admin/imports', json=bad).status_code == 422


def test_notification_ownership_read_and_cancel():
    owner = {'X-User-Id': str(uuid4())}; other = {'X-User-Id': str(uuid4())}
    with TestClient(app) as c:
        with SessionLocal.begin() as db:
            row = Reminder(user_id=owner['X-User-Id'], opportunity_id='job-001', due_at=datetime.now(UTC)-timedelta(minutes=1), created_at=datetime.now(UTC))
            db.add(row); db.flush(); rid=row.id
        deliver_due(); deliver_due()
        rows=c.get('/v1/notifications', headers=owner).json()
        assert len(rows)==1 and rows[0]['read_at'] is None
        nid=rows[0]['id']
        assert c.post(f'/v1/notifications/{nid}/read', headers=other).status_code==404
        first=c.post(f'/v1/notifications/{nid}/read', headers=owner).json()
        assert first['read_at']
        assert c.post(f'/v1/notifications/{nid}/read', headers=owner).json()['read_at']==first['read_at']
        assert c.delete(f'/v1/reminders/{rid}', headers=owner).status_code==409
        rid=c.post('/v1/tools/deadline_remind', json={'opportunity_id':'job-001'}, headers=owner).json()['id']
        assert c.delete(f'/v1/reminders/{rid}', headers=other).status_code==404
        assert c.delete(f'/v1/reminders/{rid}', headers=owner).json()['cancelled']

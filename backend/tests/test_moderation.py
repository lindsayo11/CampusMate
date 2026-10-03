from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import SessionLocal
from app.main import app
from app.models import AuditEvent
from app.rate_limits import SocialQuota
from app.social import Message


def setup_message(c):
    user = str(uuid4())
    h = {"X-User-Id": user}
    room = c.post('/v1/tools/message_connect', headers=h, json={"target": "demo-python"}).json()
    url = f"/v1/rooms/{room['id']}/messages"
    msg = c.post(url, headers=h, json={"body": "moderation evidence"}).json()
    return user, h, url, msg


def test_report_decision_evidence_isolation_and_idempotency():
    with TestClient(app) as c:
        _user, h, url, msg = setup_message(c)
        report_url = f"/v1/messages/{msg['id']}/report"
        assert c.post(report_url, headers={"X-User-Id": "outsider"}, json={"reason": "bad"}).status_code == 404
        assert c.post(report_url, headers=h, json={"reason": " "}).status_code == 422
        for _ in range(2):
            assert c.post(report_url, headers=h, json={"reason": "spam"}).status_code == 200
        mine = c.get('/v1/reports/mine', headers=h).json()
        assert len(mine) == 1
        rid = mine[0]['id']
        assert c.get('/v1/reports/mine', headers={"X-User-Id": str(uuid4())}).json() == []
        assert c.get('/v1/admin/reports', headers=h).status_code == 403
        endpoint = f'/v1/admin/reports/{rid}/decision'
        assert c.post(endpoint, headers=h, json={"action": "remove", "note": "spam"}).status_code == 403
        assert c.post(endpoint, json={"action": "remove", "note": " "}).status_code == 422
        assert c.post(endpoint, json={"action": "remove", "note": "spam confirmed"}).status_code == 200
        assert c.post(endpoint, json={"action": "remove", "note": "duplicate"}).status_code == 200
        assert c.post(endpoint, json={"action": "dismiss", "note": "overwrite"}).status_code == 409
        assert c.get(url, headers=h).json()[0]['body'] == '[消息已由管理员移除]'
        items = c.get('/v1/admin/reports?status=removed').json()['items']
        assert next(x for x in items if x['id'] == rid)['evidence']['body'] == 'moderation evidence'
        assert c.get('/v1/reports/mine', headers=h).json()[0]['status'] == 'removed'
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.resource == f'report:{rid}')) == 1
            assert db.get(Message, msg['id']).body == 'moderation evidence'


def test_account_quota_cross_room_and_rollback():
    with TestClient(app) as c:
        user, h, _url, _msg = setup_message(c)
        with SessionLocal.begin() as db:
            db.merge(SocialQuota(key=f'message-day:{user}', window=int(datetime.now(UTC).timestamp()) // 86400, count=200))
        room2 = c.post('/v1/tools/message_connect', headers=h, json={"target": "demo-design"}).json()
        response = c.post(f"/v1/rooms/{room2['id']}/messages", headers=h, json={"body": "other room"})
        assert response.status_code == 429
        assert int(response.headers['retry-after']) > 0
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(Message).where(Message.sender == user)) == 1
            assert db.get(SocialQuota, f'message-minute:{user}').count == 1


def test_block_owner_only_unblock_and_dismiss():
    with TestClient(app) as c:
        _user, h, url, msg = setup_message(c)
        c.post('/v1/blocks', headers=h, json={"target": "demo-python"})
        assert c.get('/v1/blocks', headers=h).json() == [{"target": "demo-python"}]
        c.delete('/v1/blocks/demo-python', headers={"X-User-Id": "outsider"})
        assert c.post(url, headers=h, json={"body": "blocked"}).status_code == 403
        assert c.delete('/v1/blocks/demo-python', headers=h).status_code == 200
        assert c.post(url, headers=h, json={"body": "unblocked"}).status_code == 200
        c.post(f"/v1/messages/{msg['id']}/report", headers=h, json={"reason": "review"})
        rid = c.get('/v1/reports/mine', headers=h).json()[0]['id']
        assert c.post(f'/v1/admin/reports/{rid}/decision', json={"action": "dismiss", "note": "no violation"}).status_code == 200
        assert c.get(url, headers=h).json()[0]['body'] == 'moderation evidence'

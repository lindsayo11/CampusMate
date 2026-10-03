"""Five fictional students; isolated integration simulation, never live approval."""
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from test_data_catalog import sample, submit, approve  # noqa: F401
from app.database import SessionLocal
from app.data_catalog import deliver_data_alerts
from app.intake_models import DataSubscription, DevelopmentItem


def test_five_students_review_read_plan_reminder_and_withdraw(sample):
    c, d = sample
    with SessionLocal.begin() as db:
        item = db.get(DevelopmentItem, d['item_id'])
        item.title = '模拟测试：五人交互事项（非真实公告）'
        item.deadline = datetime.now(UTC) + timedelta(days=3)
    # All approvals below are simulated roles in the fixture database.
    pid = submit(c, d).json()['id']
    assert approve(c, pid, 'demo-user').status_code == 409
    assert approve(c, pid, 'review-one').json()['status'] == 'pending'
    assert c.get(f'/v1/data/publications/{pid}').status_code == 404
    assert approve(c, pid, 'review-two').json()['status'] == 'published'
    majors = ['统计学', '计算机科学', '产品设计', '机械工程', '英语']
    subscriptions = []
    for index, major in enumerate(majors, 1):
        user = f'simulation-student-{index}'
        headers = {'x-user-id': user}
        response = c.put('/v1/profile', headers=headers, json={
            'display_name': f'模拟学生{index}', 'school': '模拟大学',
            'college': '模拟学院', 'grade': '大四', 'major': major,
            'target_year': 2027, 'target_path': 'startup_policy'})
        assert response.status_code == 200, response.text
        assert c.get('/v1/profile', headers=headers).json()['major'] == major
        catalog = c.get('/v1/data/catalog', params={'q': '五人交互'}, headers=headers)
        assert any(row['id'] == d['item_id'] for row in catalog.json()['items'])
        detail = c.get(f'/v1/data/publications/{pid}', headers=headers)
        assert detail.status_code == 200 and detail.json()['evidence']
        body = {'publication_id': pid, 'item_id': d['item_id'], 'remind_before_hours': 24}
        response = c.post('/v1/data/subscriptions', json=body, headers=headers)
        assert response.status_code == 201, response.text
        subscription = response.json()
        assert c.post('/v1/data/subscriptions', json=body, headers=headers).json() == subscription
        plans = c.get('/v1/plans', headers=headers).json()
        assert len(plans) == 1 and plans[0]['id'] == subscription['plan_id']
        assert c.get('/v1/admin/data/overview', headers=headers).status_code == 403
        subscriptions.append((headers, subscription))
    assert len({s['plan_id'] for _, s in subscriptions}) == 5
    for index, (headers, sub) in enumerate(subscriptions):
        rows = c.get('/v1/data/subscriptions', headers=headers).json()
        assert len(rows) == 1 and rows[0]['id'] == sub['id']
        other = subscriptions[(index + 1) % 5][1]
        assert c.patch(f"/v1/data/subscriptions/{other['id']}?action=cancel", headers=headers).status_code == 404
    # Cancel student 5; preserve their personal plan and suppress future alerts.
    headers, sub = subscriptions[-1]
    assert c.patch(f"/v1/data/subscriptions/{sub['id']}?action=cancel", headers=headers).status_code == 200
    assert len(c.get('/v1/plans', headers=headers).json()) == 1
    with SessionLocal.begin() as db:
        for row in db.scalars(select(DataSubscription).where(DataSubscription.publication_id == pid)):
            row.remind_at = datetime.now(UTC) - timedelta(minutes=1)
    assert deliver_data_alerts() == 4
    assert deliver_data_alerts() == 0
    for headers, sub in subscriptions[:4]:
        rows = c.get('/v1/data/subscriptions', headers=headers).json()
        assert rows[0]['alerted_at'] and '截止' in rows[0]['message']
        assert c.patch(f"/v1/data/subscriptions/{sub['id']}?action=read", headers=headers).status_code == 200
    response = c.patch(f'/v1/admin/data/publications/{pid}', json={
        'action': 'withdraw', 'note': '模拟内容撤回测试', 'verified_original': True})
    assert response.status_code == 200
    assert c.get(f'/v1/data/publications/{pid}').status_code == 404
    assert deliver_data_alerts() == 4
    assert deliver_data_alerts() == 0
    for headers, _ in subscriptions[:4]:
        row = c.get('/v1/data/subscriptions', headers=headers).json()[0]
        assert row['status'] == 'source_changed' and row['read_at'] is None
    assert c.get('/v1/data/subscriptions', headers=subscriptions[-1][0]).json() == []

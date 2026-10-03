import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


def content():
    url = 'https://example.edu/' + str(uuid4())
    return {'raw_text': '官方测试公告，招收计算机专业学生。仅限大三报名。截止时间见结构化字段。',
            'payload': {'type': 'civil_service', 'title': '归档测试职位', 'organization': '测试单位',
                        'summary': '测试摘要', 'location': '线上', 'source_url': url,
                        'source_label': '测试来源', 'fetched_at': datetime.now(UTC).isoformat(),
                        'deadline': (datetime.now(UTC) + timedelta(days=7)).isoformat(),
                        'rules': [{'field': 'grade', 'operator': 'in', 'expected': '大三',
                                   'label': '年级条件', 'source_url': url, 'evidence': '仅限大三报名。'}]}}


def test_archive_dedup_change_history_and_permission():
    with TestClient(app) as c:
        body = content()
        assert c.post('/v1/admin/sources/import', json=body, headers={'X-User-Id': 'other'}).status_code == 403
        first = c.post('/v1/admin/sources/import', json=body)
        assert first.status_code == 201
        first = first.json()
        body['payload']['fetched_at'] = datetime.now(UTC).isoformat()
        duplicate = c.post('/v1/admin/sources/import', json=body).json()
        assert duplicate['duplicate'] and duplicate['review_id'] == first['review_id']
        body['raw_text'] += '\n新增说明：名额以官方公布为准。'
        second = c.post('/v1/admin/sources/import', json=body).json()
        assert second['changed'] and second['document_id'] != first['document_id']
        detail = c.get('/v1/admin/sources/' + second['document_id']).json()
        assert detail['previous_id'] == first['document_id']
        assert detail['content_hash'] == hashlib.sha256(body['raw_text'].encode()).hexdigest()
        assert '+新增说明' in detail['diff']
        assert c.get('/v1/admin/sources/' + first['document_id'], headers={'X-User-Id': 'other'}).status_code == 403
        assert c.get(f"/v1/admin/reviews/{second['review_id']}/evidence").json()['archive']['id'] == second['document_id']


def test_archived_rules_publish_atomically_and_retain_quote():
    with TestClient(app) as c:
        body = content()
        bad = content(); bad['payload']['rules'][0]['evidence'] = '原文没有这句'
        assert c.post('/v1/admin/sources/import', json=bad).status_code == 422
        rid = c.post('/v1/admin/sources/import', json=body).json()['review_id']
        assert c.post(f'/v1/admin/reviews/{rid}/approve').status_code == 200
        events = c.get('/v1/admin/audit').json()
        event = next(e for e in events if e['resource'] == f'review:{rid}' and e['action'] == 'approve')
        oid = json.loads(event['detail'])['opportunity_id']
        result = c.post('/v1/tools/eligibility_check', json={'opportunity_id': oid}).json()
        assert result['results'][0]['evidence'] == '仅限大三报名。'
        assert result['results'][0]['source_url'] == body['payload']['source_url']
        bad = content(); bad['payload']['rules'][0]['expected'] = '大三,'
        assert c.post('/v1/admin/sources/import', json=bad).status_code == 422

"""Retain clearly labelled synthetic data in a dedicated, disposable demo DB."""
import sys
from pathlib import Path
from datetime import UTC, datetime, timedelta
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.database import SessionLocal
from app.adapters.base import RawArtifact
from app.intake import record_document_version
from app.intake_models import Source, SourceEndpoint, Evidence, DevelopmentItem, DocumentVersion, DataPublication
from app.data_catalog import auto_publish
from sqlalchemy import select

BATCH = 'demo-five-people-20260929'
if not settings.demo_mode or 'retained-demo' not in settings.database_url:
    raise SystemExit('Requires DEMO_MODE=true and a dedicated retained-demo database')

with TestClient(app) as client:
    with SessionLocal.begin() as db:
        existing = db.scalar(select(DocumentVersion).where(DocumentVersion.test_batch == BATCH))
        sid, eid = str(uuid4()), str(uuid4())
        now = datetime.now(UTC)
        source = Source(id=sid, source_code=BATCH, name='模拟数据批次', publisher='模拟测试，非官方',
            authority_level='D', source_class='demo', official=False, jurisdiction_level='demo',
            base_url='https://example.invalid', verified_at=now, active=True, region_code='DEMO')
        endpoint = SourceEndpoint(id=eid, source_id=sid, name='本地合成测试，无外网采集',
            endpoint_type='html', url='https://example.invalid/demo', auth_type='none',
            automation_level='AUTO-4', agent_mode='USER_ACTION', license_status='unknown',
            robots_status='unknown', adapter_config='{}', active=True, scheduled=False)
        published = []
        if not existing:
            db.add_all([source, endpoint]); db.flush()
        else:
            for doc in db.scalars(select(DocumentVersion).where(DocumentVersion.test_batch == BATCH)):
                if doc.deleted_at:
                    continue
                item = db.scalar(select(DevelopmentItem).where(DevelopmentItem.source_document_id == doc.id))
                pub = db.scalar(select(DataPublication).where(DataPublication.document_id == doc.id))
                if pub and pub.status == 'published':
                    published.append((pub.id, item.id))
        for index, title in enumerate([] if existing else ['模拟岗位：数据分析助理', '模拟升学：项目申请', '模拟创业：项目征集'], 1):
            raw = RawArtifact(f'<main data-fixture="test-only">{title}</main>'.encode(),
                endpoint.url, f'{BATCH}-{index}')
            doc, _ = record_document_version(db, endpoint, raw, title)
            doc.import_mode, doc.test_batch = 'demo', BATCH
            item_id = f'{BATCH}-item-{index}'
            db.add(DevelopmentItem(id=item_id, title=title, item_type='demo', description='仅用于模拟交互，可删除',
                source_document_id=doc.id, deadline=now+timedelta(days=7+index), location='模拟地区'))
            db.add(Evidence(id=str(uuid4()), document_version_id=doc.id, source_id=sid,
                evidence_location='main', quote_or_normalized_fact=title, extractor='demo-generator',
                review_status='pending'))
            db.flush()
            assert auto_publish(db, doc)
            pub = db.scalar(select(DataPublication).where(DataPublication.document_id == doc.id))
            published.append((pub.id, item_id))
    for index, major in enumerate(['统计学','计算机科学','产品设计','机械工程','英语'], 1):
        headers = {'x-user-id': f'{BATCH}-student-{index}'}
        r = client.put('/v1/profile', headers=headers, json={'display_name':f'模拟学生{index}',
            'school':'模拟大学','college':'模拟学院','grade':'大四','major':major})
        assert r.status_code == 200, r.text
        for pub_id, item_id in published:
            r = client.post('/v1/data/subscriptions', headers=headers, json={
                'publication_id':pub_id,'item_id':item_id,'remind_before_hours':24})
            assert r.status_code == 201, r.text
    print(f'Retained batch {BATCH}: 5 profiles, 3 published demo items, 15 plans, 15 subscriptions')

"""Cross-channel discovery, ingestion and sustainable configuration regressions."""
import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import notice_watch as watch
from app.adapters.base import RawArtifact
from app.adapters.education import PublicNoticeAdapter
from app.adapters.notice_text import discover_notices
from app.database import SessionLocal
from app.intake_models import DevelopmentItem, DocumentVersion, Evidence, Source, SourceEndpoint
from app.main import app
from app.models import EligibilityRule
from app.parsers import ParseError
from app.public_source_catalog import catalog_status, load_catalog, registry_sources, watch_entries


def test_catalog_is_honest_about_probe_and_installation():
    catalog = load_catalog()
    codes = [e['code'] for e in catalog['sources']]
    assert len(set(codes)) == len(codes)
    status = catalog_status([])
    assert status['total'] == len(codes)
    assert sum(status['statuses'].values()) == status['total']
    assert not any(s['enabled'] for s in status['sources'])
    ready = {s['code'] for s in watch_entries()}
    assert ready <= {s['code'] for s in registry_sources()}
    for source in watch_entries():
        assert source['probe']['sample']['evidence'] > 0
        assert source['probe']['sample']['sha256']
        assert source['probe']['sample']['url'].startswith('https://')
    assert all(s['status'] == 'ready' for s in watch_entries())


@pytest.mark.parametrize('topic,title', [
    ('employment', '某大学2027届毕业生秋季双选招聘会通知'),
    ('recruitment', '某省2027年事业单位公开招聘工作人员公告'),
    ('overseas', '2027年国家公派出国留学奖学金申请通知'),
    ('entrepreneurship', '2027年大学生创新创业竞赛申报通知'),
    ('examination', '2027年全国硕士研究生招生考试报名须知'),
    ('funding', '2027年高校学生资助项目申请通知'),
])
def test_topics_discover_same_host_public_articles_only(topic, title):
    html = (f'<a href="/notice">{title}</a><a href="https://other.example/notice">{title}</a>'
            f'<a href="/private">{title}登录系统</a><a href="/names">{title}拟录取名单</a>')
    assert discover_notices(html, 'https://official.example/list', topic=topic) == [
        {'title': title, 'url': 'https://official.example/notice'}]


def test_navigation_procurement_and_internal_graduate_activity_are_not_notices():
    html = '<a href="index.htm">某大学研究生招生信息网</a><a href="buy">2027年硕士招生系统采购通知</a><a href="photo">2027届研究生图像采集报名通知</a><a href="phd">2027年博士研究生招生简章</a>'
    assert not discover_notices(html, 'https://official.example/')
    with pytest.raises(ParseError):
        PublicNoticeAdapter('employment').parse(RawArtifact(
            b'<h1>2027 job</h1><input type="password">', 'https://official.example/notice', 'notice'))


def test_public_watch_collects_employment_with_evidence_and_no_qualification_rules(monkeypatch):
    sid, eid = str(uuid4()), str(uuid4())
    base = 'https://public-watch.example/'
    title = '某大学2027届毕业生实习招聘申请通知'
    with TestClient(app):
        with SessionLocal.begin() as db:
            db.add(Source(id=sid, source_code='PUBLIC-'+sid[:24], name='实习招聘测试来源', publisher='测试大学',
                authority_level='A', source_class='university', official=True, jurisdiction_level='school',
                base_url=base, active=True, verified_at=datetime.now(UTC)))
            db.add(SourceEndpoint(id=eid, source_id=sid, name='public_notices', endpoint_type='html',
                url=base+'list', parser_type='PublicNoticeAdapter', automation_level='AUTO-2', agent_mode='EXTRACT',
                scheduled=True, active=True, adapter_config=json.dumps({'collection_mode': watch.MODE,
                    'topic':'employment', 'path_code':'employment', 'interval_hours':18,
                    'detail_interval_hours':36, 'authorized_by':'operator', 'index_urls':[base+'list']})))
        monkeypatch.setattr(watch.time, 'sleep', lambda _: None)
        def fetch(url, *args, **kwargs):
            assert kwargs['strict_robots']
            html = (f'<a href="article">{title}</a>' if url.endswith('list') else
                f'<h1>{title}</h1><time>2026-10-01</time><div class="articleDiv"><p>报名截止：2026年10月15日。岗位及申请材料应以企业公开信息为准，请先核实招聘机构和申请流程。</p></div>')
            return {'data': html.encode(), 'final_url': url, 'content_type': 'text/html',
                'not_modified': False, 'status_code': 200, 'etag': '"v1"', 'last_modified': None}
        monkeypatch.setattr(watch, 'collect_bytes_conditional', fetch)
        with SessionLocal.begin() as db:
            watch.add_resource(db,eid,base+'list','index',datetime.now(UTC))
        assert watch.process_once()['kind'] == 'index'
        assert watch.process_once()['status'] == 'updated'
        with SessionLocal.begin() as db:
            doc = db.scalar(select(DocumentVersion).where(DocumentVersion.source_endpoint_id == eid))
            item = db.scalar(select(DevelopmentItem).where(DevelopmentItem.source_document_id == doc.id))
            assert item.title == title and item.deadline is not None
            assert db.scalar(select(Evidence.id).where(Evidence.document_version_id == doc.id))
            assert not db.scalar(select(EligibilityRule.id).where(EligibilityRule.target_id == item.id))
            assert doc.import_mode == 'system'
            db.get(SourceEndpoint,eid).scheduled = False


def test_seeded_catalog_never_starts_collection():
    assert all(not endpoint['scheduled'] for source in registry_sources() for endpoint in source['endpoints'])


def test_source_path_filter_applies_before_pagination():
    code = 'ZZ-LAST-' + uuid4().hex[:20]
    school = uuid4().hex
    target_path = 'expanded-source-filter-' + str(uuid4())
    with TestClient(app) as client:
        with SessionLocal.begin() as db:
            db.add(Source(id=str(uuid4()), source_code=code, name='分页后的来源', publisher='测试',
                authority_level='Z', source_class='university', official=True, jurisdiction_level='school',
                base_url='https://example.edu/', active=True, verified_at=datetime.now(UTC),
                school_id=school, supported_paths=json.dumps([target_path])))
            db.add(Source(id=str(uuid4()), source_code='EARLY-'+uuid4().hex[:20], name='排在前面的其他路径来源', publisher='测试',
                authority_level='A', source_class='university', official=True, jurisdiction_level='school',
                base_url='https://example.edu/', active=True, verified_at=datetime.now(UTC),
                school_id=school, supported_paths=json.dumps(['employment'])))
        rows = client.get('/v1/sources', params={'path':target_path,'school_id':school,'limit':1}).json()
        assert len(rows) == 1 and target_path in rows[0]['supported_paths']

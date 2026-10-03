"""Real discovery -> durable fetch -> version changes, including list 304."""
import json
from datetime import UTC,datetime,timedelta
from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy import select,update
from app import notice_watch as watch
from app.config import settings
from app.database import SessionLocal
from app.intake_models import Source,SourceEndpoint,NoticeResource,DocumentVersion
from app.main import app
from app.adapters.notice_text import discover_notices
from app.collector_http import FetchError

def setup(monkeypatch):
    eid,sid=str(uuid4()),str(uuid4())
    base='https://watch.example.edu/'
    with SessionLocal.begin() as db:
        db.add(Source(id=sid,source_code='WATCH-'+sid,name='自动采集测试大学',publisher='测试大学',
            authority_level='A',source_class='university',official=True,jurisdiction_level='school',
            base_url=base,active=True,verified_at=datetime.now(UTC)))
        db.add(SourceEndpoint(id=eid,source_id=sid,name='watch',endpoint_type='html',url=base+'list',
            parser_type='UniversityNoticeAdapter',automation_level='AUTO-2',agent_mode='EXTRACT',
            scheduled=True,active=True,adapter_config=json.dumps({'collection_mode':watch.MODE,
                'authorized_by':'test-operator','index_urls':[base+'list']})))
    monkeypatch.setattr(settings,'public_notice_watch_enabled',True)
    monkeypatch.setattr(watch.time,'sleep',lambda _:None)
    watch.seed_frontier()
    return eid,base

def response(url,data=b'',not_modified=False):
    return dict(data=data,final_url=url,content_type='text/html',not_modified=not_modified,
        status_code=304 if not_modified else 200,etag='"v1"',last_modified=None)

def article(text='材料和报名安排以院系官方原文为准，请仔细阅读本通知并核实申请条件。'):
    return ('<h1>测试大学2027年推免研究生申请通知</h1><time>2026-09-30</time><article><p>'+text+'</p></article>').encode()

def due(eid,kind):
    with SessionLocal.begin() as db:
        db.execute(update(NoticeResource).where(NoticeResource.endpoint_id==eid,NoticeResource.kind==kind)
            .values(next_check_at=datetime.now(UTC)-timedelta(seconds=1)))

def test_new_links_detail_changes_even_when_index_304(monkeypatch):
    with TestClient(app):
        eid,base=setup(monkeypatch)
        pages={base+'list':response(base+'list',b'<a href="a">'+ '测试大学2027年推免研究生申请通知'.encode()+b'</a>'),
            base+'a':response(base+'a',article())}
        calls=[]
        def fetch(url,*a,**kw):
            assert kw['strict_robots'] is True
            calls.append((url,a));return pages[url]
        monkeypatch.setattr(watch,'collect_bytes_conditional',fetch)
        assert watch.process_once()['kind']=='index'
        assert watch.process_once()['status']=='updated'
        with SessionLocal() as db:
            first=db.scalar(select(DocumentVersion).where(DocumentVersion.source_endpoint_id==eid))
            first_id=first.id
        # Newly added URL is automatically discovered; no manifest edits.
        pages[base+'list']=response(base+'list',('<a href="a">测试大学2027年推免研究生申请通知</a><a href="b">测试大学2027年硕士招生报名通知</a>').encode())
        pages[base+'b']=response(base+'b',article('报名截止：2026年10月9日。申请材料和提交方式以官方通知为准，请在规定时间完成报名。'))
        due(eid,'index');assert watch.process_once()['kind']=='index'
        assert watch.process_once()['status']=='updated'
        pages[base+'list']=response(base+'list',not_modified=True)
        due(eid,'index');assert watch.process_once()['status']=='unchanged'
        pages[base+'a']=response(base+'a',article('报名截止：2026年10月10日。申请材料和提交方式以官方通知为准，请在规定时间完成报名。'))
        due(eid,'detail')
        results=[watch.process_once(),watch.process_once()]
        assert {r['status'] for r in results}=={'updated','unchanged'}
        with SessionLocal() as db:
            docs=db.scalars(select(DocumentVersion).where(DocumentVersion.source_endpoint_id==eid,
                DocumentVersion.canonical_url==base+'a').order_by(DocumentVersion.version_no)).all()
            assert len(docs)==2 and docs[1].previous_id==first_id
        due(eid,'detail');watch.process_once();watch.process_once()
        with SessionLocal() as db:
            assert len(db.scalars(select(DocumentVersion).where(DocumentVersion.source_endpoint_id==eid)).all())==3
        with SessionLocal.begin() as db:db.get(SourceEndpoint,eid).scheduled=False
        due(eid,'index');assert watch.process_once() is None

def test_failures_isolated_and_lease_fence(monkeypatch):
    with TestClient(app):
        eid,base=setup(monkeypatch)
        def fail(*a,**kw):raise FetchError('来源限流',429,'7200')
        monkeypatch.setattr(watch,'collect_bytes_conditional',fail)
        result=watch.process_once();assert result['status']=='retry'
        with SessionLocal() as db:
            row=db.scalar(select(NoticeResource).where(NoticeResource.endpoint_id==eid))
            assert row.next_check_at-row.checked_at>=timedelta(hours=2)
            assert row.lease_token is None
        due(eid,'index')
        def steal(url,*a,**kw):
            with SessionLocal.begin() as db:
                db.execute(update(NoticeResource).where(NoticeResource.endpoint_id==eid).values(lease_token='new-owner'))
            return response(url,b'<a href="a">'+ '测试大学2027年推免研究生申请通知'.encode()+b'</a>')
        monkeypatch.setattr(watch,'collect_bytes_conditional',steal)
        assert watch.process_once()['status']=='lease_lost'
        with SessionLocal.begin() as db:
            db.execute(update(NoticeResource).where(NoticeResource.endpoint_id==eid)
                .values(lease_until=datetime.now(UTC)-timedelta(minutes=1)))
            db.get(SourceEndpoint,eid).scheduled=False

def test_pdf_wrapper_and_scanned_pdf_are_visible_issues(monkeypatch):
    with TestClient(app):
        eid,base=setup(monkeypatch)
        with SessionLocal.begin() as db:
            db.execute(update(NoticeResource).where(NoticeResource.endpoint_id==eid)
                .values(next_check_at=datetime.now(UTC)+timedelta(days=2)))
            watch.add_resource(db,eid,base+'wrapper','detail',datetime.now(UTC))
        monkeypatch.setattr(watch,'collect_bytes_conditional',lambda url,*a,**kw:response(url,
            b'<iframe src="file.pdf"></iframe>' if url.endswith('wrapper') else b'%PDF-broken'))
        assert watch.process_once()['status']=='attachments_pending'
        assert watch.process_once()['status']=='needs_review'
        with SessionLocal.begin() as db:db.get(SourceEndpoint,eid).scheduled=False

def test_literal_onclick_and_no_script_execution():
    html='''<div onclick="window.open('/article/2','_blank')">某大学2028年接收推免研究生办法</div>
    <div onclick="evil();window.open('/private')">某大学2028年接收推免研究生办法</div>'''
    assert discover_notices(html,'https://watch.example.edu/list')==[
        {'url':'https://watch.example.edu/article/2','title':'某大学2028年接收推免研究生办法'}]


def test_targeted_collection_respects_pauses_and_leaves_other_sources_queued(monkeypatch):
    with TestClient(app):
        first, base = setup(monkeypatch)
        second, _ = setup(monkeypatch)
        calls = []
        def fetch(url, *args, **kwargs):
            calls.append(url)
            return response(url, '<a href="a">测试大学2027年硕士招生报名通知</a>'.encode())
        monkeypatch.setattr(watch, 'collect_bytes_conditional', fetch)
        with SessionLocal.begin() as db:
            db.get(SourceEndpoint, second).scheduled = False
        assert watch.process_once(endpoint_ids=[second]) is None and not calls
        assert watch.process_once(endpoint_ids=[]) is None
        with SessionLocal.begin() as db:
            db.get(SourceEndpoint, second).scheduled = True
        assert watch.process_once(endpoint_ids=[second])['kind'] == 'index'
        with SessionLocal.begin() as db:
            untouched = db.scalar(select(NoticeResource).where(NoticeResource.endpoint_id == first))
            assert untouched.checked_at is None and untouched.lease_token is None
            db.get(SourceEndpoint, first).scheduled = False
            db.get(SourceEndpoint, second).scheduled = False


def test_title_and_discovery_cover_embedded_pdf_and_joint_programme():
    from app.adapters.notice_text import notice_title
    from bs4 import BeautifulSoup
    title='电子科技大学-法国鲁昂学院合作办学项目理学硕士2026年招生简章'
    assert notice_title(BeautifulSoup('<title>'+title+'-电子科技大学研究生招生网</title>','html.parser'))==title
    notices=discover_notices('<a href="x">上海交通大学2027年招收优秀应届本科毕业生免试攻读研究生办法</a><a href="y">复旦大学2027年招收攻读硕士学位研究生章程</a>','https://watch.example.edu/list')
    assert len(notices)==2

def test_monitor_admin_auth():
    with TestClient(app) as client:
        assert client.get('/v1/admin/notice-watch',headers={'X-User-Id':'student'}).status_code==403
        assert client.get('/v1/admin/notice-watch').status_code==200


def test_install_updates_columns_without_fabricating_approval_or_resuming_pause(monkeypatch,tmp_path):
    with TestClient(app):
        eid,base=setup(monkeypatch)
        monkeypatch.setattr(settings,'collector_allowed_hosts','watch.example.edu')
        with SessionLocal.begin() as db:
            ep=db.get(SourceEndpoint,eid)
            ep.name='graduate_admission_notices';ep.scheduled=False
            code=db.get(Source,ep.source_id).source_code
        manifest=tmp_path/'columns.json'
        manifest.write_text(json.dumps({'sources':[{'code':code,'index_urls':[base+'new-column']}]}))
        with SessionLocal() as db:assert watch.install(db,'operator',manifest)=={'sources':1}
        with SessionLocal() as db:
            ep=db.get(SourceEndpoint,eid)
            assert not ep.scheduled and ep.license_status=='unknown'
            old=db.scalar(select(NoticeResource).where(NoticeResource.endpoint_id==eid,NoticeResource.url==base+'list'))
            assert old.status=='retired'
            assert watch.config_for(ep)['index_urls']==[base+'new-column']
            assert next(s for s in watch.monitor_status(db) if s['endpoint_id']==eid)['enabled'] is False


def test_legacy_scheduler_keeps_public_monitor_separate(monkeypatch):
    from app.source_scheduler import schedule_due_endpoints
    from app.intake_models import SourceEndpointRun
    with TestClient(app):
        eid,base=setup(monkeypatch)
        schedule_due_endpoints()
        with SessionLocal.begin() as db:
            ep=db.get(SourceEndpoint,eid)
            assert ep.scheduled
            assert not db.scalar(select(SourceEndpointRun.id).where(SourceEndpointRun.endpoint_id==eid))
            ep.scheduled=False


def test_public_monitor_never_uses_robots_override(monkeypatch):
    from app import collector_http as http
    monkeypatch.setattr(settings,'collector_allowed_hosts','robotstest.example.edu')
    monkeypatch.setattr(settings,'collector_skip_robots',True)
    monkeypatch.setattr(http,'fetch_url',lambda *a,**kw:(b'User-agent: *\nDisallow: /','text/plain',a[0],200))
    import pytest
    with pytest.raises(FetchError,match='robots'):
        http.assert_robots('https://robotstest.example.edu/notice',strict=True)

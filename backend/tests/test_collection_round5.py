import io,json
from datetime import UTC,datetime,timedelta
from fastapi.testclient import TestClient
from sqlalchemy import select,func
import pytest
from pypdf import PdfWriter
from app import notice_watch as watch
from app.database import SessionLocal
from app.main import app
from app.intake_models import NoticeResource,SourceEndpoint,CollectionAttempt,CollectionAlert
from app.collection_monitor import check_alerts
from app.operations import WorkerHeartbeat
from app.parsers import extract,ParseError
from app.adapters.education import UniversityNoticeAdapter
from app.adapters.base import RawArtifact
from app.adapters.notice_text import registration_dates,discover_notices
from app.adapters.index_discovery import discover_index
from app.adapters.public_request import request_spec
from app.notice_duplicates import group_identical
from test_notice_watch import setup,response,article,due


def test_scanned_pdf_preserves_boxes_and_never_promotes_ocr_dates(monkeypatch):
    from app import ocr
    writer=PdfWriter();writer.add_blank_page(500,500);out=io.BytesIO();writer.write(out)
    proofs=[{'page':1,'line':1,'text':'测试大学2027年硕士研究生招生通知','confidence':95,'box':[1,2,400,50]},
        {'page':1,'line':2,'text':'报名截止：2026年10月20日。申请材料和提交方式以官方原文为准，请核实。','confidence':95,'box':[1,60,400,70]}]
    monkeypatch.setattr(ocr,'recognize_pdf',lambda data,pages:proofs)
    parsed=extract(out.getvalue(),'pdf')
    assert parsed.evidence==proofs and '[第 1 页]' in parsed.text
    import app.parsers
    monkeypatch.setattr(app.parsers,'extract_isolated',lambda data,format:parsed)
    notice=UniversityNoticeAdapter().parse(RawArtifact(out.getvalue(),'https://official.example/notice.pdf','n'))
    assert 'deadline_at' not in notice.records[0]
    assert any('confidence=95' in e['evidence_location'] for e in notice.evidence)
    monkeypatch.setattr(ocr,'recognize_pdf',lambda data,pages:[{**proofs[0],'confidence':40}])
    with pytest.raises(ParseError,match='置信度'):extract(out.getvalue(),'pdf')


def test_dates_support_numeric_and_submission_labels_without_guessing_year():
    assert registration_dates('申请时间：2026.10.01-2026.10.20 17:00')[1]=='2026-10-20T17:00:00+08:00'
    assert registration_dates('申报截止时间：2026年10月20日')[1]=='2026-10-20T23:59:00+08:00'
    assert registration_dates('申报截止时间：10月20日')==(None,None)
    assert registration_dates('面试时间：2026年10月20日')==(None,None)


def test_official_literal_window_open_and_deep_json_pages():
    html='<div onclick=\'windowOpen("\\/notice")\'>2027年校园招聘公告</div>'
    assert discover_notices(html,'https://official.example/','',topic='employment')[0]['url']=='https://official.example/notice'
    config={'topic':'employment','discovery_format':'json',
        'index_page_url':'https://official.example/list?pageindex=3',
        'json_index':{'items_path':['data'],'title_field':'title','url_field':'url',
            'pagination':{'page_parameter':'pageindex','page_count_field':'pages','max_pages':50}},
        'index_requests':{'https://official.example/list':{'url':'https://official.example/api',
            'method':'POST','read_only':True,'form':{'action':'list','pageindex':1}}}}
    found=discover_index(json.dumps({'data':[],'pages':43}).encode(),'https://official.example/api',config)
    assert found['indexes']==['https://official.example/list?pageindex=4']
    assert request_spec(found['indexes'][0],config)[1]['pageindex']==4
    assert request_spec('https://official.example/list?pageindex=51',config) is None
    assert request_spec('https://official.example/list?pageindex=4&action=delete',config) is None


def test_failure_archives_are_private_and_success_freshness_survives_later_failure(monkeypatch):
    with TestClient(app):
        eid,base=setup(monkeypatch)
        monkeypatch.setattr(watch,'collect_bytes_conditional',lambda url,*a,**kw:response(url,
            '<a href="/notice">2027年硕士招生报名通知</a>'.encode() if url.endswith('list') else article()))
        watch.process_once(endpoint_ids=[eid]);watch.process_once(endpoint_ids=[eid])
        with SessionLocal() as db:
            row=db.scalar(select(NoticeResource).where(NoticeResource.endpoint_id==eid,NoticeResource.kind=='index'))
            previous=row.last_success_at;assert previous
        due(eid,'index')
        monkeypatch.setattr(watch,'collect_bytes_conditional',lambda url,*a,**kw:response(url,b'<html>unrecognized page</html>'))
        assert watch.process_once(endpoint_ids=[eid])['status']=='needs_review'
        with SessionLocal.begin() as db:
            row=db.get(NoticeResource,row.id);assert row.last_success_at==previous
            failed=db.scalar(select(CollectionAttempt).where(CollectionAttempt.resource_id==row.id,CollectionAttempt.outcome=='failed'))
            assert failed.content==b'<html>unrecognized page</html>'
            assert db.scalar(select(func.count()).select_from(CollectionAttempt).where(CollectionAttempt.endpoint_id==eid,CollectionAttempt.outcome=='success'))==2
            db.get(SourceEndpoint,eid).scheduled=False


def test_independent_monitor_deduplicates_and_resolves_worker_alert():
    now=datetime.now(UTC)
    with SessionLocal.begin() as db:
        db.merge(WorkerHeartbeat(name='reminders',state='ok',observed_at=now-timedelta(minutes=10)))
        check_alerts(db,now);db.flush();check_alerts(db,now)
        assert db.get(CollectionAlert,'worker').status=='active'
        db.get(WorkerHeartbeat,'reminders').observed_at=now;db.flush()
        check_alerts(db,now);assert db.get(CollectionAlert,'worker').status=='resolved'


def test_same_title_only_is_never_merged_and_provenance_is_retained():
    item={'title':'notice','description':'body','paths':[],'deadline':None,'start_time':None,
        'document':{'content_hash':'a','canonical_url':'https://official.example/a'},
        'publication_id':'one','source':{'name':'school'}}
    duplicate={**item,'publication_id':'two'}
    different={**item,'document':{**item['document'],'content_hash':'b'},'publication_id':'three'}
    rows=group_identical([item,duplicate,different])
    assert len(rows)==2 and rows[0]['duplicate_count']==2
    assert rows[0]['alternate_sources'][0]['publication_id']=='two'


def test_restful_public_detail_keeps_id_date_and_explicit_read_only_boundary():
    from app.adapters.public_json_notice import PublicJSONNoticeAdapter
    from app.collector_http import FetchError
    pattern=r'/career/zpxx/view/zpxx/(?P<id>[0-9]{1,24})'
    url='https://official.example/career/zpxx/view/zpxx/244767943823593472'
    spec={'url':'https://official.example/api/{id}','page_path_pattern':pattern,
        'method':'POST','read_only':True,'form':{}}
    assert request_spec(url,{'detail_request':spec},'detail')==('https://official.example/api/244767943823593472',{})
    with pytest.raises(FetchError):request_spec('https://official.example/career/delete/1',{'detail_request':spec},'detail')
    mapping={'success_field':'code','success_value':200,'items_path':['data'],'title_field':'title','body_field':'html',
        'id_field':'id','page_path_pattern':pattern,'date_fields':{'deadline_at':'close'},'date_timezone':'Asia/Shanghai'}
    payload={'code':200,'data':{'id':'244767943823593472','title':'2027年校园招聘公告',
        'html':'<p>毕业生请核对本单位的公开招聘公告，提交材料和报名办法以官方发布的完整要求为准。</p>','close':'2027-02-28'}}
    adapter=PublicJSONNoticeAdapter('employment',mapping)
    parsed=adapter.parse(RawArtifact(json.dumps(payload).encode(),url,'id'))
    assert parsed.records[0]['deadline_at']=='2027-02-28T23:59:00+08:00'
    assert any(e['evidence_location']=='json=$.data.close' for e in parsed.evidence)
    payload['data']['id']='other'
    with pytest.raises(ParseError):adapter.parse(RawArtifact(json.dumps(payload).encode(),url,'id'))


def test_portable_bundle_excludes_personal_tables_and_is_insert_only():
    from app.collection_bundle import export_bundle,import_bundle,TABLES
    import gzip
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.database import Base
    with SessionLocal() as db:content=export_bundle(db)
    lines=gzip.decompress(content).splitlines();payload=json.loads(lines[0]);records=[json.loads(line) for line in lines[1:]]
    assert set(payload['tables'])=={m.__tablename__ for m in TABLES}
    assert not {'profiles','user_plans','notifications','users'} & set(payload['tables'])
    assert all(e['auth_type']=='none' and not e['secret_ref'] for e in [r['row'] for r in records if r['table']=='source_endpoints'])
    target=create_engine('sqlite://')
    Base.metadata.create_all(target)
    with Session(target) as db:
        first=import_bundle(db,content);db.commit()
        assert any(first.values())
        assert not any(import_bundle(db,content).values())

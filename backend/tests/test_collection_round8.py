"""Real legacy/OCR parsing, first-party attachments, protected exchange and alert retries."""
import base64
import hashlib
import io
import json
from datetime import UTC,datetime,timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from app import alert_delivery as alerts,collection_exchange as exchange
from app import notice_watch as watch
from app.adapters.base import RawArtifact
from app.adapters.education import PublicNoticeAdapter
from app.adapters.public_json_notice import PublicJSONNoticeAdapter
from app.adapters.public_request import request_spec
from app.config import settings
from app.database import SessionLocal
from app.intake_models import CollectionAlert,CollectionAlertDelivery,DataPublication,DocumentVersion,DocumentArchive,DevelopmentItem
from app.intake_models import SourceEndpoint
from app.main import app
from app.parsers import extract_isolated,ParseError
from app.supporting_attachments import supporting_links
from test_collection_exchange import setup,entry
from test_notice_watch import setup as setup_watch,response

FIXTURES=Path(__file__).parent/'fixtures/round8'


@pytest.mark.parametrize('name,format,expected',[
    ('application.doc','doc','[文本行 1] CampusMate'),('application.xls','xls','[行 3] Read the original'),
    ('notice.png','image','Scholarship Application Notice')])
def test_real_isolated_extractors(name,format,expected):
    parsed=extract_isolated((FIXTURES/name).read_bytes(),format)
    assert expected in parsed.text
    if format=='image':assert all(p['box'] and p['confidence']>=65 for p in parsed.evidence)


def test_legacy_formulas_and_invalid_containers_never_become_facts():
    parsed=extract_isolated((FIXTURES/'formula.xls').read_bytes(),'xls')
    assert '[公式，需人工核对]' in parsed.text and '[行 3] 2' not in parsed.text
    with pytest.raises(ParseError):extract_isolated(b'not a Word document'*20,'doc')


def test_image_limits_and_ocr_dates_require_confirmation():
    data=(FIXTURES/'notice.png').read_bytes()
    parsed=PublicNoticeAdapter('funding').parse(RawArtifact(data,'https://official.example/notice.png','notice','image/png'))
    assert parsed.records[0]['title']=='2027 Postgraduate Scholarship Application Notice'
    assert 'OCR' in parsed.records[0]['body'] and 'deadline_at' not in parsed.records[0]
    assert parsed.metadata['publish_time'] is None
    assert any('box=' in p['evidence_location'] for p in parsed.evidence)
    out=io.BytesIO();Image.new('RGB',(4000,3100)).save(out,format='PNG')
    with pytest.raises(ParseError,match='像素'):extract_isolated(out.getvalue(),'image')


def test_discovery_includes_legacy_pdf_and_article_images_only():
    html='<header><img src="/banner.png"></header><article><img src="/body.png"><img src="/qrcode.png"><img src="/tiny.png" width="20"><img src="https://third.example/a.png"><a href="/f.pdf">申请表.pdf</a><a href="/f.doc">申请表.doc</a><a href="/f.xls">岗位表.xls</a><a href="/names.xls">名单公示.xls</a></article>'
    assert supporting_links(html,'https://official.example/notice')==[
        'https://official.example/f.pdf','https://official.example/f.doc','https://official.example/f.xls','https://official.example/body.png']


@pytest.mark.parametrize('json_source',[False,True])
def test_attachment_exchange_requires_current_public_parent_and_keeps_original(setup,json_source):
    parent=entry(setup)
    raw=base64.b64decode(parent.content).replace(b'</article>',b'<a href="/form.doc">Application.doc</a></article>')
    parent=parent.model_copy(update={'content':base64.b64encode(raw).decode(),'content_hash':hashlib.sha256(raw).hexdigest()})
    if json_source:
        with SessionLocal.begin() as db:
            ep=db.get(SourceEndpoint,setup[1]);config=json.loads(ep.adapter_config)
            config.update(topic='funding',path_code='domestic_study',
                json_detail={'title_field':'title','body_field':'body','id_field':'id','query_parameter':'id'},
                detail_request={'method':'POST','read_only':True,'page_path':'/notice','query_parameter':'id',
                    'id_parameter':'id','url':'/api/detail','form':{}})
            ep.adapter_config=json.dumps(config)
        raw=json.dumps({'id':123,'title':'2026年官方奖学金申请通知','body':'<p>申请人应完整阅读奖学金公告并按照官方要求提交全部申请材料，核对相关信息。</p><a href="/form.doc">Application.doc</a>'},ensure_ascii=False).encode()
        url=setup[2]+'notice?id=123'
        parent=parent.model_copy(update={'canonical_url':url,'source_item_id':url,'content_type':'application/json',
            'content':base64.b64encode(raw).decode(),'content_hash':hashlib.sha256(raw).hexdigest()})
    p=exchange.receive_transaction(parent)
    content=(FIXTURES/'application.doc').read_bytes();url=setup[2]+'form.doc'
    child=exchange.Original(publication_id=uuid4(),source_code=setup[0],source_item_id=url,canonical_url=url,
        kind='attachment',parent_url=parent.canonical_url,parent_content_hash=parent.content_hash,
        content_hash=hashlib.sha256(content).hexdigest(),content_type='application/msword',
        fetched_at=parent.fetched_at,last_changed_at=parent.last_changed_at,content=base64.b64encode(content).decode())
    c=exchange.receive_transaction(child);assert c['state']=='imported'
    assert exchange.receive_transaction(child)['state']=='unchanged'
    with SessionLocal() as db:
        document=db.get(DocumentVersion,c['document_id'])
        assert db.get(DocumentArchive,document.id).content==content
        assert not db.scalar(select(DataPublication).where(DataPublication.document_id==document.id))
        assert not db.scalar(select(DevelopmentItem).where(DevelopmentItem.source_document_id==document.id))
        original=exchange.original(db,document.id)
        assert original['kind']=='attachment' and original['parent_content_hash']==parent.content_hash
        # A legacy item ID can leave two published documents at one URL.
        # The child's parent must match the current native frontier document.
        source_document=db.get(DocumentVersion,p['document_id'])
        alternate=DocumentVersion(**{c.name:getattr(source_document,c.name) for c in DocumentVersion.__table__.columns})
        alternate.id=str(uuid4())
        alternate.source_item_id='legacy-item-alias';alternate.content_hash='f'*64
        db.add(alternate);db.flush()
        alternate_publication_id=str(uuid4())
        # Feed a second valid publication into visible(), without weakening readiness.
        original_visible=exchange.visible
        def publications(db):
            yield from original_visible(db)
            class Pub:document_id=alternate.id;id=alternate_publication_id
            yield Pub(),{}
        # Use an archive with its actual bytes/hash so this is a genuine alternate version.
        other_raw=raw+b'\n'
        alternate.content_hash=hashlib.sha256(other_raw).hexdigest()
        db.add(DocumentArchive(document_id=alternate.id,content=other_raw,content_type=parent.content_type,is_fixture=False))
        db.flush()
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(exchange,'visible',publications)
            rows=exchange.inventory(db)
            child_row=next(r for r in rows if r['publication_id']==document.id)
            assert child_row['parent_content_hash']==original['parent_content_hash']
        db.rollback()
    with pytest.raises(HTTPException):exchange.receive_transaction(child.model_copy(update={'parent_content_hash':'0'*64}))
    with pytest.raises(HTTPException):exchange.receive_transaction(child.model_copy(update={'canonical_url':setup[2]+'unlinked.doc','source_item_id':setup[2]+'unlinked.doc'}))
    with SessionLocal.begin() as db:
        pub=db.scalar(select(DataPublication).where(DataPublication.document_id==p['document_id']));pub.status='withdrawn'
    with SessionLocal() as db:assert not [r for r in exchange.inventory(db) if r.get('kind')=='attachment' and r['source_code']==setup[0]]
    with SessionLocal() as db:
        with pytest.raises(HTTPException):exchange.original(db,c['document_id'])
    with pytest.raises(HTTPException):exchange.receive_transaction(child)


def test_local_monitor_does_not_resolve_independent_cloud_outage(monkeypatch):
    from app.collection_monitor import check_alerts
    from app.operations import WorkerHeartbeat
    from app import collection_exchange,notice_watch
    key='cloud:test-'+str(uuid4());now=datetime.now(UTC)
    monkeypatch.setattr(settings,'collection_alert_channel','desktop')
    monkeypatch.setattr(notice_watch,'monitor_status',lambda db:[])
    monkeypatch.setattr(collection_exchange,'status',lambda db:{'state':'ok'})
    with SessionLocal.begin() as db:
        db.merge(WorkerHeartbeat(name='reminders',state='ok',observed_at=now))
        db.add(CollectionAlert(key=key,status='active',message='云端来源异常',first_seen_at=now,last_seen_at=now))
    with SessionLocal.begin() as db:
        check_alerts(db,now)
        alert=db.get(CollectionAlert,key)
        assert alert.status=='active' and alert.resolved_at is None
        delivery=db.scalar(select(CollectionAlertDelivery).where(CollectionAlertDelivery.alert_key==key))
        delivery.state='sent';delivery.delivered_at=now
    with SessionLocal.begin() as db:
        check_alerts(db,now+timedelta(seconds=30))
        assert db.get(CollectionAlert,key).status=='active'
        assert len(db.scalars(select(CollectionAlertDelivery).where(CollectionAlertDelivery.alert_key==key)).all())==1


def test_wps_doc_fallback_preserves_compatibility_warning(monkeypatch):
    from app import legacy_office
    from types import SimpleNamespace
    monkeypatch.setattr(legacy_office.shutil,'which',lambda name:name if name in {'antiword','catdoc'} else None)
    calls=[]
    def run(args,**kwargs):
        calls.append(args[0])
        if args[0]=='antiword':return SimpleNamespace(returncode=1,stdout=b'',stderr=b'not recognized')
        return SimpleNamespace(returncode=0,stdout='官方申请材料内容'.encode(),stderr=b'fast-saved; some information lost')
    monkeypatch.setattr(legacy_office.subprocess,'run',run)
    result=legacy_office.word((FIXTURES/'application.doc').read_bytes())
    assert calls==['antiword','catdoc']
    assert '可能不完整' in result and '以归档原件核对' in result and '官方申请材料内容' in result


def test_explicit_readonly_get_maps_only_numeric_public_ids():
    config={'detail_request':{'method':'GET','read_only':True,'page_path_pattern':r'/front/content/(?P<id>[0-9]{1,16})',
        'url':'/api/detail','id_parameter':'id','params':{'isStatic':'false'}}}
    assert request_spec('https://official.example/front/content/123',config,'detail')==(
        'https://official.example/api/detail?isStatic=false&id=123',None)
    with pytest.raises(ValueError):request_spec('https://official.example/front/content/delete',config,'detail')
    config['detail_request']['read_only']=False
    with pytest.raises(ValueError):request_spec('https://official.example/front/content/123',config,'detail')


def test_nested_json_body_has_exact_field_provenance_and_id_check():
    mapping={'items_path':['data'],'title_field':'title','body_path':['instance','items',{'field':'field','equals':'contents'},'value','正文'],
        'id_field':'id','page_path_pattern':r'/front/content/(?P<id>[0-9]+)'}
    value={'data':{'id':123,'title':'2026年硕士研究生考试报名公告','instance':{'items':[
        {'field':'irrelevant','value':'ignore'},{'field':'contents','value':{'正文':'<p>请仔细阅读考试报名安排，准确填写申请材料并按照官方要求完成提交与核验工作。</p>'}}]}}}
    adapter=PublicJSONNoticeAdapter('examination',mapping)
    raw=RawArtifact(json.dumps(value,ensure_ascii=False).encode(),'https://official.example/front/content/123','123')
    parsed=adapter.parse(raw)
    assert parsed.evidence[0]['evidence_location']=='json=$.data.instance.items[1].value.正文'
    value['data']['instance']['items'].append(value['data']['instance']['items'][1])
    with pytest.raises(ParseError):adapter.parse(RawArtifact(json.dumps(value).encode(),raw.canonical_url,'123'))


def test_split_title_retains_body_evidence():
    html='<div class="TRS_UEDITOR"><p>测试医院</p><p>2026年公开招聘博士研究生公告</p><p>招聘岗位和申请材料以正式公告为准，请核实条件后按时提交全部材料。</p></div>'
    parsed=PublicNoticeAdapter('recruitment','.TRS_UEDITOR',{'join':'.TRS_UEDITOR p','limit':2}).parse(RawArtifact(html.encode(),'https://official.example/a','a'))
    assert parsed.records[0]['title'].startswith('测试医院')
    assert any(e['field']=='body' for e in parsed.evidence) and sum(e['field']=='title' for e in parsed.evidence)==2


@pytest.mark.parametrize('image_only',[False,True])
def test_native_queue_archives_pdf_and_ocr_body_without_inventing_dates(monkeypatch,image_only):
    with TestClient(app):
        eid,base=setup_watch(monkeypatch)
        with SessionLocal.begin() as db:
            ep=db.get(SourceEndpoint,eid);config=json.loads(ep.adapter_config)
            config.update(topic='funding',path_code='domestic_study');ep.adapter_config=json.dumps(config)
        text='' if image_only else '<p>申请人必须核对官方奖学金公告和申请材料，所有资格要求与报名方式以正式公告为准。</p><a href="/form.pdf">申请表.pdf</a>'
        parent=('<h1>2026年奖学金申请公告</h1><article>'+text+'<img src="/notice.png"></article>').encode()
        def fetch(url,*args,**kwargs):
            raw=(FIXTURES/'notice.png').read_bytes() if url.endswith('png') else (FIXTURES/'application.pdf').read_bytes() if url.endswith('pdf') else parent if url.endswith('poster') else '<a href="/poster">2026年奖学金申请公告</a>'.encode()
            return response(url,raw)
        monkeypatch.setattr(watch,'collect_bytes_conditional',fetch)
        assert watch.process_once(endpoint_ids=[eid])['kind']=='index'
        result=watch.process_once(endpoint_ids=[eid])
        assert result['status']=='attachments_pending' if image_only else result['status']=='updated'
        outcomes=[watch.process_once(endpoint_ids=[eid]) for _ in range(1 if image_only else 2)]
        assert all(r['status']=='updated' for r in outcomes)
        with SessionLocal.begin() as db:
            docs=list(db.scalars(select(DocumentVersion).where(DocumentVersion.source_endpoint_id==eid)))
            poster=next(d for d in docs if d.canonical_url.endswith('png'))
            assert db.get(DocumentArchive,poster.id).content==(FIXTURES/'notice.png').read_bytes()
            if image_only:
                assert json.loads(poster.raw_text)[0]['body'].startswith('[OCR')
                item=db.scalar(select(DevelopmentItem).where(DevelopmentItem.source_document_id==poster.id));assert item.deadline is None
            else:
                pdf=next(d for d in docs if d.canonical_url.endswith('pdf'))
                assert json.loads(pdf.raw_text)['format']=='pdf'
                assert not db.scalar(select(DevelopmentItem).where(DevelopmentItem.source_document_id==poster.id))
            db.get(SourceEndpoint,eid).scheduled=False


def test_alert_dedup_recovery_and_secret_free_retry(monkeypatch):
    monkeypatch.setattr(settings,'collection_alert_webhook','https://alerts.example/private-secret')
    key='test-alert-'+str(uuid4());now=datetime.now(UTC)
    with SessionLocal.begin() as db:
        db.add(CollectionAlert(key=key,status='active',message='Worker 停止',first_seen_at=now,last_seen_at=now))
        db.flush();alerts.queue_alerts(db)
        assert alerts.queue_alerts(db)==0
    monkeypatch.setattr(alerts,'send_alert',lambda *args:(_ for _ in ()).throw(ValueError('private-secret')))
    result=alerts.deliver_once(limit=200)
    assert result['failed']>=1
    with SessionLocal.begin() as db:
        row=db.scalar(select(CollectionAlertDelivery).where(CollectionAlertDelivery.alert_key==key))
        assert row.state=='retry' and 'private-secret' not in row.error
        row.next_attempt_at=now-timedelta(seconds=1)
    sent=[];monkeypatch.setattr(alerts,'send_alert',lambda *args:sent.append(args))
    alerts.deliver_once(limit=200)
    with SessionLocal.begin() as db:
        alert=db.get(CollectionAlert,key);alert.status='resolved';alert.resolved_at=now
        assert alerts.queue_alerts(db)==1
    alerts.deliver_once(limit=200)
    assert ('Worker 停止','active') in sent and ('Worker 停止','resolved') in sent
    with SessionLocal.begin() as db:
        db.get(CollectionAlert,key).message='同一已恢复事件的统计更新'
        assert alerts.queue_alerts(db)==0


def test_offsite_upload_reads_back_bytes_and_rejects_truncation(tmp_path):
    import importlib.util
    spec=importlib.util.spec_from_file_location('offsite',Path(__file__).resolve().parents[2]/'scripts/railway-backup/offsite.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    path=tmp_path/'backup.age';path.write_bytes(b'age-encryption.org/v1\n'+b'encrypted bytes'*30)
    class Store:
        def upload_file(self,filename,bucket,key,ExtraArgs):self.content=Path(filename).read_bytes();self.metadata=ExtraArgs
        def get_object(self,**kwargs):return {'Body':io.BytesIO(self.content)}
    store=Store();assert module.upload(path,store,'bucket','key')['bytes']==path.stat().st_size
    class Truncated(Store):
        def get_object(self,**kwargs):return {'Body':io.BytesIO(self.content[:-1])}
    with pytest.raises(ValueError,match='hash'):module.upload(path,Truncated(),'bucket','key')


def test_sqlite_coverage_read_does_not_block_archive_writer():
    from app.database import engine
    from app.operations import WorkerHeartbeat
    if engine.dialect.name!='sqlite':pytest.skip('SQLite-specific concurrency regression')
    key='wal-'+uuid4().hex
    with engine.connect() as reader:
        assert reader.exec_driver_sql('PRAGMA journal_mode').scalar()=='wal'
        reader.exec_driver_sql('BEGIN')
        before=reader.exec_driver_sql('SELECT count(*) FROM worker_heartbeats').scalar()
        with SessionLocal.begin() as writer:writer.add(WorkerHeartbeat(name=key,state='ok',observed_at=datetime.now(UTC)))
        # The reader retains its snapshot while the writer successfully commits.
        assert reader.exec_driver_sql('SELECT count(*) FROM worker_heartbeats').scalar()==before
        reader.rollback()
    with SessionLocal.begin() as db:db.delete(db.get(WorkerHeartbeat,key))

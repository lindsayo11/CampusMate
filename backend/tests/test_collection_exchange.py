"""Actual public-original import, duplicate versions, moderation and transport boundaries."""
import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import collection_exchange as exchange
from app.config import settings
from app.database import SessionLocal
from app.intake_models import (CollectionSyncState, DataPublication, DocumentArchive,
    DocumentVersion, NoticeResource, Source, SourceEndpoint)
from app.main import app
from app.models import Path


@pytest.fixture
def setup(monkeypatch):
    sid,eid = str(uuid4()),str(uuid4())
    code = 'SYNC-' + sid[:20]
    base = 'https://exchange.example.edu/'
    config = {'collection_mode':'public_notice_watch','authorized_by':'test-operator',
        'topic':'postgraduate','notice_scope':'university','index_urls':[base+'list']}
    old = datetime.now(UTC)-timedelta(days=3)
    with SessionLocal.begin() as db:
        for path_code,path_name in [('recommendation_exemption','推免'),('employment','测试就业')]:
            if not db.scalar(select(Path).where(Path.code==path_code)):
                db.add(Path(code=path_code,name=path_name,description='测试路径'))
        db.add(Source(id=sid,source_code=code,name='原文同步测试大学',publisher='测试大学',
            authority_level='A',source_class='university',official=True,jurisdiction_level='school',
            base_url=base,active=True,verified_at=old))
        db.add(SourceEndpoint(id=eid,source_id=sid,name='notice-watch',endpoint_type='html',url=base+'list',
            parser_type='UniversityNoticeAdapter',automation_level='AUTO-2',agent_mode='EXTRACT',
            scheduled=True,active=True,adapter_config=json.dumps(config),last_success_at=old,consecutive_failures=4))
    monkeypatch.setattr(settings,'collection_exchange_token','x'*40)
    monkeypatch.setattr(settings,'collector_allowed_hosts','exchange.example.edu')
    monkeypatch.setattr(settings,'collection_peer_url','https://peer.example.edu')
    yield code,eid,base,old
    with SessionLocal.begin() as db:
        db.get(SourceEndpoint,eid).scheduled=False
        # Each test gets its own automatic peer scheduling state.
        state=db.get(CollectionSyncState,'peer')
        if state:db.delete(state)


def entry(setup, text='', age=2):
    code,_,base,_ = setup
    raw = ('<h1>测试大学2027年推免研究生申请通知</h1><time>2026-09-30</time><article>'
        '<p>报名截止：2026年10月9日。申请材料和提交方式以官方原文为准，请在规定时间完成报名。'+text+'</p></article>').encode()
    changed = datetime.now(UTC)-timedelta(days=age)
    return exchange.Original(publication_id=uuid4(),source_code=code,source_item_id=base+'a',
        canonical_url=base+'a',content_hash=hashlib.sha256(raw).hexdigest(),content_type='text/html',
        fetched_at=changed,last_changed_at=changed,content=base64.b64encode(raw).decode())


def test_import_is_idempotent_preserves_native_failures_and_source_time(setup):
    value=entry(setup)
    first=exchange.receive_transaction(value)
    assert first['state']=='imported' and first['changed']
    assert exchange.receive_transaction(value)['state']=='unchanged'
    with SessionLocal() as db:
        doc=db.get(DocumentVersion,first['document_id'])
        assert doc.version_no==1 and exchange.utc(doc.fetched_at)==value.fetched_at
        assert exchange.utc(doc.last_changed_at)==value.last_changed_at
        endpoint=db.get(SourceEndpoint,setup[1])
        assert endpoint.consecutive_failures==4 and exchange.utc(endpoint.last_success_at)==setup[3]
        assert db.scalar(select(func.count()).select_from(DocumentVersion).where(
            DocumentVersion.source_endpoint_id==setup[1]))==1
        resource=db.scalar(select(NoticeResource).where(NoticeResource.document_id==doc.id))
        assert resource.status=='peer_imported' and resource.last_success_at is None
        pub=db.scalar(select(DataPublication).where(DataPublication.document_id==doc.id))
        assert pub.status=='published' and pub.submitted_by=='system-ingestion'
        saved=exchange.original(db,pub.id)
        assert base64.b64decode(saved['content'])==base64.b64decode(value.content)
        assert not any(k in saved for k in ('rules','plans','users','adapter_config','verified_by'))


def test_new_versions_and_older_conflict_cannot_roll_back(setup):
    first=entry(setup)
    result=exchange.receive_transaction(first)
    second=entry(setup,'新增提交说明。',age=1)
    newer=exchange.receive_transaction(second)
    assert newer['changed']
    assert exchange.receive_transaction(first)['state']=='stale'
    with SessionLocal() as db:
        doc=db.get(DocumentVersion,newer['document_id'])
        assert doc.version_no==2 and doc.previous_id==result['document_id']
        assert db.scalar(select(DataPublication).where(DataPublication.document_id==result['document_id'])).status=='superseded'


@pytest.mark.parametrize('protection',['withdrawn','rejected','human','deleted','manual'])
def test_local_operator_decisions_are_protected(setup,protection):
    first=entry(setup)
    result=exchange.receive_transaction(first)
    with SessionLocal.begin() as db:
        doc=db.get(DocumentVersion,result['document_id'])
        pub=db.scalar(select(DataPublication).where(DataPublication.document_id==doc.id))
        if protection in {'withdrawn','rejected'}:pub.status=protection
        elif protection=='human':pub.first_reviewed_by='local-reviewer'
        elif protection=='deleted':doc.deleted_at=datetime.now(UTC)
        else:doc.import_mode='manual'
    assert exchange.receive_transaction(entry(setup,'变化。',age=1))['state']=='protected'


def test_remote_withdrawal_hides_and_restoration_never_adds_a_version(setup):
    value=entry(setup)
    result=exchange.receive_transaction(value)
    assert exchange.receive_transaction(value.model_copy(update={'status':'withdrawn','content':None}))['state']=='hidden'
    with SessionLocal() as db:
        assert not [row for row in exchange.inventory(db) if row['source_code']==setup[0] and row['status']=='published']
        assert [row for row in exchange.inventory(db) if row['source_code']==setup[0]][0]['status']=='held'
        # An ordinary native re-check cannot undo an explicit peer withdrawal.
        assert exchange.auto_publish(db,db.get(DocumentVersion,result['document_id'])) is False
    assert exchange.receive_transaction(value)['state']=='restored'
    with SessionLocal() as db:assert db.get(DocumentVersion,result['document_id']).version_no==1


def test_raw_bytes_and_origin_are_checked_before_any_import(setup):
    value=entry(setup)
    bad=[value.model_copy(update={'content_hash':'0'*64}),value.model_copy(update={'content':'bad'}),
        value.model_copy(update={'canonical_url':'https://private.example.net/a'}),
        value.model_copy(update={'source_item_id':'unrelated'})]
    for row in bad:
        with pytest.raises(HTTPException):exchange.receive_transaction(row)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(DocumentVersion).where(
            DocumentVersion.source_endpoint_id==setup[1]))==0
    with SessionLocal.begin() as db:db.get(SourceEndpoint,setup[1]).scheduled=False
    with pytest.raises(HTTPException):exchange.receive_transaction(value)


def test_http_authentication_private_fields_and_corrupt_archives(setup):
    value=entry(setup)
    headers={'x-collection-token':'x'*40}
    with TestClient(app) as client:
        assert client.get('/v1/collection-exchange/inventory').status_code==401
        assert client.get('/v1/collection-exchange/inventory',headers={'x-collection-token':'wrong'}).status_code==401
        assert client.post('/v1/collection-exchange/receive',headers=headers,
            json={**value.model_dump(mode='json'),'user_plan':{'user_id':'private'}}).status_code==422
        response=client.post('/v1/collection-exchange/receive',headers=headers,json=value.model_dump(mode='json'))
        assert response.status_code==200
        with SessionLocal() as db:
            pub=db.scalar(select(DataPublication).where(DataPublication.document_id==response.json()['document_id']))
            pubid=pub.id
        assert client.get('/v1/collection-exchange/originals/'+pubid,headers=headers).status_code==200
        with SessionLocal.begin() as db:db.get(DocumentArchive,response.json()['document_id']).content=b'corrupt'
        assert client.get('/v1/collection-exchange/originals/'+pubid,headers=headers).status_code==409
        rows=client.get('/v1/collection-exchange/inventory',headers=headers).json()['items']
        assert not any(row['source_code']==setup[0] for row in rows)


def test_held_records_are_not_reflected_as_withdrawals(setup):
    value=entry(setup).model_copy(update={'content':None})
    held=value.model_copy(update={'status':'held'})
    withdrawn=value.model_copy(update={'status':'withdrawn'})
    assert exchange.compare([value],[held])==[('push',value)]
    assert exchange.compare([value],[withdrawn])==[('pull',withdrawn)]
    assert exchange.compare([value],[value])==[]


def test_worker_transfers_both_directions_and_resume_is_idempotent(setup,monkeypatch):
    ours=entry(setup)
    result=exchange.receive_transaction(ours)
    theirs=entry(setup).model_copy(update={'canonical_url':setup[2]+'b','source_item_id':setup[2]+'b'})
    remote=[theirs.model_dump(mode='json',exclude={'content'})]
    sent=[]
    def request(method,path,payload=None):
        if path=='/inventory':return {'items':remote,'complete':True}
        if path.startswith('/originals/'):return theirs.model_dump(mode='json')
        if path=='/receive':
            sent.append(payload)
            remote.append({k:v for k,v in payload.items() if k!='content'})
            return {'state':'imported','changed':True}
        raise AssertionError(path)
    monkeypatch.setattr(exchange,'peer_request',request)
    cycle=exchange.run_cycle(force=True)
    assert cycle=={'state':'ok','pulled':1,'pushed':1,'pending':0,'failed':0}
    assert len(sent)==1 and sent[0]['content_hash']==ours.content_hash
    assert exchange.run_cycle(force=True)['pushed']==0 and len(sent)==1
    with SessionLocal() as db:
        assert db.get(DocumentVersion,result['document_id']).version_no==1
        assert exchange.status(db)['pending']==0


def test_transport_never_sends_token_to_redirect_or_private_address(setup,monkeypatch):
    monkeypatch.setattr(settings,'collection_peer_url','http://peer.example.edu')
    with pytest.raises(ValueError):exchange.peer_request('GET','/inventory')
    monkeypatch.setattr(settings,'collection_peer_url','https://peer.example.edu/private')
    with pytest.raises(ValueError):exchange.peer_request('GET','/inventory')
    monkeypatch.setattr(settings,'collection_peer_url','https://peer.example.edu')
    monkeypatch.setattr(exchange,'public_ip',lambda host:(_ for _ in ()).throw(ValueError('private')))
    with pytest.raises(ValueError):exchange.peer_request('GET','/inventory')


def test_official_permission_page_is_an_access_boundary():
    from app.adapters.education import PublicNoticeAdapter
    from app.adapters.base import RawArtifact
    from app.coverage_quality import error_category
    from app.parsers import ParseError
    raw=RawArtifact('<title>系统提示</title><p>您没有访问当前栏目的权限。</p>'.encode(),
        'https://ygb.sdu.edu.cn/system/resource/code/auth/ipauth.htm','a','text/html')
    with pytest.raises(ParseError,match='权限限制') as caught:PublicNoticeAdapter('funding').parse(raw)
    assert error_category(str(caught.value))=='access_denied'


def test_transport_pins_host_and_refuses_redirect_before_reading_body(setup,monkeypatch):
    monkeypatch.setattr(exchange,'public_ip',lambda host:'8.8.8.8')
    class Redirect:
        status_code=302
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def iter_bytes(self):raise AssertionError('A redirect body must not be read')
    class Client:
        def __init__(self,**kwargs):
            assert kwargs['follow_redirects'] is False and kwargs['trust_env'] is False
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def stream(self,method,url,**kwargs):
            assert url=='https://8.8.8.8/v1/collection-exchange/inventory'
            assert kwargs['headers']['Host']=='peer.example.edu'
            assert kwargs['extensions']['sni_hostname']=='peer.example.edu'
            assert kwargs['headers']['x-collection-token']=='x'*40
            return Redirect()
    monkeypatch.setattr(exchange.httpx,'Client',Client)
    with pytest.raises(ValueError,match='HTTP 302'):exchange.peer_request('GET','/inventory')


def test_nested_json_title_evidence_repair_keeps_original_version_and_time(setup):
    from app.intake_models import Evidence
    from app.parser_upgrade import repair_json_title_provenance
    config={'collection_mode':'public_notice_watch','authorized_by':'test','topic':'employment',
        'json_detail':{'items_path':['data'],'title_field':'title','body_field':'body'}}
    with SessionLocal.begin() as db:db.get(SourceEndpoint,setup[1]).adapter_config=json.dumps(config)
    raw=json.dumps({'data':{'title':'测试大学校园招聘公告','body':'报名截止：2026年10月9日。申请材料和提交方式以官方通知为准，请在规定时间完成报名。'}}).encode()
    value=entry(setup).model_copy(update={'content':base64.b64encode(raw).decode(),
        'content_hash':hashlib.sha256(raw).hexdigest(),'content_type':'application/json'})
    result=exchange.receive_transaction(value)
    with SessionLocal.begin() as db:
        doc=db.get(DocumentVersion,result['document_id'])
        proof=db.scalar(select(Evidence).where(Evidence.document_version_id==doc.id,
            Evidence.evidence_location=='json=$.data.title'))
        assert proof
        proof.evidence_location='json=$.title'
        db.flush();assert exchange.auto_publish(db,doc)
        assert repair_json_title_provenance(db,doc,config,apply=True)['status']=='updated'
        assert proof.evidence_location=='json=$.data.title'
        assert doc.version_no==1 and exchange.utc(doc.fetched_at)==value.fetched_at
        assert repair_json_title_provenance(db,doc,config,apply=True)['status']=='unchanged'

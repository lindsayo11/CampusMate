"""Public JSON file discovery, immutable repair and actionable safe sync failures."""
import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select

from app import collection_exchange as exchange, notice_watch as watch
from app.adapters.base import RawArtifact
from app.adapters.public_json_notice import PublicJSONNoticeAdapter
from app.database import SessionLocal
from app.intake_models import (CollectionSyncState, DataPublication, DevelopmentItem,
    DocumentArchive, DocumentVersion, Evidence, NoticeResource, SourceEndpoint)
from app.parser_upgrade import repair_json_attachments
from app.supporting_attachments import office_links
from test_collection_exchange import entry, setup
from test_parser_upgrade_and_attachments import word

MAPPING={'items_path':['data'],'title_field':'title','body_field':'body',
    'attachments':{'field':'files','encoding':'json_string','title_field':'name',
        'url_field':'url','url_prefix':'/career','url_path_prefix':'/download/fileDownload/'}}


def payload(files=None):
    return json.dumps({'data':{'title':'测试大学2027届校园招聘公告',
        'body':'报名截止：2026年10月9日。申请材料和提交方式以官方通知为准，请在规定时间完成报名。',
        'files':json.dumps(files if files is not None else [
            {'name':'岗位表.xlsx','url':'/download/fileDownload/12/34'}],ensure_ascii=False)}},ensure_ascii=False).encode()


def test_explicit_attachment_mapping_tracks_json_position_and_official_context():
    raw=RawArtifact(payload(),'https://official.example/career/view/1','1','application/json')
    parsed=PublicJSONNoticeAdapter('employment',MAPPING).parse(raw)
    assert parsed.records[0]['attachments']==[{'title':'岗位表.xlsx',
        'url':'https://official.example/career/download/fileDownload/12/34'}]
    proof=next(p for p in parsed.evidence if p['field']=='attachments')
    assert proof['evidence_location']=='json=$.data.files;json-string-index=0'
    assert office_links(raw.content,raw.canonical_url,{'topic':'employment','json_detail':MAPPING})==[
        'https://official.example/career/download/fileDownload/12/34']


def test_unmapped_external_private_list_and_action_files_are_not_discovered():
    files=[{'name':'岗位表.xlsx','url':'https://external.example/f.xlsx'},
        {'name':'岗位表.xlsx','url':'/delete/12'},
        {'name':'名单公示.xlsx','url':'/download/fileDownload/12/34'},
        {'name':'岗位表.xlsx','url':'/download/fileDownload/../../delete'},
        {'name':'岗位表.xlsx','url':'/download/fileDownload/%2e%2e/delete'},
        {'name':'岗位表.xlsx','url':'//external.example/f.xlsx'}]
    raw=RawArtifact(payload(files),'https://official.example/career/view/1','1','application/json')
    assert PublicJSONNoticeAdapter('employment',MAPPING).parse(raw).records[0]['attachments']==[]
    assert PublicJSONNoticeAdapter('employment',{k:v for k,v in MAPPING.items() if k!='attachments'}).parse(
        raw).records[0]['attachments']==[]


def test_yunnan_template_keeps_navigation_out_and_uses_explicit_application_time():
    from app.public_source_catalog import load_catalog
    from app.adapters.education import UniversityNoticeAdapter
    source=next(s for s in load_catalog()['sources'] if s['code']=='CM-HRSS-YN')
    html=('<nav>公务员招聘导航</nav><div class="readBox"><h2>云南省2026年高校毕业生“三支一扶”计划招募公告</h2>'
        '<h3>发布时间：2026/4/15 8:51:12</h3><span id="Body_ltl_newsContent">'
        '<p>提交报考申请（4月20日09:00至4月24日18:00）。报考人员应核对岗位要求，所有条件以本官方公告为准。</p>'
        '</span></div><footer>其他招聘导航</footer>').encode()
    parsed=UniversityNoticeAdapter('recruitment',source['article_selector'],source['title_selector']).parse(
        RawArtifact(html,source['probe']['sample']['url'],'yunnan','text/html'))
    assert parsed.records[0]['deadline_at']=='2026-04-24T18:00:00+08:00'
    assert '导航' not in parsed.records[0]['body']
    assert any('Body_ltl_newsContent' in p['evidence_location'] for p in parsed.evidence)
    from app.adapters.index_discovery import discover_index
    links=discover_index(('<a href="/NewsLsit.aspx?ClassID=950">2026年三支一扶计划</a>'
        '<a href="/NewsView.aspx?NewsID=64608">2026年三支一扶计划招募公告</a>').encode(),
        source['index_urls'][0],source)['links']
    assert len(links)==1 and '/NewsView.aspx?' in links[0]['url']


def json_entry(setup):
    raw=payload([{'name':'申请表.docx','url':'/download/fileDownload/12/34'}])
    return entry(setup).model_copy(update={'content':base64.b64encode(raw).decode(),
        'content_hash':hashlib.sha256(raw).hexdigest(),'content_type':'application/json'})


def configure(setup,mapping):
    with SessionLocal.begin() as db:
        ep=db.get(SourceEndpoint,setup[1]); config=json.loads(ep.adapter_config)
        config.update(topic='employment',json_detail=mapping);ep.adapter_config=json.dumps(config)


def test_archived_attachment_repair_keeps_original_and_respects_withdrawal(setup):
    configure(setup,{k:v for k,v in MAPPING.items() if k!='attachments'})
    result=exchange.receive_transaction(json_entry(setup))
    with SessionLocal.begin() as db:
        doc=db.get(DocumentVersion,result['document_id'])
        item=db.scalar(select(DevelopmentItem).where(DevelopmentItem.source_document_id==doc.id))
        before=(doc.version_no,doc.content_hash,doc.fetched_at,doc.last_changed_at,doc.last_seen_at)
        config={'topic':'employment','json_detail':MAPPING}
        assert repair_json_attachments(db,doc,config)['status']=='proposed'
        assert json.loads(item.materials)==[]
        assert repair_json_attachments(db,doc,config,True)['status']=='updated'
        assert json.loads(item.materials)[0]['url'].endswith('/career/download/fileDownload/12/34')
        assert before==(doc.version_no,doc.content_hash,doc.fetched_at,doc.last_changed_at,doc.last_seen_at)
        assert db.get(DocumentArchive,doc.id).content==base64.b64decode(json_entry(setup).content)
        assert repair_json_attachments(db,doc,config,True)['status']=='unchanged'
        pub=db.scalar(select(DataPublication).where(DataPublication.document_id==doc.id));pub.status='withdrawn'
        assert repair_json_attachments(db,doc,config,True)['status']=='skipped'


def test_native_json_queue_collects_support_file_without_inventing_an_opportunity(setup,monkeypatch):
    configure(setup,MAPPING)
    result=exchange.receive_transaction(json_entry(setup))
    monkeypatch.setattr(watch.time,'sleep',lambda _:None)
    office=word()
    def fetch(url,*args,**kwargs):
        assert kwargs['strict_robots'] is True
        return {'data':office if '/download/' in url else payload([
            {'name':'申请表.docx','url':'/download/fileDownload/12/34'}]),
            'final_url':url,'content_type':'application/octet-stream','not_modified':False,
            'status_code':200,'etag':None,'last_modified':None}
    monkeypatch.setattr(watch,'collect_bytes_conditional',fetch)
    assert watch.process_once(endpoint_ids=[setup[1]])['kind']=='detail'
    collected=watch.process_once(endpoint_ids=[setup[1]])
    assert collected['kind']=='support_file' and collected['status']=='updated'
    with SessionLocal() as db:
        doc=db.get(DocumentVersion,collected['document_id'])
        assert json.loads(doc.raw_text)['parent_document_id']==result['document_id']
        assert db.get(DocumentArchive,doc.id).content==office
        assert db.scalar(select(Evidence).where(Evidence.document_version_id==doc.id))
        assert db.scalar(select(func.count()).select_from(DevelopmentItem).where(
            DevelopmentItem.source_document_id==doc.id))==0


@pytest.mark.parametrize('method,code,retry_after,expected',[
    ('GET',503,None,2),('GET',503,'60',1),('GET',429,None,1),('GET',401,None,1),('POST',503,None,1)])
def test_read_retry_is_bounded_and_obeys_auth_rate_limits_and_retry_after(monkeypatch,method,code,retry_after,expected):
    calls=[]
    def request(*args):
        calls.append(args)
        raise exchange.ExchangeHTTPError(code,retry_after)
    monkeypatch.setattr(exchange,'_peer_request',request)
    monkeypatch.setattr(exchange.time,'sleep',lambda _:None)
    with pytest.raises(exchange.ExchangeHTTPError):exchange.peer_request(method,'/inventory')
    assert len(calls)==expected


def test_transient_read_failure_can_recover_in_same_cycle_without_disclosing_payload(monkeypatch):
    calls=[]
    def request(*args):
        calls.append(args)
        if len(calls)==1:raise httpx.ConnectTimeout('secret-token-and-private-payload')
        return {'items':[],'complete':True}
    monkeypatch.setattr(exchange,'_peer_request',request)
    monkeypatch.setattr(exchange.time,'sleep',lambda _:None)
    assert exchange.peer_request('GET','/inventory')['complete']
    assert len(calls)==2
    assert 'secret' not in exchange.safe_failure(httpx.ConnectTimeout('secret'),'读取云端目录')


def test_failed_manifest_persists_stage_and_preserves_previous_progress(setup,monkeypatch):
    with SessionLocal.begin() as db:
        db.add(CollectionSyncState(name='peer',state='ok',pulled=7,pushed=9,pending=3))
    monkeypatch.setattr(exchange,'peer_request',lambda *args:{'items':[{'private':'secret'}],'complete':True})
    assert exchange.run_cycle(force=True)=={'state':'error'}
    with SessionLocal() as db:
        state=db.get(CollectionSyncState,'peer')
        assert state.error=='校验云端目录：原文元数据校验失败；下一轮自动重试'
        assert (state.pulled,state.pushed,state.pending)==(7,9,3)
        assert state.lease_until is None


def test_expired_sync_lease_resumes_after_worker_exit_in_sqlite(setup,monkeypatch):
    with SessionLocal.begin() as db:
        db.add(CollectionSyncState(name='peer',state='running',
            lease_until=datetime.now(UTC)-timedelta(seconds=1)))
    monkeypatch.setattr(exchange,'peer_request',lambda *args:{'items':[],'complete':True})
    monkeypatch.setattr(exchange,'inventory',lambda db:[])
    assert exchange.run_cycle(force=True)['state']=='ok'
    with SessionLocal() as db:assert db.get(CollectionSyncState,'peer').lease_until is None


def test_expired_notice_lease_resumes_without_a_false_network_failure(setup,monkeypatch):
    with SessionLocal.begin() as db:
        watch.add_resource(db,setup[1],setup[2]+'list','index',datetime.now(UTC))
        row=db.scalar(select(NoticeResource).where(NoticeResource.endpoint_id==setup[1]))
        row.lease_until=datetime.now(UTC)-timedelta(seconds=1);row.lease_token='exited-worker'
    monkeypatch.setattr(watch.time,'sleep',lambda _:None)
    def fetch(url,*args,**kwargs):
        return {'data':'<a href="a">测试大学2027年推免研究生申请通知</a>'.encode(),
            'final_url':url,'content_type':'text/html','not_modified':False,
            'status_code':200,'etag':None,'last_modified':None}
    monkeypatch.setattr(watch,'collect_bytes_conditional',fetch)
    assert watch.process_once(endpoint_ids=[setup[1]])['status']=='checked'

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app import collector_http as http, notice_watch as watch
from app.adapters.base import RawArtifact
from app.adapters.index_discovery import discover_index
from app.adapters.public_json_notice import PublicJSONNoticeAdapter
from app.adapters.public_request import request_spec
from app.config import settings
from app.database import SessionLocal
from app.intake_models import NoticeResource, SourceEndpoint, DocumentArchive, DocumentVersion
from app.main import app
from test_notice_watch import setup

TITLE = '某科技公司2027届校园招聘公告'
BODY = '<p>招聘方向包含技术研发和产品运营，申请者应阅读岗位要求后通过单位官方渠道提交简历。</p>'
MAPPING = {'title_field':'JobName','body_field':'PostionDesc','id_field':'ID',
           'query_parameter':'itemid','success_field':'r','success_value':0}


def test_explicit_form_is_ip_pinned_and_never_follows_redirects(monkeypatch):
    monkeypatch.setattr(settings,'collector_allowed_hosts','official.example')
    monkeypatch.setattr(http,'public_ip',lambda _: '93.184.216.34')
    robots, calls = [], []
    monkeypatch.setattr(http,'assert_robots',lambda url,strict=False: robots.append((url,strict)))
    original = httpx.Client
    def handle(req):
        calls.append(req)
        assert req.method == 'POST' and req.headers['host']=='official.example'
        assert req.url.host=='93.184.216.34' and req.extensions['sni_hostname']=='official.example'
        assert req.content == b'action=joblist2&pagesize=30'
        return httpx.Response(302,headers={'location':'https://official.example/moved'})
    monkeypatch.setattr(http.httpx,'Client',lambda **kw: original(transport=httpx.MockTransport(handle)))
    with pytest.raises(http.FetchError,match='重定向'):
        http.collect_public_form('https://official.example/list',{'action':'joblist2','pagesize':30})
    assert len(calls)==1 and robots==[('https://official.example/list',True)]
    with pytest.raises(http.FetchError):
        http.fetch_url('https://official.example/list',method='POST',form_data={'action':'x'})


def test_detail_request_rejects_external_host_and_untrusted_ids():
    spec={'url':'https://official.example/api','method':'POST','read_only':True,
        'form':{'action':'jobinfo2'},'page_path':'/info','query_parameter':'itemid','id_parameter':'jid'}
    config={'detail_request':spec}
    assert request_spec('https://official.example/info?itemid=12',config,'detail')[1]['jid']=='12'
    for url in ['https://official.example/info?itemid=1&itemid=2',
                'https://official.example/info?itemid=../../private','https://official.example/other?itemid=12']:
        with pytest.raises(http.FetchError):request_spec(url,config,'detail')
    with pytest.raises(http.FetchError):request_spec('https://official.example/info?itemid=12',
        {'detail_request':{**spec,'url':'https://elsewhere.example/api'}},'detail')
    with pytest.raises(http.FetchError):request_spec('https://official.example/info?itemid=12',
        {'detail_request':{**spec,'read_only':False}},'detail')


def test_json_discovery_and_detail_identity_do_not_trust_scripts_or_update_dates():
    config={'topic':'employment','discovery_format':'json','json_index':{
        'items_path':['data'],'title_field':'JobName','id_field':'JID','url_template':'/info?itemid={id}'}}
    data=json.dumps({'data':[{'JID':12,'JobName':TITLE}]}).encode()
    assert discover_index(data,'https://official.example/api',config)['links'][0]['url']=='https://official.example/info?itemid=12'
    adapter=PublicJSONNoticeAdapter('employment',MAPPING)
    payload=json.dumps({'r':0,'ID':'12','JobName':TITLE,'PostionDesc':BODY+'<script>dangerous()</script>',
                        'UpdateTime':'2026-09-30'}).encode()
    parsed=adapter.parse(RawArtifact(payload,'https://official.example/info?itemid=12','12'))
    assert 'dangerous' not in parsed.records[0]['body'] and parsed.metadata['publish_time'] is None
    assert all(p['evidence_location'].startswith('json=') for p in parsed.evidence)
    with pytest.raises(ValueError):adapter.parse(RawArtifact(payload,'https://official.example/info?itemid=13','13'))
    with pytest.raises(ValueError):adapter.parse(RawArtifact(b'callback('+payload+b')','https://official.example/info?itemid=12','12'))


def test_public_json_pagination_uses_publisher_page_count_and_bounded_forms():
    base='https://official.example/list'
    pagination={'page_count_field':'PageCount','page_parameter':'pageindex','max_pages':3}
    config={'topic':'employment','discovery_format':'json','index_page_url':base,
        'json_index':{'items_path':['data'],'title_field':'JobName','id_field':'JID',
            'url_template':'/info?itemid={id}','pagination':pagination},
        'index_requests':{base:{'url':'https://official.example/api','method':'POST','read_only':True,
            'form':{'action':'joblist2','pageindex':1,'pagesize':30}}}}
    payload=json.dumps({'PageCount':129,'data':[{'JID':12,'JobName':TITLE}]}).encode()
    assert discover_index(payload,'https://official.example/api',config)['indexes']==[base+'?pageindex=2']
    assert request_spec(base+'?pageindex=2',config)[1]=={'action':'joblist2','pageindex':2,'pagesize':30}
    for url in [base+'?pageindex=4',base+'?pageindex=2&action=delete',base+'?pageindex=1&pageindex=2']:
        assert request_spec(url,config) is None
    assert discover_index(payload,'https://official.example/api',{**config,'index_page_url':base+'?pageindex=3'})['indexes']==[]
    assert discover_index(json.dumps({'PageCount':1,'data':[]}).encode(),'https://official.example/api',config)['indexes']==[]
    with pytest.raises(ValueError):discover_index(json.dumps({'PageCount':'bad','data':[]}).encode(),'https://official.example/api',config)


def test_form_monitor_archives_original_json_with_human_page_and_provenance(monkeypatch):
    with TestClient(app):
        eid,base=setup(monkeypatch)
        with SessionLocal.begin() as db:
            ep=db.get(SourceEndpoint,eid)
            config=watch.config_for(ep)
            config.update(topic='employment',path_code='employment',discovery_format='json',json_detail=MAPPING,
                index_requests={base+'list':{'url':base+'api','method':'POST','read_only':True,'form':{'action':'joblist2'}}},
                detail_request={'url':base+'api','method':'POST','read_only':True,'form':{'action':'jobinfo2'},
                    'page_path':'/info','query_parameter':'itemid','id_parameter':'jid'},
                json_index={'items_path':['data'],'title_field':'JobName','id_field':'JID','url_template':'/info?itemid={id}'})
            ep.adapter_config=json.dumps(config)
        payload=json.dumps({'r':0,'ID':'12','JobName':TITLE,'PostionDesc':BODY}).encode()
        def fetch(url,config,kind,*args):
            data=json.dumps({'data':[{'JID':12,'JobName':TITLE}]}).encode() if kind=='index' else payload
            return {'data':data,'final_url':base+'api','canonical_url':url,'content_type':'application/json',
                'not_modified':False,'etag':None,'last_modified':None,'retrieval_url':base+'api',
                'retrieval_method':'POST','retrieval_form':{'action':'jobinfo2','jid':'12'}}
        monkeypatch.setattr(watch,'fetch_public_resource',fetch)
        assert watch.process_once(endpoint_ids=[eid])['kind']=='index'
        assert watch.process_once(endpoint_ids=[eid])['status']=='updated'
        with SessionLocal() as db:
            doc=db.scalar(select(DocumentVersion).where(DocumentVersion.source_endpoint_id==eid))
            assert doc.canonical_url==base+'info?itemid=12'
            assert db.get(DocumentArchive,doc.id).content == payload
            assert json.loads(doc.raw_text)[0]['retrieval']['method']=='POST'
        with SessionLocal.begin() as db:
            db.execute(update(NoticeResource).where(NoticeResource.endpoint_id==eid,NoticeResource.kind=='detail')
                .values(next_check_at=datetime.now(UTC)-timedelta(seconds=1)))
        assert watch.process_once(endpoint_ids=[eid])['status']=='unchanged'
        with SessionLocal.begin() as db:
            assert len(db.scalars(select(DocumentVersion).where(DocumentVersion.source_endpoint_id==eid)).all())==1
            db.get(SourceEndpoint,eid).scheduled=False

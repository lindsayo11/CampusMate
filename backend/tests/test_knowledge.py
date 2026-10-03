import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.knowledge import DocumentChunk, split_text
from app.main import app
from app.models import Opportunity

TEXT = '本竞赛要求：报名材料包括团队介绍、项目计划书和成员分工。仅限大三报名。截止前需提交完整材料。'


def publish(c, text=TEXT):
    url='https://example.edu/'+str(uuid4())
    payload={'type':'contest','title':'原文检索测试竞赛','organization':'测试单位','summary':'测试摘要',
        'location':'线上','deadline':(datetime.now(UTC)+timedelta(days=7)).isoformat(),
        'source_url':url,'source_label':'测试来源','fetched_at':datetime.now(UTC).isoformat(),'rules':[]}
    first=c.post('/v1/admin/sources/import',json={'raw_text':text,'payload':payload}).json()
    assert c.post(f'/v1/admin/reviews/{first["review_id"]}/approve').status_code==200
    events=c.get('/v1/admin/audit').json()
    event=next(e for e in events if e['resource']==f'review:{first["review_id"]}' and e['action']=='approve')
    oid=json.loads(event['detail'])['opportunity_id']
    return first['document_id'],oid,payload


def test_chunks_preserve_exact_source_offsets():
    text=('第一段竞赛要求与报名材料。'*70+'\n')*10
    chunks=list(split_text(text))
    covered=set()
    for _,start,end,fragment in chunks:
        assert text[start:end]==fragment and len(fragment)<=900
        covered.update(range(start,end))
    assert covered==set(range(len(text)))


def test_review_and_explicit_access_then_revocation():
    with TestClient(app) as c:
        doc,oid,_=publish(c)
        request={'query':'报名材料','opportunity_id':oid}
        assert c.post('/v1/knowledge/search',json=request).json()['items']==[]
        path=f'/v1/admin/knowledge/documents/{doc}/access'
        assert c.put(path,json={'public':True},headers={'X-User-Id':'outsider'}).status_code==403
        assert c.put(path,json={'public':True}).status_code==200
        result=c.post('/v1/knowledge/search',json=request).json()
        assert result['mode']=='lexical' and result['items'][0]['text']==TEXT
        ref=result['items'][0]
        assert c.get('/v1/knowledge/chunks/'+ref['chunk_id']).json()['content_hash']==ref['content_hash']
        assert ref['text']==TEXT[ref['start_offset']:ref['end_offset']]
        assert c.put(path,json={'public':False}).status_code==200
        assert c.get('/v1/knowledge/chunks/'+ref['chunk_id']).status_code==404
        assert c.post('/v1/knowledge/search',json=request).json()['message']=='未找到依据'


def test_stale_unpublished_and_expired_evidence_is_hidden():
    with TestClient(app) as c:
        doc,oid,payload=publish(c)
        c.put(f'/v1/admin/knowledge/documents/{doc}/access',json={'public':True})
        request={'query':'报名材料','opportunity_id':oid}
        assert c.post('/v1/knowledge/search',json=request).json()['items']
        c.post('/v1/admin/sources/import',json={'raw_text':TEXT+'新版本规则尚待审核。','payload':payload})
        assert c.post('/v1/knowledge/search',json=request).json()['items']==[]
        doc2,oid2,_=publish(c)
        c.put(f'/v1/admin/knowledge/documents/{doc2}/access',json={'public':True})
        c.post(f'/v1/admin/opportunities/{oid2}/unpublish')
        assert c.post('/v1/knowledge/search',json={'query':'报名材料','opportunity_id':oid2}).json()['items']==[]
        doc3,oid3,_=publish(c)
        c.put(f'/v1/admin/knowledge/documents/{doc3}/access',json={'public':True})
        with SessionLocal.begin() as db:db.get(Opportunity,oid3).deadline=datetime.now(UTC)-timedelta(days=1)
        assert c.post('/v1/knowledge/search',json={'query':'报名材料','opportunity_id':oid3}).json()['items']==[]


def test_filters_validation_and_agent_citations():
    with TestClient(app) as c:
        doc,oid,_=publish(c)
        c.put(f'/v1/admin/knowledge/documents/{doc}/access',json={'public':True})
        assert c.post('/v1/knowledge/search',json={'query':'报名材料','type':'job','opportunity_id':oid}).json()['items']==[]
        for body in [{'query':' '},{'query':'%%'},{'query':'报名材料','limit':100}]:
            assert c.post('/v1/knowledge/search',json=body).status_code==422
        result=c.post('/v1/agent/chat',json={'query':'报名材料','opportunity_id':oid}).json()
        assert result['references'][0]['document_id']==doc
        assert result['status']=='completed'
        with SessionLocal() as db:
            before=db.query(DocumentChunk).filter_by(document_id=doc).count()
        c.put(f'/v1/admin/knowledge/documents/{doc}/access',json={'public':True})
        with SessionLocal() as db:assert db.query(DocumentChunk).filter_by(document_id=doc).count()==before


def test_long_numeric_query_does_not_match_a_date_fragment():
    with TestClient(app) as c:
        doc, oid, _ = publish(c, text='发布日期：2026-10-02。报名材料包括团队介绍和项目计划书。')
        c.put(f'/v1/admin/knowledge/documents/{doc}/access', json={'public': True})
        result = c.post('/v1/knowledge/search', json={
            'query': '报名材料2026-10-02-123456', 'opportunity_id': oid,
        }).json()
        assert result['items'] == []
        assert result['message'] == '未找到依据'


def test_unreviewed_source_cannot_be_public():
    with TestClient(app) as c:
        _doc,_,payload=publish(c)
        pending=c.post('/v1/admin/sources/import',json={'raw_text':TEXT+'这是未审核的新版本。','payload':payload}).json()
        assert c.put(f'/v1/admin/knowledge/documents/{pending["document_id"]}/access',json={'public':True}).status_code==409

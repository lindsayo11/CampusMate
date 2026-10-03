import base64
from datetime import UTC, datetime, timedelta
from uuid import uuid4
import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.adapters.base import RawArtifact
from app.adapters.education import UniversityNoticeAdapter, classify_path
from app.adapters.notice_text import registration_dates, discover_notices, content_kind
from app.database import SessionLocal
from app.main import app
from app.config import settings
from app.agent_state import PlanReminder
from app.development_agent import deliver_plan_reminders
from app.source_scheduler import ensure_supported_parser
from app.parsers import ParseError


@pytest.mark.parametrize('text,year,start,end',[
 ('报名时间：2026年9月1日10:00-8日10:00',None,'2026-09-01T10:00:00+08:00','2026-09-08T10:00:00+08:00'),
 ('应于9月22日上午08:00前完成报名',2026,None,'2026-09-22T08:00:00+08:00'),
 ('报名截止：2026年9月2日下午2:30',None,None,'2026-09-02T14:30:00+08:00'),
 ('报名时间：2026年12月28日至1月2日',None,'2026-12-28T00:00:00+08:00','2027-01-02T23:59:00+08:00'),
 ('初试日期：2026年12月20日至12月21日。其他安排另行通知',2026,None,None),
 ('报名时间：9月1日至9月2日',None,None,None),
 ('报名截止：2026年2月30日',None,None,None),
])
def test_conservative_registration_dates(text,year,start,end):
    assert registration_dates(text,year)==(start,end)


def test_discovery_rejects_other_hosts_and_login_and_old_year():
    html='''<a href="/2027.html">某大学2027年推免生接收办法</a><a href="https://evil.test/x">某大学2027年推免生接收办法</a><a href="/login">某大学2027年推免登录系统</a><a href="/2026.html">某大学2026年推免生接收办法</a>'''
    assert discover_notices(html,'https://example.edu/notices',2027)==[{'title':'某大学2027年推免生接收办法','url':'https://example.edu/2027.html'}]


def test_faculty_admission_notice_is_an_application_notice():
    assert content_kind('材料学院关于2027年外校免试研究生招生的第1号通知')=='application_notice'


def test_unknown_parser_never_silently_archives_navigation():
    with pytest.raises(ParseError): ensure_supported_parser('MissingNoticeAdapter')


def test_notice_uses_real_article_title_and_never_invents_program_rules():
    html='<h1>招生信息</h1><h3>某大学2027年接收免试攻读研究生办法<span>发布时间：2026-09-15</span></h3><div class="mce-content-body"><p>申请者应先核对学院发布的详细要求，报名时间另行通知，请持续关注官方公告。</p></div>'
    doc=UniversityNoticeAdapter().parse(RawArtifact(html.encode(),'https://example.edu/notice','notice'))
    assert doc.records[0]['title']=='某大学2027年接收免试攻读研究生办法'
    assert classify_path(doc.records[0]['title'])=='recommendation_exemption'
    assert not UniversityNoticeAdapter().extract_rules(doc)
    assert 'deadline_at' not in doc.records[0]


def test_school_notice_import_is_traceable_idempotent_and_searchable():
    uid=str(uuid4())
    html='<h1>清华大学2027年研究生招生申请通知</h1><time>2026-09-30</time><article><p>报名时间：2026年10月15日至10月24日。申请材料以院系公开通知为准，请在报名之前核对院系要求。</p></article>'
    body={'source_code':'CM-GR-004-THU','endpoint_name':'graduate_admission_notices','source_url':'https://yz.tsinghua.edu.cn/notices/'+uid,
        'source_item_id':uid,'adapter_config':{'notice_scope':'university'},'content_base64':base64.b64encode(html.encode()).decode(),'import_mode':'system'}
    with TestClient(app) as client:
        r=client.post('/v1/admin/intake/education-html',json=body)
        assert r.status_code==201,r.text
        assert r.json()['items']==1 and r.json()['rules']==0
        duplicate=client.post('/v1/admin/intake/education-html',json=body)
        assert duplicate.json()['changed'] is False
        items=client.get('/v1/data/catalog',params={'q':'清华大学2027年研究生招生申请通知','school':'清华','year':2027,'kind':'application_notice','status':'all'}).json()['items']
        assert len(items)==1
        item=items[0]
        assert item['document']['publish_time'].startswith('2026-09-29T16:00') # Beijing midnight in UTC.
        proof=client.get('/v1/data/publications/'+item['publication_id']).json()
        assert proof['evidence'] and proof['document']['content_hash']
        correction=client.post('/v1/data/corrections',headers={'X-User-Id':'feedback-owner'},json={
            'publication_id':item['publication_id'],'category':'date','message':'请核对原文中的具体截止时刻'}).json()
        assert correction['status']=='pending'
        assert not client.get('/v1/data/corrections',headers={'X-User-Id':'other-student'}).json()
        url='/v1/admin/data/corrections/'+str(correction['id'])
        assert client.patch(url,headers={'X-User-Id':'feedback-owner'},json={'status':'resolved','note':'本人无法管理'}).status_code==403
        assert client.patch(url,json={'status':'resolved','note':'已核对官方原文，日期保持一致'}).status_code==200
        mine=client.get('/v1/data/corrections',headers={'X-User-Id':'feedback-owner'}).json()
        assert mine[0]['review_note']=='已核对官方原文，日期保持一致'
        assert client.get('/v1/data/publications/'+item['publication_id']).json()['snapshot_hash']==proof['snapshot_hash']
        docid=r.json()['document_version_id']
        from app.knowledge import DocumentChunk, KnowledgeAccess
        with SessionLocal() as db:
            chunkid=db.scalar(select(DocumentChunk.id).where(DocumentChunk.document_id==docid))
        assert client.get('/v1/knowledge/chunks/'+chunkid).status_code==200
        assert client.put('/v1/admin/knowledge/documents/'+docid+'/access',json={'public':False}).status_code==200
        client.post('/v1/admin/intake/education-html',json=body)
        assert client.get('/v1/knowledge/chunks/'+chunkid).status_code==404
        assert client.put('/v1/admin/knowledge/documents/'+docid+'/access',json={'public':True}).status_code==200
        from app.intake_models import DataPublication
        with SessionLocal.begin() as db:
            db.get(DataPublication,item['publication_id']).status='withdrawn'
        assert client.get('/v1/knowledge/chunks/'+chunkid).status_code==404


    from app.sources import SourceDocument
    from app.knowledge import KnowledgePublication
    with SessionLocal() as db:
        doc=db.get(SourceDocument,r.json()['document_version_id'])
        assert doc and doc.raw_text
        assert db.get(KnowledgePublication,doc.id).source=='system'


def test_real_auth_plan_checklist_and_reminder_isolation(monkeypatch):
    # Real mode ignores forged X-User-Id and takes identity only from the provider.
    with TestClient(app) as client:
        monkeypatch.setattr(settings,'demo_mode',False)
        monkeypatch.setattr(settings,'supabase_url','https://identity.example.test')
        monkeypatch.setattr(settings,'supabase_anon_key','test-key')
        monkeypatch.setattr(settings,'admin_user_ids','real-admin')
        def identity(url,headers,timeout):
            token=headers['Authorization'].removeprefix('Bearer ')
            return httpx.Response(200,json={'id':token}) if token in {'student-a','student-b','real-admin'} else httpx.Response(401)
        monkeypatch.setattr('app.auth.httpx.get',identity)
        a={'Authorization':'Bearer student-a','X-User-Id':'real-admin'};b={'Authorization':'Bearer student-b'}
        assert client.get('/v1/plans',headers={'X-User-Id':'student-a'}).status_code==401
        assert client.get('/v1/plans',headers={'Authorization':'Bearer expired'}).status_code==401
        assert client.get('/v1/admin/data/overview',headers=a).status_code==403
        plan=client.post('/v1/plans',headers=a,json={'title':'账号隔离验证 '+str(uuid4())}).json()
        assert plan['user_id']=='student-a'
        base='/v1/plans/'+str(plan['id'])
        step=client.post(base+'/steps',headers=a,json={'title':'核对官方院系要求'}).json()
        assert client.post(base+'/steps',headers=a,json={'title':step['title']}).json()['id']==step['id']
        assert client.get(base+'/steps',headers=b).status_code==404
        assert client.patch(base+'/steps/'+str(step['id']),headers=b,json={'done':True}).status_code==404
        assert client.delete(base+'/steps/'+str(step['id']),headers=b).status_code==404
        assert client.patch(base+'/steps/'+str(step['id']),headers=a,json={'done':True}).json()['done'] is True
        due=datetime.now(UTC)+timedelta(hours=1)
        r=client.post(base+'/reminders',headers=a,json={'due_at':due.isoformat()})
        assert r.status_code==201,r.text
        assert client.post(base+'/reminders',headers=a,json={'due_at':due.isoformat()}).json()['id']==r.json()['id']
        assert client.post(base+'/reminders',headers=b,json={'due_at':due.isoformat()}).status_code==404
        assert client.patch(base,headers=b,json={'title':'tampered'}).status_code==404
        with SessionLocal.begin() as db: db.get(PlanReminder,r.json()['id']).due_at=datetime.now(UTC)-timedelta(seconds=1)
        assert deliver_plan_reminders()>=1
        assert deliver_plan_reminders()==0
        assert not any(x['id']==r.json()['id'] for x in client.get('/v1/development-agent/reminders',headers=b).json())
        owned=client.get('/v1/development-agent/reminders',headers=a).json()
        assert next(x for x in owned if x['id']==r.json()['id'])['status']=='delivered'

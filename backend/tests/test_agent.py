from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4
import httpx
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.database import SessionLocal
from app.models import AgentAction


def test_propose_does_not_write_confirm_is_atomic_and_private():
    owner={'X-User-Id':str(uuid4())}; stranger={'X-User-Id':str(uuid4())}
    with TestClient(app) as c:
        p=c.post('/v1/agent/chat',headers=owner,json={'query':'加入看板','opportunity_id':'job-001'}).json()
        assert p['status']=='confirmation_required' and p['mode']=='rules'
        assert c.get('/v1/tracker/items',headers=owner).json()==[]
        path='/v1/agent/actions/'+p['action_id']+'/confirm'
        assert c.post(path,headers=stranger).status_code==404
        with ThreadPoolExecutor(2) as pool:
            results=list(pool.map(lambda _:c.post(path,headers=owner),range(2)))
        assert all(r.status_code==200 for r in results)
        assert results[0].json()==results[1].json()
        assert len(c.get('/v1/tracker/items',headers=owner).json())==1


def test_cancel_expire_and_invalid_tool_do_not_write(monkeypatch):
    owner={'X-User-Id':str(uuid4())}
    with TestClient(app) as c:
        def proposal():
            return c.post('/v1/agent/chat',headers=owner,json={'query':'设置提醒','opportunity_id':'job-001'}).json()['action_id']
        aid=proposal()
        assert c.post(f'/v1/agent/actions/{aid}/cancel',headers=owner).status_code==200
        assert c.post(f'/v1/agent/actions/{aid}/confirm',headers=owner).status_code==409
        aid=proposal()
        with SessionLocal.begin() as db:
            db.get(AgentAction,aid).expires_at=datetime.now(UTC)-timedelta(minutes=1)
        assert c.post(f'/v1/agent/actions/{aid}/confirm',headers=owner).status_code==409
        assert c.get('/v1/reminders',headers=owner).json()==[]
        monkeypatch.setattr(settings,'dify_api_base','https://dify.test/v1')
        monkeypatch.setattr(settings,'dify_app_key','test-key')
        def malformed(*args,**kwargs):
            return httpx.Response(200,json={'data':{'status':'succeeded','outputs':{'decision':{'tool':'delete_everything','arguments':{}}}}},request=httpx.Request('POST','https://dify.test'))
        monkeypatch.setattr('app.agent.httpx.post',malformed)
        assert c.post('/v1/agent/chat',headers=owner,json={'query':'test'}).status_code==502


def test_dify_adapter_all_six_tools(monkeypatch):
    user={'X-User-Id':str(uuid4())}
    monkeypatch.setattr(settings,'dify_api_base','https://dify.test/v1')
    monkeypatch.setattr(settings,'dify_app_key','test-key')
    decisions=[('opportunity_search',{'type':'job'}),('eligibility_check',{'opportunity_id':'civil-001'}),
               ('team_match',{'skills':['Python']}),('tracker_write',{'opportunity_id':'job-001'}),
               ('deadline_remind',{'opportunity_id':'job-001'}),('message_connect',{'target':'demo-python'})]
    with TestClient(app) as c:
        for tool,args in decisions:
            def response(url,**kwargs):
                assert url=='https://dify.test/v1/workflows/run'
                assert kwargs['json']['response_mode']=='blocking'
                assert kwargs['json']['user']!=user['X-User-Id']
                return httpx.Response(200,json={'data':{'status':'succeeded','outputs':{'decision':{'tool':tool,'arguments':args}}}},request=httpx.Request('POST',url))
            monkeypatch.setattr('app.agent.httpx.post',response)
            reply=c.post('/v1/agent/chat',headers=user,json={'query':'测试请求'})
            assert reply.status_code==200,reply.text
            result=reply.json(); assert result['mode']=='dify'
            if tool in {'tracker_write','deadline_remind','message_connect'}:
                assert result['status']=='confirmation_required'
                executed=c.post('/v1/agent/actions/'+result['action_id']+'/confirm',headers=user)
                assert executed.status_code==200,executed.text
                assert executed.json()['status']=='completed'
            else:
                assert result['status']=='completed'
        assert len(c.get('/v1/reminders',headers=user).json())==1
        assert len(c.get('/v1/rooms',headers=user).json())==1


def test_tracker_state_transition_constraints():
    owner={'X-User-Id':str(uuid4())}
    with TestClient(app) as c:
        path='/v1/tools/tracker_write'
        assert c.post(path,headers=owner,json={'opportunity_id':'job-001','stage':'completed'}).status_code==409
        assert c.post(path,headers=owner,json={'opportunity_id':'job-001','stage':'applied'}).status_code==200
        assert c.post(path,headers=owner,json={'opportunity_id':'job-001','stage':'saved'}).status_code==409
        assert c.post(path,headers=owner,json={'opportunity_id':'job-001','stage':'completed'}).status_code==200

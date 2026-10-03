from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from fastapi import Header
from fastapi.testclient import TestClient
from app.auth import actor_id
from app.config import settings
from app.main import app


def user():
    return {'X-User-Id': str(uuid4())}


def profile(school, enabled=True):
    return {'school': school, 'college':'学院', 'grade':'大三', 'major':'计算机', 'display_name':'测试同学', 'discoverable':enabled, 'skills':['Python'], 'interests':[], 'weekly_hours':8}


def test_real_matching_opt_in_school_block_and_connect(monkeypatch):
    a,b,private,foreign=user(),user(),user(),user()
    school=str(uuid4())
    with TestClient(app) as c:
        for headers,body in [(a,profile(school)),(b,profile(school)),(private,profile(school,False)),(foreign,profile('other'))]:
            assert c.put('/v1/profile',headers=headers,json=body).status_code==200
        monkeypatch.setattr(settings,'demo_mode',False)
        # Test domain permissions with explicit verified-identity test dependency.
        def verified(x_user_id: str = Header()):
            return x_user_id
        app.dependency_overrides[actor_id]=verified
        try:
            result=c.post('/v1/tools/team_match',headers=a,json=['python']).json()
            assert result['demo'] is False
            assert [p['user_id'] for p in result['items']]==[b['X-User-Id']]
            assert result['items'][0]['score']==100
            assert 'major' not in result['items'][0]
            for target in [private,foreign]:
                assert c.post('/v1/tools/message_connect',headers=a,json={'target':target['X-User-Id']}).status_code==422
            path='/v1/tools/message_connect'
            room=c.post(path,headers=a,json={'target':b['X-User-Id']}).json()
            assert c.post(path,headers=b,json={'target':a['X-User-Id']}).json()['id']==room['id']
            c.post('/v1/blocks',headers=b,json={'target':a['X-User-Id']})
            assert c.post('/v1/tools/team_match',headers=a,json=['Python']).json()['items']==[]
            assert c.post(path,headers=a,json={'target':b['X-User-Id']}).status_code==403
        finally:
            app.dependency_overrides.pop(actor_id,None)


def test_team_capacity_concurrent_accept_leave_remove_dissolve():
    owner,a,b,outsider=user(),user(),user(),user()
    with TestClient(app) as c:
        for h in (a,b): c.get('/v1/profile',headers=h)
        team=c.post('/v1/teams',headers=owner,json={'title':'小队','capacity':2}).json()
        base='/v1/teams/'+team['id']
        room='/v1/rooms/'+team['room_id']+'/messages'
        for h in (a,b):
            assert c.post(base+'/invitations',headers=owner,json={'target':h['X-User-Id']}).status_code==200
        def accept(h):
            return c.post('/v1/invitations/'+team['id']+'/decision',headers=h,json={'action':'accept'}).status_code
        with ThreadPoolExecutor(2) as pool:
            statuses=list(pool.map(accept,[a,b]))
        assert sorted(statuses)==[200,409]
        joined=[a,b][statuses.index(200)]
        assert c.post(base+'/leave',headers=owner).status_code==409
        assert c.post(base+'/remove',headers=outsider,json={'target':joined['X-User-Id']}).status_code==404
        assert c.post(base+'/leave',headers=joined).status_code==200
        assert c.get(room,headers=joined).status_code==404
        assert c.post(base+'/invitations',headers=owner,json={'target':joined['X-User-Id']}).status_code==200
        assert accept(joined)==200
        assert c.post(base+'/remove',headers=owner,json={'target':joined['X-User-Id']}).status_code==200
        assert c.post(room,headers=joined,json={'body':'越权'}).status_code==404
        assert c.post(base+'/dissolve',headers=owner).status_code==200
        assert c.get(room,headers=owner).status_code==404
        assert c.post(base+'/invitations',headers=owner,json={'target':joined['X-User-Id']}).status_code==404


def test_message_rate_limit():
    owner=user()
    with TestClient(app) as c:
        team=c.post('/v1/teams',headers=owner,json={'title':'限流测试'}).json()
        room='/v1/rooms/'+team['room_id']+'/messages'
        for n in range(20):
            assert c.post(room,headers=owner,json={'body':str(n)}).status_code==200
        limited=c.post(room,headers=owner,json={'body':'过量'})
        assert limited.status_code==429 and limited.headers['retry-after']=='60'
        assert len(c.get(room,headers=owner).json())==20

from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import app


def test_invitation_membership():
    a={"X-User-Id":str(uuid4())}; b={"X-User-Id":str(uuid4())}; outsider={"X-User-Id":str(uuid4())}
    with TestClient(app) as c:
        c.get("/v1/profile",headers=b)
        team=c.post("/v1/teams",headers=a,json={"title":"比赛组"}).json()
        invite=f"/v1/teams/{team['id']}/invitations"
        assert c.post(invite,headers=outsider,json={"target":b["X-User-Id"]}).status_code==404
        assert c.post(invite,headers=a,json={"target":b["X-User-Id"]}).status_code==200
        room=f"/v1/rooms/{team['room_id']}/messages"
        assert c.get(room,headers=b).status_code==404
        decision=f"/v1/invitations/{team['id']}/decision"
        assert c.post(decision,headers=b,json={"action":"accept"}).status_code==200
        assert c.post(decision,headers=b,json={"action":"accept"}).status_code==409
        assert c.get(room,headers=b).status_code==200
        assert c.post(room,headers=b,json={"body":"已加入"}).status_code==200
        assert len(c.get("/v1/teams",headers=b).json())==1

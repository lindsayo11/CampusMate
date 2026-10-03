from uuid import uuid4

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.social import Message, Room


def fixture():
    room, user = str(uuid4()), str(uuid4())
    with SessionLocal() as db:
        db.add(Room(id=room, title="分页验收", members=[user, "sender"]))
        db.add_all([Message(room_id=room, sender="sender", body=str(i),
                    created_at="2026-09-28T00:00:00+00:00", hidden=i == 120) for i in range(125)])
        db.commit()
    return room, {"X-User-Id": user}


def test_history_pagination_recovery_and_read_cursor():
    with TestClient(app) as c:
        room, h = fixture()
        url = f"/v1/rooms/{room}"
        latest = c.get(url + "/history", headers=h).json()
        assert len(latest["items"]) == 50 and latest["has_more"]
        assert latest["items"][-1]["body"] == "124"
        assert latest["items"][-5]["body"] == "[消息已由管理员移除]"
        previous = c.get(url + f'/history?before={latest["oldest_id"]}', headers=h).json()
        first = c.get(url + f'/history?before={previous["oldest_id"]}', headers=h).json()
        assert len(first["items"]) == 25 and not first["has_more"]
        ids = [m["id"] for p in [first, previous, latest] for m in p["items"]]
        assert ids == sorted(set(ids)) and len(ids) == 125
        catchup = c.get(url + "/history?after=0&limit=100", headers=h).json()
        assert catchup["has_more"]
        rest = c.get(url + f'/history?after={catchup["newest_id"]}', headers=h).json()
        assert len(rest["items"]) == 25 and not rest["has_more"]
        assert c.get("/v1/rooms", headers=h).json()[0]["unread_count"] == 124
        assert c.post(url+"/read", headers=h, json={"message_id": ids[-1]}).status_code == 200
        assert c.post(url+"/read", headers=h, json={"message_id": ids[0]}).json()["last_read_message_id"] == ids[-1]
        assert c.get("/v1/rooms", headers=h).json()[0]["unread_count"] == 0
        assert c.get(url+"/history?before=2&after=1", headers=h).status_code == 422
        assert c.get(url+"/history?limit=101", headers=h).status_code == 422


def test_history_and_reads_enforce_room_membership():
    with TestClient(app) as c:
        room, h = fixture()
        other, _ = fixture()
        foreign_id = c.get(f"/v1/rooms/{room}/history", headers=h).json()["newest_id"]
        url = f"/v1/rooms/{other}"
        assert c.get(url+"/history", headers=h).status_code == 404
        assert c.post(url+"/read", headers=h, json={"message_id": foreign_id}).status_code == 404
        assert c.post(f"/v1/rooms/{room}/read", headers=h, json={"message_id": foreign_id+100000}).status_code == 422
        with SessionLocal() as db:
            r = db.get(Room, room);r.members = ["sender"];db.commit()
        assert c.get(f"/v1/rooms/{room}/history", headers=h).status_code == 404

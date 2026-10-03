from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


def test_social_flow():
    headers = {"X-User-Id": str(uuid4())}
    with TestClient(app) as c:
        matches = c.post("/v1/tools/team_match", json=["Python"]).json()
        assert matches["items"][0]["score"] == 100
        room = c.post(
            "/v1/tools/message_connect", headers=headers, json={"target": "demo-python"}
        ).json()
        again = c.post(
            "/v1/tools/message_connect", headers=headers, json={"target": "demo-python"}
        ).json()
        assert room["id"] == again["id"]
        url = f"/v1/rooms/{room['id']}/messages"
        assert c.get(url, headers={"X-User-Id": "outsider"}).status_code == 404
        assert c.post(url, headers=headers, json={"body": "  "}).status_code == 422
        msg = c.post(url, headers=headers, json={"body": "一起参加比赛"}).json()
        assert c.get(url, headers=headers).json()[0]["body"] == "一起参加比赛"
        assert c.get(url + f"?after={msg['id']}", headers=headers).json() == []
        assert (
            c.post(
                f"/v1/messages/{msg['id']}/report", headers=headers, json={"reason": "测试举报"}
            ).status_code
            == 200
        )
        c.post("/v1/blocks", headers=headers, json={"target": "demo-python"})
        assert c.post(url, headers=headers, json={"body": "blocked"}).status_code == 403

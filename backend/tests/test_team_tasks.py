from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


def setup(c):
    owner, member, stranger = [{"X-User-Id": str(uuid4())} for _ in range(3)]
    team = c.post("/v1/teams", headers=owner, json={"title": "任务验收"}).json()
    c.get("/v1/profile", headers=member)
    base = f'/v1/teams/{team["id"]}'
    c.post(base+"/invitations", headers=owner, json={"target": member["X-User-Id"]})
    c.post(f'/v1/invitations/{team["id"]}/decision', headers=member, json={"action": "accept"})
    return base, owner, member, stranger


def test_task_permissions_dates_and_membership():
    with TestClient(app) as c:
        base, owner, member, stranger = setup(c)
        url = base + "/tasks"
        payload = {"title": "建模初稿", "assignee": member["X-User-Id"], "due_at": "2026-10-01T08:00:00+08:00"}
        assert c.post(url, headers=member, json=payload).status_code == 403
        assert c.get(url, headers=stranger).status_code == 404
        assert c.post(url, headers=owner, json={**payload, "assignee": stranger["X-User-Id"]}).status_code == 422
        assert c.post(url, headers=owner, json={**payload, "title": " "}).status_code == 422
        assert c.post(url, headers=owner, json={**payload, "due_at": "2026-10-01T08:00:00"}).status_code == 422
        task = c.post(url, headers=owner, json=payload).json()
        assert task["due_at"].startswith("2026-10-01T00:00:00")
        path = url + f'/{task["id"]}'
        assert c.put(path, headers=member, json={**payload, "version": 1}).status_code == 403
        assert c.post(path+"/status", headers=member, json={"status": "doing", "version": 1}).status_code == 200
        assert c.put(path, headers=owner, json={**payload, "version": 1}).status_code == 409
        assert c.post(path+"/status", headers=member, json={"status": "cancelled", "version": 2}).status_code == 403
        assert c.post(base+"/leave", headers=member).status_code == 200
        task = c.get(url, headers=owner).json()[0]
        assert task["assignee"] is None and task["version"] == 3
        assert c.get(url, headers=member).status_code == 404
        assert c.post(path+"/status", headers=member, json={"status": "done", "version": 3}).status_code == 404
        c.post(base+"/dissolve", headers=owner)
        assert c.get(url, headers=owner).status_code == 404


def test_concurrent_task_updates_and_cross_team_access():
    with TestClient(app) as c:
        base, owner, member, _ = setup(c)
        task = c.post(base+"/tasks", headers=owner, json={"title": "提交", "assignee": member["X-User-Id"]}).json()
        path = base+f'/tasks/{task["id"]}/status'
        def complete(status):
            return c.post(path, headers=member, json={"status": status, "version": 1}).status_code
        with ThreadPoolExecutor(2) as pool:
            assert sorted(pool.map(complete, ["doing", "done"])) == [200, 409]
        other = c.post("/v1/teams", headers=owner, json={"title": "另一队"}).json()
        assert c.post(f'/v1/teams/{other["id"]}/tasks/{task["id"]}/status', headers=owner,
                      json={"status": "done", "version": 2}).status_code == 404
        assert c.post(path, headers=owner, json={"status": "cancelled", "version": 2}).status_code == 200
        assert c.post(path, headers=member, json={"status": "done", "version": 3}).status_code == 403
        assert c.post(path, headers=owner, json={"status": "todo", "version": 3}).status_code == 200

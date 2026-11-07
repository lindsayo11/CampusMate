"""Local isolated regression tests; synthetic notices never enter the real DB."""
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import pytest
from sqlalchemy import select
from app.config import settings
from app.database import SessionLocal
from app.intake_models import DataPublication
from app.models import UserPlan
from app.social import Block
from test_data_catalog import sample, publish  # noqa: F401

ANSWERS = dict(stage="junior", direction="recommendation_exemption", subject="计算机",
    goal="research", hours=8, experience="project", collaboration="team", horizon="semester")


def headers():
    return {"x-user-id": str(uuid4())}


def create_team(c, d, pid, owner, capacity=2):
    response = c.post("/v1/activity-teams", headers=owner, json={
        "publication_id": pid, "item_id": d["item_id"], "title": "隔离组队测试",
        "capacity": capacity, "description": "不写入演示或线上数据库"})
    assert response.status_code == 200, response.text
    return response.json()


def test_questionnaire_personalization_confirmation_and_validation(sample, monkeypatch):
    c, _ = sample
    monkeypatch.setattr(settings, "deepseek_api_key", "")
    monkeypatch.setattr(settings, "development_dify_app_key", "")
    actor = headers()
    profile_before = c.get("/v1/profile", headers=actor).json()
    reply = c.post("/v1/development-agent/chat", headers=actor,
        json={"query": "请按问卷规划", "intent": "assessment", "assessment": ANSWERS})
    assert reply.status_code == 200, reply.text
    result = reply.json()["result"]
    assert result["focus"] == "保研推免"
    assert result["assessment"]["subject"] == "计算机"
    assert "6 小时" in result["tasks"][1]["steps"][0]
    changed = {**ANSWERS, "direction": "employment", "hours": 20, "collaboration": "solo"}
    alternate = c.post("/v1/development-agent/chat", headers=actor,
        json={"query": "修改方向", "intent": "assessment", "assessment": changed}).json()["result"]
    assert alternate["focus"] == "实习就业"
    assert alternate["tasks"] != result["tasks"]
    assert "15 小时" in alternate["tasks"][1]["steps"][0]
    profile_after = c.get("/v1/profile", headers=actor).json()
    # SQLite reloads timezone-naive datetimes; compare equivalent serialization.
    for profile in (profile_before, profile_after):
        profile["updated_at"] = profile["updated_at"].removesuffix("Z")
    assert profile_after == profile_before
    with SessionLocal() as db:
        assert not db.scalars(select(UserPlan).where(UserPlan.user_id == actor["x-user-id"])).all()
    proposal = c.post("/v1/development-agent/chat", headers=actor,
        json={"query": "根据刚才问卷生成计划", "intent": "plan",
              "conversation_id": reply.json()["conversation_id"]}).json()
    assert proposal["status"] == "confirmation_required"
    assert len(proposal["arguments"]["plans"]) == 3
    assert "计算机" in proposal["arguments"]["plans"][0]["note"]
    with SessionLocal() as db:
        assert not db.scalars(select(UserPlan).where(UserPlan.user_id == actor["x-user-id"])).all()
    action = "/v1/development-agent/actions/" + proposal["action_id"] + "/confirm"
    assert c.post(action, headers=headers(), json={}).status_code == 404
    assert c.post(action, headers=actor, json={}).status_code == 200
    with SessionLocal() as db:
        assert len(db.scalars(select(UserPlan).where(UserPlan.user_id == actor["x-user-id"])).all()) == 3
    assert c.post("/v1/development-agent/chat", headers=actor, json={
        "query": "测试", "intent": "assessment", "assessment": {**ANSWERS, "hours": 999}}).status_code == 422
    assert c.post("/v1/development-agent/chat", headers=actor, json={
        "query": "测试", "intent": "assessment"}).status_code == 422


def test_source_preview_requires_current_publication(sample):
    c, d = sample
    pid = publish(c, d)
    response = c.get(f"/v1/data/publications/{pid}/source")
    assert response.status_code == 200
    assert response.json()["text"] == "Public notice"
    assert response.json()["url"] == d["url"]
    assert "content" not in response.json()
    with SessionLocal.begin() as db:
        db.get(DataPublication, pid).status = "withdrawn"
    assert c.get(f"/v1/data/publications/{pid}/source").status_code == 404
    assert c.get("/v1/data/publications/" + d["did"] + "/source").status_code == 404


def test_directory_join_approval_privacy_and_capacity(sample):
    c, d = sample
    pid = publish(c, d)
    owner, applicant, other = headers(), headers(), headers()
    query = "/v1/activity-teams/directory?q=" + d["item_id"]  # ID isn't searchable title
    assert c.get(query, headers=owner).json()["total"] == 0
    route = f"/v1/activity-teams/activity/{pid}/{d['item_id']}"
    assert c.get(route, headers=applicant).json()["teams"] == []
    team = create_team(c, d, pid, owner)
    shown = c.get(route, headers=applicant).json()["teams"][0]
    assert shown["state"] == "recruiting"
    assert not ({"members", "owner", "room_id", "email"} & shown.keys())
    request = "/v1/activity-teams/" + team["id"] + "/request"
    assert c.post(request, headers=applicant, json={"message": "会 Python"}).json()["status"] == "pending"
    assert c.post(request, headers=applicant, json={}).json()["status"] == "pending"
    private = "/v1/rooms/" + team["room_id"] + "/messages"
    assert c.get(private, headers=applicant).status_code == 404
    requests = c.get("/v1/activity-teams/requests", headers=owner).json()
    assert len(requests) == 1
    decision = "/v1/activity-teams/requests/" + requests[0]["id"] + "/decision"
    assert c.post(decision, headers=other, json={"action": "accept"}).status_code == 404
    assert c.post(decision, headers=owner, json={"action": "accept"}).status_code == 200
    assert c.post(decision, headers=owner, json={"action": "accept"}).status_code == 409
    assert c.get(private, headers=applicant).status_code == 200
    assert c.get(route, headers=applicant).json()["teams"][0]["state"] == "joined"
    assert c.get(route, headers=other).json()["teams"][0]["state"] == "full"
    assert c.post(request, headers=other, json={}).status_code == 409
    assert c.get(private, headers=other).status_code == 404
    assert len(c.get("/v1/teams", headers=applicant).json()) == 1


def test_team_closed_blocked_and_withdrawn(sample):
    c, d = sample
    pid = publish(c, d)
    owner, applicant = headers(), headers()
    team = create_team(c, d, pid, owner, 4)
    base = "/v1/activity-teams/" + team["id"]
    assert c.post(base+"/recruitment", headers=applicant, json={"recruiting": False}).status_code == 404
    assert c.post(base+"/recruitment", headers=owner, json={"recruiting": False}).status_code == 200
    assert c.post(base+"/request", headers=applicant, json={}).status_code == 409
    c.post(base+"/recruitment", headers=owner, json={"recruiting": True})
    with SessionLocal.begin() as db:
        db.add(Block(owner=owner["x-user-id"], target=applicant["x-user-id"]))
    assert c.post(base+"/request", headers=applicant, json={}).status_code == 403
    route = f"/v1/activity-teams/activity/{pid}/{d['item_id']}"
    assert c.get(route, headers=applicant).json()["teams"] == []
    with SessionLocal.begin() as db:
        db.get(DataPublication, pid).status = "withdrawn"
    assert c.get(route, headers=owner).status_code == 404
    assert c.post("/v1/activity-teams", headers=owner, json={
        "publication_id": pid, "item_id": d["item_id"], "title": "不应创建"}).status_code == 404
    # Existing private membership is retained even if the announcement withdraws.
    assert len(c.get("/v1/teams", headers=owner).json()) == 1


def test_concurrent_last_seat_is_not_overfilled(sample):
    c, d = sample
    pid = publish(c, d)
    owner, a, b = headers(), headers(), headers()
    team = create_team(c, d, pid, owner, 2)
    for user in [a,b]:
        assert c.post("/v1/activity-teams/"+team["id"]+"/request", headers=user, json={}).status_code == 200
    requests = c.get("/v1/activity-teams/requests", headers=owner).json()
    def approve(row):
        return c.post("/v1/activity-teams/requests/"+row["id"]+"/decision",
            headers=owner, json={"action":"accept"}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(approve, requests)) == [200,409]
    mine = c.get("/v1/teams", headers=owner).json()
    assert len(mine[0]["members"]) == 2


def test_directory_pagination_and_login_required(sample, monkeypatch):
    c, d = sample
    pid = publish(c, d)
    actor = headers()
    total = c.get("/v1/data/catalog?status=all&limit=1").json()["total"]
    first = c.get("/v1/activity-teams/directory?limit=1", headers=actor).json()
    second = c.get("/v1/activity-teams/directory?limit=1&offset=1", headers=actor).json()
    assert first["total"] == second["total"]
    if total > 1:
        assert first["items"][0]["id"] != second["items"][0]["id"]
    assert c.get("/v1/activity-teams/directory?state=joined", headers=actor).json()["items"] == []
    assert c.post("/v1/activity-teams", headers=actor, json={
        "publication_id":pid, "item_id":"wrong-item", "title":"测试"}).status_code == 404
    assert c.post("/v1/activity-teams", headers=actor, json={
        "publication_id":pid, "item_id":d["item_id"], "title":"  "}).status_code == 422
    monkeypatch.setattr(settings, "demo_mode", False)
    assert c.get("/v1/activity-teams/directory").status_code == 401
    assert c.post("/v1/activity-teams", json={
        "publication_id":pid,"item_id":d["item_id"],"title":"无权创建"}).status_code == 401

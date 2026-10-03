from fastapi.testclient import TestClient
from app.main import app

def test_unknown_and_validation():
    with TestClient(app) as c:
        assert c.post("/v1/tools/eligibility_check",json={"opportunity_id":"job-001"}).json()["eligible"] is None
        assert c.post("/v1/tools/tracker_write",json={"opportunity_id":"job-001","stage":"invented"}).status_code == 422
        assert c.post("/v1/tools/deadline_remind",json={"opportunity_id":"job-001","hours_before":-1}).status_code == 422
        assert c.put("/v1/profile",json={"college":"", "grade":"", "major":"", "weekly_hours":999}).status_code == 422

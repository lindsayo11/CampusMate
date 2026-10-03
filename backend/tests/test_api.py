from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import ReviewItem


def test_health():
    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "ok"


def test_opportunities_and_filter():
    with TestClient(app) as client:
        all_items = client.get("/v1/opportunities").json()
        assert all_items["total"] >= 6
        jobs = client.get("/v1/opportunities", params={"type": "job"}).json()
        assert jobs["total"] >= 1
        assert all(item["type"] == "job" for item in jobs["items"])


def test_missing_opportunity():
    with TestClient(app) as client:
        assert client.get("/v1/opportunities/missing").status_code == 404


def test_profile_eligibility_and_actions():
    with TestClient(app) as client:
        headers = {"X-User-Id": "phase2-test"}
        profile = client.put(
            "/v1/profile",
            headers=headers,
            json={
                "school": "示范大学",
                "college": "计算机学院",
                "grade": "大四",
                "major": "计算机科学与技术",
                "interests": ["AI"],
                "skills": ["Python"],
                "weekly_hours": 10,
            },
        )
        assert profile.status_code == 200
        eligibility = client.post(
            "/v1/tools/eligibility_check", headers=headers, json={"opportunity_id": "civil-001"}
        ).json()
        assert eligibility["eligible"] is True
        assert len(eligibility["results"]) == 2
        tracked = client.post(
            "/v1/tools/tracker_write",
            headers=headers,
            json={"opportunity_id": "job-001", "stage": "preparing", "note": "更新简历"},
        )
        assert tracked.status_code == 200
        assert client.get("/v1/tracker/items", headers=headers).json()[0]["stage"] == "preparing"
        reminder = client.post(
            "/v1/tools/deadline_remind",
            headers=headers,
            json={"opportunity_id": "job-001", "hours_before": 24},
        )
        assert reminder.status_code == 200


def test_review_queue():
    with TestClient(app) as client:
        with SessionLocal() as db:
            db.add(
                ReviewItem(
                    title="测试审核记录",
                    source_url="https://example.edu/test",
                    risk_level="low",
                    confidence=0.8,
                    status="pending",
                    extracted_payload="{}",
                    created_at=datetime.now(UTC),
                )
            )
            db.commit()
        rows = client.get("/v1/admin/reviews").json()
        row = next(item for item in rows if item["title"] == "测试审核记录")
        accepted = client.post(f"/v1/admin/reviews/{row['id']}/approve")
        assert accepted.status_code == 422
        assert client.post(f"/v1/admin/reviews/{row['id']}/reject").json()["status"] == "rejected"

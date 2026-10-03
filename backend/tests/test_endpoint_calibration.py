import json

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.intake_models import SourceBlocker, SourceEndpoint
from app.main import app
from app.source_registry import seed_registry


def test_blocked_endpoint_requires_three_person_calibration_and_seed_preserves_resolution(monkeypatch):
    monkeypatch.setattr(settings, "admin_user_ids", "demo-user,reviewer-1,reviewer-2")
    monkeypatch.setattr(settings, "collector_allowed_hosts", "www.ox.ac.uk")
    exact_url = "https://www.ox.ac.uk/admissions/graduate/courses/calibration-test-only"
    adapter_config = {
        "institution_id": "oxford:ukprn-10007774",
        "program_code": "calibration-test-only",
        "program_name": "Calibration Test Only",
        "path_code": "overseas_masters",
    }
    with TestClient(app) as client:
        source = client.get("/v1/sources/CM-OS-003-OXF").json()
        endpoint = next(row for row in source["endpoints"] if row["name"] == "graduate_program_page")
        endpoint_id = endpoint["id"]

        blocked = client.patch(
            f"/v1/admin/intake/endpoints/{endpoint_id}",
            json={"action": "enable", "reason": "test", "url": exact_url,
                  "adapter_config": adapter_config},
        )
        assert blocked.status_code == 422
        assert "双人校准审核" in blocked.json()["detail"]

        submitted = client.post(
            f"/v1/admin/intake/endpoints/{endpoint_id}/calibrations",
            json={
                "exact_url": exact_url,
                "robots_status": "allowed",
                "terms_status": "permitted",
                "license_status": "permitted",
                "field_mapping": {"title": "h1", "deadline": "table.deadline"},
                "adapter_config": adapter_config,
                "proof": {"robots_url":"https://www.ox.ac.uk/robots.txt", "robots_quote":"unit test only",
                          "terms_url":"https://www.ox.ac.uk/terms", "terms_quote":"unit test only",
                          "license_url":"https://www.ox.ac.uk/license", "license_quote":"unit test only",
                          "page_sha256":"a" * 64},
            },
        )
        assert submitted.status_code == 201, submitted.text
        calibration_id = submitted.json()["id"]
        assert client.patch(
            f"/v1/admin/intake/calibrations/{calibration_id}",
            headers={"x-user-id": "demo-user"},
            json={"action": "approve", "note": "self review"},
        ).status_code == 409

        first = client.patch(
            f"/v1/admin/intake/calibrations/{calibration_id}",
            headers={"x-user-id": "reviewer-1"},
            json={"action": "approve", "note": "first independent review"},
        )
        assert first.status_code == 200 and first.json()["status"] == "pending"
        repeated = client.patch(
            f"/v1/admin/intake/calibrations/{calibration_id}",
            headers={"x-user-id": "reviewer-1"},
            json={"action": "approve", "note": "same reviewer"},
        )
        assert repeated.status_code == 409
        second = client.patch(
            f"/v1/admin/intake/calibrations/{calibration_id}",
            headers={"x-user-id": "reviewer-2"},
            json={"action": "approve", "note": "second independent review"},
        )
        assert second.status_code == 200 and second.json()["status"] == "approved"

        with SessionLocal() as db:
            assert not db.scalar(select(SourceBlocker).where(
                SourceBlocker.endpoint_id == endpoint_id,
                SourceBlocker.status == "open",
                SourceBlocker.blocker_type == "live_access_unverified",
            ))
            seed_registry(db)
            stored = db.get(SourceEndpoint, endpoint_id)
            assert stored.url == exact_url
            assert stored.robots_status == "allowed"
            assert stored.license_status == "permitted"
            assert json.loads(stored.adapter_config) == adapter_config
            assert not db.scalar(select(SourceBlocker).where(
                SourceBlocker.endpoint_id == endpoint_id,
                SourceBlocker.status == "open",
                SourceBlocker.blocker_type == "live_access_unverified",
            ))

        enabled = client.patch(
            f"/v1/admin/intake/endpoints/{endpoint_id}",
            headers={"x-user-id": "reviewer-2"},
            json={"action": "enable", "reason": "approved calibration", "url": exact_url,
                  "adapter_config": {"ignored": "approved record wins"}},
        )
        assert enabled.status_code == 200, enabled.text
        assert enabled.json()["scheduled"] is True
        client.patch(f"/v1/admin/intake/endpoints/{endpoint_id}",
                     json={"action":"pause", "reason":"isolated test cleanup"})

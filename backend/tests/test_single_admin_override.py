"""Local-dev override: single administrator can approve a calibration.

These tests pin the behaviour of `settings.single_admin_overrides`, which is a
LOCAL DEVELOPMENT aid. It relaxes ONLY the identity-separation part of the
anti-collusion control; the evidence (robots/terms/licence proof) requirement
is untouched, and nothing is auto-approved.

The overriding point of this file is to prove the flag is OFF by default, so
that the upstream three-person guarantee still holds unless explicitly opened.
"""
import json

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.intake_models import SourceBlocker, SourceEndpoint
from app.main import app


def _prepare(monkeypatch, allowed_hosts):
    monkeypatch.setattr(settings, "admin_user_ids", "demo-user")
    monkeypatch.setattr(settings, "collector_allowed_hosts", allowed_hosts)


def _submit(client, endpoint_id, exact_url, adapter_config):
    return client.post(
        f"/v1/admin/intake/endpoints/{endpoint_id}/calibrations",
        json={
            "exact_url": exact_url,
            "robots_status": "allowed",
            "terms_status": "permitted",
            "license_status": "permitted",
            "field_mapping": {"title": "h1"},
            "adapter_config": adapter_config,
            "proof": {"robots_url": exact_url.rsplit("/", 1)[0] + "/robots.txt",
                      "robots_quote": "local dev probe",
                      "terms_url": exact_url.rsplit("/", 1)[0] + "/terms",
                      "terms_quote": "local dev probe",
                      "license_url": exact_url.rsplit("/", 1)[0] + "/license",
                      "license_quote": "local dev probe",
                      "page_sha256": "b" * 64},
        },
    )


def test_override_off_by_default_rejects_self_review(monkeypatch):
    """With the flag off (the default), the submitter still cannot self-review."""
    monkeypatch.setattr(settings, "single_admin_overrides", False)
    _prepare(monkeypatch, "www.ox.ac.uk")
    exact_url = "https://www.ox.ac.uk/admissions/graduate/courses/override-off-probe"
    adapter_config = {"institution_id": "oxford:ukprn-10007774",
                      "program_code": "override-off-probe",
                      "program_name": "Override Off Probe",
                      "path_code": "overseas_masters"}
    with TestClient(app) as client:
        source = client.get("/v1/sources/CM-OS-003-OXF").json()
        endpoint_id = next(r for r in source["endpoints"]
                           if r["name"] == "graduate_program_page")["id"]
        submitted = _submit(client, endpoint_id, exact_url, adapter_config)
        assert submitted.status_code == 201, submitted.text
        calibration_id = submitted.json()["id"]
        blocked = client.patch(
            f"/v1/admin/intake/calibrations/{calibration_id}",
            headers={"x-user-id": "demo-user"},
            json={"action": "approve", "note": "self review must fail"},
        )
        assert blocked.status_code == 409, "flag off must keep the separation control"
        assert "提交人不能担任校准审核人" in blocked.json()["detail"]


def test_override_on_allows_single_admin_to_unblock(monkeypatch):
    """With the flag on, one admin can complete submit -> review -> enable."""
    monkeypatch.setattr(settings, "single_admin_overrides", True)
    _prepare(monkeypatch, "www.ox.ac.uk")
    exact_url = "https://www.ox.ac.uk/admissions/graduate/courses/override-on-probe"
    adapter_config = {"institution_id": "oxford:ukprn-10007774",
                      "program_code": "override-on-probe",
                      "program_name": "Override On Probe",
                      "path_code": "overseas_masters"}
    try:
        with TestClient(app) as client:
            source = client.get("/v1/sources/CM-OS-003-OXF").json()
            endpoint_id = next(r for r in source["endpoints"]
                               if r["name"] == "graduate_program_page")["id"]

            # Still blocked before any calibration exists.
            blocked = client.patch(
                f"/v1/admin/intake/endpoints/{endpoint_id}",
                json={"action": "enable", "reason": "probe", "url": exact_url,
                      "adapter_config": adapter_config},
            )
            assert blocked.status_code == 422

            submitted = _submit(client, endpoint_id, exact_url, adapter_config)
            assert submitted.status_code == 201, submitted.text
            calibration_id = submitted.json()["id"]

            # Same single identity now reviews twice - allowed only because the
            # local-dev override is on.
            first = client.patch(
                f"/v1/admin/intake/calibrations/{calibration_id}",
                headers={"x-user-id": "demo-user"},
                json={"action": "approve", "note": "local first"},
            )
            assert first.status_code == 200, first.text
            assert first.json()["status"] == "pending"

            second = client.patch(
                f"/v1/admin/intake/calibrations/{calibration_id}",
                headers={"x-user-id": "demo-user"},
                json={"action": "approve", "note": "local second"},
            )
            assert second.status_code == 200, second.text
            assert second.json()["status"] == "approved"

            # The live_access_unverified blocker must now be resolved.
            with SessionLocal() as db:
                leftover = db.scalar(select(SourceBlocker).where(
                    SourceBlocker.endpoint_id == endpoint_id,
                    SourceBlocker.status == "open",
                    SourceBlocker.blocker_type == "live_access_unverified",
                ))
                assert leftover is None
                stored = db.get(SourceEndpoint, endpoint_id)
                assert stored.url == exact_url
                assert json.loads(stored.adapter_config) == adapter_config

            enabled = client.patch(
                f"/v1/admin/intake/endpoints/{endpoint_id}",
                headers={"x-user-id": "demo-user"},
                json={"action": "enable", "reason": "local override",
                      "url": exact_url, "adapter_config": adapter_config},
            )
            assert enabled.status_code == 200, enabled.text
            assert enabled.json()["scheduled"] is True
            client.patch(f"/v1/admin/intake/endpoints/{endpoint_id}",
                         json={"action": "pause", "reason": "cleanup"})
    finally:
        # Never leak the relaxed control into other tests.
        settings.single_admin_overrides = False

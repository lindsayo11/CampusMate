"""Isolated synthetic database tests, never real production calibration evidence."""
import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.adapters.base import RawArtifact
from app.config import settings
from app.database import SessionLocal
from app.intake import record_document_version
from app.intake_models import (
    DataPublication,
    DevelopmentItem,
    DevelopmentItemPath,
    DocumentArchive,
    Evidence,
    Source,
    SourceBlocker,
    SourceEndpoint,
    SourceEndpointCalibration,
)
from app.main import app
from app.models import EligibilityRule, Path


@pytest.fixture
def sample(monkeypatch):
    monkeypatch.setattr(settings, "admin_user_ids", "demo-user,review-one,review-two")
    with TestClient(app) as client:
        now, suffix = datetime.now(UTC), str(uuid4())
        sid, eid, item_id, proof_id = [str(uuid4()) for _ in range(4)]
        url = "https://example.edu/notice/" + suffix
        content = b"<h1>Public notice</h1><p>Minimum degree: Bachelor</p>"
        with SessionLocal.begin() as db:
            source = Source(id=sid, source_code="UNIT-" + suffix, name="Unit source", publisher="Unit publisher",
                authority_level="A", source_class="government", official=True, jurisdiction_level="national",
                base_url="https://example.edu", verified_at=now, active=True, region_code="CN")
            ep = SourceEndpoint(id=eid, source_id=sid, name="notice", endpoint_type="html", url=url,
                auth_type="none", automation_level="AUTO-2", agent_mode="REVIEW", license_status="permitted",
                robots_status="allowed", adapter_config="{}", active=True, scheduled=False)
            db.add_all([source, ep]); db.flush()
            doc, _ = record_document_version(db, ep, RawArtifact(content, url, "notice"), "Public notice")
            did = doc.id
            db.add(SourceEndpointCalibration(id=str(uuid4()), endpoint_id=eid, exact_url=url,
                robots_status="allowed", terms_status="permitted", license_status="permitted",
                checked_at=now, submitted_by="calibrator", first_reviewed_by="cal-review-a",
                second_reviewed_by="cal-review-b", second_reviewed_at=now, status="approved",
                field_mapping='{"title":"h1"}', adapter_config="{}", created_at=now,
                proof=json.dumps({"robots_url":"https://example.edu/robots.txt","robots_quote":"Unit test",
                    "terms_url":"https://example.edu/terms","terms_quote":"Unit test",
                    "license_url":"https://example.edu/license","license_quote":"Unit test",
                    "page_sha256":hashlib.sha256(content).hexdigest()})))
            db.add(Evidence(id=proof_id, document_version_id=did, source_id=sid, evidence_location="p",
                quote_or_normalized_fact="Minimum degree: Bachelor", extractor="parser",
                review_status="verified", verified_by="rule-reviewer", verified_at=now))
            db.add(DevelopmentItem(id=item_id, title="Published unit " + suffix, item_type="notice",
                cycle_type="policy", cycle_id=item_id, description="Public notice", source_document_id=did,
                start_time=now, deadline=None, location="CN"))
            rule = EligibilityRule(target_type="policy", target_id=item_id, field="degree", operator="equals",
                expected="Bachelor", label="Degree requirement", source_url=url, evidence_id=proof_id,
                review_status="verified", extractor="parser", confidence=1.0, logic_group="all")
            db.add(rule)
            path = db.scalar(select(Path).where(Path.code == "startup_policy"))
            db.add(DevelopmentItemPath(development_item_id=item_id, path_id=path.id))
            db.flush(); rule_id = rule.id
        yield client, {"sid":sid, "eid":eid, "did":did, "item_id":item_id,
                       "rule_id":rule_id, "url":url, "content":content}


def submit(client, data):
    return client.post(f"/v1/admin/data/documents/{data['did']}/submit",
        json={"note":"Unit original verified", "verified_original":True})


def approve(client, pid, actor):
    return client.patch(f"/v1/admin/data/publications/{pid}", headers={"x-user-id":actor},
        json={"action":"approve", "note":"Unit independent review", "verified_original":True})


def publish(client, data):
    response = submit(client, data)
    assert response.status_code == 201, response.text
    pid = response.json()["id"]
    assert approve(client, pid, "review-one").status_code == 200
    response = approve(client, pid, "review-two")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "published"
    return pid


def test_publish_search_evidence_timeline_and_withdraw(sample):
    c, d = sample
    assert d["item_id"] not in {x["id"] for x in c.get("/v1/data/catalog").json()["items"]}
    pid = publish(c, d)
    detail = c.get(f"/v1/data/publications/{pid}").json()
    assert detail["rules"][0]["evidence_id"] == detail["evidence"][0]["id"]
    assert detail["document"]["content_hash"] == hashlib.sha256(d["content"]).hexdigest()
    assert c.get("/v1/data/catalog?path=startup_policy&region=CN&q=" + d["item_id"]).json()["total"] == 0
    assert any(x["item_id"] == d["item_id"] for x in c.get("/v1/data/timeline").json())
    assert c.get(f"/v1/admin/data/documents/{d['did']}/raw").content == d["content"]
    result = c.patch(f"/v1/admin/data/publications/{pid}", json={"action":"withdraw",
        "note":"Remove unit notice", "verified_original":True})
    assert result.status_code == 200
    assert c.get(f"/v1/data/publications/{pid}").status_code == 404


def test_no_self_or_duplicate_reviews(sample):
    c, d = sample
    pid = submit(c, d).json()["id"]
    assert approve(c, pid, "demo-user").status_code == 409
    assert approve(c, pid, "review-one").json()["status"] == "pending"
    assert approve(c, pid, "review-one").status_code == 409
    assert c.get(f"/v1/data/publications/{pid}").status_code == 404
    assert submit(c, d).status_code == 409


@pytest.mark.parametrize("case", ["fixture", "missing_archive", "hash", "pending_rule", "blocker", "calibration"])
def test_publish_fail_closed(sample, case):
    c, d = sample
    with SessionLocal.begin() as db:
        if case == "fixture": db.get(DocumentArchive, d["did"]).is_fixture = True
        elif case == "missing_archive": db.delete(db.get(DocumentArchive, d["did"]))
        elif case == "hash": db.get(DocumentArchive, d["did"]).content = b"tampered"
        elif case == "pending_rule": db.get(EligibilityRule, d["rule_id"]).review_status = "pending"
        elif case == "blocker": db.add(SourceBlocker(id=str(uuid4()), source_id=d["sid"],
            endpoint_id=None, blocker_type="license", status="open", detail="Unit blocker", observed_at=datetime.now(UTC)))
        else:
            cal = db.scalar(select(SourceEndpointCalibration).where(SourceEndpointCalibration.endpoint_id == d["eid"]))
            cal.proof = "{}"
    assert submit(c, d).status_code == 422


def test_new_version_retracts_old_and_retains_original(sample):
    c, d = sample
    pid = publish(c, d)
    with SessionLocal.begin() as db:
        ep = db.get(SourceEndpoint, d["eid"])
        new, changed = record_document_version(db, ep,
            RawArtifact(b"Updated official notice", d["url"], "notice"), "Updated official notice")
        assert changed and new.previous_id == d["did"]
    assert c.get(f"/v1/data/publications/{pid}").status_code == 404
    assert c.get(f"/v1/admin/data/documents/{d['did']}/raw").content == d["content"]
    with SessionLocal() as db:
        assert db.get(DataPublication, pid).status == "superseded"


def test_source_disabled_and_rule_change_hide_publication(sample):
    c, d = sample
    pid = publish(c, d)
    with SessionLocal.begin() as db: db.get(Source, d["sid"]).active = False
    assert c.get(f"/v1/data/publications/{pid}").status_code == 404
    with SessionLocal.begin() as db: db.get(Source, d["sid"]).active = True
    assert c.get(f"/v1/data/publications/{pid}").status_code == 200
    c.patch(f"/v1/admin/intake/rules/{d['rule_id']}", json={"action":"modify","expected":"Master"})
    assert c.get(f"/v1/data/publications/{pid}").status_code == 404


def test_non_admin_and_tampered_review(sample):
    c, d = sample
    headers={"x-user-id":"not-admin"}
    assert c.get("/v1/admin/data/overview", headers=headers).status_code == 403
    assert c.get(f"/v1/admin/data/documents/{d['did']}/raw", headers=headers).status_code == 403
    pid = submit(c, d).json()["id"]
    with SessionLocal.begin() as db: db.get(DevelopmentItem, d["item_id"]).title = "Changed during review"
    assert approve(c, pid, "review-one").status_code == 409


def test_fixture_detection_and_duplicate_archive(sample):
    _c, d = sample
    with SessionLocal.begin() as db:
        ep = db.get(SourceEndpoint, d["eid"])
        same, changed = record_document_version(db, ep, RawArtifact(d["content"],d["url"],"notice"),"Public notice")
        assert not changed and same.id == d["did"]
        doc, _ = record_document_version(db, ep, RawArtifact(b'<main data-fixture="synthetic-offline-test-only">x</main>',d["url"],"fixture"),"x")
        assert db.get(DocumentArchive, doc.id).is_fixture


def test_subscription_is_private_idempotent_and_detects_withdrawal(sample):
    from app.data_catalog import deliver_data_alerts
    c, d = sample
    pid = publish(c, d)
    body = {"publication_id":pid,"item_id":d["item_id"]}
    headers = {"x-user-id":"subscriber"}
    first = c.post("/v1/data/subscriptions",headers=headers,json=body)
    assert first.status_code == 201, first.text
    assert c.post("/v1/data/subscriptions",headers=headers,json=body).json() == first.json()
    assert len(c.get("/v1/plans",headers=headers).json()) >= 1
    subid = first.json()["id"]
    assert not c.get("/v1/data/subscriptions",headers={"x-user-id":"other"}).json()
    assert c.patch(f"/v1/data/subscriptions/{subid}?action=cancel",
        headers={"x-user-id":"other"}).status_code == 404
    assert c.post("/v1/data/subscriptions",headers=headers,
        json={**body,"remind_before_hours":24}).status_code == 422
    c.patch(f"/v1/admin/data/publications/{pid}",json={"action":"withdraw","note":"Unit withdrawal","verified_original":True})
    assert deliver_data_alerts() >= 1
    assert deliver_data_alerts() == 0
    rows = c.get("/v1/data/subscriptions",headers=headers).json()
    assert next(r for r in rows if r["id"] == subid)["status"] == "source_changed"
    assert c.patch(f"/v1/data/subscriptions/{subid}?action=read",headers=headers).status_code == 200
    assert c.patch(f"/v1/data/subscriptions/{subid}?action=cancel",headers=headers).status_code == 200

import base64
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal
from app.intake_models import (ApplicationCycle, DevelopmentItem, DocumentVersion, EntityAlias,
                               Evidence, Institution, Program, RegistryAssertion, Source,
                               SourceBlocker, SourceEndpoint)
from app.main import app
from app.models import EligibilityRule

FIXTURES = Path(__file__).with_name("fixtures")


def stable(kind, *values):
    return str(uuid5(NAMESPACE_URL, "campusmate:" + kind + ":" + ":".join(map(str, values))))


def payload(source_code, endpoint, host, filename, item_id, config=None):
    return {"source_code": source_code, "endpoint_name": endpoint,
            "source_url": f"https://{host}/fixture/{filename}", "source_item_id": item_id,
            "adapter_config": config or {},
            "content_base64": base64.b64encode((FIXTURES / filename).read_bytes()).decode()}


def test_overseas_registry_then_first_party_program_complete_chain():
    registry = payload("CM-OS-007", "public_dataset_fixture", "discoveruni.gov.uk",
                       "discover_uni_oxford_registry.html", "discover-uni-oxford-2026-09")
    institution_id = stable("institution", "GB", "10007774")
    program = payload("CM-OS-003-OXF", "graduate_program_page", "www.ox.ac.uk",
                      "oxford_msc_advanced_computer_science_2027.html", "oxford-msc-acs-2027",
                      {"institution_id": institution_id, "program_code": "TM_MF1",
                       "program_name": "MSc in Advanced Computer Science",
                       "path_code": "overseas_masters", "degree_level": "masters",
                       "study_mode": "full_time"})
    with TestClient(app) as client:
        first = client.post("/v1/admin/intake/overseas-html", json=registry)
        assert first.status_code == 201, first.text
        assert first.json()["institutions"] == first.json()["assertions"] == 1
        second = client.post("/v1/admin/intake/overseas-html", json=program)
        assert second.status_code == 201, second.text
        assert second.json()["programs"] == second.json()["cycles"] == second.json()["items"] == 1
        assert second.json()["rules"] == 7
        duplicate = client.post("/v1/admin/intake/overseas-html", json=program)
        assert duplicate.json()["changed"] is False

    with SessionLocal() as db:
        institution = db.get(Institution, institution_id)
        course = db.scalar(select(Program).where(Program.institution_id == institution_id,
                                                  Program.program_code == "TM_MF1"))
        cycle = db.scalar(select(ApplicationCycle).where(ApplicationCycle.program_id == course.id,
                                                          ApplicationCycle.cycle_year == 2027))
        item = db.scalar(select(DevelopmentItem).where(DevelopmentItem.cycle_id == cycle.id))
        rules = db.scalars(select(EligibilityRule).where(
            EligibilityRule.target_type == "application_cycle",
            EligibilityRule.target_id == cycle.id)).all()
        assertion = db.scalar(select(RegistryAssertion).where(
            RegistryAssertion.entity_id == institution_id))
        aliases = db.scalars(select(EntityAlias).where(EntityAlias.entity_id.in_([
            institution_id, course.id]))).all()
        assert institution.public_status == "registered" and assertion
        assert cycle.requirements_source_type == "university_first_party"
        assert item.materials.startswith('["Three referees"')
        assert {rule.field for rule in rules} == {"deadline_at", "degree", "gpa", "language",
                                                   "gre_gmat", "materials", "application_fee"}
        assert len(aliases) >= 2
        for rule in rules:
            evidence = db.get(Evidence, rule.evidence_id)
            document = db.get(DocumentVersion, evidence.document_version_id)
            assert evidence.evidence_type == "table"
            assert document.content_hash and document.canonical_url.startswith("https://www.ox.ac.uk/")


def test_registry_cannot_publish_application_requirements():
    malicious = b"""<table><tr><th>Institution name</th><th>Country code</th><th>Status</th><th>Deadline</th></tr>
    <tr><td>University of Oxford</td><td>GB</td><td>registered</td><td>2027-01-06</td></tr></table>"""
    body = {"source_code": "CM-OS-007", "endpoint_name": "public_dataset_fixture",
            "source_url": "https://discoveruni.gov.uk/fixture/invalid", "source_item_id": "invalid",
            "adapter_config": {}, "content_base64": base64.b64encode(malicious).decode()}
    with TestClient(app) as client:
        response = client.post("/v1/admin/intake/overseas-html", json=body)
        assert response.status_code == 422


def test_restricted_registry_is_recorded_but_cannot_import():
    with TestClient(app) as client:
        detail = client.get("/v1/sources/CM-OS-010").json()
        endpoint = detail["endpoints"][0]
        assert endpoint["license_status"] == "restricted"
        assert endpoint["manual_takeover"] is True
        queue = client.get("/v1/admin/intake/overseas/review-queue").json()
        assert any(item["blocker_type"] == "commercial_license" for item in queue["blockers"])
        body = {"source_code": "CM-OS-010", "endpoint_name": "institution_download",
                "source_url": "https://www.hochschulkompass.de/fixture/list", "source_item_id": "blocked",
                "adapter_config": {}, "content_base64": base64.b64encode(b"<table></table>").decode()}
        response = client.post("/v1/admin/intake/overseas-html", json=body)
        assert response.status_code == 422


def test_cscse_personal_login_endpoint_never_enters_scheduler():
    with SessionLocal() as db:
        source = db.scalar(select(Source).where(Source.source_code == "CM-OS-001"))
        endpoint = db.scalar(select(SourceEndpoint).where(
            SourceEndpoint.source_id == source.id,
            SourceEndpoint.name == "personal_credential_service"))
        blocker = db.scalar(select(SourceBlocker).where(SourceBlocker.endpoint_id == endpoint.id))
        assert endpoint.auth_type == "login" and endpoint.scheduled is False
        assert endpoint.manual_takeover is True and blocker.blocker_type == "login_required"

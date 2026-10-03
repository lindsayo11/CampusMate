import base64
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal
from app.intake_models import (
    DevelopmentItem,
    DocumentVersion,
    Evidence,
    OpenDataResource,
    PolicyRecord,
    PolicyRelation,
    SourceBlocker,
)
from app.main import app
from app.models import EligibilityRule

FIXTURES = Path(__file__).with_name("fixtures")


def body(source_code, endpoint, url, filename, item_id, config=None):
    return {"source_code": source_code, "endpoint_name": endpoint, "source_url": url,
            "source_item_id": item_id, "adapter_config": config or {},
            "content_base64": base64.b64encode((FIXTURES / filename).read_bytes()).decode()}


def test_national_to_school_policy_chain_has_evidence_and_rules():
    cases = [
        ("CM-ENT-005", "inclusive_finance_policy_fixture", "https://fgk.mof.gov.cn/fixture/policy",
         "mof_inclusive_finance_policy.html", ["CN"]),
        ("CM-ENT-101-GD", "entrepreneurship_policy_fixture", "https://www.gd.gov.cn/fixture/policy",
         "entrepreneurship_province_fixture.html", ["CN", "CN-GD"]),
        ("CM-ENT-102-SZ", "entrepreneurship_policy_fixture", "https://hrss.sz.gov.cn/fixture/policy",
         "entrepreneurship_city_fixture.html", ["CN", "CN-GD", "CN-GD-SZ"]),
        ("CM-ENT-103-NS", "entrepreneurship_policy_fixture", "https://www.szns.gov.cn/fixture/policy",
         "entrepreneurship_county_fixture.html", ["CN", "CN-GD", "CN-GD-SZ", "CN-GD-SZ-NS"]),
        ("CM-ENT-104-SZU", "university_entrepreneurship_fixture", "https://www.szu.edu.cn/fixture/policy",
         "entrepreneurship_school_fixture.html", ["CN", "CN-GD", "CN-GD-SZ", "CN-GD-SZ-NS", "SZU-10590"]),
    ]
    parent = None
    with TestClient(app) as client:
        for index, (source, endpoint, url, filename, jurisdiction) in enumerate(cases):
            config = {"path_code": "startup_policy", "jurisdiction_path": jurisdiction}
            if parent:
                config["parent_policy_ids"] = [parent]
            response = client.post("/v1/admin/intake/entrepreneurship-policy-html", json=body(
                source, endpoint, url, filename, f"m6-fixture-{index}", config))
            assert response.status_code == 201, response.text
            result = response.json()
            assert result["policies"] == result["items"] == 1
            assert result["relations"] == (0 if index == 0 else 1)
            parent = result["policy_id"]
        duplicate = client.post("/v1/admin/intake/entrepreneurship-policy-html", json=body(
            cases[-1][0], cases[-1][1], cases[-1][2], cases[-1][3], "m6-fixture-4",
            {"path_code": "startup_policy", "jurisdiction_path": cases[-1][4]}))
        assert duplicate.json()["changed"] is False
        listed = client.get("/v1/admin/intake/entrepreneurship/policies")
        assert listed.status_code == 200 and len(listed.json()) >= 5

    with SessionLocal() as db:
        policies = db.scalars(select(PolicyRecord).where(
            PolicyRecord.policy_code.like("M6-FIXTURE-%") | (PolicyRecord.policy_code == "财金〔2023〕75号"))).all()
        assert {row.jurisdiction_level for row in policies} >= {"national", "province", "city", "county", "school"}
        assert db.scalar(select(PolicyRelation).where(PolicyRelation.from_policy_id == parent)).evidence_id
        assert db.scalar(select(DevelopmentItem).where(DevelopmentItem.cycle_id == parent))
        rules = db.scalars(select(EligibilityRule).where(EligibilityRule.target_type == "policy",
            EligibilityRule.target_id.in_([policy.id for policy in policies]))).all()
        assert {rule.field for rule in rules} >= {"loan_amount", "loan_duration", "subsidy_ratio", "materials"}
        for rule in rules:
            evidence = db.get(Evidence, rule.evidence_id)
            assert evidence and evidence.evidence_type == "table"
            assert db.get(DocumentVersion, evidence.document_version_id).content_hash


def test_login_and_api_key_sources_never_import():
    login = b'<html><h1>Policy</h1><input type="password"><table><tr><th>Policy code</th><td>X</td></tr></table></html>'
    request = {"source_code": "CM-ENT-005", "endpoint_name": "inclusive_finance_policy_fixture",
               "source_url": "https://fgk.mof.gov.cn/fixture/login", "source_item_id": "login",
               "adapter_config": {"path_code": "startup_policy", "jurisdiction_path": ["CN"]},
               "content_base64": base64.b64encode(login).decode()}
    with TestClient(app) as client:
        assert client.post("/v1/admin/intake/entrepreneurship-policy-html", json=request).status_code == 422
        source = client.get("/v1/sources/CM-ENT-201-BJOD").json()
        endpoint = source["endpoints"][0]
        blocked = {**request, "source_code": "CM-ENT-201-BJOD", "endpoint_name": "open_api_catalog",
                   "source_url": "https://data.beijing.gov.cn/fixture/data"}
        assert client.post("/v1/admin/intake/entrepreneurship-policy-html", json=blocked).status_code in {404, 422}
        assert endpoint["auth_type"] == "api_key" and endpoint["scheduled"] is False
    with SessionLocal() as db:
        resource = db.scalar(select(OpenDataResource))
        blocker = db.get(SourceBlocker, resource.blocker_id)
        assert resource.import_status == "blocked" and blocker.blocker_type == "api_key_required"
        assert not db.scalar(select(DocumentVersion).where(DocumentVersion.source_endpoint_id == resource.endpoint_id))

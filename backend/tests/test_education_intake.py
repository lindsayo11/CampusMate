import base64
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal
from app.intake_models import (
    ApplicationCycle,
    DevelopmentItem,
    DevelopmentItemPath,
    Evidence,
    Institution,
    PolicyRecord,
    Program,
)
from app.main import app
from app.models import EligibilityRule
from app.models import Path as DevelopmentPath

FIXTURES = Path(__file__).with_name("fixtures")


SOURCE_HOSTS = {
    "CM-GR-001": "www.moe.gov.cn",
    "CM-GR-002": "yz.chsi.com.cn",
    "CM-GR-004-THU": "yz.tsinghua.edu.cn",
}


def request_body(source_code, endpoint_name, filename, item_id, config=None):
    return {"source_code": source_code, "endpoint_name": endpoint_name,
            "source_url": f"https://{SOURCE_HOSTS[source_code]}/fixture/{filename}",
            "source_item_id": item_id,
            "adapter_config": config or {},
            "content_base64": base64.b64encode((FIXTURES / filename).read_bytes()).decode()}


def test_yz_catalog_creates_full_traceable_application_chain():
    body = request_body("CM-GR-002", "public_admission_information", "yz_program_catalog.html",
                        "2027-public-program-catalog")
    with TestClient(app) as client:
        response = client.post("/v1/admin/intake/education-html", json=body)
        assert response.status_code == 201, response.text
        result = response.json()
        assert result["programs"] == result["cycles"] == result["items"] == 1
        assert result["rules"] == 3 and result["evidence"] >= 10
        duplicate = client.post("/v1/admin/intake/education-html", json=body).json()
        assert duplicate["changed"] is False

    with SessionLocal() as db:
        institution = db.scalar(select(Institution).where(Institution.official_id == "10003"))
        program = db.scalar(select(Program).where(Program.institution_id == institution.id,
                                                  Program.program_code == "081200"))
        path = db.scalar(select(DevelopmentPath).where(
            DevelopmentPath.code == "domestic_postgraduate_exam"))
        cycle = db.scalar(select(ApplicationCycle).where(ApplicationCycle.program_id == program.id,
                                                          ApplicationCycle.path_id == path.id,
                                                          ApplicationCycle.cycle_year == 2027))
        item = db.scalar(select(DevelopmentItem).where(DevelopmentItem.cycle_id == cycle.id))
        link = db.scalar(select(DevelopmentItemPath).where(
            DevelopmentItemPath.development_item_id == item.id,
            DevelopmentItemPath.path_id == path.id))
        rules = db.scalars(select(EligibilityRule).where(
            EligibilityRule.target_type == "application_cycle",
            EligibilityRule.target_id == cycle.id)).all()
        assert institution.name == "清华大学" and program.name == "计算机科学与技术"
        assert cycle.deadline_at is not None and item.source_document_id == cycle.source_document_id and link
        assert {rule.field for rule in rules} == {"open_at", "deadline_at", "exam_at"}
        assert all(db.get(Evidence, rule.evidence_id) for rule in rules)


def test_university_notice_creates_recommendation_item_and_rules():
    config = {"institution_code": "10003", "institution_name": "清华大学",
              "program_code": "081200-TM", "program_name": "计算机科学与技术推免",
              "path_code": "recommendation_exemption", "cycle_year": 2027,
              "item_type": "recommendation_exemption_notice", "degree_level": "硕士",
              "study_mode": "全日制"}
    body = request_body("CM-GR-004-THU", "graduate_admission_notices",
                        "university_recommendation_notice.html", "thu-2027-recommendation", config)
    with TestClient(app) as client:
        response = client.post("/v1/admin/intake/education-html", json=body)
        assert response.status_code == 201, response.text
        result = response.json()
        assert result["items"] == 1 and result["rules"] == 7 and result["evidence"] == 8
    with SessionLocal() as db:
        item = db.scalar(select(DevelopmentItem).where(
            DevelopmentItem.item_type == "recommendation_exemption_notice"))
        path = db.scalar(select(DevelopmentPath).where(DevelopmentPath.code == "recommendation_exemption"))
        assert item and db.scalar(select(DevelopmentItemPath).where(
            DevelopmentItemPath.development_item_id == item.id,
            DevelopmentItemPath.path_id == path.id))


def test_moe_policy_is_candidate_with_paragraph_evidence():
    body = request_body("CM-GR-001", "graduate_policy", "moe_policy.html", "policy-fixture-2027")
    with TestClient(app) as client:
        response = client.post("/v1/admin/intake/education-html", json=body)
        assert response.status_code == 201, response.text
        assert response.json()["policies"] == 1
    with SessionLocal() as db:
        policy = db.scalar(select(PolicyRecord).where(PolicyRecord.title.contains("招生工作管理规定")))
        evidence = db.scalars(select(Evidence).where(
            Evidence.document_version_id == policy.source_document_id)).all()
        assert policy.status == "candidate" and len(evidence) == 2


def test_login_page_is_rejected_not_parsed():
    login = b"<html><body><form><input type='password'><p>captcha</p></form></body></html>"
    body = {"source_code": "CM-GR-002", "endpoint_name": "public_admission_information",
            "source_url": "https://yz.chsi.com.cn/login", "source_item_id": "forbidden-login",
            "adapter_config": {}, "content_base64": base64.b64encode(login).decode()}
    with TestClient(app) as client:
        response = client.post("/v1/admin/intake/education-html", json=body)
        assert response.status_code == 422
        assert "登录或验证码" in response.json()["detail"]


def test_manual_import_rejects_non_official_host():
    body = request_body("CM-GR-001", "graduate_policy", "moe_policy.html", "wrong-host")
    body["source_url"] = "https://example.edu/policy.html"
    with TestClient(app) as client:
        response = client.post("/v1/admin/intake/education-html", json=body)
        assert response.status_code == 422
        assert "官方来源域名" in response.json()["detail"]

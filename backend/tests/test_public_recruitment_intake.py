import base64
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal
from app.intake_models import (
    DevelopmentItem,
    DevelopmentItemPath,
    Evidence,
    Position,
    RecruitmentCycle,
    Source,
    SourceRegistryCandidate,
)
from app.main import app
from app.models import EligibilityRule
from app.models import Path as DevelopmentPath

FIXTURES = Path(__file__).with_name("fixtures")


def payload(source_code, endpoint_name, filename, item_id, config=None, host="www.mohrss.gov.cn"):
    return {"source_code": source_code, "endpoint_name": endpoint_name,
            "source_url": f"https://{host}/fixture/{filename}", "source_item_id": item_id,
            "adapter_config": config or {},
            "content_base64": base64.b64encode((FIXTURES / filename).read_bytes()).decode()}


def test_public_institution_notice_creates_traceable_positions_and_item():
    config = {"cycle_code": "PI-2027-CENTRAL", "cycle_name": "2027中央事业单位公开招聘",
              "cycle_year": 2027, "path_code": "public_institution_general",
              "location": "全国"}
    body = payload("CM-PI-001", "public_recruitment", "public_institution_recruitment.html",
                   "pi-2027-central", config)
    with TestClient(app) as client:
        response = client.post("/v1/admin/intake/public-recruitment-html", json=body)
        assert response.status_code == 201, response.text
        result = response.json()
        assert result["positions"] == 2 and result["items"] == 1
        assert result["rules"] >= 16 and result["evidence"] >= 25
        assert client.post("/v1/admin/intake/public-recruitment-html", json=body).json()["changed"] is False
    with SessionLocal() as db:
        cycle = db.scalar(select(RecruitmentCycle).where(
            RecruitmentCycle.cycle_code == "PI-2027-CENTRAL"))
        positions = db.scalars(select(Position).where(Position.recruitment_cycle_id == cycle.id)).all()
        item = db.scalar(select(DevelopmentItem).where(DevelopmentItem.cycle_id == cycle.id))
        path = db.scalar(select(DevelopmentPath).where(
            DevelopmentPath.code == "public_institution_general"))
        link = db.scalar(select(DevelopmentItemPath).where(
            DevelopmentItemPath.development_item_id == item.id,
            DevelopmentItemPath.path_id == path.id))
        rules = db.scalars(select(EligibilityRule).where(
            EligibilityRule.target_type == "position",
            EligibilityRule.target_id == positions[0].id)).all()
        assert cycle.deadline_at and len(positions) == 2 and link
        assert all(rule.review_status == "pending" and db.get(Evidence, rule.evidence_id)
                   for rule in rules)


def test_public_job_uses_same_governed_chain_with_employment_path():
    config = {"cycle_code": "PUBLIC-JOBS-2027-01", "cycle_name": "公共招聘岗位样例",
              "cycle_year": 2027, "path_code": "enterprise_employment",
              "item_type": "public_job_listing"}
    body = payload("CM-JOB-002", "public_jobs", "public_institution_recruitment.html",
                   "public-jobs-2027-01", config, host="job.mohrss.gov.cn")
    with TestClient(app) as client:
        response = client.post("/v1/admin/intake/public-recruitment-html", json=body)
        assert response.status_code == 201, response.text
        assert response.json()["positions"] == 2
    with SessionLocal() as db:
        item = db.scalar(select(DevelopmentItem).where(
            DevelopmentItem.item_type == "public_job_listing"))
        path = db.scalar(select(DevelopmentPath).where(DevelopmentPath.code == "enterprise_employment"))
        assert item and db.scalar(select(DevelopmentItemPath).where(
            DevelopmentItemPath.development_item_id == item.id,
            DevelopmentItemPath.path_id == path.id))


def test_regional_directory_creates_reviewable_inactive_source_candidate():
    body = payload("CM-PI-001", "regional_platform_directory",
                   "regional_recruitment_directory.html", "regional-directory-2027")
    with TestClient(app) as client:
        response = client.post("/v1/admin/intake/public-recruitment-html", json=body)
        assert response.status_code == 201, response.text
        assert response.json()["candidates"] == 2
        candidates = client.get("/v1/admin/intake/source-candidates").json()
        candidate = next(row for row in candidates if row["region_code"] == "110000")
        reviewed = client.patch(f"/v1/admin/intake/source-candidates/{candidate['id']}", json={
            "action": "approve", "note": "测试人工核验地方入口",
        })
        assert reviewed.status_code == 200, reviewed.text
    with SessionLocal() as db:
        candidate = db.scalar(select(SourceRegistryCandidate).where(
            SourceRegistryCandidate.region_code == "110000"))
        source = db.scalar(select(Source).where(Source.source_code == candidate.source_code))
        proof = db.get(Evidence, candidate.evidence_id)
        assert candidate.status == "approved" and source and not source.active
        assert proof.verified_by == "demo-user"


def test_public_recruitment_rejects_login_page_and_foreign_host():
    login = b"<html><body><input type='password'><p>captcha</p></body></html>"
    body = {"source_code": "CM-PI-001", "endpoint_name": "public_recruitment",
            "source_url": "https://www.mohrss.gov.cn/login", "source_item_id": "login-page",
            "adapter_config": {"cycle_code": "x", "cycle_name": "x", "cycle_year": 2027,
                               "path_code": "public_institution_general"},
            "content_base64": base64.b64encode(login).decode()}
    with TestClient(app) as client:
        rejected = client.post("/v1/admin/intake/public-recruitment-html", json=body)
        assert rejected.status_code == 422 and "登录或验证码" in rejected.json()["detail"]
        body["source_url"] = "https://example.edu/notice"
        foreign = client.post("/v1/admin/intake/public-recruitment-html", json=body)
        assert foreign.status_code == 422 and "官方来源域名" in foreign.json()["detail"]

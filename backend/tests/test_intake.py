import base64
import io
import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import select

from app.database import SessionLocal
from app.intake_models import DocumentVersion, Evidence, Position, RecruitmentCycle, Source
from app.main import app
from app.models import EligibilityRule

FIXTURE = Path(__file__).with_name("fixtures") / "civil_service_rows.json"


def workbook_bytes(mutator=None):
    records = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if mutator:
        mutator(records)
    book = Workbook()
    sheet = book.active
    sheet.title = "中央机关职位表"
    headers = list(records[0])
    sheet.append(["2027年度考试录用公务员职位表"])
    sheet.append(headers)
    for record in records:
        sheet.append([record.get(header, "") for header in headers])
    output = io.BytesIO()
    book.save(output)
    return output.getvalue()


def payload(content, cycle_code):
    return {
        "source_code": "CM-CS-001", "endpoint_name": "annual_position_workbook",
        "source_url": "https://bm.scs.gov.cn/kl2027/position.xlsx",
        "source_item_id": "2027-national-civil-service-positions",
        "cycle_code": cycle_code, "cycle_name": "2027年度国家公务员招录", "cycle_year": 2027,
        "content_base64": base64.b64encode(content).decode(),
    }


def test_registry_seed_query_and_login_boundary():
    with TestClient(app) as client:
        sources = client.get("/v1/sources", params={"path": "civil_service"}).json()
        assert any(item["source_code"] == "CM-CS-001" for item in sources)
        yz = client.get("/v1/sources/CM-GR-002").json()
        login = next(item for item in yz["endpoints"] if item["endpoint_type"] == "login")
        assert login["automation_level"] == "AUTO-4"
        assert login["agent_mode"] == "USER_ACTION"
        assert login["secret_ref"] is None


def test_civil_workbook_end_to_end_dedup_and_version_change():
    cycle_code = "test-" + str(uuid4())
    original = workbook_bytes()
    with TestClient(app) as client:
        first = client.post("/v1/admin/intake/civil-service-workbook", json=payload(original, cycle_code))
        assert first.status_code == 201, first.text
        first_result = first.json()
        assert first_result["changed"] and first_result["positions"] == 2
        assert first_result["evidence"] >= 20 and first_result["rules"] >= 12

        duplicate = client.post("/v1/admin/intake/civil-service-workbook", json=payload(original, cycle_code)).json()
        assert duplicate["changed"] is False and duplicate["document_version_id"] == first_result["document_version_id"]

        changed_bytes = workbook_bytes(lambda rows: rows[0].update({"招考人数": 3}))
        changed = client.post("/v1/admin/intake/civil-service-workbook", json=payload(changed_bytes, cycle_code)).json()
        assert changed["changed"] and changed["document_version_id"] != first_result["document_version_id"]
        detail = client.get("/v1/admin/intake/documents/" + changed["document_version_id"]).json()
        assert detail["version_no"] == 2 and detail["previous_id"] == first_result["document_version_id"]
        assert '"headcount":2' in detail["diff"] and '"headcount":3' in detail["diff"]

        with SessionLocal() as db:
            cycle = db.scalar(select(RecruitmentCycle).where(RecruitmentCycle.cycle_code == cycle_code))
            position = db.scalar(select(Position).where(Position.recruitment_cycle_id == cycle.id,
                                                        Position.position_code == "TEST1001"))
            rule = db.scalar(select(EligibilityRule).where(EligibilityRule.target_id == position.id,
                                                            EligibilityRule.field == "education")
                             .order_by(EligibilityRule.id.desc()))
            rule_id, evidence_id = rule.id, rule.evidence_id
        approved = client.patch(f"/v1/admin/intake/rules/{rule_id}", json={"action": "approve"})
        assert approved.status_code == 200 and approved.json()["review_status"] == "verified"
        with SessionLocal() as db:
            verified = db.get(Evidence, evidence_id)
            assert verified.verified_by == "demo-user" and verified.verified_at is not None

        health = client.get("/v1/admin/intake/health")
        assert health.status_code == 200
        assert any(item["name"] == "annual_position_workbook" for item in health.json())

    with SessionLocal() as db:
        cycle = db.scalar(select(RecruitmentCycle).where(RecruitmentCycle.cycle_code == cycle_code))
        positions = db.scalars(select(Position).where(Position.recruitment_cycle_id == cycle.id)).all()
        assert len(positions) == 2
        position = next(row for row in positions if row.position_code == "TEST1001")
        assert position.headcount == 3
        rules = db.scalars(select(EligibilityRule).where(EligibilityRule.target_id == position.id)).all()
        assert rules and all(rule.evidence_id for rule in rules)
        evidence = db.get(Evidence, rules[0].evidence_id)
        assert evidence.evidence_location.startswith("sheet=中央机关职位表;cell=")
        document = db.get(DocumentVersion, evidence.document_version_id)
        source = db.get(Source, evidence.source_id)
        assert document.canonical_url.startswith("https://bm.scs.gov.cn/")
        assert source.source_code == "CM-CS-001" and source.authority_level == "A+"


def test_civil_workbook_rejects_formula_in_fact_cell():
    book = Workbook()
    sheet = book.active
    sheet.append(["职位代码", "职位名称", "招考人数", "学历", "专业"])
    sheet.append(["FORMULA", "测试岗", "=1+1", "本科", "计算机"])
    output = io.BytesIO(); book.save(output)
    with TestClient(app) as client:
        response = client.post("/v1/admin/intake/civil-service-workbook",
                               json=payload(output.getvalue(), "formula-" + str(uuid4())))
        assert response.status_code == 422
        assert "公式" in response.json()["detail"]

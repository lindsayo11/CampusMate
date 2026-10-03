"""Admin APIs for deterministic source intake and evidence review."""
import base64
import binascii
import difflib
import json
from datetime import UTC, datetime, timedelta
from typing import Literal
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .adapters.base import RawArtifact
from .auth import require_admin
from .collector_http import FetchError, validate_url
from .config import settings
from .database import get_db
from .governance import audit
from .intake import (
    ingest_civil_service_workbook,
    ingest_education_html,
    ingest_entrepreneurship_policy,
    ingest_overseas_program,
    ingest_overseas_registry,
    ingest_public_recruitment,
)
from .intake_governance import PROOF_KEYS, gate_reason
from .intake_models import (
    ApplicationCycle,
    DocumentVersion,
    Evidence,
    Institution,
    PolicyRecord,
    PolicyRelation,
    Position,
    Program,
    RecruitmentCycle,
    RegistryAssertion,
    Source,
    SourceBlocker,
    SourceChangeReview,
    SourceEndpoint,
    SourceEndpointCalibration,
    SourceEndpointRun,
    SourceRegistryCandidate,
)
from .models import EligibilityRule
from .source_scheduler import enqueue_endpoint, interval_delta

router = APIRouter(prefix="/v1/admin/intake", dependencies=[Depends(require_admin)])


def _belongs_to_official_host(candidate_url: str, official_url: str) -> bool:
    candidate = (urlsplit(candidate_url).hostname or "").lower()
    official = (urlsplit(official_url).hostname or "").lower()
    return bool(candidate and official and (candidate == official or candidate.endswith("." + official)))


def _validate_calibration_url(url: str) -> None:
    """Validate a human-reviewed URL without requiring deployment fetch allowlists."""
    parts = urlsplit(url)
    if (not parts.hostname or parts.username or parts.password
            or parts.fragment or len(url) > 500):
        raise HTTPException(422, "校准 URL 必须是无凭据、无片段的官方页面")
    if parts.scheme == "https":
        if parts.port not in (None, 443):
            raise HTTPException(422, "校准 URL 必须是无凭据、无片段的 HTTPS 官方页面")
        return
    plaintext = {h.strip().lower()
                 for h in settings.collector_allow_plaintext_hosts.split(",") if h.strip()}
    host = parts.hostname.lower()
    if (parts.scheme == "http" and parts.port in (None, 80)
            and (host in plaintext or any(host.endswith("." + item) for item in plaintext))):
        return
    raise HTTPException(422, "校准 URL 必须是无凭据、无片段的 HTTPS 官方页面（明文仅限显式例外主机）")


def _validate_manual_import(source, endpoint, url):
    _validate_calibration_url(url)
    if not _belongs_to_official_host(url, source.base_url):
        raise HTTPException(422, "提交 URL 不属于该官方来源域名")
    tags = set(json.loads(endpoint.access_tags or "[]"))
    if (endpoint.auth_type != "none" or endpoint.agent_mode == "USER_ACTION"
            or endpoint.license_status == "restricted"
            or tags & {"API-AUTH", "LOGIN-USER", "COMMERCIAL", "LICENSE"}):
        raise HTTPException(422, "登录、认证或受限许可证来源不允许导入")


class CivilWorkbookIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source_code: Literal["CM-CS-001"] = "CM-CS-001"
    endpoint_name: str = "annual_position_workbook"
    source_url: HttpUrl
    source_item_id: str = Field(min_length=1, max_length=160)
    cycle_code: str = Field(min_length=1, max_length=100)
    cycle_name: str = Field(min_length=1, max_length=200)
    cycle_year: int = Field(ge=2000, le=2100)
    content_base64: str = Field(max_length=8_000_000)


class EducationHtmlIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source_code: str = Field(min_length=3, max_length=40)
    endpoint_name: str = Field(min_length=1, max_length=120)
    source_url: HttpUrl
    source_item_id: str = Field(min_length=1, max_length=160)
    adapter_config: dict = Field(default_factory=dict)
    content_base64: str = Field(max_length=8_000_000)
    # 这条接口是「把已抓取的官方页面送进治理链路」，通常由采集脚本调用，因此
    # 默认按系统导入处理（入库即自动发布，不走人工审核）。管理员如需按人工
    # 录入处理（走审核），显式传 manual。
    import_mode: Literal["system", "manual"] = "system"


class PublicRecruitmentHtmlIn(EducationHtmlIn):
    pass


class OverseasHtmlIn(EducationHtmlIn):
    pass


class RuleReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    action: Literal["approve", "modify", "reject", "expire"]
    expected: str | None = Field(default=None, max_length=2000)


class SourceStateIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    active: bool
    reason: str = Field(min_length=3, max_length=500)


class EndpointControlIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    action: Literal["enable", "pause", "resume", "takeover"]
    reason: str = Field(min_length=3, max_length=500)
    url: HttpUrl | None = None
    adapter_config: dict = Field(default_factory=dict)


class ChangeReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    action: Literal["approve", "reject", "acknowledge"]
    note: str = Field(default="", max_length=1000)


class CandidateReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    action: Literal["approve", "reject"]
    note: str = Field(default="", max_length=1000)


class OverseasReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    action: Literal["approve", "reject", "expire"]
    note: str = Field(default="", max_length=1000)


class PolicyReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    action: Literal["approve", "reject", "expire"]
    note: str = Field(default="", max_length=1000)


class EndpointCalibrationIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    exact_url: HttpUrl
    robots_status: Literal["allowed", "disallowed", "unknown"]
    terms_status: Literal["permitted", "restricted", "unknown"]
    license_status: Literal["permitted", "restricted", "unknown"]
    field_mapping: dict[str, str] = Field(min_length=1)
    adapter_config: dict = Field(default_factory=dict)
    checked_at: datetime | None = None
    proof: dict[str, str] = Field(default_factory=dict)


class EndpointCalibrationReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    action: Literal["approve", "reject"]
    note: str = Field(default="", max_length=1000)


@router.post("/civil-service-workbook", status_code=201)
def import_civil_workbook(body: CivilWorkbookIn, user: str = Depends(require_admin),
                          db: Session = Depends(get_db)):
    source = db.scalar(select(Source).where(Source.source_code == body.source_code, Source.active.is_(True)))
    if not source:
        raise HTTPException(404, "请先执行 SourceRegistry Seed")
    endpoint = db.scalar(select(SourceEndpoint).where(SourceEndpoint.source_id == source.id,
                                                       SourceEndpoint.name == body.endpoint_name,
                                                       SourceEndpoint.active.is_(True)))
    if not endpoint or endpoint.auth_type != "none" or "FILE" not in endpoint.access_tags:
        raise HTTPException(422, "端点不是允许匿名导入的官方文件端点")
    _validate_manual_import(source, endpoint, str(body.source_url))
    try:
        content = base64.b64decode(body.content_base64, validate=True)
        raw = RawArtifact(content=content, canonical_url=str(body.source_url),
                          source_item_id=body.source_item_id,
                          content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        result = ingest_civil_service_workbook(db, source, endpoint, raw,
                                               body.cycle_code, body.cycle_name, body.cycle_year)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(422, "工作簿解析失败：" + str(exc)) from exc
    audit(db, user, "civil_workbook_import", f"document:{result['document_version_id']}", result)
    db.commit()
    return result


@router.post("/education-html", status_code=201)
def import_education_html(body: EducationHtmlIn, user: str = Depends(require_admin),
                          db: Session = Depends(get_db)):
    source = db.scalar(select(Source).where(Source.source_code == body.source_code, Source.active.is_(True)))
    if not source:
        raise HTTPException(404, "信息源不存在或已停用")
    endpoint = db.scalar(select(SourceEndpoint).where(SourceEndpoint.source_id == source.id,
                                                       SourceEndpoint.name == body.endpoint_name,
                                                       SourceEndpoint.active.is_(True)))
    allowed = {"MoEPolicyAdapter", "YZChsiAdapter", "UniversityNoticeAdapter"}
    if not endpoint or endpoint.parser_type not in allowed or endpoint.auth_type != "none":
        raise HTTPException(422, "端点未配置为允许的公开教育信息 Adapter")
    _validate_manual_import(source, endpoint, str(body.source_url))
    if not _belongs_to_official_host(str(body.source_url), source.base_url):
        raise HTTPException(422, "提交 URL 不属于该官方来源域名")
    try:
        content = base64.b64decode(body.content_base64, validate=True)
        raw = RawArtifact(content=content, canonical_url=str(body.source_url),
                          source_item_id=body.source_item_id,
                          content_type="application/pdf" if content.startswith(b'%PDF') else "text/html")
        # 决定这份文档是否走人工审核：system 走自动发布，manual 进审核队列。
        db.info["import_mode"] = body.import_mode
        result = ingest_education_html(db, source, endpoint, raw, body.adapter_config)
        if body.import_mode == "system":
            from .data_catalog import auto_publish
            document = db.get(DocumentVersion, result["document_version_id"])
            publication = auto_publish(db, document)
            if publication:
                from .source_scheduler import publish_collected_document
                publish_collected_document(db, document)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(422, "教育信息解析失败：" + str(exc)) from exc
    audit(db, user, "education_html_import", f"document:{result['document_version_id']}", result)
    db.commit()
    return result


@router.post("/public-recruitment-html", status_code=201)
def import_public_recruitment_html(body: PublicRecruitmentHtmlIn,
                                   user: str = Depends(require_admin),
                                   db: Session = Depends(get_db)):
    source = db.scalar(select(Source).where(Source.source_code == body.source_code,
                                             Source.active.is_(True)))
    if not source:
        raise HTTPException(404, "信息源不存在或已停用")
    endpoint = db.scalar(select(SourceEndpoint).where(
        SourceEndpoint.source_id == source.id, SourceEndpoint.name == body.endpoint_name,
        SourceEndpoint.active.is_(True)))
    allowed = {"InstitutionRecruitmentAdapter", "MohrssPublicJobAdapter",
               "RegionalRecruitmentDirectoryAdapter"}
    if not endpoint or endpoint.parser_type not in allowed or endpoint.auth_type != "none":
        raise HTTPException(422, "端点未配置为允许的公开招聘 Adapter")
    _validate_manual_import(source, endpoint, str(body.source_url))
    if not _belongs_to_official_host(str(body.source_url), source.base_url):
        raise HTTPException(422, "提交 URL 不属于该官方来源域名")
    try:
        content = base64.b64decode(body.content_base64, validate=True)
        raw = RawArtifact(content=content, canonical_url=str(body.source_url),
                          source_item_id=body.source_item_id, content_type="text/html")
        result = ingest_public_recruitment(db, source, endpoint, raw, body.adapter_config)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(422, "公开招聘信息解析失败：" + str(exc)) from exc
    audit(db, user, "public_recruitment_import", f"document:{result['document_version_id']}", result)
    db.commit()
    return result


@router.post("/overseas-html", status_code=201)
def import_overseas_html(body: OverseasHtmlIn, user: str = Depends(require_admin),
                         db: Session = Depends(get_db)):
    source = db.scalar(select(Source).where(Source.source_code == body.source_code,
                                             Source.active.is_(True)))
    if not source:
        raise HTTPException(404, "境外信息源不存在或已停用")
    endpoint = db.scalar(select(SourceEndpoint).where(
        SourceEndpoint.source_id == source.id, SourceEndpoint.name == body.endpoint_name,
        SourceEndpoint.active.is_(True)))
    allowed = {"OverseasRegistryAdapter", "OverseasUniversityProgramAdapter"}
    if not endpoint or endpoint.parser_type not in allowed or endpoint.auth_type != "none":
        raise HTTPException(422, "端点不是允许匿名导入的境外官方来源")
    _validate_manual_import(source, endpoint, str(body.source_url))
    tags = set(json.loads(endpoint.access_tags or "[]"))
    if tags & {"LOGIN-USER", "COMMERCIAL", "LICENSE"} or endpoint.license_status == "restricted":
        raise HTTPException(422, "登录、商业或许可证受限来源只登记状态，不导入生产数据")
    if not _belongs_to_official_host(str(body.source_url), source.base_url):
        raise HTTPException(422, "提交 URL 不属于该官方来源域名")
    try:
        raw = RawArtifact(content=base64.b64decode(body.content_base64, validate=True),
                          canonical_url=str(body.source_url), source_item_id=body.source_item_id,
                          content_type="text/html")
        result = (ingest_overseas_registry(db, source, endpoint, raw, body.adapter_config)
                  if endpoint.parser_type == "OverseasRegistryAdapter"
                  else ingest_overseas_program(db, source, endpoint, raw, body.adapter_config))
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(422, "境外升学信息解析失败：" + str(exc)) from exc
    audit(db, user, "overseas_html_import", f"document:{result['document_version_id']}", result)
    db.commit()
    return result


@router.post("/entrepreneurship-policy-html", status_code=201)
def import_entrepreneurship_policy(body: EducationHtmlIn, user: str = Depends(require_admin),
                                   db: Session = Depends(get_db)):
    source = db.scalar(select(Source).where(Source.source_code == body.source_code,
                                             Source.active.is_(True)))
    endpoint = db.scalar(select(SourceEndpoint).where(
        SourceEndpoint.source_id == source.id, SourceEndpoint.name == body.endpoint_name,
        SourceEndpoint.active.is_(True))) if source else None
    if not source or not endpoint or endpoint.parser_type != "GovernmentPolicyAdapter":
        raise HTTPException(404, "创业政策来源或端点不存在")
    _validate_manual_import(source, endpoint, str(body.source_url))
    tags = set(json.loads(endpoint.access_tags or "[]"))
    if endpoint.auth_type != "none" or tags & {"API-AUTH", "LOGIN-USER", "COMMERCIAL", "LICENSE"}:
        raise HTTPException(422, "认证、登录、商业或许可证受限来源仅登记元数据与 Blocker")
    if endpoint.license_status == "restricted" or not _belongs_to_official_host(str(body.source_url), source.base_url):
        raise HTTPException(422, "来源许可证受限或 URL 不属于官方域名")
    try:
        raw = RawArtifact(content=base64.b64decode(body.content_base64, validate=True),
                          canonical_url=str(body.source_url), source_item_id=body.source_item_id,
                          content_type="text/html")
        result = ingest_entrepreneurship_policy(db, source, endpoint, raw, body.adapter_config)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(422, "创业政策解析失败：" + str(exc)) from exc
    audit(db, user, "entrepreneurship_policy_import", f"document:{result['document_version_id']}", result)
    db.commit()
    return result


@router.get("/entrepreneurship/policies")
def entrepreneurship_policies(review_status: str | None = None,
                              limit: int = Query(300, ge=1, le=500), db: Session = Depends(get_db)):
    stmt = select(PolicyRecord).where(PolicyRecord.policy_type == "entrepreneurship")
    if review_status:
        stmt = stmt.where(PolicyRecord.review_status == review_status)
    rows = db.scalars(stmt.order_by(PolicyRecord.jurisdiction_level, PolicyRecord.title).limit(limit)).all()
    result = []
    for policy in rows:
        rules = db.scalars(select(EligibilityRule).where(
            EligibilityRule.target_type == "policy", EligibilityRule.target_id == policy.id)).all()
        relations = db.scalars(select(PolicyRelation).where(
            PolicyRelation.from_policy_id == policy.id)).all()
        result.append({"policy": {c.name: getattr(policy, c.name) for c in policy.__table__.columns},
                       "rules": [{c.name: getattr(rule, c.name) for c in rule.__table__.columns} for rule in rules],
                       "relations": [{c.name: getattr(row, c.name) for c in row.__table__.columns}
                                     for row in relations]})
    return result


@router.get("/entrepreneurship/review-queue")
def entrepreneurship_review_queue(db: Session = Depends(get_db)):
    blockers = db.scalars(select(SourceBlocker).join(Source, Source.id == SourceBlocker.source_id).where(
        SourceBlocker.status == "open", Source.supported_paths.contains("entrepreneurship"))
        .order_by(SourceBlocker.observed_at.desc())).all()
    return {"blockers": blockers}


@router.patch("/entrepreneurship/policies/{policy_id}/review")
def review_entrepreneurship_policy(policy_id: str, body: PolicyReviewIn,
                                   user: str = Depends(require_admin), db: Session = Depends(get_db)):
    policy = db.get(PolicyRecord, policy_id)
    if not policy or policy.policy_type != "entrepreneurship":
        raise HTTPException(404, "创业政策不存在")
    policy.review_status = {"approve": "verified", "reject": "rejected", "expire": "expired"}[body.action]
    audit(db, user, f"entrepreneurship_policy_{body.action}", f"policy:{policy_id}", {"note": body.note})
    db.commit()
    return {"id": policy.id, "review_status": policy.review_status}


@router.get("/overseas/institutions")
def overseas_institutions(review_status: str | None = None,
                          limit: int = Query(200, ge=1, le=500), db: Session = Depends(get_db)):
    stmt = select(Institution).where(Institution.country_code != "CN")
    if review_status:
        stmt = stmt.where(Institution.review_status == review_status)
    institutions = db.scalars(stmt.order_by(Institution.country_code, Institution.name).limit(limit)).all()
    result = []
    for institution in institutions:
        programs = db.scalars(select(Program).where(Program.institution_id == institution.id)
                              .order_by(Program.name)).all()
        result.append({"institution": {c.name: getattr(institution, c.name)
                                       for c in institution.__table__.columns},
                       "programs": [{c.name: getattr(program, c.name)
                                     for c in program.__table__.columns} for program in programs]})
    return result


@router.get("/overseas/cycles")
def overseas_cycles(review_status: str | None = None, limit: int = Query(200, ge=1, le=500),
                    db: Session = Depends(get_db)):
    stmt = select(ApplicationCycle).where(
        ApplicationCycle.requirements_source_type == "university_first_party")
    if review_status:
        stmt = stmt.where(ApplicationCycle.review_status == review_status)
    cycles = db.scalars(stmt.order_by(ApplicationCycle.cycle_year.desc()).limit(limit)).all()
    result = []
    for cycle in cycles:
        program = db.get(Program, cycle.program_id)
        institution = db.get(Institution, program.institution_id) if program else None
        rules = db.scalars(select(EligibilityRule).where(
            EligibilityRule.target_type == "application_cycle",
            EligibilityRule.target_id == cycle.id)).all()
        result.append({"cycle": {c.name: getattr(cycle, c.name) for c in cycle.__table__.columns},
                       "program": None if not program else {c.name: getattr(program, c.name)
                                                            for c in program.__table__.columns},
                       "institution": None if not institution else {
                           c.name: getattr(institution, c.name) for c in institution.__table__.columns},
                       "rules": [{c.name: getattr(rule, c.name) for c in rule.__table__.columns}
                                 for rule in rules]})
    return result


@router.get("/overseas/review-queue")
def overseas_review_queue(db: Session = Depends(get_db)):
    assertions = db.scalars(select(RegistryAssertion).where(
        RegistryAssertion.review_status == "pending")).all()
    blockers = db.scalars(select(SourceBlocker).where(SourceBlocker.status == "open")
                          .order_by(SourceBlocker.observed_at.desc())).all()
    return {"registry_assertions": assertions, "blockers": blockers}


@router.patch("/overseas/{entity_type}/{entity_id}/review")
def review_overseas_entity(entity_type: Literal["institution", "program", "cycle", "assertion"],
                           entity_id: str, body: OverseasReviewIn,
                           user: str = Depends(require_admin), db: Session = Depends(get_db)):
    model = {"institution": Institution, "program": Program, "cycle": ApplicationCycle,
             "assertion": RegistryAssertion}[entity_type]
    row = db.get(model, entity_id)
    if not row:
        raise HTTPException(404, "境外升学审核对象不存在")
    if not hasattr(row, "review_status"):
        raise HTTPException(422, "该对象不支持审核状态")
    row.review_status = {"approve": "verified", "reject": "rejected", "expire": "expired"}[body.action]
    audit(db, user, f"overseas_{entity_type}_{body.action}", f"{entity_type}:{entity_id}",
          {"note": body.note})
    db.commit()
    return {"id": entity_id, "review_status": row.review_status}


@router.get("/cycles/{cycle_id}/positions")
def cycle_positions(cycle_id: str, db: Session = Depends(get_db)):
    cycle = db.get(RecruitmentCycle, cycle_id)
    if not cycle:
        raise HTTPException(404, "招录周期不存在")
    rows = db.scalars(select(Position).where(Position.recruitment_cycle_id == cycle_id)
                      .order_by(Position.position_code).limit(1000)).all()
    return [{c.name: getattr(row, c.name) for c in row.__table__.columns} for row in rows]


@router.get("/positions/{position_id}/evidence")
def position_evidence(position_id: str, db: Session = Depends(get_db)):
    position = db.get(Position, position_id)
    if not position:
        raise HTTPException(404, "岗位不存在")
    rules = db.scalars(select(EligibilityRule).where(EligibilityRule.target_type == "position",
                                                      EligibilityRule.target_id == position_id)).all()
    result = []
    for rule in rules:
        evidence = db.get(Evidence, rule.evidence_id) if rule.evidence_id else None
        document = db.get(DocumentVersion, evidence.document_version_id) if evidence else None
        result.append({"field": rule.field, "operator": rule.operator, "value": rule.expected,
                       "extractor": rule.extractor, "confidence": rule.confidence,
                       "review_status": rule.review_status,
                       "evidence": None if not evidence else {
                           "id": evidence.id, "location": evidence.evidence_location,
                           "fact": evidence.quote_or_normalized_fact,
                           "document_version_id": evidence.document_version_id,
                           "official_url": document.canonical_url if document else None}})
    return {"position": {c.name: getattr(position, c.name) for c in position.__table__.columns}, "rules": result}


@router.get("/documents/{document_id}")
def document_detail(document_id: str, db: Session = Depends(get_db)):
    document = db.get(DocumentVersion, document_id)
    if not document:
        raise HTTPException(404, "文档版本不存在")
    previous = db.get(DocumentVersion, document.previous_id) if document.previous_id else None
    diff = "".join(difflib.unified_diff((previous.raw_text if previous else "").splitlines(True),
                                        document.raw_text.splitlines(True), fromfile="previous", tofile="current"))
    return {**{c.name: getattr(document, c.name) for c in document.__table__.columns}, "diff": diff}


@router.patch("/rules/{rule_id}")
def review_rule(rule_id: int, body: RuleReviewIn, user: str = Depends(require_admin),
                db: Session = Depends(get_db)):
    rule = db.get(EligibilityRule, rule_id)
    if not rule or rule.target_type not in {"position", "application_cycle", "recruitment_cycle", "policy"}:
        raise HTTPException(404, "资格规则不存在")
    if body.action == "modify":
        if not body.expected:
            raise HTTPException(422, "修改规则必须提供新值")
        rule.expected = body.expected
        rule.label = f"人工修正：{rule.field}: {body.expected}"
        rule.extractor = "human"
        rule.confidence = 1.0
        rule.review_status = "verified"
    elif body.action == "approve":
        rule.review_status, rule.confidence = "verified", 1.0
    elif body.action == "reject":
        rule.review_status = "rejected"
    else:
        rule.review_status = "expired"
    evidence = db.get(Evidence, rule.evidence_id) if rule.evidence_id else None
    if evidence and body.action in {"approve", "modify"}:
        evidence.review_status = "verified"
        evidence.verified_by, evidence.verified_at = user, datetime.now(UTC)
    if evidence:
        from .intake_models import DataPublication
        db.execute(update(DataPublication).where(
            DataPublication.document_id == evidence.document_version_id,
            DataPublication.status.in_(["pending", "published"]),
        ).values(status="withdrawn", updated_at=datetime.now(UTC), note="规则审核改变，需重新提交发布"))
    audit(db, user, f"intake_rule_{body.action}", f"eligibility_rule:{rule.id}",
          {"target_type": rule.target_type, "target_id": rule.target_id})
    db.commit()
    return {"id": rule.id, "review_status": rule.review_status, "expected": rule.expected,
            "extractor": rule.extractor, "verified_at": evidence.verified_at if evidence else None}


@router.patch("/sources/{source_code}")
def set_source_state(source_code: str, body: SourceStateIn, user: str = Depends(require_admin),
                     db: Session = Depends(get_db)):
    source = db.scalar(select(Source).where(Source.source_code == source_code))
    if not source:
        raise HTTPException(404, "信息源不存在")
    source.active = body.active
    audit(db, user, "source_activate" if body.active else "source_deactivate", f"source:{source_code}",
          {"reason": body.reason})
    db.commit()
    return {"source_code": source.source_code, "active": source.active}


@router.get("/health")
def source_health(db: Session = Depends(get_db)):
    now = datetime.now(UTC)
    endpoints = db.scalars(select(SourceEndpoint).order_by(SourceEndpoint.consecutive_failures.desc(),
                                                            SourceEndpoint.name)).all()
    result = []
    for ep in endpoints:
        blocker_count = db.scalar(select(func.count()).select_from(SourceBlocker).where(
            SourceBlocker.endpoint_id == ep.id, SourceBlocker.status == "open")) or 0
        calibration = db.scalar(select(SourceEndpointCalibration).where(
            SourceEndpointCalibration.endpoint_id == ep.id).order_by(
            SourceEndpointCalibration.created_at.desc()))
        result.append({"id": ep.id, "source_id": ep.source_id, "name": ep.name, "url": ep.url,
             "active": ep.active, "last_success_at": ep.last_success_at,
             "last_attempt_at": ep.last_attempt_at, "next_run_at": ep.next_run_at,
             "scheduled": ep.scheduled, "manual_takeover": ep.manual_takeover,
             "paused_reason": ep.paused_reason, "last_error": ep.last_error,
             "auth_type": ep.auth_type, "automation_level": ep.automation_level,
             "license_status": ep.license_status, "license_note": ep.license_note,
             "agent_mode": ep.agent_mode, "fetch_interval": ep.fetch_interval,
             "parser_type": ep.parser_type, "access_tags": json.loads(ep.access_tags or "[]"),
             "open_blockers": blocker_count,
             "calibration_status": calibration.status if calibration else None,
             "calibration_id": calibration.id if calibration else None,
             "gate_reason": gate_reason(db, ep, automated=True),
             "consecutive_failures": ep.consecutive_failures,
             "status": "disabled" if not ep.active else (
                 "failed" if ep.consecutive_failures >= 3 else
                 "stale" if ep.last_success_at is None or
                 (ep.last_success_at.replace(tzinfo=UTC) if ep.last_success_at.tzinfo is None else ep.last_success_at)
                 < now - timedelta(days=30) else "healthy")})
    return result


@router.patch("/endpoints/{endpoint_id}")
def control_endpoint(endpoint_id: str, body: EndpointControlIn, user: str = Depends(require_admin),
                     db: Session = Depends(get_db)):
    endpoint = db.get(SourceEndpoint, endpoint_id)
    if not endpoint:
        raise HTTPException(404, "端点不存在")
    if body.action in {"enable", "resume"}:
        source = db.get(Source, endpoint.source_id)
        if not source or not source.active:
            raise HTTPException(422, "端点所属来源不存在或已停用")
        if endpoint.auth_type != "none" or endpoint.automation_level not in {"AUTO-1", "AUTO-2"}:
            raise HTTPException(422, "仅允许无认证的 AUTO-1/AUTO-2 端点进入后台调度")
        tags = set(json.loads(endpoint.access_tags or "[]"))
        if (tags & {"LOGIN-USER", "COMMERCIAL", "LICENSE"} or
                endpoint.agent_mode == "USER_ACTION" or endpoint.license_status == "restricted"):
            raise HTTPException(422, "登录、商业授权、许可证受限或用户操作端点不得自动调度")
        if body.url is not None and not _belongs_to_official_host(str(body.url), source.base_url):
            raise HTTPException(422, "端点 URL 不属于该来源的官方域名")
        blocking = db.scalar(select(SourceBlocker).where(
            SourceBlocker.endpoint_id == endpoint.id,
            SourceBlocker.status == "open",
            SourceBlocker.blocker_type.in_({"live_access_unverified", "exact_url_pending"}),
        ))
        calibration = db.scalar(select(SourceEndpointCalibration).where(
            SourceEndpointCalibration.endpoint_id == endpoint.id,
            SourceEndpointCalibration.status == "approved",
        ).order_by(SourceEndpointCalibration.second_reviewed_at.desc()))
        if blocking and not calibration:
            raise HTTPException(422, "该端点仍有线上校准阻塞，必须先完成双人校准审核")
        if calibration:
            if body.url is not None and str(body.url) != calibration.exact_url:
                raise HTTPException(422, "启用 URL 必须与已批准校准记录一致")
            endpoint.url = calibration.exact_url
            body.adapter_config = json.loads(calibration.adapter_config)
        if body.url is not None:
            endpoint.url = str(body.url)
        if not _belongs_to_official_host(endpoint.url, source.base_url):
            raise HTTPException(422, "端点 URL 不属于该来源的官方域名")
        try:
            validate_url(endpoint.url)
            delta = interval_delta(endpoint.fetch_interval)
        except (FetchError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from exc
        if delta is None:
            raise HTTPException(422, "刷新周期为 manual，不能启用自动调度")
        if endpoint.parser_type == "CivilServiceWorkbookAdapter":
            required = {"cycle_code", "cycle_name", "cycle_year"}
            if not required.issubset(body.adapter_config):
                raise HTTPException(422, "公务员工作簿端点必须配置 cycle_code、cycle_name、cycle_year")
        if endpoint.parser_type == "UniversityNoticeAdapter" and body.adapter_config.get('notice_scope') != 'university':
            required = {"institution_code", "institution_name", "program_code", "program_name",
                        "path_code", "cycle_year"}
            if not required.issubset(body.adapter_config):
                raise HTTPException(422, "高校通知端点必须配置学校、专业、路径和招生年度")
        if endpoint.parser_type in {"InstitutionRecruitmentAdapter", "MohrssPublicJobAdapter"}:
            required = {"cycle_code", "cycle_name", "cycle_year", "path_code"}
            if not required.issubset(body.adapter_config):
                raise HTTPException(422, "公开招聘端点必须配置周期、年度和发展路径")
        if endpoint.parser_type == "OverseasUniversityProgramAdapter":
            required = {"institution_id", "program_code", "program_name", "path_code"}
            if not required.issubset(body.adapter_config):
                raise HTTPException(422, "境外大学项目端点必须配置院校、项目和发展路径")
        if endpoint.parser_type == "GovernmentPolicyAdapter":
            required = {"path_code", "jurisdiction_path"}
            if not required.issubset(body.adapter_config):
                raise HTTPException(422, "创业政策端点必须配置发展路径和辖区链")
        endpoint.adapter_config = json.dumps(body.adapter_config, ensure_ascii=False, separators=(",", ":"))
        endpoint.manual_takeover = False
        reason = gate_reason(db, endpoint, automated=True)
        if reason:
            raise HTTPException(422, reason)
        endpoint.scheduled, endpoint.manual_takeover = True, False
        endpoint.paused_reason, endpoint.last_error = "", ""
        endpoint.next_run_at = datetime.now(UTC)
    elif body.action == "pause":
        endpoint.scheduled, endpoint.next_run_at = False, None
        endpoint.paused_reason = body.reason
    else:
        endpoint.scheduled, endpoint.manual_takeover, endpoint.next_run_at = False, True, None
        endpoint.paused_reason = body.reason
    audit(db, user, f"source_endpoint_{body.action}", f"endpoint:{endpoint.id}",
          {"reason": body.reason})
    db.commit()
    return {"id": endpoint.id, "scheduled": endpoint.scheduled,
            "manual_takeover": endpoint.manual_takeover, "next_run_at": endpoint.next_run_at,
            "paused_reason": endpoint.paused_reason}


@router.post("/endpoints/{endpoint_id}/calibrations", status_code=201)
def submit_endpoint_calibration(endpoint_id: str, body: EndpointCalibrationIn,
                                user: str = Depends(require_admin), db: Session = Depends(get_db)):
    endpoint = db.get(SourceEndpoint, endpoint_id)
    if not endpoint:
        raise HTTPException(404, "端点不存在")
    source = db.get(Source, endpoint.source_id)
    exact_url = str(body.exact_url)
    if not source or not _belongs_to_official_host(exact_url, source.base_url):
        raise HTTPException(422, "校准 URL 不属于该来源的官方域名")
    _validate_calibration_url(exact_url)
    now = datetime.now(UTC)
    if body.checked_at and (body.checked_at.tzinfo is None or body.checked_at > now):
        raise HTTPException(422, "校准时间必须带时区且不能在未来")
    if any(not k.strip() or not v.strip() for k, v in body.field_mapping.items()):
        raise HTTPException(422, "字段映射不得为空")
    if body.proof:
        import re
        if (not PROOF_KEYS.issubset(body.proof) or
                not all(body.proof[k].strip() for k in PROOF_KEYS) or
                not re.fullmatch(r"[a-fA-F0-9]{64}", body.proof.get("page_sha256", ""))):
            raise HTTPException(422, "需要 robots、条款、许可证 URL/原文摘录及页面 SHA256")
        for key in ("robots_url", "terms_url", "license_url"):
            _validate_calibration_url(body.proof[key])
    row = SourceEndpointCalibration(
        id=str(uuid4()), endpoint_id=endpoint.id, exact_url=exact_url,
        robots_status=body.robots_status, terms_status=body.terms_status,
        license_status=body.license_status,
        field_mapping=json.dumps(body.field_mapping, ensure_ascii=False, separators=(",", ":")),
        adapter_config=json.dumps(body.adapter_config, ensure_ascii=False, separators=(",", ":")),
        checked_at=body.checked_at or datetime.now(UTC), submitted_by=user,
        status="pending", created_at=datetime.now(UTC),
        proof=json.dumps(body.proof, ensure_ascii=False),
    )
    db.add(row)
    audit(db, user, "source_endpoint_calibration_submit", f"endpoint_calibration:{row.id}",
          {"endpoint_id": endpoint.id, "exact_url": exact_url})
    db.commit()
    return row


@router.get("/calibrations")
def endpoint_calibrations(status: str | None = None, endpoint_id: str | None = None,
                          limit: int = Query(100, ge=1, le=200), db: Session = Depends(get_db)):
    stmt = select(SourceEndpointCalibration)
    if status:
        stmt = stmt.where(SourceEndpointCalibration.status == status)
    if endpoint_id:
        stmt = stmt.where(SourceEndpointCalibration.endpoint_id == endpoint_id)
    rows = db.scalars(stmt.order_by(SourceEndpointCalibration.created_at.desc()).limit(limit)).all()
    return [{**{column.name: getattr(row, column.name) for column in row.__table__.columns},
             "field_mapping": json.loads(row.field_mapping),
             "adapter_config": json.loads(row.adapter_config)} for row in rows]


@router.patch("/calibrations/{calibration_id}")
def review_endpoint_calibration(calibration_id: str, body: EndpointCalibrationReviewIn,
                                user: str = Depends(require_admin), db: Session = Depends(get_db)):
    row = db.get(SourceEndpointCalibration, calibration_id)
    if not row:
        raise HTTPException(404, "校准记录不存在")
    if row.status != "pending":
        raise HTTPException(409, "校准记录已经处理")
    # Compare-and-swap prevents concurrent reviewers overwriting a prior decision.
    locked = db.execute(update(SourceEndpointCalibration).where(
        SourceEndpointCalibration.id == row.id,
        SourceEndpointCalibration.status == "pending",
        SourceEndpointCalibration.first_reviewed_by == row.first_reviewed_by,
    ).values(review_note=row.review_note).execution_options(synchronize_session=False))
    if not locked.rowcount:
        raise HTTPException(409, "审核状态已变化，请刷新")
    now = datetime.now(UTC)
    if body.action == "reject":
        row.status, row.review_note = "rejected", body.note
    elif not (row.robots_status == "allowed" and row.terms_status == "permitted" and
              row.license_status == "permitted"):
        raise HTTPException(422, "robots、条款和许可证均明确允许后才能批准")
    elif not PROOF_KEYS.issubset(json.loads(row.proof or "{}")):
        raise HTTPException(422, "校准缺少原始依据，请重新提交完整证据")
    elif row.first_reviewed_by is None:
        # LOCAL-DEV OVERRIDE: when single_admin_overrides is on, the submitter may
        # also review, so one operator can unblock endpoints. Evidence checks above
        # still apply. Never enable this on a shared or production deployment.
        if row.submitted_by == user and not settings.single_admin_overrides:
            raise HTTPException(409, "提交人不能担任校准审核人")
        row.first_reviewed_by, row.first_reviewed_at = user, now
        row.review_note = body.note
    else:
        if user in {row.submitted_by, row.first_reviewed_by} and not settings.single_admin_overrides:
            raise HTTPException(409, "第二审核人必须与提交人、第一审核人不同")
        endpoint = db.get(SourceEndpoint, row.endpoint_id)
        if not endpoint:
            raise HTTPException(409, "端点已不存在")
        row.second_reviewed_by, row.second_reviewed_at = user, now
        row.status = "approved"
        row.review_note = "\n".join(value for value in (row.review_note, body.note) if value)
        endpoint.url = row.exact_url
        endpoint.robots_status = row.robots_status
        endpoint.license_status = row.license_status
        endpoint.adapter_config = row.adapter_config
        blockers = db.scalars(select(SourceBlocker).where(
            SourceBlocker.endpoint_id == endpoint.id,
            SourceBlocker.status == "open",
            SourceBlocker.blocker_type.in_({"live_access_unverified", "exact_url_pending"}),
        )).all()
        for blocker in blockers:
            blocker.status, blocker.resolved_at = "resolved", now
    audit(db, user, f"source_endpoint_calibration_{body.action}",
          f"endpoint_calibration:{row.id}", {"note": body.note, "status": row.status})
    db.commit()
    return row


@router.post("/endpoints/{endpoint_id}/run", status_code=201)
def run_endpoint(endpoint_id: str, user: str = Depends(require_admin), db: Session = Depends(get_db)):
    try:
        run = enqueue_endpoint(db, endpoint_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    audit(db, user, "source_endpoint_enqueue", f"endpoint_run:{run.id}")
    db.commit()
    return run


@router.get("/runs")
def endpoint_runs(status: str | None = None, limit: int = Query(100, ge=1, le=200),
                  db: Session = Depends(get_db)):
    stmt = select(SourceEndpointRun)
    if status:
        stmt = stmt.where(SourceEndpointRun.status == status)
    return db.scalars(stmt.order_by(SourceEndpointRun.created_at.desc()).limit(limit)).all()


@router.get("/change-reviews")
def change_reviews(status: str = "pending", limit: int = Query(100, ge=1, le=200),
                   db: Session = Depends(get_db)):
    return db.scalars(select(SourceChangeReview).where(SourceChangeReview.status == status)
                      .order_by(SourceChangeReview.created_at.desc()).limit(limit)).all()


@router.patch("/change-reviews/{review_id}")
def review_source_change(review_id: int, body: ChangeReviewIn, user: str = Depends(require_admin),
                         db: Session = Depends(get_db)):
    review = db.get(SourceChangeReview, review_id)
    if not review:
        raise HTTPException(404, "变化审核记录不存在")
    if review.status != "pending":
        raise HTTPException(409, "变化审核已经处理")
    review.status = {"approve": "approved", "reject": "rejected",
                     "acknowledge": "acknowledged"}[body.action]
    review.reviewed_by, review.reviewed_at = user, datetime.now(UTC)
    audit(db, user, f"source_change_{body.action}", f"source_change_review:{review.id}",
          {"note": body.note, "document_version_id": review.document_version_id})
    db.commit()
    return review


@router.get("/source-candidates")
def source_candidates(status: str = "pending", limit: int = Query(100, ge=1, le=200),
                      db: Session = Depends(get_db)):
    return db.scalars(select(SourceRegistryCandidate).where(
        SourceRegistryCandidate.status == status).order_by(
        SourceRegistryCandidate.created_at.desc()).limit(limit)).all()


@router.patch("/source-candidates/{candidate_id}")
def review_source_candidate(candidate_id: str, body: CandidateReviewIn,
                            user: str = Depends(require_admin), db: Session = Depends(get_db)):
    candidate = db.get(SourceRegistryCandidate, candidate_id)
    if not candidate:
        raise HTTPException(404, "来源候选不存在")
    if candidate.status != "pending":
        raise HTTPException(409, "来源候选已经处理")
    now = datetime.now(UTC)
    if body.action == "approve":
        if db.scalar(select(Source).where(Source.source_code == candidate.source_code)):
            raise HTTPException(409, "该来源编码已经存在，请人工合并")
        source = Source(
            id=str(uuid4()), source_code=candidate.source_code, name=candidate.name,
            publisher=candidate.name, authority_level=candidate.authority_level,
            source_class="government", official=True, jurisdiction_level="province",
            region_code=candidate.region_code, supported_paths='["public_institution"]',
            supported_item_types='["recruitment_cycle","position"]',
            base_url=candidate.base_url, active=False, verified_at=now,
        )
        endpoint = SourceEndpoint(
            id=str(uuid4()), source_id=source.id, name="public_recruitment",
            endpoint_type="html", url=candidate.base_url, access_tags='["DIRECT","FILE"]',
            auth_type="none", format="html", parser_type="InstitutionRecruitmentAdapter",
            automation_level="AUTO-3", agent_mode="EXTRACT",
            license_note="目录发现来源；启用前须复核精确栏目、robots 和条款",
            fetch_interval="12h", active=True, scheduled=False,
        )
        db.add_all([source, endpoint])
        proof = db.get(Evidence, candidate.evidence_id)
        if proof:
            proof.verified_by, proof.verified_at = user, now
        candidate.status = "approved"
    else:
        candidate.status = "rejected"
    candidate.reviewed_by, candidate.reviewed_at = user, now
    audit(db, user, f"source_candidate_{body.action}", f"source_candidate:{candidate.id}",
          {"note": body.note, "source_code": candidate.source_code})
    db.commit()
    return candidate

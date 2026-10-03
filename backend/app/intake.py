"""Versioning, evidence persistence and deterministic workbook ingestion."""
import hashlib
import json
from datetime import UTC, datetime
from urllib.parse import urljoin
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .adapters.base import RawArtifact
from .adapters.civil_service import CivilServiceWorkbookAdapter
from .adapters.education import (MoEPolicyAdapter, UniversityNoticeAdapter, YZChsiAdapter,
                                   classify_path)
from .adapters.entrepreneurship import GovernmentPolicyAdapter
from .adapters.overseas import OverseasRegistryAdapter, OverseasUniversityProgramAdapter
from .adapters.public_recruitment import (
    InstitutionRecruitmentAdapter,
    MohrssPublicJobAdapter,
    RegionalRecruitmentDirectoryAdapter,
)
from .intake_models import (
    ApplicationCycle,
    DataPublication,
    DevelopmentItem,
    DevelopmentItemPath,
    DocumentArchive,
    DocumentVersion,
    EntityAlias,
    Evidence,
    Institution,
    PolicyRecord,
    PolicyRelation,
    Position,
    Program,
    RecruitmentCycle,
    RegistryAssertion,
    Source,
    SourceEndpoint,
    SourceRegistryCandidate,
)
from .models import EligibilityRule
from .models import Path as DevelopmentPath


def record_document_version(db: Session, endpoint: SourceEndpoint, raw: RawArtifact,
                            raw_text: str, fetched_at: datetime | None = None):
    now = fetched_at or datetime.now(UTC)
    digest = hashlib.sha256(raw.content).hexdigest()
    latest = db.scalar(select(DocumentVersion).where(
        DocumentVersion.source_endpoint_id == endpoint.id,
        DocumentVersion.source_item_id == raw.source_item_id,
    ).order_by(DocumentVersion.version_no.desc()).limit(1))
    if latest and latest.content_hash == digest:
        if not db.get(DocumentArchive, latest.id):
            db.add(DocumentArchive(document_id=latest.id, content=raw.content,
                                   content_type=raw.content_type, is_fixture=_fixture(raw)))
        latest.last_seen_at = now
        endpoint.last_success_at, endpoint.consecutive_failures = now, 0
        db.flush()
        return latest, False
    version_no = (latest.version_no + 1) if latest else 1
    document = DocumentVersion(
        import_mode=db.info.get('import_mode', 'manual'),
        id=str(uuid4()), source_endpoint_id=endpoint.id, canonical_url=raw.canonical_url,
        source_item_id=raw.source_item_id, last_modified=raw.last_modified, etag=raw.etag,
        content_hash=digest, attachment_hash=digest, first_seen_at=latest.first_seen_at if latest else now,
        last_seen_at=now, last_changed_at=now, version_no=version_no, fetched_at=now,
        raw_text=raw_text, previous_id=latest.id if latest else None,
    )
    db.add(document)
    db.add(DocumentArchive(document_id=document.id, content=raw.content,
                           content_type=raw.content_type, is_fixture=_fixture(raw)))
    if latest:
        old_ids = select(DocumentVersion.id).where(
            DocumentVersion.source_endpoint_id == endpoint.id,
            DocumentVersion.source_item_id == raw.source_item_id)
        db.execute(update(DataPublication).where(DataPublication.document_id.in_(old_ids),
            DataPublication.status.in_(["pending", "published"])).values(
                status="superseded", updated_at=now, note="来源产生新版本，必须重新审核"))
    endpoint.last_success_at, endpoint.consecutive_failures = now, 0
    db.flush()
    return document, True


def _fixture(raw):
    markers = (b"synthetic-offline", b"data-fixture", b"test-only", b"M6-FIXTURE")
    return "fixture" in raw.canonical_url.lower() or any(m in raw.content for m in markers)


def _position_id(cycle_id: str, code: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"campusmate:position:{cycle_id}:{code}"))


def _stable(kind: str, *values) -> str:
    return str(uuid5(NAMESPACE_URL, "campusmate:" + kind + ":" + ":".join(map(str, values))))


def _date(value: str | None):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"日期必须为 ISO 8601 格式：{value}") from exc
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _persist_evidence(db, source: Source, document: DocumentVersion, items):
    result = {}
    for item in items:
        row = Evidence(id=str(uuid4()), document_version_id=document.id, source_id=source.id,
                       evidence_location=item["evidence_location"],
                       quote_or_normalized_fact=item["quote_or_normalized_fact"],
                       extractor=item.get("extractor", "parser"),
                       evidence_type=item.get("evidence_type", "dom"), review_status="pending")
        db.add(row)
        result[(item["record_key"], item["field"])] = row
    db.flush()
    return result


def ingest_civil_service_workbook(db: Session, source: Source, endpoint: SourceEndpoint,
                                  raw: RawArtifact, cycle_code: str, cycle_name: str, cycle_year: int):
    adapter = CivilServiceWorkbookAdapter()
    parsed = adapter.parse(raw)
    raw_text = json.dumps(adapter.normalize(parsed), ensure_ascii=False, separators=(",", ":"))
    document, changed = record_document_version(db, endpoint, raw, raw_text)
    if not changed:
        return {"changed": False, "document_version_id": document.id, "positions": 0, "rules": 0, "evidence": 0}

    cycle_id = str(uuid5(NAMESPACE_URL, f"campusmate:cycle:{source.id}:{cycle_code}"))
    cycle = db.get(RecruitmentCycle, cycle_id)
    if not cycle:
        cycle = RecruitmentCycle(id=cycle_id, source_id=source.id, cycle_code=cycle_code,
                                 name=cycle_name, cycle_year=cycle_year, status="draft",
                                 source_document_id=document.id)
        db.add(cycle)
    else:
        cycle.name, cycle.cycle_year, cycle.source_document_id = cycle_name, cycle_year, document.id

    path = _ensure_path(db, "national_civil_service")
    item_id = _stable("development-item", cycle_id, "civil-service-positions")
    item = db.get(DevelopmentItem, item_id)
    item_values = {"title": cycle_name, "item_type": "civil_service_positions",
                   "cycle_type": "recruitment_cycle", "cycle_id": cycle_id,
                   "description": "官方职位表；报名日期未从职位表推断", "location": source.region_code or "",
                   "materials": "[]", "status": "draft", "source_document_id": document.id}
    if item:
        for key, value in item_values.items():
            setattr(item, key, value)
    else:
        db.add(DevelopmentItem(id=item_id, **item_values))
    if not db.scalar(select(DevelopmentItemPath).where(
            DevelopmentItemPath.development_item_id == item_id, DevelopmentItemPath.path_id == path.id)):
        db.add(DevelopmentItemPath(development_item_id=item_id, path_id=path.id))

    evidence_by_key = {}
    for item in parsed.evidence:
        evidence = Evidence(id=str(uuid4()), document_version_id=document.id, source_id=source.id,
                            evidence_location=item["evidence_location"],
                            quote_or_normalized_fact=item["quote_or_normalized_fact"], extractor="parser",
                            evidence_type="table")
        db.add(evidence)
        evidence_by_key[(item["record_key"], item["field"])] = evidence
    db.flush()

    positions = 0
    for values in adapter.normalize(parsed):
        pid = _position_id(cycle_id, values["position_code"])
        position = db.get(Position, pid)
        payload = {key: values.get(key, "") for key in (
            "position_code", "department", "organization", "title", "headcount", "education", "degree",
            "majors", "political_status", "grassroots_years", "fresh_graduate", "work_region", "remarks")}
        if position:
            for key, value in payload.items():
                setattr(position, key, value)
            position.source_document_id = document.id
        else:
            db.add(Position(id=pid, recruitment_cycle_id=cycle_id, source_document_id=document.id, **payload))
        positions += 1

    rule_count = 0
    for rule in adapter.extract_rules(parsed):
        pid = _position_id(cycle_id, rule["record_key"])
        evidence = evidence_by_key[(rule["record_key"], rule["field"])]
        existing = db.scalar(select(EligibilityRule).where(
            EligibilityRule.target_type == "position", EligibilityRule.target_id == pid,
            EligibilityRule.field == rule["field"], EligibilityRule.evidence_id == evidence.id))
        if not existing:
            db.add(EligibilityRule(opportunity_id=None, target_type="position", target_id=pid,
                                   field=rule["field"], operator=rule["operator"], expected=rule["expected"],
                                   label=rule["description"], source_url=raw.canonical_url,
                                   evidence=rule["evidence"]["quote_or_normalized_fact"], evidence_id=evidence.id,
                                   confidence=rule["confidence"], review_status=rule["review_status"],
                                   extractor=rule["extractor"], logic_group="all"))
            rule_count += 1
    db.flush()
    return {"changed": True, "document_version_id": document.id, "positions": positions,
            "rules": rule_count, "evidence": len(parsed.evidence)}


def _parse_date(value) -> datetime | None:
    """把适配器给出的 ``YYYY-MM-DD`` 字符串解析成 datetime。

    政策没有报名截止日，但正文有成文日期与报名窗口。学生端时间线只渲染带日期的
    条目，不落这些字段，采集到的政策在库里存在却不会出现在时间线上。
    """
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).replace(tzinfo=UTC)
    except ValueError:
        return None


def ingest_moe_policy(db: Session, source: Source, endpoint: SourceEndpoint, raw: RawArtifact,
                      config: dict):
    adapter = MoEPolicyAdapter()
    parsed = adapter.parse(raw)
    raw_text = json.dumps(adapter.normalize(parsed), ensure_ascii=False, separators=(",", ":"))
    document, changed = record_document_version(db, endpoint, raw, raw_text)
    if not changed:
        return {"changed": False, "document_version_id": document.id, "policies": 0, "evidence": 0}
    _persist_evidence(db, source, document, parsed.evidence)
    values = parsed.records[0]
    document.publish_time = _date(parsed.metadata.get('publish_time'))
    issued = _parse_date(values.get("issued_at"))
    # 报名窗口优先：它才是学生真正需要的时间节点；没有则退回成文日期。
    start = _parse_date(values.get("registration_start")) or issued
    deadline = _parse_date(values.get("registration_deadline"))
    policy_id = _stable("policy", source.id, raw.source_item_id)
    policy = db.get(PolicyRecord, policy_id)
    payload = {"title": values["title"], "jurisdiction_level": source.jurisdiction_level,
               "region_code": source.region_code, "effective_at": issued,
               "expires_at": None, "policy_type": "education", "status": "candidate",
               "source_document_id": document.id}
    if policy:
        for key, value in payload.items():
            setattr(policy, key, value)
    else:
        db.add(PolicyRecord(id=policy_id, **payload))
    item_id = _stable("development-item", policy_id, "education-policy")
    item = db.get(DevelopmentItem, item_id)
    item_values = {"title": values["title"], "item_type": "education_policy",
        "cycle_type":"policy", "cycle_id":policy_id, "description":values["body"],
        "location": source.region_code or "", "source_document_id":document.id, "status":"draft",
        # 落到 start_time / deadline，学生端时间线才有条目可渲染。
        "start_time": start, "deadline": deadline}
    if item:
        for key, value in item_values.items():
            setattr(item, key, value)
    else:
        db.add(DevelopmentItem(id=item_id, **item_values))
    # 发展频道的六个入口各自按自己的 path code 过滤，且 path_codes() 只向下找子孙，
    # 所以条目必须挂到**叶子路径**。以前硬编码父路径 domestic_study，结果六个频道全空。
    # 优先用调用方显式指定的 path_code，否则按内容分类；都匹配不到就不挂路径
    # （仍会出现在信息中心"全部事项"里，只是不属于任何频道）。
    path_code = config.get("path_code") or classify_path(values["title"], values["body"])
    if path_code:
        path = _ensure_path(db, path_code)
        if not db.scalar(select(DevelopmentItemPath).where(
                DevelopmentItemPath.development_item_id == item_id,
                DevelopmentItemPath.path_id == path.id)):
            db.add(DevelopmentItemPath(development_item_id=item_id, path_id=path.id))
    db.flush()
    return {"changed": True, "document_version_id": document.id, "policies": 1,
            "evidence": len(parsed.evidence)}


def ingest_entrepreneurship_policy(db: Session, source: Source, endpoint: SourceEndpoint,
                                   raw: RawArtifact, config: dict):
    """Persist a public policy, its application item, rules and evidenced parent relations."""
    if source.jurisdiction_level not in {"national", "province", "city", "county", "school"}:
        raise ValueError("创业政策来源必须声明 national/province/city/county/school 层级")
    adapter = GovernmentPolicyAdapter()
    parsed = adapter.parse(raw)
    raw_text = json.dumps(adapter.normalize(parsed), ensure_ascii=False, separators=(",", ":"))
    document, changed = record_document_version(db, endpoint, raw, raw_text)
    if not changed:
        return {"changed": False, "document_version_id": document.id, "policies": 0,
                "relations": 0, "items": 0, "rules": 0, "evidence": 0}
    proof = _persist_evidence(db, source, document, parsed.evidence)
    values = parsed.records[0]
    policy_id = _stable("policy", source.id, values["policy_code"])
    path_codes = config.get("jurisdiction_path") or ([source.region_code] if source.region_code else [])
    policy_payload = {
        "policy_code": values["policy_code"], "title": values["title"],
        "publisher": values["publisher"], "policy_type": config.get("policy_type", "entrepreneurship"),
        "jurisdiction_level": source.jurisdiction_level, "region_code": source.region_code,
        "jurisdiction_path": json.dumps(path_codes, ensure_ascii=False),
        "effective_at": _date(values.get("effective_at")), "expires_at": _date(values.get("expires_at")),
        "application_url": values.get("application_url", ""), "status": "candidate",
        "review_status": "pending", "source_document_id": document.id,
    }
    policy = db.get(PolicyRecord, policy_id)
    if policy:
        for field, value in policy_payload.items():
            setattr(policy, field, value)
    else:
        db.add(PolicyRecord(id=policy_id, **policy_payload))
    path = _ensure_path(db, config.get("path_code", "startup_policy"))
    item_id = _stable("development-item", policy_id, "policy-service")
    item_payload = {"title": values["title"], "item_type": "entrepreneurship_policy",
                    "organization_id": None, "cycle_type": "policy", "cycle_id": policy_id,
                    "description": f"{values['publisher']} · {values['policy_code']}",
                    "start_time": policy_payload["effective_at"], "deadline": policy_payload["expires_at"],
                    "location": source.region_code or "CN", "materials": "[]", "status": "draft",
                    "source_document_id": document.id}
    item = db.get(DevelopmentItem, item_id)
    if item:
        for field, value in item_payload.items():
            setattr(item, field, value)
    else:
        db.add(DevelopmentItem(id=item_id, **item_payload))
    if not db.scalar(select(DevelopmentItemPath).where(
            DevelopmentItemPath.development_item_id == item_id,
            DevelopmentItemPath.path_id == path.id)):
        db.add(DevelopmentItemPath(development_item_id=item_id, path_id=path.id))
    rules = 0
    for rule in adapter.extract_rules(parsed):
        evidence = proof.get(("policy", rule["field"]))
        if evidence:
            rules += _upsert_target_rule(db, "policy", policy_id, rule, evidence, raw.canonical_url)
    relation_count = 0
    relation_evidence = proof.get(("policy", "policy_code"))
    for parent_id in config.get("parent_policy_ids", []):
        if not db.get(PolicyRecord, parent_id):
            raise ValueError(f"上位政策不存在：{parent_id}")
        relation_type = config.get("relation_type", "implements")
        relation = db.scalar(select(PolicyRelation).where(
            PolicyRelation.from_policy_id == policy_id,
            PolicyRelation.to_policy_id == parent_id,
            PolicyRelation.relation_type == relation_type))
        if not relation:
            db.add(PolicyRelation(from_policy_id=policy_id, to_policy_id=parent_id,
                                  relation_type=relation_type, confidence=1.0,
                                  review_status="pending",
                                  evidence_id=relation_evidence.id if relation_evidence else None))
        relation_count += 1
    db.flush()
    return {"changed": True, "document_version_id": document.id, "policy_id": policy_id,
            "policies": 1, "relations": relation_count, "items": 1, "rules": rules,
            "evidence": len(parsed.evidence)}


def _ensure_path(db, code: str):
    path = db.scalar(select(DevelopmentPath).where(DevelopmentPath.code == code))
    if not path:
        raise ValueError(f"发展路径不存在：{code}，请先执行 SourceRegistry Seed")
    return path


def _upsert_program(db, values, document_id):
    institution_id = _stable("institution", values["institution_code"])
    institution = db.get(Institution, institution_id)
    institution_payload = {"name": values["institution_name"], "official_name": values["institution_name"],
                           "institution_type": "university",
                           "country_code": "CN", "official_id": values["institution_code"],
                           "source_document_id": document_id}
    if institution:
        for key, value in institution_payload.items():
            setattr(institution, key, value)
    else:
        db.add(Institution(id=institution_id, **institution_payload))
    program_id = _stable("program", institution_id, values["program_code"])
    program = db.get(Program, program_id)
    program_payload = {"institution_id": institution_id, "program_code": values["program_code"],
                       "name": values["program_name"], "degree_level": values.get("degree_level", ""),
                       "study_mode": values.get("study_mode", "")}
    if program:
        for key, value in program_payload.items():
            setattr(program, key, value)
    else:
        db.add(Program(id=program_id, **program_payload))
    return institution_id, program_id


def _alias_key(value: str) -> str:
    return " ".join(value.casefold().split())


def _ensure_alias(db, entity_type: str, entity_id: str, alias: str,
                  document_id: str | None = None, locale: str = "und"):
    normalized = _alias_key(alias)
    row = db.scalar(select(EntityAlias).where(EntityAlias.entity_type == entity_type,
                                               EntityAlias.normalized_alias == normalized))
    if row and row.entity_id != entity_id:
        raise ValueError(f"别名冲突：{alias} 已指向其他 {entity_type} 实体")
    if not row:
        db.add(EntityAlias(entity_type=entity_type, entity_id=entity_id, alias=alias,
                           normalized_alias=normalized, locale=locale,
                           source_document_id=document_id))


def ingest_overseas_registry(db: Session, source: Source, endpoint: SourceEndpoint,
                             raw: RawArtifact, config: dict):
    adapter = OverseasRegistryAdapter()
    parsed = adapter.parse(raw)
    raw_text = json.dumps(adapter.normalize(parsed), ensure_ascii=False, separators=(",", ":"))
    document, changed = record_document_version(db, endpoint, raw, raw_text)
    if not changed:
        return {"changed": False, "document_version_id": document.id, "institutions": 0,
                "programs": 0, "assertions": 0, "evidence": 0}
    proof = _persist_evidence(db, source, document, parsed.evidence)
    counts = {"institutions": 0, "programs": 0, "assertions": 0}
    for record in parsed.records:
        values = {key: value for key, value in record.items() if not key.startswith("_")}
        country_code = values["country_code"].upper()
        official_id = values.get("institution_official_id") or _alias_key(values["institution_name"])
        institution_id = _stable("institution", country_code, official_id)
        institution = db.get(Institution, institution_id)
        payload = {"name": values["institution_name"], "official_name": values["institution_name"],
                   "institution_type": "university", "country_code": country_code,
                   "region_code": config.get("region_code"), "official_id": official_id,
                   "website_url": values.get("website_url", ""),
                   "public_status": values.get("public_status", "unknown"),
                   "review_status": "pending", "source_document_id": document.id}
        if institution:
            for key, value in payload.items():
                setattr(institution, key, value)
        else:
            db.add(Institution(id=institution_id, **payload))
        _ensure_alias(db, "institution", institution_id, values["institution_name"], document.id)
        key = record["_record_key"]
        status_evidence = proof.get((key, "public_status"))
        if status_evidence:
            assertion_id = _stable("registry-assertion", source.id, institution_id, official_id)
            assertion = db.get(RegistryAssertion, assertion_id)
            assertion_payload = {"source_id": source.id, "entity_type": "institution",
                                 "entity_id": institution_id, "registry_id": official_id,
                                 "assertion_type": "public_status",
                                 "assertion_value": values.get("public_status", "unknown"),
                                 "evidence_id": status_evidence.id, "review_status": "pending"}
            if assertion:
                for field, value in assertion_payload.items():
                    setattr(assertion, field, value)
            else:
                db.add(RegistryAssertion(id=assertion_id, **assertion_payload))
            counts["assertions"] += 1
        if values.get("program_name"):
            program_code = values.get("program_code") or _alias_key(values["program_name"])
            program_id = _stable("program", institution_id, program_code)
            program = db.get(Program, program_id)
            program_payload = {"institution_id": institution_id, "program_code": program_code,
                               "name": values["program_name"],
                               "degree_level": values.get("degree_level", ""), "study_mode": "",
                               "official_url": "", "public_status": values.get("public_status", "unknown"),
                               "review_status": "pending",
                               "source_document_id": document.id}
            if program:
                for field, value in program_payload.items():
                    setattr(program, field, value)
            else:
                db.add(Program(id=program_id, **program_payload))
            _ensure_alias(db, "program", program_id, values["program_name"], document.id)
            counts["programs"] += 1
        counts["institutions"] += 1
    db.flush()
    return {"changed": True, "document_version_id": document.id, **counts,
            "evidence": len(parsed.evidence)}


def ingest_overseas_program(db: Session, source: Source, endpoint: SourceEndpoint,
                            raw: RawArtifact, config: dict):
    required = {"institution_id", "program_code", "program_name", "path_code"}
    if not required.issubset(config):
        raise ValueError("境外项目配置缺少 institution_id、program_code、program_name 或 path_code")
    if source.source_class != "university" or source.jurisdiction_level != "foreign":
        raise ValueError("年度申请要求只能从目标大学第一方来源导入")
    institution = db.get(Institution, config["institution_id"])
    if not institution:
        raise ValueError("院校实体不存在；必须先导入 Registry 实体层")
    adapter = OverseasUniversityProgramAdapter()
    parsed = adapter.parse(raw)
    raw_text = json.dumps(adapter.normalize(parsed), ensure_ascii=False, separators=(",", ":"))
    document, changed = record_document_version(db, endpoint, raw, raw_text)
    if not changed:
        return {"changed": False, "document_version_id": document.id, "programs": 0,
                "cycles": 0, "items": 0, "rules": 0, "evidence": 0}
    proof = _persist_evidence(db, source, document, parsed.evidence)
    values = parsed.records[0]
    program_id = _stable("program", institution.id, config["program_code"])
    program = db.get(Program, program_id)
    program_payload = {"institution_id": institution.id, "program_code": config["program_code"],
                       "name": config["program_name"],
                       "degree_level": config.get("degree_level", "masters"),
                       "study_mode": config.get("study_mode", "full_time"),
                       "official_url": raw.canonical_url, "public_status": "active",
                       "review_status": "pending",
                       "source_document_id": document.id}
    if program:
        for field, value in program_payload.items():
            setattr(program, field, value)
    else:
        db.add(Program(id=program_id, **program_payload))
    _ensure_alias(db, "program", program_id, config["program_name"], document.id, "en")
    path = _ensure_path(db, config["path_code"])
    year = int(values["cycle_year"])
    cycle_id = _stable("application-cycle", program_id, path.id, year)
    deadline = _date(values.get("deadline_at"))
    cycle_payload = {"program_id": program_id, "path_id": path.id, "cycle_year": year,
                     "open_at": _date(values.get("open_at")), "deadline_at": deadline,
                     "application_url": raw.canonical_url, "status": "draft",
                     "source_document_id": document.id,
                     "requirements_source_type": "university_first_party",
                     "review_status": "pending"}
    cycle = db.get(ApplicationCycle, cycle_id)
    if cycle:
        for field, value in cycle_payload.items():
            setattr(cycle, field, value)
    else:
        db.add(ApplicationCycle(id=cycle_id, **cycle_payload))
    materials = [item.strip() for item in values["materials"].split(";") if item.strip()]
    item_id = _stable("development-item", cycle_id, "overseas-application")
    item_payload = {"title": f"{year} {institution.name} {config['program_name']} application",
                    "item_type": "overseas_application", "organization_id": institution.id,
                    "cycle_type": "application_cycle", "cycle_id": cycle_id,
                    "description": values["title"], "start_time": cycle_payload["open_at"],
                    "deadline": deadline, "location": institution.country_code,
                    "materials": json.dumps(materials, ensure_ascii=False), "status": "draft",
                    "source_document_id": document.id}
    item = db.get(DevelopmentItem, item_id)
    if item:
        for field, value in item_payload.items():
            setattr(item, field, value)
    else:
        db.add(DevelopmentItem(id=item_id, **item_payload))
    if not db.scalar(select(DevelopmentItemPath).where(
            DevelopmentItemPath.development_item_id == item_id,
            DevelopmentItemPath.path_id == path.id)):
        db.add(DevelopmentItemPath(development_item_id=item_id, path_id=path.id))
    rules = 0
    for rule in adapter.extract_rules(parsed):
        evidence = proof.get(("application", rule["field"]))
        if evidence:
            rules += _upsert_target_rule(db, "application_cycle", cycle_id, rule, evidence,
                                         raw.canonical_url)
    db.flush()
    return {"changed": True, "document_version_id": document.id, "programs": 1,
            "cycles": 1, "items": 1, "rules": rules, "evidence": len(parsed.evidence)}


def _add_cycle_fact_rule(db, cycle_id, field, value, evidence, source_url):
    if value is None or evidence is None:
        return 0
    db.execute(update(EligibilityRule).where(
        EligibilityRule.target_type == "application_cycle", EligibilityRule.target_id == cycle_id,
        EligibilityRule.field == field, EligibilityRule.review_status.in_(["pending", "verified"]),
    ).values(review_status="expired"))
    db.add(EligibilityRule(opportunity_id=None, target_type="application_cycle", target_id=cycle_id,
                           field=field, operator="equals", expected=str(value), label=f"{field}: {value}",
                           source_url=source_url, evidence=evidence.quote_or_normalized_fact,
                           evidence_id=evidence.id, logic_group="all", confidence=1.0,
                           review_status="pending", extractor="parser"))
    return 1


def ingest_yz_program_catalog(db: Session, source: Source, endpoint: SourceEndpoint, raw: RawArtifact,
                              config: dict):
    adapter = YZChsiAdapter()
    parsed = adapter.parse(raw)
    raw_text = json.dumps(adapter.normalize(parsed), ensure_ascii=False, separators=(",", ":"))
    document, changed = record_document_version(db, endpoint, raw, raw_text)
    if not changed:
        return {"changed": False, "document_version_id": document.id, "programs": 0, "cycles": 0,
                "items": 0, "rules": 0, "evidence": 0}
    evidence = _persist_evidence(db, source, document, parsed.evidence)
    path = _ensure_path(db, config.get("path_code", "domestic_postgraduate_exam"))
    counts = {"programs": 0, "cycles": 0, "items": 0, "rules": 0}
    for record in parsed.records:
        values = {key: value for key, value in record.items() if not key.startswith("_")}
        institution_id, program_id = _upsert_program(db, values, document.id)
        year = int(values["cycle_year"])
        cycle_id = _stable("application-cycle", program_id, path.id, year)
        cycle = db.get(ApplicationCycle, cycle_id)
        cycle_payload = {"program_id": program_id, "path_id": path.id, "cycle_year": year,
                         "open_at": _date(values.get("open_at")), "deadline_at": _date(values.get("deadline_at")),
                         "exam_at": _date(values.get("exam_at")),
                         "application_url": urljoin(raw.canonical_url, values.get("application_url", "")),
                         "status": "draft", "source_document_id": document.id}
        if cycle:
            for key, value in cycle_payload.items():
                setattr(cycle, key, value)
        else:
            db.add(ApplicationCycle(id=cycle_id, **cycle_payload))
        item_id = _stable("development-item", cycle_id, "application")
        item = db.get(DevelopmentItem, item_id)
        item_payload = {"title": f"{year}年{values['institution_name']}{values['program_name']}招生",
                        "item_type": "postgraduate_application", "organization_id": institution_id,
                        "cycle_type": "application_cycle", "cycle_id": cycle_id,
                        "description": f"{values.get('degree_level', '')} {values.get('study_mode', '')}".strip(),
                        "start_time": cycle_payload["open_at"], "deadline": cycle_payload["deadline_at"],
                        "location": "", "materials": "[]", "status": "draft",
                        "source_document_id": document.id}
        if item:
            for key, value in item_payload.items():
                setattr(item, key, value)
        else:
            db.add(DevelopmentItem(id=item_id, **item_payload))
        if not db.scalar(select(DevelopmentItemPath).where(
                DevelopmentItemPath.development_item_id == item_id,
                DevelopmentItemPath.path_id == path.id)):
            db.add(DevelopmentItemPath(development_item_id=item_id, path_id=path.id))
        key = record["_record_key"]
        for field in ("open_at", "deadline_at", "exam_at"):
            counts["rules"] += _add_cycle_fact_rule(db, cycle_id, field, values.get(field),
                                                    evidence.get((key, field)), raw.canonical_url)
        counts["programs"] += 1
        counts["cycles"] += 1
        counts["items"] += 1
    db.flush()
    return {"changed": True, "document_version_id": document.id, **counts,
            "evidence": len(parsed.evidence)}


def ingest_university_notice(db: Session, source: Source, endpoint: SourceEndpoint, raw: RawArtifact,
                             config: dict):
    # School-wide notices have no specific program. Do not manufacture one.
    if config.get('notice_scope') == 'university':
        adapter = UniversityNoticeAdapter()
        parsed = adapter.parse(raw)
        values = parsed.records[0]
        document, changed = record_document_version(db, endpoint, raw,
            json.dumps(adapter.normalize(parsed), ensure_ascii=False))
        document.publish_time = _date(parsed.metadata.get('publish_time'))
        if not changed:
            override = config.get('path_code')
            if override:
                if override not in {'recommendation_exemption','domestic_postgraduate_exam'}:
                    raise ValueError('高校通知路径必须是考研或推免')
                item_id = _stable('university-notice', source.id, raw.source_item_id)
                path = _ensure_path(db, override)
                for link in db.scalars(select(DevelopmentItemPath).where(
                        DevelopmentItemPath.development_item_id == item_id)).all():
                    if link.path_id != path.id:
                        db.delete(link)
                if not db.scalar(select(DevelopmentItemPath).where(
                        DevelopmentItemPath.development_item_id == item_id, DevelopmentItemPath.path_id == path.id)):
                    db.add(DevelopmentItemPath(development_item_id=item_id,path_id=path.id))
                db.flush()
            return {'changed':False,'document_version_id':document.id,'items':0,'rules':0,'evidence':0}
        _persist_evidence(db, source, document, parsed.evidence)
        path_code = config.get('path_code') or classify_path(values['title'])
        if path_code not in {'recommendation_exemption','domestic_postgraduate_exam'}:
            raise ValueError('高校通知主题不是明确的考研或推免信息，需人工核对')
        path = _ensure_path(db, path_code)
        item_id = _stable('university-notice', source.id, raw.source_item_id)
        item = db.get(DevelopmentItem,item_id)
        payload = {'title':values['title'][:200],'item_type':'university_notice',
            'description':values['body'],'start_time':_date(values.get('open_at')),
            'deadline':_date(values.get('deadline_at')),'location':source.region_code or '',
            'materials':json.dumps(values.get('material_quotes',[])+values.get('attachments',[]),ensure_ascii=False),
            'source_document_id':document.id,'status':'draft'}
        if item:
            for key,value in payload.items():setattr(item,key,value)
        else:
            db.add(DevelopmentItem(id=item_id,**payload))
        if not db.scalar(select(DevelopmentItemPath).where(
                DevelopmentItemPath.development_item_id==item_id,DevelopmentItemPath.path_id==path.id)):
            db.add(DevelopmentItemPath(development_item_id=item_id,path_id=path.id))
        db.flush()
        return {'changed':True,'document_version_id':document.id,'items':1,'rules':0,'evidence':len(parsed.evidence)}
    required = {"institution_code", "institution_name", "program_code", "program_name",
                "path_code", "cycle_year"}
    if not required.issubset(config):
        raise ValueError("高校通知配置缺少 institution_code、institution_name、program_code、program_name、path_code 或 cycle_year")
    adapter = UniversityNoticeAdapter()
    parsed = adapter.parse(raw)
    raw_text = json.dumps(adapter.normalize(parsed), ensure_ascii=False, separators=(",", ":"))
    document, changed = record_document_version(db, endpoint, raw, raw_text)
    if not changed:
        return {"changed": False, "document_version_id": document.id, "items": 0, "rules": 0, "evidence": 0}
    evidence = _persist_evidence(db, source, document, parsed.evidence)
    values = parsed.records[0]
    document.publish_time = _date(parsed.metadata.get('publish_time'))
    program_values = {**config, "degree_level": config.get("degree_level", ""),
                      "study_mode": config.get("study_mode", "")}
    institution_id, program_id = _upsert_program(db, program_values, document.id)
    path = _ensure_path(db, config["path_code"])
    year = int(config["cycle_year"])
    cycle_id = _stable("application-cycle", program_id, path.id, year)
    cycle_payload = {"program_id": program_id, "path_id": path.id, "cycle_year": year,
                     "open_at": _date(values.get("open_at")), "deadline_at": _date(values.get("deadline_at")),
                     "exam_at": _date(values.get("exam_at")), "interview_at": _date(values.get("interview_at")),
                     "application_url": raw.canonical_url, "status": "draft",
                     "source_document_id": document.id}
    cycle = db.get(ApplicationCycle, cycle_id)
    if cycle:
        for key, value in cycle_payload.items():
            setattr(cycle, key, value)
    else:
        db.add(ApplicationCycle(id=cycle_id, **cycle_payload))
    item_id = _stable("development-item", cycle_id, raw.source_item_id)
    item_payload = {"title": values["title"], "item_type": config.get("item_type", "university_notice"),
                    "organization_id": institution_id, "cycle_type": "application_cycle", "cycle_id": cycle_id,
                    "description": values.get("body", ""), "start_time": cycle_payload["open_at"],
                    "deadline": cycle_payload["deadline_at"], "location": "",
                    "materials": json.dumps([values["materials"]], ensure_ascii=False) if values.get("materials") else "[]",
                    "status": "draft", "source_document_id": document.id}
    item = db.get(DevelopmentItem, item_id)
    if item:
        for key, value in item_payload.items():
            setattr(item, key, value)
    else:
        db.add(DevelopmentItem(id=item_id, **item_payload))
    if not db.scalar(select(DevelopmentItemPath).where(
            DevelopmentItemPath.development_item_id == item_id,
            DevelopmentItemPath.path_id == path.id)):
        db.add(DevelopmentItemPath(development_item_id=item_id, path_id=path.id))
    rules = 0
    for field in ("open_at", "deadline_at", "exam_at", "interview_at", "degree", "gpa", "ranking", "language"):
        rules += _add_cycle_fact_rule(db, cycle_id, field, values.get(field),
                                     evidence.get(("notice", field)), raw.canonical_url)
    db.flush()
    return {"changed": True, "document_version_id": document.id, "items": 1, "rules": rules,
            "evidence": len(parsed.evidence)}


def _upsert_target_rule(db, target_type, target_id, rule, evidence, source_url):
    db.execute(update(EligibilityRule).where(
        EligibilityRule.target_type == target_type, EligibilityRule.target_id == target_id,
        EligibilityRule.field == rule["field"],
        EligibilityRule.review_status.in_(["pending", "verified"]),
    ).values(review_status="expired"))
    db.add(EligibilityRule(
        opportunity_id=None, target_type=target_type, target_id=target_id,
        field=rule["field"], operator=rule["operator"], expected=str(rule["expected"]),
        label=rule["description"], source_url=source_url,
        evidence=evidence.quote_or_normalized_fact, evidence_id=evidence.id,
        confidence=rule["confidence"], review_status=rule["review_status"],
        extractor=rule["extractor"], logic_group="all",
    ))
    return 1


def ingest_public_recruitment_html(db: Session, source: Source, endpoint: SourceEndpoint,
                                   raw: RawArtifact, config: dict):
    required = {"cycle_code", "cycle_name", "cycle_year", "path_code"}
    if not required.issubset(config):
        raise ValueError("公开招聘配置缺少 cycle_code、cycle_name、cycle_year 或 path_code")
    adapter = (MohrssPublicJobAdapter() if endpoint.parser_type == "MohrssPublicJobAdapter"
               else InstitutionRecruitmentAdapter())
    parsed = adapter.parse(raw)
    raw_text = json.dumps(adapter.normalize(parsed), ensure_ascii=False, separators=(",", ":"))
    document, changed = record_document_version(db, endpoint, raw, raw_text)
    if not changed:
        return {"changed": False, "document_version_id": document.id, "positions": 0,
                "items": 0, "rules": 0, "evidence": 0}
    evidence = _persist_evidence(db, source, document, parsed.evidence)
    notice = next(row for row in parsed.records if row.get("_kind") == "notice")
    positions = [row for row in parsed.records if row.get("_kind") == "position"]
    cycle_id = _stable("recruitment-cycle", source.id, config["cycle_code"])
    cycle = db.get(RecruitmentCycle, cycle_id)
    cycle_payload = {
        "source_id": source.id, "cycle_code": config["cycle_code"],
        "name": config["cycle_name"], "cycle_year": int(config["cycle_year"]),
        "open_at": _date(notice.get("open_at")), "deadline_at": _date(notice.get("deadline_at")),
        "status": "draft", "source_document_id": document.id,
    }
    if cycle:
        for key, value in cycle_payload.items():
            setattr(cycle, key, value)
    else:
        db.add(RecruitmentCycle(id=cycle_id, **cycle_payload))
    path = _ensure_path(db, config["path_code"])
    item_id = _stable("development-item", cycle_id, raw.source_item_id)
    item_payload = {
        "title": notice["title"],
        "item_type": config.get("item_type", "public_institution_recruitment"),
        "organization_id": None, "cycle_type": "recruitment_cycle", "cycle_id": cycle_id,
        "description": config.get("description", notice["title"]),
        "start_time": cycle_payload["open_at"], "deadline": cycle_payload["deadline_at"],
        "location": config.get("location", source.region_code or ""),
        "materials": json.dumps(notice.get("attachments", []), ensure_ascii=False),
        "status": "draft", "source_document_id": document.id,
    }
    item = db.get(DevelopmentItem, item_id)
    if item:
        for key, value in item_payload.items():
            setattr(item, key, value)
    else:
        db.add(DevelopmentItem(id=item_id, **item_payload))
    if not db.scalar(select(DevelopmentItemPath).where(
            DevelopmentItemPath.development_item_id == item_id,
            DevelopmentItemPath.path_id == path.id)):
        db.add(DevelopmentItemPath(development_item_id=item_id, path_id=path.id))

    rule_count = 0
    for field in ("open_at", "deadline_at", "exam_at", "interview_at"):
        value, proof = notice.get(field), evidence.get(("notice", field))
        if value and proof:
            rule_count += _upsert_target_rule(db, "recruitment_cycle", cycle_id, {
                "field": field, "operator": "equals", "expected": value,
                "description": f"{field}: {value}", "confidence": 1.0,
                "review_status": "pending", "extractor": "parser",
            }, proof, raw.canonical_url)

    for values in positions:
        position_id = _position_id(cycle_id, values["position_code"])
        position = db.get(Position, position_id)
        payload = {key: values.get(key, "") for key in (
            "position_code", "department", "organization", "title", "education", "degree",
            "majors", "political_status", "grassroots_years", "fresh_graduate", "work_region",
            "remarks")}
        payload["headcount"] = values.get("headcount") or None
        if position:
            for key, value in payload.items():
                setattr(position, key, value)
            position.source_document_id = document.id
        else:
            db.add(Position(id=position_id, recruitment_cycle_id=cycle_id,
                            source_document_id=document.id, **payload))
    db.flush()
    for rule in adapter.extract_rules(parsed):
        proof = evidence[(rule["record_key"], rule["field"])]
        rule_count += _upsert_target_rule(db, "position", _position_id(cycle_id, rule["record_key"]),
                                          rule, proof, raw.canonical_url)
    db.flush()
    return {"changed": True, "document_version_id": document.id, "positions": len(positions),
            "items": 1, "rules": rule_count, "evidence": len(parsed.evidence)}


def ingest_regional_source_directory(db: Session, source: Source, endpoint: SourceEndpoint,
                                     raw: RawArtifact, config: dict):
    adapter = RegionalRecruitmentDirectoryAdapter()
    parsed = adapter.parse(raw)
    raw_text = json.dumps(adapter.normalize(parsed), ensure_ascii=False, separators=(",", ":"))
    document, changed = record_document_version(db, endpoint, raw, raw_text)
    if not changed:
        return {"changed": False, "document_version_id": document.id, "candidates": 0, "evidence": 0}
    proof_by_key = _persist_evidence(db, source, document, parsed.evidence)
    created = 0
    for values in parsed.records:
        key = f"{values['region_code']}:{values['base_url']}"
        proof = proof_by_key[(key, "base_url")]
        candidate_id = _stable("source-candidate", document.id, values["base_url"])
        if not db.get(SourceRegistryCandidate, candidate_id):
            db.add(SourceRegistryCandidate(
                id=candidate_id, discovery_source_id=source.id, document_version_id=document.id,
                source_code=values["source_code"], name=values["name"],
                region_code=values["region_code"], base_url=values["base_url"],
                authority_level="A+", status="pending", evidence_id=proof.id,
                created_at=datetime.now(UTC),
            ))
            created += 1
    db.flush()
    return {"changed": True, "document_version_id": document.id, "candidates": created,
            "evidence": len(parsed.evidence)}


def ingest_education_html(db: Session, source: Source, endpoint: SourceEndpoint, raw: RawArtifact,
                          config: dict):
    handlers = {"MoEPolicyAdapter": ingest_moe_policy, "YZChsiAdapter": ingest_yz_program_catalog,
                "UniversityNoticeAdapter": ingest_university_notice}
    handler = handlers.get(endpoint.parser_type)
    if not handler:
        raise ValueError(f"不支持的教育信息 Adapter：{endpoint.parser_type}")
    return handler(db, source, endpoint, raw, config)


def ingest_public_recruitment(db: Session, source: Source, endpoint: SourceEndpoint, raw: RawArtifact,
                              config: dict):
    if endpoint.parser_type == "RegionalRecruitmentDirectoryAdapter":
        return ingest_regional_source_directory(db, source, endpoint, raw, config)
    if endpoint.parser_type in {"InstitutionRecruitmentAdapter", "MohrssPublicJobAdapter"}:
        return ingest_public_recruitment_html(db, source, endpoint, raw, config)
    raise ValueError(f"不支持的公开招聘 Adapter：{endpoint.parser_type}")

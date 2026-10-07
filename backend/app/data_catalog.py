"""Version-bound review and public catalog; drafts never reach public APIs."""
import hashlib
import json
from datetime import UTC, datetime, timedelta
from collections import defaultdict
from typing import Annotated, Literal
from uuid import uuid4
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from .auth import actor_id, require_admin
from .database import SessionLocal, get_db
from .governance import audit
from .intake_governance import PROOF_KEYS, gate_reason, official_https_ok, separation_ok
from .intake_models import (
    DataPublication,
    DataSubscription,
    DevelopmentItem,
    DevelopmentItemPath,
    DocumentArchive,
    DocumentVersion,
    Evidence,
    PolicyRelation,
    Position,
    Source,
    SourceBlocker,
    SourceEndpointCalibration,
    SourceEndpoint,
)
from .models import EligibilityRule, Path, UserPlan
from .adapters.notice_text import content_kind
import re

router = APIRouter(prefix="/v1/data")
admin = APIRouter(prefix="/v1/admin/data", dependencies=[Depends(require_admin)])


def encoded(row, fields):
    return jsonable_encoder({key: getattr(row, key) for key in fields}, custom_encoder={
        datetime: lambda value: (value.replace(tzinfo=UTC) if value.tzinfo is None
                                 else value.astimezone(UTC)).isoformat()})


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _build_snapshot(doc, source, items, positions, evidence, all_rules, relations,
                    paths_by_item):
    """Build one immutable publication snapshot from already loaded rows.

    The public catalog used to call ``snapshot_for`` once per publication.  A
    slow SQLite volume therefore turned the read path into an N+1 query storm.
    Keeping snapshot construction separate from row loading lets the normal
    admin path retain its fail-closed checks while the public path bulk-loads
    the same inputs.
    """
    if not source:
        raise HTTPException(422, "文档来源不存在")
    items = sorted(items, key=lambda row: row.id)
    positions = sorted(positions, key=lambda row: row.id)
    evidence = sorted(evidence, key=lambda row: row.id)
    proofs = {e.id: e for e in evidence}
    targets = {i.cycle_id for i in items if i.cycle_id} | {p.id for p in positions}
    rules = [r for r in sorted(all_rules, key=lambda row: row.id)
             if r.target_id in targets and (not r.evidence_id or r.evidence_id in proofs)]
    blocks = []
    if not items and not positions:
        blocks.append("当前文档没有可发布事项或岗位（院校注册表和来源目录不等于申请事项）")
    if not evidence:
        blocks.append("当前版本没有 Evidence")
    for rule in rules:
        if rule.review_status != "verified" or rule.evidence_id not in proofs:
            blocks.append(f"规则 {rule.id} 未核验或缺少当前版本证据")
        elif not proofs[rule.evidence_id].verified_by:
            blocks.append(f"规则 {rule.id} 缺少核验人")
    relations = [r for r in sorted(relations, key=lambda row: row.id)
                 if r.from_policy_id in targets]
    for rel in relations:
        if rel.review_status not in {"verified", "rejected"}:
            blocks.append(f"政策关系 {rel.id} 尚未审核")
        elif rel.review_status == "verified" and rel.evidence_id not in proofs:
            blocks.append(f"政策关系 {rel.id} 证据不属于当前版本")
    output_items = []
    for item in items:
        value = encoded(item, ["id", "title", "item_type", "description", "cycle_type",
            "cycle_id", "start_time", "deadline", "location"])
        value["materials"] = json.loads(item.materials or "[]")
        value["paths"] = [encoded(p, ["id", "code", "name", "parent_id"])
                           for p in sorted(paths_by_item.get(item.id, []), key=lambda row: row.id)]
        output_items.append(value)
    snapshot = {
        "document": encoded(doc, ["id", "canonical_url", "content_hash", "version_no", "fetched_at", "import_mode", "test_batch"]),
        "source": encoded(source, ["source_code", "name", "publisher", "authority_level", "region_code"]),
        "items": output_items,
        "positions": [encoded(p, ["id", "position_code", "title", "organization", "department",
            "headcount", "education", "degree", "majors", "work_region", "remarks",
            "recruitment_cycle_id"]) for p in positions],
        "rules": [encoded(r, ["id", "target_type", "target_id", "field", "operator", "expected",
            "label", "evidence_id", "extractor"]) for r in rules],
        "evidence": [encoded(e, ["id", "evidence_location", "quote_or_normalized_fact",
            "evidence_type", "extractor"]) for e in evidence],
        "relations": [encoded(r, ["id", "from_policy_id", "to_policy_id", "relation_type",
            "evidence_id"]) for r in relations if r.review_status == "verified"],
    }
    return snapshot, blocks


def snapshot_for(db, doc):
    endpoint = db.get(SourceEndpoint, doc.source_endpoint_id)
    source = db.get(Source, endpoint.source_id) if endpoint else None
    items = db.scalars(select(DevelopmentItem).where(
        DevelopmentItem.source_document_id == doc.id).order_by(DevelopmentItem.id)).all()
    positions = db.scalars(select(Position).where(
        Position.source_document_id == doc.id).order_by(Position.id)).all()
    evidence = db.scalars(select(Evidence).where(
        Evidence.document_version_id == doc.id).order_by(Evidence.id)).all()
    targets = {i.cycle_id for i in items if i.cycle_id} | {p.id for p in positions}
    all_rules = db.scalars(select(EligibilityRule).where(
        EligibilityRule.target_id.in_(targets)).order_by(EligibilityRule.id)).all() if targets else []
    relations = db.scalars(select(PolicyRelation).where(
        PolicyRelation.from_policy_id.in_(targets)).order_by(PolicyRelation.id)).all() if targets else []
    paths_by_item = defaultdict(list)
    if items:
        path_rows = db.execute(select(DevelopmentItemPath, Path).join(Path,
            DevelopmentItemPath.path_id == Path.id).where(
            DevelopmentItemPath.development_item_id.in_(i.id for i in items)).order_by(Path.id)).all()
        for link, path in path_rows:
            paths_by_item[link.development_item_id].append(path)
    return _build_snapshot(doc, source, items, positions, evidence, all_rules,
                           relations, paths_by_item)


def readiness(db, doc):
    snapshot, blocks = snapshot_for(db, doc)
    endpoint = db.get(SourceEndpoint, doc.source_endpoint_id)
    direct = doc.import_mode in {'system', 'demo'}
    if direct:
        # Direct ingestion publishes facts without claiming human verification.
        blocks = [] if snapshot['items'] or snapshot['positions'] else ['没有可展示的事项或岗位']
    reason = gate_reason(db, endpoint) if not direct else None
    if doc.deleted_at:
        blocks.append('管理员已删除')
    if direct:
        source = db.get(Source, endpoint.source_id) if endpoint else None
        if not endpoint or not endpoint.active or not source or not source.active:
            blocks.append('来源或端点已停用')
    if doc.import_mode == 'demo':
        from .config import settings
        if not settings.demo_mode or not doc.test_batch:
            blocks.append('测试数据仅在演示环境展示')
    if reason:
        blocks.append(reason)
    if not direct and endpoint and doc.canonical_url != endpoint.url:
        blocks.append("文档原始 URL 与已校准精确 URL 不一致")
    latest = db.scalar(select(DocumentVersion.id).where(
        DocumentVersion.source_endpoint_id == doc.source_endpoint_id,
        DocumentVersion.source_item_id == doc.source_item_id,
    ).order_by(DocumentVersion.version_no.desc()))
    if latest != doc.id:
        blocks.append("文档不是最新版本")
    archive = db.get(DocumentArchive, doc.id)
    if not archive:
        blocks.append("缺少原始字节归档；历史文档需要重新导入原文件")
    elif hashlib.sha256(archive.content).hexdigest() != doc.content_hash:
        blocks.append("原始文件 SHA256 校验不通过")
    elif archive.is_fixture and doc.import_mode != 'demo':
        blocks.append("离线 Fixture 禁止发布为真实数据")
    return snapshot, blocks


def auto_publish(db, doc, restore_peer=False):
    if doc.import_mode not in {'system', 'demo'} or doc.deleted_at:
        return False
    snapshot, blocks = readiness(db, doc)
    if blocks:
        return False
    row = db.scalar(select(DataPublication).where(DataPublication.document_id == doc.id))
    if row and row.status in {'withdrawn', 'rejected', 'superseded'}:
        return False
    if row and row.status == "peer_hidden" and not restore_peer:
        return False
    payload, now = canonical(snapshot), datetime.now(UTC)
    if not row:
        row = DataPublication(id=str(uuid4()), document_id=doc.id, created_at=now,
            submitted_by='system-ingestion', note='系统直接入库，无人工审核')
        db.add(row)
    row.status, row.snapshot = 'published', payload
    row.snapshot_hash, row.updated_at = hashlib.sha256(payload.encode()).hexdigest(), now
    audit(db, 'system-ingestion', 'data_auto_publish', f'data_publication:{row.id}')
    db.flush()
    return True


@admin.post('/publish-system')
def publish_system(db: Session = Depends(get_db)):
    docs = db.scalars(select(DocumentVersion).where(DocumentVersion.import_mode == 'system')).all()
    results = [{'id': d.id, 'published': auto_publish(db, d)} for d in docs]
    db.commit()
    return {'results': results}


@admin.delete('/documents/{document_id}')
def delete_document(document_id: str, user: str = Depends(require_admin), db: Session = Depends(get_db)):
    doc = db.get(DocumentVersion, document_id)
    if not doc:
        raise HTTPException(404, '文档不存在')
    doc.deleted_at = datetime.now(UTC)
    db.execute(update(DataPublication).where(DataPublication.document_id == doc.id).values(
        status='withdrawn', updated_at=doc.deleted_at, note='管理员删除'))
    audit(db, user, 'data_delete', f'document:{doc.id}')
    db.commit()
    return {'id': doc.id, 'deleted': True}


class Submit(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    note: str = Field(min_length=3, max_length=1000)
    verified_original: Literal[True]


class Decision(Submit):
    action: Literal["approve", "reject", "withdraw"]


@admin.get("/overview")
def overview(db: Session = Depends(get_db)):
    def counts(model, field):
        return dict(db.execute(select(field, func.count()).group_by(field)).all())
    endpoints = db.scalars(select(SourceEndpoint).order_by(SourceEndpoint.id)).all()
    return {"documents": db.scalar(select(func.count()).select_from(DocumentVersion)),
            "publications": counts(DataPublication, DataPublication.status),
            "rules": counts(EligibilityRule, EligibilityRule.review_status),
            "blockers": counts(SourceBlocker, SourceBlocker.status),
            "endpoints": [{"id": ep.id, "name": ep.name, "source_id": ep.source_id,
                "parser_type": ep.parser_type, "scheduled": ep.scheduled,
                "gate_reason": gate_reason(db, ep, automated=True)} for ep in endpoints]}


@admin.get("/documents")
def documents(offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100),
              db: Session = Depends(get_db)):
    rows = db.scalars(select(DocumentVersion).order_by(
        DocumentVersion.fetched_at.desc(), DocumentVersion.id).offset(offset).limit(limit)).all()
    publications = {p.document_id: p for p in db.scalars(select(DataPublication).where(
        DataPublication.document_id.in_([d.id for d in rows]))).all()}
    return {"total": db.scalar(select(func.count()).select_from(DocumentVersion)), "items": [
        {**encoded(d, ["id", "canonical_url", "version_no", "fetched_at", "content_hash", "import_mode", "test_batch", "deleted_at"]),
         "publication": encoded(publications[d.id], ["id", "status", "submitted_by",
            "first_reviewed_by", "second_reviewed_by", "note"]) if d.id in publications else None}
        for d in rows]}


@admin.get("/documents/{document_id}")
def inspect_document(document_id: str, db: Session = Depends(get_db)):
    doc = db.get(DocumentVersion, document_id)
    if not doc:
        raise HTTPException(404, "文档不存在")
    snapshot, blocks = readiness(db, doc)
    targets = [i["cycle_id"] for i in snapshot["items"] if i["cycle_type"] == "policy"]
    relations = db.scalars(select(PolicyRelation).where(
        PolicyRelation.from_policy_id.in_(targets))).all() if targets else []
    return {"snapshot": snapshot, "blockers": blocks, "ready": not blocks,
            "relation_reviews": [encoded(r, ["id", "to_policy_id", "relation_type", "review_status"])
                                 for r in relations]}


@admin.get("/documents/{document_id}/raw")
def download_raw(document_id: str, db: Session = Depends(get_db)):
    archive = db.get(DocumentArchive, document_id)
    doc = db.get(DocumentVersion, document_id)
    if not archive or not doc:
        raise HTTPException(404, "原始文件未归档")
    if hashlib.sha256(archive.content).hexdigest() != doc.content_hash:
        raise HTTPException(409, "归档校验失败")
    return Response(archive.content, media_type="application/octet-stream", headers={
        "Content-Disposition": f'attachment; filename="{document_id}.bin"',
        "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})


@admin.post("/documents/{document_id}/submit", status_code=201)
def submit(document_id: str, body: Submit, user: str = Depends(require_admin),
           db: Session = Depends(get_db)):
    doc = db.get(DocumentVersion, document_id)
    if not doc:
        raise HTTPException(404, "文档不存在")
    snapshot, blocks = readiness(db, doc)
    if blocks:
        raise HTTPException(422, "；".join(blocks))
    payload = canonical(snapshot)
    now = datetime.now(UTC)
    row = db.scalar(select(DataPublication).where(DataPublication.document_id == document_id))
    if row and row.status in {"pending", "published", "superseded"}:
        raise HTTPException(409, "该版本已有审核或发布记录")
    if row:
        row.first_reviewed_by = row.second_reviewed_by = None
        row.submitted_by, row.status, row.note = user, "pending", body.note
        row.snapshot, row.snapshot_hash, row.updated_at = payload, hashlib.sha256(payload.encode()).hexdigest(), now
    else:
        row = DataPublication(id=str(uuid4()), document_id=document_id, status="pending",
            snapshot=payload, snapshot_hash=hashlib.sha256(payload.encode()).hexdigest(),
            submitted_by=user, note=body.note, created_at=now, updated_at=now)
        db.add(row)
    audit(db, user, "data_submit", f"data_publication:{row.id}", {"note": body.note})
    db.commit()
    return {"id": row.id, "status": row.status}


@admin.patch("/publications/{publication_id}")
def decide(publication_id: str, body: Decision, user: str = Depends(require_admin),
           db: Session = Depends(get_db)):
    row = db.get(DataPublication, publication_id)
    if not row:
        raise HTTPException(404, "发布记录不存在")
    old_status, first = row.status, row.first_reviewed_by
    if body.action != "withdraw" and old_status != "pending":
        raise HTTPException(409, "审核已处理")
    if body.action == "withdraw" and old_status not in {"pending", "published"}:
        raise HTTPException(409, "当前状态不可撤回")
    claimed = db.execute(update(DataPublication).where(
        DataPublication.id == row.id, DataPublication.status == old_status,
        DataPublication.first_reviewed_by == first,
    ).values(updated_at=datetime.now(UTC)).execution_options(synchronize_session=False))
    if not claimed.rowcount:
        raise HTTPException(409, "审核发生并发变化，请刷新")
    if body.action == "approve":
        if user in {row.submitted_by, first}:
            raise HTTPException(409, "提交人与两名审核人必须相互独立")
        doc = db.get(DocumentVersion, row.document_id)
        snapshot, blocks = readiness(db, doc)
        if blocks or canonical(snapshot) != row.snapshot:
            raise HTTPException(409, "数据或校准状态已变化，撤回后重新提交：" + "；".join(blocks))
        if not first:
            row.first_reviewed_by = user
        else:
            row.second_reviewed_by, row.status = user, "published"
    else:
        row.status = "rejected" if body.action == "reject" else "withdrawn"
    row.note = body.note
    row.updated_at = datetime.now(UTC)
    audit(db, user, "data_" + body.action, f"data_publication:{row.id}",
          {"note": body.note, "status": row.status})
    db.commit()
    return {"id": row.id, "status": row.status, "first_reviewed_by": row.first_reviewed_by}


def _bulk_gate_reasons(db, endpoints, sources):
    """Evaluate the public source gate with bounded database reads.

    ``gate_reason`` is intentionally query-backed for individual admin and
    intake operations.  Public catalog reads can have many published
    documents sharing a small set of endpoints, so loading blockers and
    calibrations once avoids repeating those queries for every document.
    """
    endpoint_ids = {endpoint.id for endpoint in endpoints}
    source_ids = {source.id for source in sources.values()}
    blockers = db.scalars(select(SourceBlocker).where(
        SourceBlocker.status == "open",
        or_(SourceBlocker.source_id.in_(source_ids),
            SourceBlocker.endpoint_id.in_(endpoint_ids)))).all() if endpoint_ids else []
    blocked = {(blocker.source_id, blocker.endpoint_id) for blocker in blockers}
    calibrations = db.scalars(select(SourceEndpointCalibration).where(
        SourceEndpointCalibration.status == "approved",
        SourceEndpointCalibration.endpoint_id.in_(endpoint_ids))).all() if endpoint_ids else []
    calibrations_by_endpoint = defaultdict(list)
    for calibration in calibrations:
        calibrations_by_endpoint[calibration.endpoint_id].append(calibration)
    for rows in calibrations_by_endpoint.values():
        rows.sort(key=lambda row: row.second_reviewed_at.timestamp()
                  if row.second_reviewed_at else 0, reverse=True)

    def valid_calibration(endpoint):
        for row in calibrations_by_endpoint.get(endpoint.id, []):
            if row.exact_url != endpoint.url:
                continue
            try:
                proof = json.loads(row.proof or "{}")
                adapter_config = json.loads(row.adapter_config or "{}")
                endpoint_config = json.loads(endpoint.adapter_config or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if (PROOF_KEYS.issubset(proof) and all(proof[key] for key in PROOF_KEYS)
                    and separation_ok(row)
                    and row.robots_status == "allowed"
                    and row.terms_status == "permitted"
                    and row.license_status == "permitted"
                    and adapter_config == endpoint_config):
                return True
        return False

    reasons = {}
    for endpoint in endpoints:
        source = sources.get(endpoint.source_id)
        if not endpoint.active:
            reasons[endpoint.id] = "端点不存在或已停用"
        elif not source or not source.active or not source.official:
            reasons[endpoint.id] = "来源未启用或不是官方来源"
        else:
            try:
                tags = set(json.loads(endpoint.access_tags or "[]"))
            except (TypeError, ValueError, json.JSONDecodeError):
                tags = {"INVALID"}
            if (endpoint.auth_type != "none" or endpoint.agent_mode == "USER_ACTION"
                    or tags & {"API-AUTH", "LOGIN-USER", "COMMERCIAL", "LICENSE"}
                    or endpoint.license_status != "permitted"):
                reasons[endpoint.id] = "认证、登录、商业限制或许可未明确的端点不可发布或采集"
            else:
                parts, base = urlsplit(endpoint.url), urlsplit(source.base_url)
                if not official_https_ok(parts, base):
                    reasons[endpoint.id] = "端点不是无凭据的官方 URL（默认仅 HTTPS，明文仅限显式例外主机）"
                elif ((source.id, endpoint.id) in blocked
                      or (source.id, None) in blocked):
                    reasons[endpoint.id] = "来源仍有开放 Blocker"
                elif not valid_calibration(endpoint):
                    reasons[endpoint.id] = "缺少含原始依据的双人校准审核"
    return reasons


def visible(db):
    """Yield current public snapshots using bulk-loaded validation inputs.

    The checks intentionally mirror ``readiness``.  Only the row loading is
    different: all documents, items, evidence, rules, paths, archives and
    source-gate inputs are fetched in batches, eliminating the per-document
    N+1 query pattern that made catalog pages exceed the frontend timeout on
    network-backed SQLite volumes.
    """
    rows = db.execute(
        select(DataPublication, DocumentVersion, SourceEndpoint, Source)
        .join(DocumentVersion, DocumentVersion.id == DataPublication.document_id)
        .join(SourceEndpoint, SourceEndpoint.id == DocumentVersion.source_endpoint_id)
        .join(Source, Source.id == SourceEndpoint.source_id)
        .where(DataPublication.status == "published")
        .order_by(DataPublication.updated_at.desc())
    ).all()
    if not rows:
        return
    docs = [doc for _, doc, _, _ in rows]
    doc_ids = [doc.id for doc in docs]
    endpoints = {endpoint.id: endpoint for _, _, endpoint, _ in rows}
    sources = {source.id: source for _, _, _, source in rows}
    endpoint_ids = list(endpoints)

    items_by_doc = defaultdict(list)
    for item in db.scalars(select(DevelopmentItem).where(
            DevelopmentItem.source_document_id.in_(doc_ids)).order_by(DevelopmentItem.id)).all():
        items_by_doc[item.source_document_id].append(item)
    positions_by_doc = defaultdict(list)
    for position in db.scalars(select(Position).where(
            Position.source_document_id.in_(doc_ids)).order_by(Position.id)).all():
        positions_by_doc[position.source_document_id].append(position)
    evidence_by_doc = defaultdict(list)
    for evidence in db.scalars(select(Evidence).where(
            Evidence.document_version_id.in_(doc_ids)).order_by(Evidence.id)).all():
        evidence_by_doc[evidence.document_version_id].append(evidence)

    item_ids = [item.id for items in items_by_doc.values() for item in items]
    paths_by_item = defaultdict(list)
    if item_ids:
        for link, path in db.execute(select(DevelopmentItemPath, Path).join(Path,
                DevelopmentItemPath.path_id == Path.id).where(
                DevelopmentItemPath.development_item_id.in_(item_ids)).order_by(Path.id)).all():
            paths_by_item[link.development_item_id].append(path)

    target_ids = {item.cycle_id for items in items_by_doc.values() for item in items if item.cycle_id}
    target_ids.update(position.id for positions in positions_by_doc.values() for position in positions)
    all_rules = db.scalars(select(EligibilityRule).where(
        EligibilityRule.target_id.in_(target_ids)).order_by(EligibilityRule.id)).all() if target_ids else []
    rules_by_target = defaultdict(list)
    for rule in all_rules:
        rules_by_target[rule.target_id].append(rule)
    relations = db.scalars(select(PolicyRelation).where(
        PolicyRelation.from_policy_id.in_(target_ids)).order_by(PolicyRelation.id)).all() if target_ids else []
    relations_by_target = defaultdict(list)
    for relation in relations:
        relations_by_target[relation.from_policy_id].append(relation)

    versions = db.scalars(select(DocumentVersion).where(
        DocumentVersion.source_endpoint_id.in_(endpoint_ids))).all()
    latest_by_source_item = {}
    for version in versions:
        key = (version.source_endpoint_id, version.source_item_id)
        previous = latest_by_source_item.get(key)
        if previous is None or version.version_no > previous.version_no:
            latest_by_source_item[key] = version
    archives = {archive.document_id: archive for archive in db.scalars(select(DocumentArchive).where(
        DocumentArchive.document_id.in_(doc_ids))).all()}
    gate_reasons = _bulk_gate_reasons(db, list(endpoints.values()), sources)

    for row, doc, endpoint, source in rows:
        items = items_by_doc.get(doc.id, [])
        positions = positions_by_doc.get(doc.id, [])
        targets = {item.cycle_id for item in items if item.cycle_id}
        targets.update(position.id for position in positions)
        doc_rules = [rule for target in targets for rule in rules_by_target.get(target, [])]
        doc_relations = [relation for target in targets
                         for relation in relations_by_target.get(target, [])]
        snapshot, blocks = _build_snapshot(
            doc, source, items, positions, evidence_by_doc.get(doc.id, []), doc_rules,
            doc_relations, paths_by_item)
        direct = doc.import_mode in {'system', 'demo'}
        if direct:
            # Direct ingestion publishes facts without claiming human verification.
            blocks = [] if items or positions else ['没有可展示的事项或岗位']
            if not endpoint.active or not source.active:
                blocks.append('来源或端点已停用')
        else:
            reason = gate_reasons.get(endpoint.id)
            if reason:
                blocks.append(reason)
        if doc.deleted_at:
            blocks.append('管理员已删除')
        if doc.import_mode == 'demo':
            from .config import settings
            if not settings.demo_mode or not doc.test_batch:
                blocks.append('测试数据仅在演示环境展示')
        if not direct and doc.canonical_url != endpoint.url:
            blocks.append("文档原始 URL 与已校准精确 URL 不一致")
        latest = latest_by_source_item.get((doc.source_endpoint_id, doc.source_item_id))
        if not latest or latest.id != doc.id:
            blocks.append("文档不是最新版本")
        archive = archives.get(doc.id)
        if not archive:
            blocks.append("缺少原始字节归档；历史文档需要重新导入原文件")
        elif hashlib.sha256(archive.content).hexdigest() != doc.content_hash:
            blocks.append("原始文件 SHA256 校验不通过")
        elif archive.is_fixture and doc.import_mode != 'demo':
            blocks.append("离线 Fixture 禁止发布为真实数据")
        # Defense in depth: disabling a source, changing a rule or calibration hides it immediately.
        if not blocks and canonical(snapshot) == row.snapshot:
            snapshot["document"]["publish_time"] = encoded(doc, ["publish_time"])["publish_time"]
            yield row, snapshot


def information_metadata(db, data):
    """Computed display metadata does not rewrite or invalidate signed snapshots."""
    if "publish_time" in data["document"]:
        return data["document"]
    doc = db.get(DocumentVersion, data['document']['id'])
    published = doc.publish_time if doc else None
    return {**data['document'], 'publish_time':encoded(doc,['publish_time'])['publish_time'] if published else None}


def information_state(item, now=None):
    now = now or datetime.now(UTC)
    kind = content_kind(item['title'])
    if kind == 'news_report':
        return 'report'
    due = datetime.fromisoformat(item['deadline']) if item['deadline'] else None
    if due:
        due = due.replace(tzinfo=UTC) if due.tzinfo is None else due
        if due <= now:
            return 'expired'
        start = datetime.fromisoformat(item['start_time']) if item['start_time'] else None
        if start:
            start = start.replace(tzinfo=UTC) if start.tzinfo is None else start
        return 'upcoming' if start and start > now else 'open'
    return 'needs_confirmation' if kind == 'application_notice' else 'reference'


@router.get("/catalog")
def catalog(q: str = Query("", max_length=100), path: str | None = None,
            region: str | None = None, offset: int = Query(0, ge=0),
            limit: int = Query(30, ge=1, le=100), status: Literal["all", "active", "expired"] = "all",
            school: Annotated[str, Query(max_length=120)] = '', year: Annotated[int | None, Query(ge=2000,le=2100)] = None,
            kind: Literal['all','application_notice','reference','news_report']='all',
            sort: Literal['recent','deadline']='recent', group_duplicates: bool = True,
            db: Session = Depends(get_db)):
    results = []
    codes = path_codes(db, path)
    for row, data in visible(db):
        document = information_metadata(db,data)
        for item in data["items"]:
            if q and q.casefold() not in (item["title"] + item["description"]).casefold():
                continue
            if path and not any(p["code"] in codes for p in item["paths"]):
                continue
            state = information_state(item)
            category = content_kind(item['title'])
            if (status == "expired" and state != 'expired') or (status == "active" and state in {'expired','report'}):
                continue
            if kind != 'all' and category != kind:
                continue
            if school and school not in data['source']['name'] + data['source']['publisher'] + item['title']:
                continue
            admission_year = re.search(r'20\d{2}',item['title'])
            admission_year = int(admission_year.group()) if admission_year else None
            if year and year != admission_year:
                continue
            if region and region not in {item["location"], data["source"]["region_code"]}:
                continue
            results.append({**item, "publication_id": row.id, "source": data["source"],
                            "document": document, 'content_kind':category,'availability':state,
                            'admission_year':admission_year})
    if sort == 'deadline':
        results.sort(key=lambda item:(item['deadline'] is None,item['deadline'] or '',item['id']))
    else:
        results.sort(key=lambda item:(item['document'].get('publish_time') or '',item['document']['fetched_at'],item['id']),reverse=True)
    raw_total = len(results)
    if group_duplicates:
        from .notice_duplicates import group_identical
        results = group_identical(results)
    return {"total": len(results), "raw_total": raw_total, "merged_items": raw_total - len(results),
            "items": results[offset:offset + limit]}


@router.get('/coverage')
def coverage(db: Session = Depends(get_db)):
    from .config import settings
    from .notice_watch import monitor_status
    by_source = {}
    for row,data in visible(db):
        source = data['source']
        entry = by_source.setdefault(source['source_code'],{'name':source['name'],'source_code':source['source_code'],
            'items':0,'notices':0,'dated_items':0,'dated_notices':0,'availability':{},'last_collected':None})
        entry['items'] += len(data['items'])
        entry['notices'] += sum(content_kind(i['title'])=='application_notice' for i in data['items'])
        entry['dated_items'] += sum(bool(i['deadline']) for i in data['items'])
        entry['dated_notices'] += sum(bool(i['deadline']) and content_kind(i['title'])=='application_notice' for i in data['items'])
        for item in data['items']:
            state = information_state(item)
            entry['availability'][state] = entry['availability'].get(state,0)+1
        entry['last_collected'] = max(entry['last_collected'] or '',data['document']['fetched_at'])
    from .public_source_catalog import catalog_status
    monitors = monitor_status(db)
    from .coverage_quality import summarize, recent_attempts
    from .operations import WorkerHeartbeat
    return {'registered_sources':db.scalar(select(func.count()).select_from(Source).where(Source.active.is_(True))),
        'sources_with_content':len(by_source),'sources':sorted(by_source.values(),key=lambda x:x['source_code']),
        'automatic_collection_enabled':settings.collector_enabled or settings.public_notice_watch_enabled,
        'monitors':monitors, 'source_catalog':catalog_status(monitors),
        'quality':{**summarize(monitors,list(by_source.values()),db.get(WorkerHeartbeat,'reminders')),
                   **recent_attempts(db)}}


def path_codes(db, code):
    rows = db.scalars(select(Path)).all()
    ids = {p.id for p in rows if p.code == code}
    while True:
        children = {p.id for p in rows if p.parent_id in ids} - ids
        if not children:
            break
        ids |= children
    return {p.code for p in rows if p.id in ids}


@router.get("/publications/{publication_id}")
def publication(publication_id: str, db: Session = Depends(get_db)):
    for row, data in visible(db):
        if row.id == publication_id:
            return {"id": row.id, "snapshot_hash": row.snapshot_hash, **data,
                    'document':information_metadata(db,data),
                    'items':[{**item,'content_kind':content_kind(item['title']),
                              'availability':information_state(item)} for item in data['items']]}
    raise HTTPException(404, "数据尚未发布、已撤回或需重新审核")


@router.get("/timeline")
def timeline(path: str | None = None, db: Session = Depends(get_db)):
    events = []
    codes = path_codes(db, path)
    for row, data in visible(db):
        for item in data["items"]:
            if path and not any(p["code"] in codes for p in item["paths"]):
                continue
            for field, label in (("start_time", "开始"), ("deadline", "截止/失效")):
                if item[field]:
                    events.append({"item_id": item["id"], "title": item["title"], "label": label,
                        "at": item[field], "publication_id": row.id, "document": data["document"]})
    return sorted(events, key=lambda event: (event["at"], event["item_id"]))


class RelationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    action: Literal["approve", "reject"]
    quote: str = Field(default="", max_length=2000)
    location: str = Field(default="", max_length=300)


@admin.patch("/relations/{relation_id}")
def review_relation(relation_id: int, body: RelationDecision,
                    user: str = Depends(require_admin), db: Session = Depends(get_db)):
    from .intake_models import PolicyRecord
    rel = db.get(PolicyRelation, relation_id)
    policy = db.get(PolicyRecord, rel.from_policy_id) if rel else None
    if not rel or not policy:
        raise HTTPException(404, "政策关系不存在")
    archive = db.get(DocumentArchive, policy.source_document_id)
    doc = db.get(DocumentVersion, policy.source_document_id)
    if body.action == "approve":
        if (not archive or not body.quote or not body.location or
                body.quote not in archive.content.decode("utf-8", errors="replace")):
            raise HTTPException(422, "关系须提供当前原始页面中的逐字依据与位置")
        endpoint = db.get(SourceEndpoint, doc.source_endpoint_id)
        evidence = Evidence(id=str(uuid4()), document_version_id=doc.id,
            source_id=endpoint.source_id, evidence_location=body.location,
            quote_or_normalized_fact=body.quote, extractor="human", evidence_type="dom",
            review_status="verified", verified_by=user, verified_at=datetime.now(UTC))
        db.add(evidence)
        rel.evidence_id, rel.review_status = evidence.id, "verified"
    else:
        rel.review_status = "rejected"
    audit(db, user, "policy_relation_" + body.action, f"policy_relation:{rel.id}")
    db.commit()
    return {"id": rel.id, "review_status": rel.review_status}


class Subscribe(BaseModel):
    model_config = ConfigDict(extra="forbid")
    publication_id: str
    item_id: str
    remind_before_hours: int | None = Field(default=None, ge=0, le=720)


@router.post("/subscriptions", status_code=201)
def subscribe(body: Subscribe, user: str = Depends(actor_id), db: Session = Depends(get_db)):
    data = publication(body.publication_id, db)
    item = next((i for i in data["items"] if i["id"] == body.item_id), None)
    if not item:
        raise HTTPException(404, "当前发布版本中没有此事项")
    due = datetime.fromisoformat(item["deadline"]) if item["deadline"] else None
    due = due.replace(tzinfo=UTC) if due and due.tzinfo is None else due
    remind_at = None
    if body.remind_before_hours is not None:
        if not due:
            raise HTTPException(422, "原文没有截止日期，不能推测提醒时间")
        remind_at = due - timedelta(hours=body.remind_before_hours)
        if remind_at <= datetime.now(UTC):
            raise HTTPException(422, "提醒时间已过，请选择更接近截止的提前量")
    row = db.scalar(select(DataSubscription).where(
        DataSubscription.user_id == user, DataSubscription.item_id == body.item_id))
    if row and row.status == "active" and row.publication_id == body.publication_id:
        if body.remind_before_hours is not None and row.remind_at is None:
            row.remind_at = remind_at
            db.commit()
        return {"id":row.id, "plan_id":row.plan_id, "status":row.status}
    now = datetime.now(UTC)
    plan = db.get(UserPlan, row.plan_id) if row else None
    if not plan or plan.user_id != user:
        plan = UserPlan(user_id=user, title=item["title"][:160], due_date=due,
            path_id=item["paths"][0]["id"] if item["paths"] else None, status="todo",
            note=f"数据事项：/data/{body.publication_id}；原文：{data['document']['canonical_url']}",
            created_at=now, updated_at=now)
        db.add(plan); db.flush()
    if not row:
        row = DataSubscription(id=str(uuid4()), user_id=user, item_id=body.item_id,
            publication_id=body.publication_id, plan_id=plan.id, title=item["title"], status="active")
        db.add(row)
    row.publication_id, row.remind_at = body.publication_id, remind_at
    row.status, row.alerted_at, row.read_at, row.message = "active", None, None, ""
    db.commit()
    return {"id":row.id, "plan_id":row.plan_id, "status":row.status}


@router.get("/subscriptions")
def subscriptions(offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
                  user: str = Depends(actor_id), db: Session = Depends(get_db)):
    return db.scalars(select(DataSubscription).where(
        DataSubscription.user_id == user, DataSubscription.status != "cancelled").order_by(
        DataSubscription.id).offset(offset).limit(limit)).all()


@router.patch("/subscriptions/{subscription_id}")
def subscription_action(subscription_id: str, action: Literal["read", "cancel"],
                        user: str = Depends(actor_id), db: Session = Depends(get_db)):
    row = db.scalar(select(DataSubscription).where(
        DataSubscription.id == subscription_id, DataSubscription.user_id == user))
    if not row:
        raise HTTPException(404, "订阅不存在")
    if action == "cancel":
        row.status = "cancelled"
    else:
        row.read_at = datetime.now(UTC)
    db.commit()
    return {"status":row.status, "read_at":row.read_at}


def deliver_data_alerts():
    """Persist exactly once per subscription; withdrawal overrides an old deadline alert."""
    now, delivered = datetime.now(UTC), 0
    with SessionLocal.begin() as db:
        rows = db.scalars(select(DataSubscription).where(DataSubscription.status == "active")).all()
        if not rows:
            return 0
        available = {row.id for row, _ in visible(db)}
        for row in rows:
            due = row.remind_at
            due = due.replace(tzinfo=UTC) if due and due.tzinfo is None else due
            if row.publication_id not in available:
                result = db.execute(update(DataSubscription).where(
                    DataSubscription.id == row.id, DataSubscription.status == "active",
                ).values(status="source_changed", alerted_at=now, read_at=None,
                    message="来源已更新、撤回或需重新审核；请勿继续依赖旧版条件和日期。"))
                delivered += result.rowcount
            elif due and due <= now and row.alerted_at is None:
                result = db.execute(update(DataSubscription).where(
                    DataSubscription.id == row.id, DataSubscription.status == "active",
                    DataSubscription.alerted_at.is_(None),
                ).values(alerted_at=now, message="订阅事项即将截止，请核对来源最新原文。"))
                delivered += result.rowcount
    return delivered

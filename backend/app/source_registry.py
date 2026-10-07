"""SourceRegistry seed, filtering API and endpoint governance."""
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .auth import require_admin
from .database import SessionLocal, get_db
from .governance import audit
from .intake_models import (
    EntityAlias,
    GeographicEntity,
    OpenDataResource,
    Source,
    SourceBlocker,
    SourceEndpoint,
    SourceEndpointCalibration,
)
from .models import Path as DevelopmentPath

router = APIRouter(prefix="/v1")


def stable_id(value: str) -> str:
    return str(uuid5(NAMESPACE_URL, "campusmate:" + value))


def _json(value):
    return json.dumps(value or [], ensure_ascii=False, separators=(",", ":"))


def seed_registry(db: Session, path: Path | None = None) -> dict[str, int]:
    config_path = path or Path(__file__).with_name("source_registry.yaml")
    body = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if path is None:
        from .public_source_catalog import registry_sources
        existing = {item['code'] for item in body['sources']}
        body['sources'].extend(item for item in registry_sources() if item['code'] not in existing)
    source_count = endpoint_count = 0
    for item in body["sources"]:
        source_id = stable_id("source:" + item["code"])
        row = db.get(Source, source_id)
        values = {
            "source_code": item["code"], "name": item["name"], "publisher": item["publisher"],
            "authority_level": item["authority_level"], "source_class": item["source_class"],
            "official": item.get("official", True), "jurisdiction_level": item["jurisdiction_level"],
            "region_code": item.get("region_code"), "school_id": item.get("school_id"),
            "supported_paths": _json(item.get("supported_paths")),
            "supported_item_types": _json(item.get("supported_item_types")),
            "base_url": item["base_url"], "active": item.get("active", True),
            "verified_at": datetime.fromisoformat(item.get("verified_at", "2026-09-29")).replace(tzinfo=UTC),
        }
        if row:
            for key, value in values.items():
                if key != "active":
                    setattr(row, key, value)
        else:
            row = Source(id=source_id, **values)
            db.add(row)
        source_count += 1
        for endpoint in item.get("endpoints", []):
            endpoint_id = stable_id(f"endpoint:{item['code']}:{endpoint['name']}")
            endpoint_row = db.get(SourceEndpoint, endpoint_id)
            endpoint_values = {
                "source_id": source_id, "name": endpoint["name"], "endpoint_type": endpoint["type"],
                "url": endpoint["url"], "access_tags": _json(endpoint.get("access_tags")),
                "auth_type": endpoint.get("auth_type", "none"), "secret_ref": endpoint.get("secret_ref"),
                "format": endpoint.get("format", "html"), "parser_type": endpoint.get("parser_type", ""),
                "rate_limit": endpoint.get("rate_limit", ""), "cors_status": endpoint.get("cors_status", "unknown"),
                "robots_status": endpoint.get("robots_status", "unknown"),
                "fetch_interval": str(endpoint.get("fetch_interval", "7d")),
                "automation_level": endpoint["automation_level"], "agent_mode": endpoint["agent_mode"],
                "license_note": endpoint.get("license_note", ""),
                "license_status": endpoint.get("license_status", "unknown"),
                "scheduled": endpoint.get("scheduled", False),
                "manual_takeover": endpoint.get("manual_takeover", False),
                "paused_reason": endpoint.get("paused_reason", ""),
                "active": endpoint.get("active", True),
            }
            if endpoint_row:
                for key, value in endpoint_values.items():
                    if key not in {"scheduled", "manual_takeover", "paused_reason", "active"}:
                        setattr(endpoint_row, key, value)
                approved = db.scalar(select(SourceEndpointCalibration).where(
                    SourceEndpointCalibration.endpoint_id == endpoint_id,
                    SourceEndpointCalibration.status == "approved",
                ).order_by(SourceEndpointCalibration.second_reviewed_at.desc()))
                if approved:
                    endpoint_row.url = approved.exact_url
                    endpoint_row.robots_status = approved.robots_status
                    endpoint_row.license_status = approved.license_status
                    endpoint_row.adapter_config = approved.adapter_config
            else:
                db.add(SourceEndpoint(id=endpoint_id, **endpoint_values))
            if endpoint.get("parser_type") == "OpenDataPlatformAdapter":
                resource_id = stable_id(f"open-data-resource:{item['code']}:{endpoint['name']}")
                blocker_id = stable_id(f"blocker:{item['code']}:{endpoint['name']}:api_key_required")
                resource_values = {"source_id": source_id, "endpoint_id": endpoint_id,
                                   "name": f"{item['name']} · {endpoint['name']}",
                                   "resource_url": endpoint["url"],
                                   "access_mode": endpoint.get("auth_type", "none"),
                                   "license_status": endpoint.get("license_status", "unknown"),
                                   "import_status": "blocked", "blocker_id": blocker_id}
                resource = db.get(OpenDataResource, resource_id)
                if resource:
                    for key, value in resource_values.items():
                        setattr(resource, key, value)
                else:
                    db.add(OpenDataResource(id=resource_id, **resource_values))
            endpoint_count += 1
        for blocker in item.get("blockers", []):
            endpoint_name = blocker.get("endpoint")
            endpoint_id = (stable_id(f"endpoint:{item['code']}:{endpoint_name}")
                           if endpoint_name else None)
            blocker_id = stable_id(f"blocker:{item['code']}:{endpoint_name or 'source'}:{blocker['type']}")
            blocker_row = db.get(SourceBlocker, blocker_id)
            blocker_values = {
                "source_id": source_id, "endpoint_id": endpoint_id,
                "blocker_type": blocker["type"],
                "detail": blocker["detail"], "required_action": blocker.get("required_action", ""),
                "observed_at": datetime.fromisoformat(blocker.get("observed_at", "2026-09-29")).replace(tzinfo=UTC),
            }
            if blocker_row:
                for key, value in blocker_values.items():
                    setattr(blocker_row, key, value)
            else:
                db.add(SourceBlocker(id=blocker_id, status=blocker.get("status", "open"),
                                     **blocker_values))
    path_count = seed_path_hierarchy(db)
    seed_overseas_geography(db)
    db.commit()
    return {"sources": source_count, "endpoints": endpoint_count, "paths": path_count}


def seed_overseas_geography(db: Session):
    """Seed stable ISO-backed IDs and bilingual aliases used by the M5 fixture."""
    entities = [("country:GB", "GB", "country", "United Kingdom", None),
                ("region:GB-ENG", "GB-ENG", "region", "England", "country:GB")]
    aliases = [("country", "country:GB", "United Kingdom", "en"),
               ("country", "country:GB", "UK", "en"),
               ("country", "country:GB", "英国", "zh-CN"),
               ("region", "region:GB-ENG", "England", "en"),
               ("region", "region:GB-ENG", "英格兰", "zh-CN")]
    for entity_id, code, entity_type, name, parent_id in entities:
        if not db.get(GeographicEntity, entity_id):
            db.add(GeographicEntity(id=entity_id, code=code, entity_type=entity_type,
                                    canonical_name=name, parent_id=parent_id))
    for entity_type, entity_id, alias, locale in aliases:
        normalized = " ".join(alias.casefold().split())
        if not db.scalar(select(EntityAlias).where(EntityAlias.entity_type == entity_type,
                                                    EntityAlias.normalized_alias == normalized)):
            db.add(EntityAlias(entity_type=entity_type, entity_id=entity_id, alias=alias,
                               normalized_alias=normalized, locale=locale))


def seed_path_hierarchy(db: Session) -> int:
    """Upsert the six documented path families and their entry mechanisms."""
    tree = [
        ("domestic_study", "国内升学", [("recommendation_exemption", "保研"),
                                       ("domestic_postgraduate_exam", "国内考研")]),
        ("overseas_study", "国（境）外升学", [("overseas_masters", "境外硕士"),
                                             ("overseas_doctorate", "境外博士")]),
        ("civil_service", "公务员与选调", [("national_civil_service", "国考"),
                                         ("provincial_civil_service", "省考"), ("selected_graduate", "选调")]),
        ("public_institution", "事业单位与公共机构", [("public_institution_general", "综合事业单位"),
                                                   ("public_education", "教育系统"),
                                                   ("public_health_research", "医疗卫生与科研")]),
        ("employment", "市场化就业", [("enterprise_employment", "企业就业"),
                                     ("state_owned_employment", "国央企招聘"),
                                     ("research_social_employment", "科研与社会组织")]),
        ("entrepreneurship", "创业", [("company_startup", "企业创业"), ("self_employment", "个体经营"),
                                     ("university_innovation", "高校创新创业项目"),
                                     ("startup_policy", "创业政策补贴与孵化")]),
    ]
    touched = 0
    for family_code, family_name, children in tree:
        family = db.scalar(select(DevelopmentPath).where(DevelopmentPath.code == family_code))
        if not family:
            family = db.scalar(select(DevelopmentPath).where(DevelopmentPath.name == family_name))
        if not family:
            family = DevelopmentPath(code=family_code, name=family_name, description=family_name,
                                     target_group="大学生", duration="长期", status="published")
            db.add(family); db.flush()
        else:
            family.code = family_code
        touched += 1
        for child_code, child_name in children:
            child = db.scalar(select(DevelopmentPath).where(DevelopmentPath.code == child_code))
            if not child:
                child = db.scalar(select(DevelopmentPath).where(DevelopmentPath.name == child_name))
            if not child:
                child = DevelopmentPath(code=child_code, parent_id=family.id, name=child_name,
                                        description=child_name, target_group="大学生", duration="按年度周期",
                                        status="published")
                db.add(child)
            else:
                child.code, child.parent_id = child_code, family.id
            touched += 1
    return touched


def source_out(row: Source, db: Session, include_endpoints=False):
    result = {c.name: getattr(row, c.name) for c in row.__table__.columns}
    result["supported_paths"] = json.loads(row.supported_paths)
    result["supported_item_types"] = json.loads(row.supported_item_types)
    if include_endpoints:
        endpoints = db.scalars(select(SourceEndpoint).where(SourceEndpoint.source_id == row.id)
                               .order_by(SourceEndpoint.name)).all()
        result["endpoints"] = [{**{c.name: getattr(ep, c.name) for c in ep.__table__.columns},
                                  "access_tags": json.loads(ep.access_tags)} for ep in endpoints]
    return result


@router.get("/sources")
def list_sources(path: str | None = None, region_code: str | None = None, school_id: str | None = None,
                 active: bool = True, limit: int = Query(500, ge=1, le=1000),
                 offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    stmt = select(Source).where(Source.active == active)
    if region_code:
        stmt = stmt.where(Source.region_code == region_code)
    if school_id:
        stmt = stmt.where(Source.school_id == school_id)
    if path:
        # Filter before pagination; a larger inventory must not hide later sources.
        stmt = stmt.where(or_(Source.supported_paths.contains(json.dumps(path), autoescape=True),
                              Source.supported_paths.contains('"all"', autoescape=True)))
    rows = db.scalars(stmt.order_by(Source.authority_level, Source.source_code).offset(offset).limit(limit)).all()
    return [source_out(row, db) for row in rows]


@router.get("/sources/{source_code}")
def source_detail(source_code: str, db: Session = Depends(get_db)):
    row = db.scalar(select(Source).where(Source.source_code == source_code))
    if not row:
        raise HTTPException(404, "信息源不存在")
    return source_out(row, db, include_endpoints=True)


@router.post("/admin/sources/seed")
def run_seed(user: str = Depends(require_admin), db: Session = Depends(get_db)):
    result = seed_registry(db)
    audit(db, user, "source_registry_seed", "source_registry", result)
    db.commit()
    return result


if __name__ == "__main__":
    with SessionLocal() as session:
        print(seed_registry(session))

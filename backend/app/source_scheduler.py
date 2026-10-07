"""Durable scheduler for governed SourceEndpoint collection.

Seeded endpoints are not scheduled automatically. An administrator must first
verify an exact URL and explicitly enable scheduling.
"""
import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
from uuid import uuid4

from sqlalchemy import or_, select, update

from .adapters.base import RawArtifact
from .adapters.education import MoEPolicyAdapter, UniversityNoticeAdapter, PublicNoticeAdapter, YZChsiAdapter
from .adapters.entrepreneurship import GovernmentPolicyAdapter
from .adapters.overseas import OverseasRegistryAdapter, OverseasUniversityProgramAdapter
from .adapters.public_recruitment import (
    InstitutionRecruitmentAdapter,
    MohrssPublicJobAdapter,
    RegionalRecruitmentDirectoryAdapter,
)
from .collector_http import FetchError, collect_bytes_conditional
from .database import SessionLocal
from .intake import (
    ingest_civil_service_workbook,
    ingest_education_html,
    ingest_entrepreneurship_policy,
    ingest_overseas_program,
    ingest_overseas_registry,
    ingest_public_recruitment,
    ingest_public_notice,
    record_document_version,
)
from .intake_governance import gate_reason
from .intake_models import (
    DevelopmentItem,
    DocumentVersion,
    Source,
    SourceChangeReview,
    SourceEndpoint,
    SourceEndpointRun,
)
from .parsers import ParseError, extract_isolated

HIGH_RISK_PATTERN = re.compile(
    r"金额|截止|报名|考试|年龄|学历|毕业|专业|GPA|排名|语言|户籍|生源|社保|政治面貌|基层工作|股权|失效"
)

IMPLEMENTED_PARSERS = {'CivilServiceWorkbookAdapter','MoEPolicyAdapter','YZChsiAdapter',
    'UniversityNoticeAdapter','PublicNoticeAdapter','InstitutionRecruitmentAdapter','MohrssPublicJobAdapter',
    'RegionalRecruitmentDirectoryAdapter','OverseasRegistryAdapter',
    'OverseasUniversityProgramAdapter','GovernmentPolicyAdapter','GenericTextAdapter'}


def ensure_supported_parser(parser):
    if parser not in IMPLEMENTED_PARSERS:
        raise ParseError(f'未实现的采集适配器：{parser or "未配置"}，请人工接管，不能视为采集成功')


def _same_official_host(candidate_url: str, official_url: str) -> bool:
    candidate = (urlsplit(candidate_url).hostname or "").lower()
    official = (urlsplit(official_url).hostname or "").lower()
    return bool(candidate and official and (candidate == official or candidate.endswith("." + official)))


def interval_delta(value: str) -> timedelta | None:
    normalized = (value or "").strip().lower()
    match = re.match(r"^(\d+)\s*([hd])", normalized)
    if match:
        amount = int(match.group(1))
        return timedelta(hours=amount) if match.group(2) == "h" else timedelta(days=amount)
    if normalized == "annual":
        return timedelta(days=365)
    if normalized == "version_event":
        return timedelta(days=30)
    if normalized in {"manual", ""}:
        return None
    raise ValueError(f"无法识别刷新周期：{value}")


def retry_delay(error: FetchError, attempts: int, now: datetime) -> timedelta:
    raw = (error.retry_after or "").strip()
    if raw.isdigit():
        return timedelta(seconds=min(max(int(raw), 1), 86400))
    if raw:
        try:
            target = parsedate_to_datetime(raw)
            target = target.replace(tzinfo=UTC) if target.tzinfo is None else target.astimezone(UTC)
            return min(max(target - now, timedelta(seconds=1)), timedelta(days=1))
        except (TypeError, ValueError, OverflowError):
            pass
    return timedelta(seconds=min(60 * (2 ** max(attempts - 1, 0)), 3600))


def enqueue_endpoint(db, endpoint_id: str, source_item_id: str = "default"):
    endpoint = db.get(SourceEndpoint, endpoint_id)
    source = db.get(Source, endpoint.source_id) if endpoint else None
    if not endpoint or not source or not endpoint.active or not source.active or not endpoint.scheduled:
        raise ValueError("端点未启用调度或所属来源已停用")
    reason = gate_reason(db, endpoint, automated=True)
    if reason:
        raise ValueError(reason)
    existing = db.scalar(select(SourceEndpointRun).where(
        SourceEndpointRun.endpoint_id == endpoint_id,
        SourceEndpointRun.source_item_id == source_item_id,
        SourceEndpointRun.status.in_(["queued", "running", "retry"]),
    ))
    if existing:
        return existing
    now = datetime.now(UTC)
    run = SourceEndpointRun(id=str(uuid4()), endpoint_id=endpoint_id, source_item_id=source_item_id,
                            status="queued", attempts=0, ready_at=now, created_at=now)
    db.add(run)
    db.flush()
    return run


def schedule_due_endpoints(now: datetime | None = None):
    now = now or datetime.now(UTC)
    scheduled = 0
    with SessionLocal.begin() as db:
        endpoints = db.scalars(select(SourceEndpoint).join(Source, Source.id == SourceEndpoint.source_id).where(
            SourceEndpoint.active.is_(True), SourceEndpoint.scheduled.is_(True),
            SourceEndpoint.manual_takeover.is_(False), Source.active.is_(True),
            or_(SourceEndpoint.next_run_at.is_(None), SourceEndpoint.next_run_at <= now),
        ).order_by(SourceEndpoint.next_run_at, SourceEndpoint.id).limit(20)).all()
        for endpoint in endpoints:
            if json.loads(endpoint.adapter_config or '{}').get('collection_mode') == 'public_notice_watch':
                continue
            reason = gate_reason(db, endpoint, automated=True)
            if reason:
                endpoint.scheduled, endpoint.next_run_at = False, None
                endpoint.paused_reason = reason
                continue
            delta = interval_delta(endpoint.fetch_interval)
            if delta is None:
                endpoint.scheduled = False
                endpoint.paused_reason = "刷新周期为 manual，不能自动调度"
                continue
            enqueue_endpoint(db, endpoint.id)
            endpoint.next_run_at = now + delta
            scheduled += 1
    return scheduled


def _parse_generic(data: bytes, format_name: str) -> str:
    if format_name in {"json", "csv"}:
        text = data.decode("utf-8-sig")
        if format_name == "json":
            return json.dumps(json.loads(text), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if len(text) < 20:
            raise ParseError("CSV 有效内容不足 20 字符")
        return text
    if format_name not in {"html", "pdf", "xlsx", "text"}:
        raise ParseError(f"调度器暂不支持 {format_name} 格式，请人工接管")
    return extract_isolated(data, format_name).text


def _change_review(db, endpoint: SourceEndpoint, document: DocumentVersion, raw_text: str):
    if db.scalar(select(SourceChangeReview).where(
            SourceChangeReview.document_version_id == document.id)):
        return
    changed_fields = sorted(set(HIGH_RISK_PATTERN.findall(raw_text)))
    risk = "high" if changed_fields else "medium"
    db.add(SourceChangeReview(endpoint_id=endpoint.id, document_version_id=document.id,
                              risk_level=risk, status="pending",
                              summary=f"{endpoint.name} 发现第 {document.version_no} 个版本，需核验变化和证据",
                              changed_fields=json.dumps(changed_fields, ensure_ascii=False),
                              created_at=datetime.now(UTC)))


def _finish_failure(db, run: SourceEndpointRun, endpoint: SourceEndpoint, error: Exception,
                    now: datetime):
    endpoint.consecutive_failures += 1
    endpoint.last_attempt_at = now
    endpoint.last_error = str(error)[:500]
    status_code = error.status_code if isinstance(error, FetchError) else None
    run.http_status = status_code
    run.error = endpoint.last_error
    delay = retry_delay(error, run.attempts, now) if isinstance(error, FetchError) else timedelta(
        seconds=min(60 * (2 ** max(run.attempts - 1, 0)), 3600))
    if endpoint.consecutive_failures >= endpoint.max_failures or run.attempts >= endpoint.max_failures:
        run.status = "failed"
        run.finished_at = now
        endpoint.scheduled = False
        endpoint.manual_takeover = True
        endpoint.paused_reason = f"连续失败 {endpoint.consecutive_failures} 次，等待人工接管"
        endpoint.next_run_at = None
    else:
        run.status = "retry"
        run.ready_at = now + delay
        endpoint.next_run_at = run.ready_at
    run.lease_until = None
    run.lease_token = None


def process_endpoint_once():
    now, token = datetime.now(UTC), str(uuid4())
    with SessionLocal.begin() as db:
        db.execute(update(SourceEndpointRun).where(
            SourceEndpointRun.status == "running", SourceEndpointRun.lease_until < now,
        ).values(status="retry", ready_at=now, lease_token=None, lease_until=None))
        candidates = db.scalars(select(SourceEndpointRun.id).where(
            SourceEndpointRun.status.in_(["queued", "retry"]), SourceEndpointRun.ready_at <= now,
        ).order_by(SourceEndpointRun.ready_at, SourceEndpointRun.id).limit(20)).all()
        run_id = None
        for candidate in candidates:
            claimed = db.execute(update(SourceEndpointRun).where(
                SourceEndpointRun.id == candidate,
                SourceEndpointRun.status.in_(["queued", "retry"]),
                SourceEndpointRun.ready_at <= now,
            ).values(status="running", attempts=SourceEndpointRun.attempts + 1,
                     lease_token=token, lease_until=now + timedelta(minutes=5)))
            if claimed.rowcount:
                run_id = candidate
                break
        if run_id is None:
            return False
        run = db.get(SourceEndpointRun, run_id, populate_existing=True)
        endpoint = db.get(SourceEndpoint, run.endpoint_id)
        source = db.get(Source, endpoint.source_id) if endpoint else None
        if (not endpoint or not source or not endpoint.active or not source.active
                or not endpoint.scheduled or gate_reason(db, endpoint, automated=True)):
            run.status, run.finished_at, run.lease_token, run.lease_until = "cancelled", now, None, None
            return True
        endpoint.last_attempt_at = now
        latest = db.scalar(select(DocumentVersion).where(
            DocumentVersion.source_endpoint_id == endpoint.id,
            DocumentVersion.source_item_id == run.source_item_id,
        ).order_by(DocumentVersion.version_no.desc()).limit(1))
        url, format_name, parser_type = endpoint.url, endpoint.format, endpoint.parser_type
        etag = latest.etag if latest else None
        last_modified = latest.last_modified if latest else None
        config = json.loads(endpoint.adapter_config or "{}")
        official_url = source.base_url

    try:
        ensure_supported_parser(parser_type)
        fetched = collect_bytes_conditional(url, etag=etag, last_modified=last_modified)
        if not _same_official_host(fetched["final_url"], official_url):
            raise FetchError("来源重定向到了非官方域名，已拒绝采集")
        if fetched["not_modified"]:
            parsed_text = None
        elif parser_type == "CivilServiceWorkbookAdapter":
            required = {"cycle_code", "cycle_name", "cycle_year"}
            if not required.issubset(config):
                raise ParseError("CivilServiceWorkbookAdapter 缺少 cycle_code、cycle_name 或 cycle_year")
            parsed_text = None
        elif parser_type == 'PublicNoticeAdapter':
            PublicNoticeAdapter(config['topic'], config.get('article_selector'), config.get('title_selector')).parse(RawArtifact(fetched['data'], fetched['final_url'],
                run.source_item_id, fetched['content_type']))
            parsed_text = None
        elif parser_type in {"MoEPolicyAdapter", "YZChsiAdapter", "UniversityNoticeAdapter"}:
            if parser_type == "UniversityNoticeAdapter" and config.get('notice_scope') != 'university':
                required = {"institution_code", "institution_name", "program_code", "program_name",
                            "path_code", "cycle_year"}
                if not required.issubset(config):
                    raise ParseError("UniversityNoticeAdapter 缺少学校、专业、路径或年度配置")
            adapter = {"MoEPolicyAdapter": MoEPolicyAdapter, "YZChsiAdapter": YZChsiAdapter,
                       "UniversityNoticeAdapter": UniversityNoticeAdapter}[parser_type]()
            adapter.parse(RawArtifact(content=fetched["data"], canonical_url=fetched["final_url"],
                                      source_item_id=run.source_item_id,
                                      content_type=fetched["content_type"]))
            parsed_text = None
        elif parser_type in {"InstitutionRecruitmentAdapter", "MohrssPublicJobAdapter",
                             "RegionalRecruitmentDirectoryAdapter"}:
            if parser_type != "RegionalRecruitmentDirectoryAdapter":
                required = {"cycle_code", "cycle_name", "cycle_year", "path_code"}
                if not required.issubset(config):
                    raise ParseError("公开招聘 Adapter 缺少周期、年度或路径配置")
            adapter = {"InstitutionRecruitmentAdapter": InstitutionRecruitmentAdapter,
                       "MohrssPublicJobAdapter": MohrssPublicJobAdapter,
                       "RegionalRecruitmentDirectoryAdapter": RegionalRecruitmentDirectoryAdapter
                       }[parser_type]()
            adapter.parse(RawArtifact(content=fetched["data"], canonical_url=fetched["final_url"],
                                      source_item_id=run.source_item_id,
                                      content_type=fetched["content_type"]))
            parsed_text = None
        elif parser_type in {"OverseasRegistryAdapter", "OverseasUniversityProgramAdapter"}:
            if parser_type == "OverseasUniversityProgramAdapter":
                required = {"institution_id", "program_code", "program_name", "path_code"}
                if not required.issubset(config):
                    raise ParseError("境外大学项目端点缺少院校、项目或路径配置")
            adapter = (OverseasRegistryAdapter() if parser_type == "OverseasRegistryAdapter"
                       else OverseasUniversityProgramAdapter())
            adapter.parse(RawArtifact(content=fetched["data"], canonical_url=fetched["final_url"],
                                      source_item_id=run.source_item_id,
                                      content_type=fetched["content_type"]))
            parsed_text = None
        elif parser_type == "GovernmentPolicyAdapter":
            GovernmentPolicyAdapter().parse(RawArtifact(
                content=fetched["data"], canonical_url=fetched["final_url"],
                source_item_id=run.source_item_id, content_type=fetched["content_type"]))
            parsed_text = None
        else:
            parsed_text = _parse_generic(fetched["data"], format_name)
        failure = None
    except (FetchError, ParseError, UnicodeError, ValueError) as exc:
        fetched, parsed_text, failure = None, None, exc
    except Exception:  # noqa: BLE001 - durable worker records a sanitized error and preserves the lease fence
        fetched, parsed_text, failure = None, None, RuntimeError("端点采集或解析发生未预期错误")

    with SessionLocal.begin() as db:
        fence = db.execute(update(SourceEndpointRun).where(
            SourceEndpointRun.id == run_id, SourceEndpointRun.status == "running",
            SourceEndpointRun.lease_token == token,
            SourceEndpointRun.lease_until > datetime.now(UTC),
        ).values(lease_token=None))
        if not fence.rowcount:
            return True
        run = db.get(SourceEndpointRun, run_id, populate_existing=True)
        endpoint = db.get(SourceEndpoint, run.endpoint_id)
        source = db.get(Source, endpoint.source_id) if endpoint else None
        if (not endpoint or not source or not endpoint.active or not source.active
                or not endpoint.scheduled or gate_reason(db, endpoint, automated=True)
                or endpoint.url != url or endpoint.parser_type != parser_type
                or json.loads(endpoint.adapter_config or "{}") != config):
            run.status, run.finished_at, run.lease_until = "cancelled", datetime.now(UTC), None
            return True
        completed_at = datetime.now(UTC)
        if failure:
            _finish_failure(db, run, endpoint, failure, completed_at)
            return True
        if fetched["not_modified"]:
            latest = db.scalar(select(DocumentVersion).where(
                DocumentVersion.source_endpoint_id == endpoint.id,
                DocumentVersion.source_item_id == run.source_item_id,
            ).order_by(DocumentVersion.version_no.desc()).limit(1))
            if not latest:
                _finish_failure(db, run, endpoint, ParseError("来源返回 304，但本地没有历史版本"), completed_at)
                return True
            latest.last_seen_at = completed_at
            endpoint.last_success_at, endpoint.last_error, endpoint.consecutive_failures = completed_at, "", 0
            run.status, run.document_version_id, run.http_status = "unchanged", latest.id, 304
        else:
            raw = RawArtifact(content=fetched["data"], canonical_url=fetched["final_url"],
                              source_item_id=run.source_item_id, content_type=fetched["content_type"],
                              etag=fetched.get("etag"), last_modified=fetched.get("last_modified"))
            try:
                # Partial entities and raw archives must roll back together if normalization fails.
                with db.begin_nested():
                    db.info['import_mode'] = 'system'
                    document, changed = _persist_fetched(
                        db, source, endpoint, raw, config, parsed_text, completed_at)
                    db.flush()
                    from .data_catalog import auto_publish
                    auto_publish(db, document)
                    # The governed collector writes document_versions while search
                    # reads source_documents; bridge them or the text stays invisible.
                    publish_collected_document(db, document)
            except Exception:  # noqa: BLE001 - sanitize errors after rolling back the ingestion savepoint
                _finish_failure(db, run, endpoint,
                    ParseError("解析或落库失败，已回滚本次数据；请核对配置与原文"), completed_at)
                return True
            if changed:
                _change_review(db, endpoint, document, document.raw_text)
            run.status = "succeeded" if changed else "unchanged"
            run.document_version_id, run.http_status = document.id, fetched["status_code"]
            endpoint.last_success_at, endpoint.last_error, endpoint.consecutive_failures = completed_at, "", 0
        run.error, run.finished_at, run.lease_until = "", completed_at, None
    return True


def _persist_fetched(db, source, endpoint, raw, config, parsed_text, completed_at):
    parser = endpoint.parser_type
    ensure_supported_parser(parser)
    if parser == "CivilServiceWorkbookAdapter":
        result = ingest_civil_service_workbook(db, source, endpoint, raw,
            config["cycle_code"], config["cycle_name"], int(config["cycle_year"]))
    elif parser in {"MoEPolicyAdapter", "YZChsiAdapter", "UniversityNoticeAdapter"}:
        result = ingest_education_html(db, source, endpoint, raw, config)
    elif parser == 'PublicNoticeAdapter':
        result = ingest_public_notice(db, source, endpoint, raw, config)
    elif parser in {"InstitutionRecruitmentAdapter", "MohrssPublicJobAdapter", "RegionalRecruitmentDirectoryAdapter"}:
        result = ingest_public_recruitment(db, source, endpoint, raw, config)
    elif parser in {"OverseasRegistryAdapter", "OverseasUniversityProgramAdapter"}:
        result = (ingest_overseas_registry(db, source, endpoint, raw, config)
                  if parser == "OverseasRegistryAdapter"
                  else ingest_overseas_program(db, source, endpoint, raw, config))
    elif parser == "GovernmentPolicyAdapter":
        result = ingest_entrepreneurship_policy(db, source, endpoint, raw, config)
    else:
        return record_document_version(db, endpoint, raw, parsed_text, completed_at)
    return db.get(DocumentVersion, result["document_version_id"]), result["changed"]


def publish_collected_document(db, document):
    """Mirror a collected document into the archive tables and publish it for search.

    Why this bridge is required
    ---------------------------
    The project has two collector generations writing two different tables:

        collector.py         -> source_documents   (what the knowledge search reads)
        source_scheduler.py  -> document_versions  (the governed collector)

    Both the governed collector and the public-notice monitor write versioned
    source archives. This bridge mirrors the SAME id for searchable chunks and
    citations. Callers enforce their collection and publication gates; notice
    monitoring preserves evidence without claiming human verification or licence
    approval. This function does not grant eligibility-rule verification.

    Idempotent: re-collecting an unchanged document updates rows in place.
    """
    from .knowledge import publish_system_document
    from .sources import SourceDocument, SourceHead

    key = hashlib.sha256(document.canonical_url.encode()).hexdigest()
    head = db.get(SourceHead, key)
    if head:
        head.document_id = document.id
    else:
        db.add(SourceHead(url_hash=key, source_url=document.canonical_url,
                          document_id=document.id))
    doc = db.get(SourceDocument, document.id)
    if doc:
        doc.source_url, doc.content_hash = document.canonical_url, document.content_hash
        doc.raw_text, doc.fetched_at = document.raw_text, document.fetched_at
    else:
        db.add(SourceDocument(id=document.id, source_url=document.canonical_url,
                              content_hash=document.content_hash, raw_text=document.raw_text,
                              fetched_at=document.fetched_at, archived_at=datetime.now(UTC)))
    db.flush()
    item = db.scalar(select(DevelopmentItem).where(
        DevelopmentItem.source_document_id == document.id))
    return publish_system_document(
        db, document.id,
        item.title if item else document.canonical_url,
        item.item_type if item else "policy")

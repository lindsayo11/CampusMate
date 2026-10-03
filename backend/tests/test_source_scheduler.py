from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app import source_scheduler
from app.collector_http import FetchError
from app.database import SessionLocal
from app.intake_models import (
    DocumentVersion,
    Source,
    SourceChangeReview,
    SourceEndpoint,
    SourceEndpointCalibration,
    SourceEndpointRun,
)
from app.main import app
from app.source_scheduler import interval_delta, process_endpoint_once, schedule_due_endpoints


def make_endpoint(*, fetch_interval="12h", max_failures=3):
    suffix = str(uuid4())
    source = Source(
        id=str(uuid4()), source_code="TEST-SCHED-" + suffix[:24], name="调度测试源", publisher="测试发布者",
        authority_level="A", source_class="government", official=True,
        jurisdiction_level="national", supported_paths="[]", supported_item_types="[]",
        base_url="https://example.edu/", active=True, verified_at=datetime.now(UTC),
    )
    endpoint = SourceEndpoint(
        id=str(uuid4()), source_id=source.id, name="fixture", endpoint_type="html",
        url="https://example.edu/notice", access_tags='["DIRECT"]', auth_type="none",
        format="text", parser_type="GenericTextAdapter", rate_limit="1/s", cors_status="unknown",
        robots_status="allowed", license_status="permitted", fetch_interval=fetch_interval, automation_level="AUTO-1",
        agent_mode="REVIEW", license_note="测试 Fixture", active=True, scheduled=True,
        next_run_at=datetime.now(UTC) - timedelta(seconds=1), max_failures=max_failures,
    )
    with SessionLocal.begin() as db:
        db.add_all([source, endpoint])
        db.add(SourceEndpointCalibration(id=str(uuid4()), endpoint_id=endpoint.id,
            exact_url=endpoint.url, robots_status="allowed", terms_status="permitted",
            license_status="permitted", field_mapping='{"body":"body"}', adapter_config="{}",
            checked_at=datetime.now(UTC), submitted_by="test-submitter", status="approved",
            first_reviewed_by="test-first", second_reviewed_by="test-second",
            second_reviewed_at=datetime.now(UTC), created_at=datetime.now(UTC),
            proof='{"robots_url":"https://example.edu/robots.txt","robots_quote":"allow",'
                  '"terms_url":"https://example.edu/terms","terms_quote":"allowed",'
                  '"license_url":"https://example.edu/license","license_quote":"allowed",'
                  '"page_sha256":"' + 'a' * 64 + '"}'))
    return source.id, endpoint.id


def success(data: bytes, etag='"v1"'):
    return {"not_modified": False, "data": data, "content_type": "text/plain",
            "final_url": "https://example.edu/notice", "status_code": 200,
            "etag": etag, "last_modified": "Tue, 29 Sep 2026 00:00:00 GMT"}


def test_interval_parser_is_bounded_and_explicit():
    assert interval_delta("12h_in_season") == timedelta(hours=12)
    assert interval_delta("7d") == timedelta(days=7)
    assert interval_delta("annual") == timedelta(days=365)
    assert interval_delta("manual") is None


def test_endpoint_scheduler_version_change_304_and_review(monkeypatch):
    _, endpoint_id = make_endpoint()
    body = "官方公告。报名截止日期为2026年10月20日，请以原文为准。".encode()
    monkeypatch.setattr(source_scheduler, "collect_bytes_conditional", lambda *a, **kw: success(body))
    assert schedule_due_endpoints() == 1
    assert process_endpoint_once()
    with SessionLocal() as db:
        run = db.scalar(select(SourceEndpointRun).where(SourceEndpointRun.endpoint_id == endpoint_id))
        document = db.get(DocumentVersion, run.document_version_id)
        review = db.scalar(select(SourceChangeReview).where(
            SourceChangeReview.document_version_id == document.id))
        assert run.status == "succeeded" and document.version_no == 1
        assert document.etag == '"v1"' and review.risk_level == "high"
        first_id, first_seen = document.id, document.last_seen_at

    with SessionLocal.begin() as db:
        endpoint = db.get(SourceEndpoint, endpoint_id)
        endpoint.next_run_at = datetime.now(UTC) - timedelta(seconds=1)
    monkeypatch.setattr(source_scheduler, "collect_bytes_conditional", lambda *a, **kw: {
        "not_modified": True, "data": b"", "content_type": "", "final_url": "https://example.edu/notice",
        "status_code": 304, "etag": '"v1"', "last_modified": None})
    assert schedule_due_endpoints() == 1 and process_endpoint_once()
    with SessionLocal() as db:
        documents = db.scalars(select(DocumentVersion).where(
            DocumentVersion.source_endpoint_id == endpoint_id)).all()
        latest_run = db.scalars(select(SourceEndpointRun).where(
            SourceEndpointRun.endpoint_id == endpoint_id).order_by(SourceEndpointRun.created_at.desc())).first()
        assert len(documents) == 1 and documents[0].id == first_id
        assert documents[0].last_seen_at >= first_seen and latest_run.status == "unchanged"

    with SessionLocal.begin() as db:
        db.get(SourceEndpoint, endpoint_id).next_run_at = datetime.now(UTC) - timedelta(seconds=1)
    changed = "官方公告更新。报名截止日期调整为2026年10月21日，请以原文为准。".encode()
    monkeypatch.setattr(source_scheduler, "collect_bytes_conditional",
                        lambda *a, **kw: success(changed, etag='"v2"'))
    assert schedule_due_endpoints() == 1 and process_endpoint_once()
    with SessionLocal() as db:
        documents = db.scalars(select(DocumentVersion).where(
            DocumentVersion.source_endpoint_id == endpoint_id).order_by(DocumentVersion.version_no)).all()
        reviews = db.scalars(select(SourceChangeReview).where(
            SourceChangeReview.endpoint_id == endpoint_id)).all()
        assert [item.version_no for item in documents] == [1, 2]
        assert documents[1].previous_id == documents[0].id and len(reviews) == 2


def test_worker_rechecks_revoked_calibration_before_http(monkeypatch):
    _, endpoint_id = make_endpoint()
    assert schedule_due_endpoints() == 1
    with SessionLocal.begin() as db:
        calibration = db.scalar(select(SourceEndpointCalibration).where(
            SourceEndpointCalibration.endpoint_id == endpoint_id))
        calibration.status = "rejected"
    def forbidden(*args, **kwargs):
        raise AssertionError("No network after revocation")
    monkeypatch.setattr(source_scheduler, "collect_bytes_conditional", forbidden)
    assert process_endpoint_once()
    with SessionLocal() as db:
        run = db.scalar(select(SourceEndpointRun).where(SourceEndpointRun.endpoint_id == endpoint_id))
        assert run.status == "cancelled"


def test_worker_rolls_back_partial_ingestion_and_records_failure(monkeypatch):
    _, endpoint_id = make_endpoint(max_failures=1)
    assert schedule_due_endpoints() == 1
    monkeypatch.setattr(source_scheduler, "collect_bytes_conditional", lambda *a, **kw:
        success("用于验证事务回滚的公告正文，满足最小文本长度要求。".encode()))
    original = source_scheduler._persist_fetched
    def fail_after_write(*args, **kwargs):
        original(*args, **kwargs)
        raise ValueError("sensitive internal data should never reach API")
    monkeypatch.setattr(source_scheduler, "_persist_fetched", fail_after_write)
    assert process_endpoint_once()
    with SessionLocal() as db:
        run = db.scalar(select(SourceEndpointRun).where(SourceEndpointRun.endpoint_id == endpoint_id))
        assert run.status == "failed"
        assert "sensitive" not in run.error
        assert not db.scalar(select(DocumentVersion).where(DocumentVersion.source_endpoint_id == endpoint_id))


def test_retry_after_then_manual_takeover(monkeypatch):
    _, endpoint_id = make_endpoint(max_failures=3)
    assert schedule_due_endpoints() == 1

    def limited(*args, **kwargs):
        raise FetchError("限流", status_code=429, retry_after="120")

    monkeypatch.setattr(source_scheduler, "collect_bytes_conditional", limited)
    for attempt in range(1, 4):
        assert process_endpoint_once()
        with SessionLocal.begin() as db:
            run = db.scalar(select(SourceEndpointRun).where(SourceEndpointRun.endpoint_id == endpoint_id))
            endpoint = db.get(SourceEndpoint, endpoint_id)
            assert run.attempts == attempt
            if attempt < 3:
                assert run.status == "retry" and run.http_status == 429
                assert run.ready_at.replace(tzinfo=UTC) >= datetime.now(UTC) + timedelta(seconds=100)
                run.ready_at = datetime.now(UTC) - timedelta(seconds=1)
            else:
                assert run.status == "failed"
                assert endpoint.manual_takeover and not endpoint.scheduled
                assert "连续失败" in endpoint.paused_reason


def test_concurrent_workers_claim_one_endpoint_run(monkeypatch):
    _, endpoint_id = make_endpoint()
    assert schedule_due_endpoints() == 1
    calls = []
    monkeypatch.setattr(source_scheduler, "collect_bytes_conditional",
                        lambda *a, **kw: calls.append(1) or success(
                            "官方测试公告正文，内容足够用于调度并发测试。".encode()))
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(lambda _: process_endpoint_once(), range(2)))
    with SessionLocal() as db:
        runs = db.scalars(select(SourceEndpointRun).where(SourceEndpointRun.endpoint_id == endpoint_id)).all()
        assert len(runs) == 1 and runs[0].status == "succeeded"
    assert len(calls) == 1


def test_login_endpoint_cannot_be_scheduled():
    with TestClient(app) as client:
        endpoint = next(item for item in client.get("/v1/sources/CM-GR-002").json()["endpoints"]
                        if item["endpoint_type"] == "login")
        response = client.patch(f"/v1/admin/intake/endpoints/{endpoint['id']}", json={
            "action": "enable", "reason": "测试登录边界", "url": endpoint["url"],
            "adapter_config": {},
        })
        assert response.status_code == 422
        assert "无认证" in response.json()["detail"]


def test_endpoint_cannot_be_repointed_to_another_allowlisted_host(monkeypatch):
    _, endpoint_id = make_endpoint()
    with SessionLocal.begin() as db:
        endpoint = db.get(SourceEndpoint, endpoint_id)
        endpoint.scheduled, endpoint.next_run_at = False, None
    monkeypatch.setattr("app.intake_api.validate_url", lambda value: value)
    with TestClient(app) as client:
        response = client.patch(f"/v1/admin/intake/endpoints/{endpoint_id}", json={
            "action": "enable", "reason": "验证来源域名边界",
            "url": "https://other.example/notice", "adapter_config": {},
        })
        assert response.status_code == 422
        assert "官方域名" in response.json()["detail"]


def test_scheduler_rejects_cross_domain_redirect(monkeypatch):
    _, endpoint_id = make_endpoint(max_failures=1)
    assert schedule_due_endpoints() == 1
    monkeypatch.setattr(source_scheduler, "collect_bytes_conditional", lambda *a, **kw: {
        **success("非官方重定向内容".encode()), "final_url": "https://other.example/notice",
    })
    assert process_endpoint_once()
    with SessionLocal() as db:
        run = db.scalar(select(SourceEndpointRun).where(SourceEndpointRun.endpoint_id == endpoint_id))
        endpoint = db.get(SourceEndpoint, endpoint_id)
        assert run.status == "failed" and endpoint.manual_takeover
        assert "非官方域名" in run.error

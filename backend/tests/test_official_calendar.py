"""Isolated synthetic fixtures. No requests to real sources or preview DB writes."""
import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.main import list_opportunities
from app.database import Base
from app.data_catalog import timeline
from app.intake_models import DevelopmentItem, DocumentArchive, DocumentVersion
from app.models import Opportunity
from app.real_content import REAL_CONTENT, _parse

spec = importlib.util.spec_from_file_location("official_calendar_import",
    Path(__file__).resolve().parents[2] / "scripts/import_official_calendar.py")
ingest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ingest)


@pytest.fixture
def db():
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


def test_policy_portals_are_not_contests():
    rows = [row for row in REAL_CONTENT if "entrepreneurship-policy" in row["key"]]
    assert len(rows) == 3
    assert all(row["item_type"] == "policy" and row["opportunity_type"] == "policy" for row in rows)


def test_beijing_deadline_is_utc_before_sqlite_drops_offset():
    assert _parse("2026-11-25T23:59:59+08:00").isoformat() == "2026-11-25T15:59:59+00:00"
    assert _parse("2026-11-26T06:00:00+08:00").isoformat() == "2026-11-25T22:00:00+00:00"


def test_reference_dates_are_not_fabricated_or_rolling():
    items = {item["key"]: item for item in REAL_CONTENT}
    for key in ("pku-2026-recommendation", "fudan-2027-masters", "moe-2027-graduate-policy", "guangdong-2026-civil-service"):
        assert items[key]["deadline"] is None
        assert items[key]["start"] is None
    for key in ("oxford-2027-social-policy", "melbourne-2027-data-science"):
        assert items[key]["start"] is None
        assert items[key]["deadline"] is not None


def test_open_filter_requires_actual_deadline_and_supported_type(db):
    future = datetime.now(UTC) + timedelta(days=3)
    for key, kind, deadline in [
        ("open", "contest", future), ("unknown", "contest", None),
        ("expired", "contest", datetime.now(UTC) - timedelta(days=3)),
        ("policy", "policy", future), ("exam-stage", "calendar", future),
    ]:
        db.add(Opportunity(id=key, type=kind, title=key, organization="Synthetic test",
            summary="Fixture", location="", deadline=deadline, source_url="https://example.edu",
            source_label="Fixture", trust_score=1, tags="", status="published", fetched_at=datetime.now(UTC)))
    db.flush()
    assert [row.id for row in list_opportunities(type="contest", q=None, db=db, status="active").items] == ["open"]
    assert {row.id for row in list_opportunities(type=None, q=None, db=db, status="all").items} == {"open", "unknown", "expired"}


def test_fetch_fails_closed_when_date_evidence_missing(monkeypatch):
    monkeypatch.setattr(ingest.time, "sleep", lambda _: None)
    def handle(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, headers={"content-type":"text/html"}, text="<h1>2026 竞赛</h1>")
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(ValueError, match="日期证据未匹配"):
            ingest.fetch_verified(client, {"url":"https://example.edu/notice", "checks":["2026年11月25日"]})


def test_fetch_respects_robots(monkeypatch):
    monkeypatch.setattr(ingest.time, "sleep", lambda _: None)
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, text="User-agent: *\nDisallow: /"))) as client:
        with pytest.raises(ValueError, match="禁止抓取"):
            ingest.fetch_verified(client, {"url":"https://example.edu/notice", "checks":[]})


def test_verified_import_retains_original_and_separate_calendar_stages(db):
    item = {
        "key":"unit-calendar", "url":"https://example.edu/notice", "source_code":"UNIT-CALENDAR",
        "source_label":"Synthetic university", "source_class":"university", "organization":"Fixture",
        "path_code":None, "item_type":"application_notice", "opportunity_type":"contest",
        "title":"Fixture competition", "summary":"Unit fixture only", "location":"Fixture",
        "published":"2026-10-21", "start":None, "deadline":"2026-11-25T23:59:59+08:00",
        "raw_text":"Fixture date facts", "archive_bytes":b"<h1>Fixture date facts</h1>",
        "content_type":"text/html", "trust":1, "excerpt":"Fixture date facts", "tags":"test",
        "milestones":[{"key":"event","title":"Fixture competition event",
            "start":"2026-11-26T06:00:00+08:00", "end":"2026-11-30T09:00:00+08:00",
            "note":"Already registered teams only"}],
    }
    result = ingest.import_entry(db, item)
    db.flush()
    assert result["result"] == "imported"
    assert db.get(DocumentArchive, result["document_id"]).content == item["archive_bytes"]
    assert db.get(DocumentVersion, result["document_id"]).raw_text == item["raw_text"]
    nodes = timeline(path=None, db=db)
    assert len(nodes) == 3
    from datetime import timezone
    beijing = timezone(timedelta(hours=8))
    assert {datetime.fromisoformat(node["at"]).astimezone(beijing).date().isoformat() for node in nodes} == {"2026-11-25","2026-11-26","2026-11-30"}
    assert len({node["item_id"] for node in nodes}) == 2
    assert ingest.import_entry(db, item)["result"] == "unchanged"
    assert db.scalar(select(func.count()).select_from(DevelopmentItem)) == 2
    with pytest.raises(ValueError, match="保留现有版本"):
        ingest.import_entry(db, {**item, "archive_bytes":b"new", "raw_text":"Changed facts"})

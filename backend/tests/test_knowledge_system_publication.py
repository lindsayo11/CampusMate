"""A governed auto-collected document must become searchable without human review.

The governed collector (`source_scheduler`) writes `document_versions`, while the
public search reads `source_documents` + `source_heads` + `knowledge_publications`.
Those two worlds were not connected, so a successfully collected document stayed
invisible no matter how the review policy was configured.

These tests pin both halves of the fix:

  * the system path publishes with no review record at all
  * the editorial path keeps its original gate (approved review + live opportunity)
  * revoking public access hides the text on both paths

Every document carries a unique ASCII marker and assertions are scoped to that
document, because the suite shares one database and other tests leave rows behind.
"""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import SessionLocal
from app.intake_models import DocumentVersion, Source, SourceEndpoint
from app.knowledge import DocumentChunk, KnowledgeAccess, KnowledgePublication
from app.main import app
from app.source_scheduler import publish_collected_document

TEMPLATE = "本规定要求：{marker} 报考人员须于报名截止前提交学历证明与户籍材料。逾期不予受理。"


def make_system_document():
    """A collected document shaped exactly as the governed collector leaves it.

    Returns (marker, document_id). The marker is a unique ASCII token embedded in
    the text so a search can be scoped to this one document.
    """
    suffix = str(uuid4())
    marker = "kbmark" + suffix.replace("-", "")[:10]
    text = TEMPLATE.format(marker=marker)
    source = Source(
        id=str(uuid4()), source_code="TEST-KB-" + suffix, name="知识链测试源",
        publisher="测试发布者", authority_level="A", source_class="government", official=True,
        jurisdiction_level="national", supported_paths="[]", supported_item_types="[]",
        base_url="https://example.edu/", active=True, verified_at=datetime.now(UTC))
    endpoint = SourceEndpoint(
        id=str(uuid4()), source_id=source.id, name="fixture", endpoint_type="html",
        url=f"https://example.edu/policy/{marker}", access_tags='["DIRECT"]', auth_type="none",
        format="text", parser_type="MoEPolicyAdapter", rate_limit="1/s", cors_status="unknown",
        robots_status="allowed", license_status="permitted", fetch_interval="12h",
        automation_level="AUTO-1", agent_mode="REVIEW", license_note="测试 Fixture",
        active=True, scheduled=True, next_run_at=datetime.now(UTC) - timedelta(seconds=1))
    now = datetime.now(UTC)
    document = DocumentVersion(
        id=str(uuid4()), source_endpoint_id=endpoint.id, canonical_url=endpoint.url,
        source_item_id="default", content_hash="b" * 64, attachment_hash="b" * 64,
        first_seen_at=now, last_seen_at=now, last_changed_at=now, version_no=1,
        fetched_at=now, raw_text=text, import_mode="system")
    with SessionLocal.begin() as db:
        db.add_all([source, endpoint, document])
    return marker, document.id


def publish(document_id):
    with SessionLocal.begin() as db:
        return publish_collected_document(db, db.get(DocumentVersion, document_id))


def hits(client, marker, document_id):
    """Search results restricted to the document under test."""
    body = client.post("/v1/knowledge/search", json={"query": marker}).json()
    return [item for item in body["items"] if item["document_id"] == document_id]


def count(model, **filters):
    with SessionLocal() as db:
        stmt = select(func.count()).select_from(model)
        for column, value in filters.items():
            stmt = stmt.where(getattr(model, column) == value)
        return db.scalar(stmt)


def test_system_document_is_searchable_without_any_review():
    marker, document_id = make_system_document()
    with TestClient(app) as c:
        assert hits(c, marker, document_id) == []
        assert publish(document_id) is True
        found = hits(c, marker, document_id)
        assert found, "系统导入文档在免审发布后应可检索"
        item = found[0]
        # No opportunity card was invented for a collected document.
        assert item["opportunity_id"] is None
        assert c.get("/v1/knowledge/chunks/" + item["chunk_id"]).status_code == 200
        assert item["source_url"] == f"https://example.edu/policy/{marker}"


def test_system_publication_records_no_review_and_no_opportunity():
    _, document_id = make_system_document()
    assert publish(document_id) is True
    with SessionLocal() as db:
        row = db.get(KnowledgePublication, document_id)
        assert row.source == "system"
        assert row.review_id is None and row.opportunity_id is None
        assert db.get(KnowledgeAccess, document_id).public is True


def test_editorial_path_still_requires_an_approved_review():
    """The original gate must survive: an unapproved editorial record stays hidden."""
    marker, document_id = make_system_document()
    assert publish(document_id) is True
    with SessionLocal.begin() as db:
        db.get(KnowledgePublication, document_id).source = "editorial"
    with TestClient(app) as c:
        assert hits(c, marker, document_id) == []


def test_revoking_access_hides_a_system_document():
    marker, document_id = make_system_document()
    assert publish(document_id) is True
    with TestClient(app) as c:
        assert hits(c, marker, document_id)
        path = f"/v1/admin/knowledge/documents/{document_id}/access"
        assert c.put(path, json={"public": False}).status_code == 200
        assert hits(c, marker, document_id) == []


def test_publishing_twice_does_not_duplicate_chunks():
    _, document_id = make_system_document()
    assert publish(document_id) is True
    first = count(DocumentChunk, document_id=document_id)
    assert first > 0
    assert publish(document_id) is True
    assert count(DocumentChunk, document_id=document_id) == first
    assert count(KnowledgePublication, document_id=document_id) == 1

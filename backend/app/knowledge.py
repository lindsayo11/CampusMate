"""Traceable lexical retrieval over explicitly public, reviewed source versions."""
import hashlib
import re
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import (Boolean, Integer, String, Text, and_, case, delete, func, or_,
                        select, update)
from sqlalchemy.orm import Mapped, Session, mapped_column

from .auth import actor_id, require_admin
from .database import Base, get_db
from .governance import audit
from .models import Opportunity, ReviewItem
from .intake_models import DocumentVersion, SourceEndpoint, Source, DataPublication
from .sources import SourceDocument, SourceExtraction, SourceHead


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(36), index=True)
    ordinal: Mapped[int]
    start_offset: Mapped[int]
    end_offset: Mapped[int]
    text: Mapped[str] = mapped_column(Text)


class KnowledgeAccess(Base):
    __tablename__ = "knowledge_access"
    document_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    public: Mapped[bool] = mapped_column(Boolean, default=False)


class KnowledgePublication(Base):
    """One publication state per document, with the ingestion path that produced it.

    `source` separates two deliberately different gates:

      editorial - human import. Still requires an approved review and a live
                  published opportunity, exactly as before.
      system    - governed auto-collection. Publishes without human review,
                  because the document already carries calibration evidence
                  (robots / terms / licence quotes), a page SHA256 and
                  DOM-level evidence rows - the traceability a reviewer would
                  otherwise verify by hand.

    `title` / `item_type` exist so the system path can render a citation
    without inventing an opportunity card.
    """
    __tablename__ = "knowledge_publications"
    document_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source: Mapped[str] = mapped_column(String(20), default="editorial",
                                        server_default="editorial", index=True)
    opportunity_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    review_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(160), default="", server_default="")
    item_type: Mapped[str] = mapped_column(String(20), default="", server_default="")


class SearchIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    query: str = Field(min_length=2, max_length=200)
    type: Literal['job', 'contest', 'civil_service', 'volunteer', 'club', 'graduate'] | None = None
    opportunity_id: str | None = Field(default=None, max_length=40)
    limit: int = Field(default=5, ge=1, le=10)

    @field_validator("query")
    @classmethod
    def searchable(cls, value):
        if not tokens(value):
            raise ValueError("请输入至少两个有意义的文字或字母")
        return value


class AccessIn(BaseModel):
    public: bool


router = APIRouter(prefix="/v1")


def split_text(text, size=900, overlap=100):
    start, ordinal = 0, 0
    while start < len(text):
        end = min(start + size, len(text))
        # Prefer a paragraph/sentence boundary near the end without dropping any source text.
        if end < len(text):
            boundary = max(text.rfind("\n", start + size // 2, end),
                           text.rfind("。", start + size // 2, end))
            if boundary >= 0:
                end = boundary + 1
        yield ordinal, start, end, text[start:end]
        if end == len(text):
            break
        start, ordinal = max(start + 1, end - overlap), ordinal + 1


def index_document(db, doc):
    db.execute(update(SourceDocument).where(SourceDocument.id == doc.id).values(
        content_hash=SourceDocument.content_hash))
    db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc.id))
    count = 0
    for ordinal, start, end, text in split_text(doc.raw_text):
        identity = hashlib.sha256(f"{doc.id}:v1:{start}:{end}:{doc.content_hash}".encode()).hexdigest()
        db.add(DocumentChunk(id=identity, document_id=doc.id, ordinal=ordinal,
                             start_offset=start, end_offset=end, text=text))
        count += 1
    db.flush()
    return count


def record_publication(db, review_id, opportunity_id):
    extraction = db.scalar(select(SourceExtraction).where(SourceExtraction.review_id == review_id))
    if extraction:
        doc = db.get(SourceDocument, extraction.document_id)
        row = db.get(KnowledgePublication, doc.id)
        if not row:
            row = KnowledgePublication(document_id=doc.id)
            db.add(row)
        row.source, row.opportunity_id, row.review_id = "editorial", opportunity_id, review_id
        index_document(db, doc)
        # Publishing a card does not implicitly publish all text in its source attachment.


def publish_system_document(db, document_id, title, item_type="policy"):
    """Publish a governed auto-collected document without human review.

    Called from the collector's persistence path for import_mode='system'.
    Idempotent: re-collecting an unchanged document re-indexes the same rows
    rather than duplicating them.
    """
    doc = db.get(SourceDocument, document_id)
    if not doc:
        return False
    index_document(db, doc)
    row = db.get(KnowledgePublication, document_id)
    if not row:
        row = KnowledgePublication(document_id=document_id)
        db.add(row)
    row.source = "system"
    row.title, row.item_type = title[:160], item_type[:20]
    row.opportunity_id, row.review_id = None, None
    access = db.get(KnowledgeAccess, document_id)
    if not access:
        db.add(KnowledgeAccess(document_id=document_id, public=True))
    db.flush()
    return True


def tokens(query):
    terms = []
    for group in re.findall(r"[\u4e00-\u9fff]+|[a-z0-9]{2,}", query.casefold()):
        if re.fullmatch(r"[\u4e00-\u9fff]+", group):
            terms.extend(group[i:i+2] for i in range(len(group)-1))
        else:
            terms.append(group)
    stop = {"什么", "如何", "是否", "请问", "一下", "这个", "那个", "可以"}
    return list(dict.fromkeys(t for t in terms if t not in stop))[:24]


def numeric_requirements(query):
    """Return long numeric runs that must be present in a matching chunk.

    A query copied from a timestamp, tracking number, or URL can contain a
    long run of digits.  Treating each date fragment as an ordinary lexical
    term makes a query such as ``未知词 2026-10-02-123456`` match unrelated
    chunks that merely contain a year or a day.  Short numbers (for example
    a graduation year) remain ordinary search terms; long runs are checked
    against the chunk after punctuation is removed.
    """
    requirements = []
    for match in re.finditer(r"(?<!\d)\d(?:[\s:/._-]*\d){5,}(?!\d)", query.casefold()):
        normalized = re.sub(r"\D", "", match.group())
        if len(normalized) >= 6:
            requirements.append(normalized)
    return list(dict.fromkeys(requirements))


def visible_statement():
    """The single public predicate every knowledge endpoint shares, chunk lookup included.

    Two publication paths, deliberately gated differently:

      system    - governed auto-collection. Publishes without human review; the
                  document already carries calibration evidence, a page SHA256
                  and DOM-level evidence rows.
      editorial - human import. Keeps the original gate: an approved review plus
                  a live published opportunity.

    The system branch still requires KnowledgeAccess.public, so revoking public
    access hides the text immediately on both paths.
    """
    return (select(DocumentChunk, SourceDocument, KnowledgePublication, Opportunity)
        .join(SourceDocument, DocumentChunk.document_id == SourceDocument.id)
        .join(KnowledgeAccess, KnowledgeAccess.document_id == SourceDocument.id)
        .join(KnowledgePublication, KnowledgePublication.document_id == SourceDocument.id)
        .join(SourceHead, SourceHead.document_id == SourceDocument.id)
        .outerjoin(DocumentVersion, DocumentVersion.id == SourceDocument.id)
        .outerjoin(SourceEndpoint, SourceEndpoint.id == DocumentVersion.source_endpoint_id)
        .outerjoin(Source, Source.id == SourceEndpoint.source_id)
        .outerjoin(DataPublication, DataPublication.document_id == DocumentVersion.id)
        .outerjoin(ReviewItem, ReviewItem.id == KnowledgePublication.review_id)
        .outerjoin(Opportunity, Opportunity.id == KnowledgePublication.opportunity_id)
        .where(KnowledgeAccess.public.is_(True),
               or_(DocumentVersion.id.is_(None),
                   and_(DocumentVersion.deleted_at.is_(None), Source.active.is_(True),
                        SourceEndpoint.active.is_(True),
                        or_(DataPublication.id.is_(None), DataPublication.status == 'published'))),
               or_(KnowledgePublication.source == "system",
                   and_(KnowledgePublication.source == "editorial",
                        ReviewItem.status == "approved",
                        Opportunity.status == "published",
                        Opportunity.deadline > datetime.now(UTC)))))


def citation(chunk, doc, publication, opportunity):
    fetched = doc.fetched_at.replace(tzinfo=UTC) if doc.fetched_at.tzinfo is None else doc.fetched_at
    # A system-collected document has no opportunity card; the publication row
    # carries the title and type so the citation still renders.
    return {"chunk_id": chunk.id, "document_id": doc.id, "text": chunk.text,
            "start_offset": chunk.start_offset, "end_offset": chunk.end_offset,
            "source_url": doc.source_url, "content_hash": doc.content_hash,
            "fetched_at": fetched,
            "opportunity_id": opportunity.id if opportunity else None,
            "title": opportunity.title if opportunity else publication.title,
            "type": opportunity.type if opportunity else publication.item_type}


def search_documents(body, db):
    terms = tokens(body.query)
    numeric_runs = numeric_requirements(body.query)
    clauses = [func.lower(DocumentChunk.text).contains(term, autoescape=True) for term in terms]
    coverage = sum((case((clause, 1), else_=0) for clause in clauses), 0)
    stmt = visible_statement().where(or_(*clauses))
    if body.type:
        # Editorial results carry the type on the opportunity; system results on the publication row.
        stmt = stmt.where(or_(Opportunity.type == body.type,
                              KnowledgePublication.item_type == body.type))
    if body.opportunity_id:
        stmt = stmt.where(Opportunity.id == body.opportunity_id)
    # Rank in SQL before the bound, so documents beyond the first page remain discoverable.
    rows = db.execute(stmt.order_by(coverage.desc(), SourceDocument.fetched_at.desc(),
                                    DocumentChunk.id, KnowledgePublication.document_id).limit(301)).all()
    candidates = []
    seen = set()
    for chunk, doc, publication, opportunity in rows[:300]:
        if chunk.id in seen:
            continue
        seen.add(chunk.id)
        text = chunk.text.casefold()
        if numeric_runs:
            normalized_text_digits = re.sub(r"\D", "", text)
            if any(run not in normalized_text_digits for run in numeric_runs):
                continue
        hits = sum(term in text for term in terms)
        # Single ubiquitous bigrams must not masquerade as evidence for a long query.
        if hits < min(2, len(terms)):
            continue
        score = hits / len(terms) + (1 if body.query.casefold() in text else 0)
        candidates.append((score, chunk, doc, publication, opportunity))
    candidates.sort(key=lambda row: (-row[0], row[1].id))
    items = [dict(citation(chunk, doc, publication, opportunity), score=round(score, 4))
             for score, chunk, doc, publication, opportunity in candidates[:body.limit]]
    return {"mode": "lexical", "items": items, "candidate_limit_reached": len(rows) > 300,
            "message": "以下为允许公开检索的原文片段；资格结论请使用资格工具。" if items else "未找到依据"}


@router.post("/knowledge/search")
def search(body: SearchIn, user: str = Depends(actor_id), db: Session = Depends(get_db)):
    return search_documents(body, db)


@router.get("/knowledge/chunks/{chunk_id}")
def read_chunk(chunk_id: str, user: str = Depends(actor_id), db: Session = Depends(get_db)):
    row = db.execute(visible_statement().where(DocumentChunk.id == chunk_id)
                     .order_by(KnowledgePublication.document_id).limit(1)).first()
    if not row:
        raise HTTPException(404, "引用不存在、版本已更新或已停止公开")
    return citation(*row)


@router.put("/admin/knowledge/documents/{document_id}/access")
def set_access(document_id: str, body: AccessIn, user: str = Depends(require_admin),
               db: Session = Depends(get_db)):
    doc = db.get(SourceDocument, document_id)
    if not doc:
        raise HTTPException(404, "归档不存在")
    db.execute(update(SourceDocument).where(SourceDocument.id == doc.id).values(content_hash=SourceDocument.content_hash))
    if body.public:
        published = db.scalar(
            select(KnowledgePublication.document_id)
            .outerjoin(ReviewItem, ReviewItem.id == KnowledgePublication.review_id)
            .outerjoin(Opportunity, Opportunity.id == KnowledgePublication.opportunity_id)
            .where(KnowledgePublication.document_id == document_id,
                   or_(KnowledgePublication.source == "system",
                       and_(ReviewItem.status == "approved",
                            Opportunity.status == "published",
                            Opportunity.deadline > datetime.now(UTC)))))
        if not published:
            raise HTTPException(409, "请先通过关联机会审核，再核对原文可公开范围")
        index_document(db, doc)
    row = db.get(KnowledgeAccess, document_id)
    if row:
        row.public = body.public
    else:
        db.add(KnowledgeAccess(document_id=document_id, public=body.public))
    audit(db, user, "knowledge_public_access", document_id, {"public": body.public})
    db.commit()
    return {"document_id": document_id, "public": body.public}

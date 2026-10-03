"""Immutable source snapshots and auditable operator-assisted extraction intake."""
import difflib
import hashlib
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import DateTime, String, Text, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from .auth import require_admin
from .database import Base, get_db
from .governance import EditorialImport, audit
from .models import ReviewItem


class SourceHead(Base):
    __tablename__ = "source_heads"
    url_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_url: Mapped[str] = mapped_column(String(500))
    document_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class SourceDocument(Base):
    __tablename__ = "source_documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_url: Mapped[str] = mapped_column(String(500), index=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    raw_text: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    previous_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class SourceExtraction(Base):
    __tablename__ = "source_extractions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(36), index=True)
    review_id: Mapped[int] = mapped_column(unique=True)


class ArchivedImport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    raw_text: str = Field(min_length=20, max_length=200000)
    payload: EditorialImport


router = APIRouter(prefix="/v1/admin")


@router.post("/sources/import", status_code=201)
def archive_import(body: ArchivedImport, user: str = Depends(require_admin),
                   db: Session = Depends(get_db)):
    if body.payload.fetched_at > datetime.now(UTC):
        raise HTTPException(422, "采集时间不能在未来")
    for rule in body.payload.rules:
        if rule.evidence not in body.raw_text:
            raise HTTPException(422, "资格规则引用必须出现在归档原文中")
    url = str(body.payload.source_url)
    doc, changed = archive_snapshot(db, url, body.raw_text, body.payload.fetched_at)
    return submit_document(db, doc, body.payload, user, changed)


@router.get("/sources")
def sources(offset: int = Query(0, ge=0), user: str = Depends(require_admin),
            db: Session = Depends(get_db)):
    rows = db.scalars(select(SourceDocument).order_by(SourceDocument.archived_at.desc(), SourceDocument.id)
                      .offset(offset).limit(50)).all()
    return [{"id": r.id, "source_url": r.source_url, "content_hash": r.content_hash,
             "fetched_at": r.fetched_at, "previous_id": r.previous_id} for r in rows]


@router.get("/sources/{document_id}")
def source_detail(document_id: str, user: str = Depends(require_admin),
                  db: Session = Depends(get_db)):
    doc = db.get(SourceDocument, document_id)
    if not doc:
        raise HTTPException(404, "归档不存在")
    previous = db.get(SourceDocument, doc.previous_id) if doc.previous_id else None
    diff = "".join(difflib.unified_diff((previous.raw_text if previous else "").splitlines(True),
                                       doc.raw_text.splitlines(True), fromfile="previous", tofile="current"))
    return {"id": doc.id, "source_url": doc.source_url, "raw_text": doc.raw_text,
            "content_hash": doc.content_hash, "previous_id": doc.previous_id,
            "diff": diff, "reviews": list(db.scalars(select(SourceExtraction.review_id)
             .where(SourceExtraction.document_id == doc.id)))}


@router.get("/reviews/{review_id}/evidence")
def review_evidence(review_id: int, user: str = Depends(require_admin),
                    db: Session = Depends(get_db)):
    review = db.get(ReviewItem, review_id)
    if not review:
        raise HTTPException(404, "审核记录不存在")
    record = db.scalar(select(SourceExtraction).where(SourceExtraction.review_id == review_id))
    return {"payload": review.extracted_payload,
            "archive": source_detail(record.document_id, user, db) if record else None}


def archive_snapshot(db, url, raw_text, fetched_at):
    key = hashlib.sha256(url.encode()).hexdigest()
    if not db.get(SourceHead, key):
        try:
            with db.begin_nested():
                db.add(SourceHead(url_hash=key, source_url=url))
                db.flush()
        except IntegrityError:
            pass
    db.execute(update(SourceHead).where(SourceHead.url_hash == key)
               .values(source_url=SourceHead.source_url))
    head = db.get(SourceHead, key, populate_existing=True)
    old = db.get(SourceDocument, head.document_id) if head.document_id else None
    digest = hashlib.sha256(raw_text.encode()).hexdigest()
    if old and old.content_hash == digest:
        doc = old
    else:
        doc = SourceDocument(id=str(uuid4()), source_url=url, content_hash=digest,
                             raw_text=raw_text, fetched_at=fetched_at,
                             archived_at=datetime.now(UTC), previous_id=old.id if old else None)
        db.add(doc)
        head.document_id = doc.id
        db.flush()
    return doc, old is not None and old.id != doc.id


def submit_document(db, doc, payload_body, user, changed=False):
    db.execute(update(SourceDocument).where(SourceDocument.id == doc.id).values(content_hash=SourceDocument.content_hash))
    if str(payload_body.source_url) != doc.source_url:
        raise HTTPException(422, "结构化来源必须与归档一致")
    for rule in payload_body.rules:
        if rule.evidence not in doc.raw_text:
            raise HTTPException(422, "资格规则引用必须出现在归档原文中")
    payload = payload_body.model_dump_json()
    # fetched_at is observational; re-fetching unchanged content is not a new review.
    canonical = payload_body.model_dump_json(exclude={"fetched_at"})
    extraction_id = hashlib.sha256((doc.id + canonical).encode()).hexdigest()
    existing = db.get(SourceExtraction, extraction_id)
    if existing:
        return {"document_id": doc.id, "review_id": existing.review_id, "changed": False, "duplicate": True}
    row = ReviewItem(title=payload_body.title, source_url=doc.source_url, risk_level="high",
                     confidence=0, status="pending", extracted_payload=payload,
                     created_at=datetime.now(UTC))
    db.add(row)
    db.flush()
    db.add(SourceExtraction(id=extraction_id, document_id=doc.id, review_id=row.id))
    audit(db, user, "archive_import", f"review:{row.id}", {"document_id": doc.id, "sha256": doc.content_hash})
    db.commit()
    return {"document_id": doc.id, "review_id": row.id, "changed": changed, "duplicate": False}

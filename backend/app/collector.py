"""Durable collection jobs, manual file intake and the existing human review boundary."""
import base64
import binascii
import hashlib
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from sqlalchemy import Boolean, DateTime, String, select, update
from sqlalchemy.orm import Mapped, Session, mapped_column

from .auth import require_admin
from .collector_http import FetchError, collect_bytes, validate_url
from .database import Base, SessionLocal, get_db
from .governance import EditorialImport, audit
from .parsers import MAX_BYTES, ParseError, extract_isolated
from .sources import SourceDocument, archive_snapshot, submit_document


class CollectionSource(Base):
    __tablename__ = "collection_sources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    url: Mapped[str] = mapped_column(String(500), unique=True)
    label: Mapped[str] = mapped_column(String(100))
    format: Mapped[str] = mapped_column(String(10))
    interval_minutes: Mapped[int]
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    permission_note: Mapped[str] = mapped_column(String(500))


class CollectionRun(Base):
    __tablename__ = "collection_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    ready_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    document_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    byte_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SourceIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    url: HttpUrl
    label: str = Field(min_length=1, max_length=100)
    format: Literal["html", "pdf", "xlsx", "text"]
    interval_minutes: int = Field(default=360, ge=60, le=43200)
    permission_note: str = Field(min_length=5, max_length=500)


class Toggle(BaseModel):
    enabled: bool


class FileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_url: HttpUrl
    format: Literal["html", "pdf", "xlsx", "text"]
    content_base64: str = Field(max_length=((MAX_BYTES + 2) // 3) * 4)


router = APIRouter(prefix="/v1/admin/collector")


@router.post("/sources", status_code=201)
def create_source(body: SourceIn, user: str = Depends(require_admin), db: Session = Depends(get_db)):
    try:
        validate_url(str(body.url))
    except (FetchError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    if db.scalar(select(CollectionSource).where(CollectionSource.url == str(body.url))):
        raise HTTPException(409, "来源已存在")
    source = CollectionSource(id=str(uuid4()), url=str(body.url), label=body.label,
        format=body.format, interval_minutes=body.interval_minutes, enabled=True,
        next_run_at=datetime.now(UTC), permission_note=body.permission_note)
    db.add(source); audit(db, user, "collection_source_create", source.id)
    db.commit()
    return source


@router.get("/sources")
def sources(user: str = Depends(require_admin), db: Session = Depends(get_db)):
    return db.scalars(select(CollectionSource).order_by(CollectionSource.label).limit(200)).all()


@router.patch("/sources/{source_id}")
def toggle(source_id: str, body: Toggle, user: str = Depends(require_admin), db: Session = Depends(get_db)):
    source = db.get(CollectionSource, source_id)
    if not source:
        raise HTTPException(404, "来源不存在")
    source.enabled = body.enabled
    audit(db, user, "collection_source_toggle", source_id, {"enabled": body.enabled})
    db.commit()
    return source


def enqueue(db, source_id):
    locked = db.execute(update(CollectionSource).where(CollectionSource.id == source_id,
        CollectionSource.enabled.is_(True)).values(label=CollectionSource.label))
    if not locked.rowcount:
        raise HTTPException(404, "来源不存在或已停用")
    existing = db.scalar(select(CollectionRun).where(CollectionRun.source_id == source_id,
        CollectionRun.status.in_(["queued", "running", "retry"])))
    if existing:
        return existing
    now = datetime.now(UTC)
    run = CollectionRun(id=str(uuid4()), source_id=source_id, status="queued", attempts=0,
                        ready_at=now, created_at=now)
    db.add(run)
    db.flush()
    return run


@router.post("/sources/{source_id}/run")
def queue_run(source_id: str, user: str = Depends(require_admin), db: Session = Depends(get_db)):
    run = enqueue(db, source_id)
    audit(db, user, "collection_enqueue", run.id)
    db.commit()
    return run


@router.get("/runs")
def runs(offset: int = Query(0, ge=0), user: str = Depends(require_admin), db: Session = Depends(get_db)):
    return db.scalars(select(CollectionRun).order_by(CollectionRun.created_at.desc(), CollectionRun.id)
                      .offset(offset).limit(50)).all()


@router.post("/files", status_code=201)
def import_file(body: FileIn, user: str = Depends(require_admin), db: Session = Depends(get_db)):
    if len(str(body.source_url)) > 500:
        raise HTTPException(422, "来源 URL 过长")
    try:
        data = base64.b64decode(body.content_base64, validate=True)
        parsed = extract_isolated(data, body.format)
    except (binascii.Error, ParseError, ValueError) as exc:
        raise HTTPException(422, "解析失败：" + str(exc)) from exc
    now = datetime.now(UTC)
    doc, _ = archive_snapshot(db, str(body.source_url), parsed.text, now)
    run = CollectionRun(id=str(uuid4()), status="succeeded", attempts=1, ready_at=now,
        document_id=doc.id, byte_hash=hashlib.sha256(data).hexdigest(), created_at=now, finished_at=now)
    db.add(run); audit(db, user, "file_text_import", doc.id, {"format": body.format, "sha256": run.byte_hash})
    db.commit()
    return {"document_id": doc.id, "run_id": run.id, "title": parsed.title, "text": parsed.text}


@router.post("/documents/{document_id}/review", status_code=201)
def submit_review(document_id: str, body: EditorialImport, user: str = Depends(require_admin),
                  db: Session = Depends(get_db)):
    doc = db.get(SourceDocument, document_id)
    if not doc:
        raise HTTPException(404, "归档不存在")
    if str(body.source_url) != doc.source_url:
        raise HTTPException(422, "结构化来源必须与归档一致")
    # Archive timestamps are authoritative, not an operator/model-invented observation time.
    payload = body.model_copy(update={"fetched_at": doc.fetched_at.replace(tzinfo=UTC)})
    result = submit_document(db, doc, payload, user)
    return result


def schedule_due():
    now = datetime.now(UTC)
    with SessionLocal.begin() as db:
        ids = db.scalars(select(CollectionSource.id).where(CollectionSource.enabled.is_(True),
            CollectionSource.next_run_at <= now).order_by(CollectionSource.next_run_at).limit(20)).all()
        for sid in ids:
            source = db.get(CollectionSource, sid)
            claimed = db.execute(update(CollectionSource).where(CollectionSource.id == sid,
                CollectionSource.enabled.is_(True), CollectionSource.next_run_at <= now).values(
                next_run_at=now + timedelta(minutes=source.interval_minutes)).execution_options(synchronize_session=False))
            if claimed.rowcount:
                enqueue(db, sid)


def process_one():
    now, token = datetime.now(UTC), str(uuid4())
    with SessionLocal.begin() as db:
        # Lost workers are reclaimable. Token fencing prevents stale completion overwrites.
        db.execute(update(CollectionRun).where(CollectionRun.status == "running",
            CollectionRun.lease_until < now).values(status="retry", ready_at=now, lease_token=None))
        candidates = db.scalars(select(CollectionRun.id).where(CollectionRun.status.in_(["queued", "retry"]),
            CollectionRun.ready_at <= now).order_by(CollectionRun.ready_at).limit(20)).all()
        run_id = None
        for rid in candidates:
            changed = db.execute(update(CollectionRun).where(CollectionRun.id == rid,
                CollectionRun.status.in_(["queued", "retry"]), CollectionRun.ready_at <= now).values(
                status="running", lease_token=token, lease_until=now + timedelta(minutes=5),
                attempts=CollectionRun.attempts + 1))
            if changed.rowcount:
                run_id = rid
                break
        if run_id is None:
            return False
        run = db.get(CollectionRun, run_id)
        source = db.get(CollectionSource, run.source_id)
        if not source or not source.enabled or run.attempts > 3:
            run.status = "cancelled" if not source or not source.enabled else "failed"
            run.finished_at = now
            run.lease_token = None
            return True
        url, format = source.url, source.format
    try:
        data, _ = collect_bytes(url)
        parsed = extract_isolated(data, format)
        error = None
    except Exception as exc:  # noqa: BLE001 - durable jobs must record parser/network failures
        error = str(exc)[:500] if isinstance(exc, (FetchError, ParseError)) else "采集或解析失败，请检查来源配置"
    with SessionLocal.begin() as db:
        fence = db.execute(update(CollectionRun).where(CollectionRun.id == run_id,
            CollectionRun.status == "running", CollectionRun.lease_token == token).values(lease_token=None))
        if not fence.rowcount:
            return True
        run = db.get(CollectionRun, run_id, populate_existing=True)
        source = db.get(CollectionSource, run.source_id)
        if not source or not source.enabled:
            run.status = "cancelled"
        elif error:
            run.status = "retry" if run.attempts < 3 else "failed"
            run.error = error
            run.ready_at = datetime.now(UTC) + timedelta(seconds=60 * 2 ** (run.attempts - 1))
        else:
            doc, changed = archive_snapshot(db, url, parsed.text, datetime.now(UTC))
            previous = db.scalar(select(CollectionRun.id).where(CollectionRun.source_id == run.source_id,
                CollectionRun.document_id == doc.id, CollectionRun.id != run_id))
            run.status = "unchanged" if previous else "succeeded"
            run.document_id, run.byte_hash = doc.id, hashlib.sha256(data).hexdigest()
            run.error = None
        if run.status != "retry":
            run.finished_at = datetime.now(UTC)
        run.lease_until = None
    return True

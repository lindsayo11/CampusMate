"""Authenticated exchange of public official originals, with local re-parsing.

No account, plan, review, source configuration or peer-derived rule is imported.
The local worker coordinates both directions; the cloud needs no localhost access.
"""
import base64
import binascii
import hashlib
import json
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from .adapters.base import RawArtifact
from .adapters.index_discovery import official_url
from .adapters.public_request import request_spec
from .collector_http import public_ip, validate_url
from .config import settings
from .data_catalog import auto_publish, canonical, readiness, visible
from .database import SessionLocal
from .governance import audit
from .intake import ingest_public_notice, ingest_university_notice
from .intake_models import (CollectionSyncRecord, CollectionSyncState, DataPublication,
    DocumentArchive, DocumentVersion, NoticeResource, Source, SourceEndpoint)
from .notice_watch import config_for, permitted, timestamp
from .parsers import MAX_BYTES

MAX_WIRE_BYTES = MAX_BYTES * 2


class ExchangeHTTPError(ValueError):
    def __init__(self, status_code, retry_after=None):
        self.status_code = status_code
        self.retry_after = retry_after
        super().__init__(f'原文交换 HTTP {status_code}')


def safe_failure(exc, stage):
    """Constant diagnostics only: never include exception payloads, URLs or tokens."""
    if isinstance(exc, (ExchangeHTTPError, HTTPException)):
        detail = f'HTTP {exc.status_code}'
    elif isinstance(exc, httpx.TimeoutException):
        detail = '网络连接或响应超时'
    elif isinstance(exc, httpx.TransportError):
        detail = '网络连接失败'
    elif isinstance(exc, ValidationError):
        detail = '原文元数据校验失败'
    elif isinstance(exc, IntegrityError):
        detail = '并发更新冲突'
    elif isinstance(exc, ValueError):
        detail = '配置、目录或原文校验失败'
    else:
        detail = '本地处理失败'
    return f'{stage}：{detail}；下一轮自动重试'


def authenticate(x_collection_token: str | None = Header(default=None)):
    token = settings.collection_exchange_token
    if len(token) < 32:
        raise HTTPException(404, '原文交换尚未配置')
    if not x_collection_token or not secrets.compare_digest(token.encode(), x_collection_token.encode()):
        raise HTTPException(401, '原文交换认证失败')


router = APIRouter(prefix='/v1/collection-exchange', dependencies=[Depends(authenticate)])


def utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class Original(BaseModel):
    model_config = ConfigDict(extra='forbid')
    publication_id: UUID
    source_code: str = Field(min_length=1, max_length=80)
    source_item_id: str = Field(min_length=1, max_length=160)
    canonical_url: str = Field(min_length=1, max_length=500)
    content_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    content_type: str = Field(min_length=1, max_length=160)
    fetched_at: datetime
    last_changed_at: datetime
    status: Literal['published', 'withdrawn', 'held'] = 'published'
    kind: Literal['notice','attachment'] = 'notice'
    parent_url: str | None = Field(default=None,max_length=500)
    parent_content_hash: str | None = Field(default=None,pattern=r'^[a-f0-9]{64}$')
    content: str | None = Field(default=None, max_length=MAX_BYTES * 4 // 3 + 8)

    @field_validator('fetched_at', 'last_changed_at')
    @classmethod
    def dated(cls, value):
        if value.tzinfo is None or utc(value) > datetime.now(UTC) + timedelta(minutes=5):
            raise ValueError('来源时间必须带时区且不能位于未来')
        return utc(value)


def eligible(db, endpoint):
    return bool(endpoint and not endpoint.secret_ref and permitted(db, endpoint))


def metadata(db, pub, doc, archive):
    endpoint = db.get(SourceEndpoint, doc.source_endpoint_id)
    source = db.get(Source, endpoint.source_id)
    return dict(publication_id=pub.id, source_code=source.source_code,
        source_item_id=doc.source_item_id, canonical_url=doc.canonical_url,
        content_hash=doc.content_hash, content_type=archive.content_type,
        fetched_at=timestamp(doc.fetched_at), last_changed_at=timestamp(doc.last_changed_at))


def inventory(db):
    # visible() validates current versions, archives and exact publication snapshots.
    rows = []
    allowed = {}
    public_parents = {}
    for pub, snapshot in visible(db):
        doc = db.get(DocumentVersion, pub.document_id)
        ep = db.get(SourceEndpoint, doc.source_endpoint_id)
        archive = db.get(DocumentArchive, doc.id)
        if ep.id not in allowed:
            allowed[ep.id] = eligible(db, ep)
        if doc.import_mode == 'system' and allowed[ep.id] and archive and not archive.is_fixture:
            entry = {**metadata(db, pub, doc, archive), 'status':'published'}
            rows.append(entry)
            public_parents[doc.id] = entry
    # Explicit withdrawals only. An absent or incomplete peer inventory is never a deletion.
    candidates = db.execute(select(DataPublication, DocumentVersion, DocumentArchive).join(
        DocumentVersion, DataPublication.document_id == DocumentVersion.id).join(
        DocumentArchive, DocumentArchive.document_id == DocumentVersion.id).where(
        DataPublication.status.in_(['withdrawn', 'rejected', 'peer_hidden']),
        DocumentVersion.import_mode == 'system', DocumentArchive.is_fixture.is_(False))).all()
    for pub, doc, archive in candidates:
        ep = db.get(SourceEndpoint, doc.source_endpoint_id)
        if not eligible(db, ep):
            continue
        latest = db.scalar(select(DocumentVersion.id).where(
            DocumentVersion.source_endpoint_id == ep.id,
            DocumentVersion.source_item_id == doc.source_item_id).order_by(DocumentVersion.version_no.desc()).limit(1))
        if latest == doc.id:
            rows.append({**metadata(db, pub, doc, archive),
                'status':'held' if pub.status == 'peer_hidden' else 'withdrawn'})
    from .supporting_attachments import supporting_links
    parent_links={}
    current_parents={(ep,url):doc for ep,url,doc in db.execute(select(
        NoticeResource.endpoint_id,NoticeResource.url,NoticeResource.document_id).where(
        NoticeResource.kind=='detail',NoticeResource.status!='retired'))}
    children=db.execute(select(NoticeResource,DocumentVersion,DocumentArchive).join(
        DocumentVersion,DocumentVersion.id==NoticeResource.document_id).join(
        DocumentArchive,DocumentArchive.document_id==DocumentVersion.id).where(
        NoticeResource.kind=='support_file',NoticeResource.status!='retired',
        DocumentVersion.import_mode=='system',DocumentVersion.deleted_at.is_(None),
        DocumentArchive.is_fixture.is_(False))).all()
    for resource,doc,archive in children:
        ep=db.get(SourceEndpoint,doc.source_endpoint_id)
        if not eligible(db,ep):continue
        source=db.get(Source,ep.source_id)
        parent_key=current_parents.get((ep.id,resource.parent_url))
        parent=public_parents.get(parent_key)
        if not parent or not archive.content or hashlib.sha256(archive.content).hexdigest()!=doc.content_hash:continue
        try:
            payload=json.loads(doc.raw_text)
            if payload.get('kind')!='supporting_attachment' or payload.get('parent_url')!=resource.parent_url:continue
        except (ValueError,AttributeError):continue
        if parent_key not in parent_links:
            parent_pub=db.get(DataPublication,parent['publication_id'])
            parent_archive=db.get(DocumentArchive,parent_pub.document_id)
            parent_links[parent_key]=supporting_links(parent_archive.content,resource.parent_url,config_for(ep))
        if doc.canonical_url not in parent_links[parent_key]:continue
        rows.append(dict(publication_id=doc.id,source_code=source.source_code,source_item_id=doc.source_item_id,
            canonical_url=doc.canonical_url,content_hash=doc.content_hash,content_type=archive.content_type,
            fetched_at=timestamp(doc.fetched_at),last_changed_at=timestamp(doc.last_changed_at),status='published',
            kind='attachment',parent_url=resource.parent_url,parent_content_hash=parent['content_hash']))
    return sorted(rows, key=lambda row:(row['source_code'], row['source_item_id']))


@router.get('/inventory')
def inventory_route():
    with SessionLocal() as db:
        rows = inventory(db)
        if len(rows) > 15000:
            raise HTTPException(503, '交换目录超过当前容量，需要分页升级')
        return {'items':rows, 'complete':True}


@router.get('/health')
def collection_health():
    from .operations import WorkerHeartbeat
    from .intake_models import CollectionAlert
    from sqlalchemy import func
    with SessionLocal() as db:
        heartbeats={}
        for name in ('reminders','collection-monitor','collection-backup','offsite-backup'):
            row=db.get(WorkerHeartbeat,name)
            heartbeats[name]={'state':row.state,'observed_at':timestamp(row.observed_at)} if row else None
        return {'heartbeats':heartbeats,'active_alerts':db.scalar(select(func.count()).select_from(CollectionAlert).where(
            CollectionAlert.status=='active')),'checked_at':datetime.now(UTC).isoformat()}


def original(db, publication_id):
    pub = db.get(DataPublication, str(publication_id))
    if not pub:
        # Revalidate this child and its public parent, without re-hashing the
        # entire collection for every file in a transfer batch.
        child=db.get(DocumentVersion,str(publication_id))
        archive=db.get(DocumentArchive,str(publication_id)) if child else None
        resource=db.scalar(select(NoticeResource).where(NoticeResource.document_id==str(publication_id),
            NoticeResource.kind=='support_file',NoticeResource.status!='retired'))
        entry=attachment_original_metadata(db,resource,child,archive)
        if not entry:raise HTTPException(404,'公开附件不存在或父文档已失效')
        return {**entry,'content':base64.b64encode(archive.content).decode('ascii')}
    doc = db.get(DocumentVersion, pub.document_id) if pub else None
    ep = db.get(SourceEndpoint, doc.source_endpoint_id) if doc else None
    archive = db.get(DocumentArchive, doc.id) if doc else None
    if (not pub or pub.status != 'published' or not doc or doc.import_mode != 'system'
            or not eligible(db, ep) or not archive or archive.is_fixture):
        raise HTTPException(404, '公开原文不存在')
    snapshot, blocks = readiness(db, doc)
    if blocks or canonical(snapshot) != pub.snapshot:
        raise HTTPException(409, '公开原文已变化，请重新读取目录')
    return {**metadata(db, pub, doc, archive), 'status':'published',
        'content':base64.b64encode(archive.content).decode('ascii')}


def attachment_original_metadata(db,resource,doc,archive):
    if (not resource or not doc or not archive or archive.is_fixture or doc.import_mode!='system' or doc.deleted_at
            or resource.endpoint_id!=doc.source_endpoint_id or hashlib.sha256(archive.content).hexdigest()!=doc.content_hash):return None
    ep=db.get(SourceEndpoint,doc.source_endpoint_id)
    if not eligible(db,ep):return None
    latest=db.scalar(select(DocumentVersion.id).where(DocumentVersion.source_endpoint_id==ep.id,
        DocumentVersion.source_item_id==doc.source_item_id).order_by(DocumentVersion.version_no.desc()).limit(1))
    if latest!=doc.id:return None
    try:
        payload=json.loads(doc.raw_text)
        if payload.get('kind')!='supporting_attachment' or payload.get('parent_url')!=resource.parent_url:return None
    except (ValueError,AttributeError):return None
    parent_resource=db.scalar(select(NoticeResource).where(NoticeResource.endpoint_id==ep.id,
        NoticeResource.url==resource.parent_url,NoticeResource.kind=='detail',NoticeResource.status!='retired'))
    parent=db.get(DocumentVersion,parent_resource.document_id) if parent_resource else None
    pub=db.scalar(select(DataPublication).where(DataPublication.document_id==parent.id)) if parent else None
    if not pub or pub.status!='published' or parent.import_mode!='system':return None
    snapshot,blocks=readiness(db,parent)
    if blocks or canonical(snapshot)!=pub.snapshot:return None
    from .supporting_attachments import supporting_links
    parent_archive=db.get(DocumentArchive,parent.id)
    if doc.canonical_url not in supporting_links(parent_archive.content,parent.canonical_url,config_for(ep)):return None
    source=db.get(Source,ep.source_id)
    return dict(publication_id=doc.id,source_code=source.source_code,source_item_id=doc.source_item_id,
        canonical_url=doc.canonical_url,content_hash=doc.content_hash,content_type=archive.content_type,
        fetched_at=timestamp(doc.fetched_at),last_changed_at=timestamp(doc.last_changed_at),status='published',
        kind='attachment',parent_url=resource.parent_url,parent_content_hash=parent.content_hash)


@router.get('/originals/{publication_id}')
def original_route(publication_id: UUID):
    with SessionLocal() as db:
        return original(db, publication_id)


def record_key(entry, direction='incoming'):
    return direction + ':' + hashlib.sha256(
        (entry.source_code + '\0' + entry.source_item_id).encode()).hexdigest()


def receipt(db, entry, state, document_id=None, error='', direction='incoming'):
    key = record_key(entry, direction)
    row = db.get(CollectionSyncRecord, key)
    if not row:
        row = CollectionSyncRecord(key=key)
        db.add(row)
    row.document_id, row.content_hash, row.state = document_id, entry.content_hash, state
    row.observed_at, row.error = datetime.now(UTC), error[:500]


def receive(db, entry):
    source = db.scalar(select(Source).where(Source.source_code == entry.source_code))
    endpoints = db.scalars(select(SourceEndpoint).where(
        SourceEndpoint.source_id == source.id)).all() if source else []
    endpoint = next((ep for ep in endpoints if eligible(db, ep)), None)
    if not endpoint or not official_url(entry.canonical_url, source.base_url):
        raise HTTPException(422, '来源未授权或原文不属于该官方主机')
    parts = validate_url(entry.canonical_url)
    if parts.scheme != 'https':
        raise HTTPException(422, '交换仅接收 HTTPS 官方原文')
    expected = entry.canonical_url if len(entry.canonical_url) <= 160 else hashlib.sha256(entry.canonical_url.encode()).hexdigest()
    if expected != entry.source_item_id or entry.last_changed_at > entry.fetched_at:
        raise HTTPException(422, '原文条目标识或来源时间不一致')
    # Lock the same endpoint as native version creation to prevent concurrent version collisions.
    db.scalar(select(SourceEndpoint).where(SourceEndpoint.id == endpoint.id).with_for_update())
    latest = db.scalar(select(DocumentVersion).where(DocumentVersion.source_endpoint_id == endpoint.id,
        DocumentVersion.source_item_id == entry.source_item_id).order_by(DocumentVersion.version_no.desc()).limit(1))
    pub = db.scalar(select(DataPublication).where(DataPublication.document_id == latest.id)) if latest else None
    protected = latest and (latest.import_mode != 'system' or latest.deleted_at or
        (pub and (pub.status in {'withdrawn','rejected'} or pub.first_reviewed_by or pub.second_reviewed_by)))
    if entry.kind=='attachment' and (entry.status!='published' or latest and pub):
        raise HTTPException(422,'附件不能改变通知发布状态')
    if protected:
        return {'state':'protected', 'changed':False}
    if entry.status != 'published':
        owned = db.get(CollectionSyncRecord, record_key(entry))
        if (latest and latest.content_hash == entry.content_hash and pub and pub.status == 'published'
                and (entry.status == 'withdrawn' or owned and owned.document_id == latest.id)):
            pub.status, pub.updated_at, pub.note = 'peer_hidden', datetime.now(UTC), '对端公开原文已撤回，等待恢复'
            receipt(db, entry, 'hidden', latest.id)
            audit(db, 'collection-exchange', 'public_original_hidden', f'document:{latest.id}')
            return {'state':'hidden', 'changed':True}
        return {'state':'unchanged', 'changed':False}
    if latest and latest.content_hash != entry.content_hash and utc(latest.last_changed_at) >= entry.last_changed_at:
        return {'state':'stale', 'changed':False}
    try:
        content = base64.b64decode(entry.content or '', validate=True)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(422, '原文字节编码不正确') from exc
    if not content or len(content) > MAX_BYTES or hashlib.sha256(content).hexdigest() != entry.content_hash:
        raise HTTPException(422, '原文字节大小或 SHA256 不符')
    if entry.kind=='attachment':
        validate_attachment_parent(db,endpoint,entry)
    if latest and latest.content_hash == entry.content_hash:
        # Repeated exchange does not simulate another native fetch or re-run expensive OCR.
        restored = bool(pub and pub.status == 'peer_hidden' and auto_publish(db, latest, restore_peer=True))
        receipt(db, entry, 'restored' if restored else 'unchanged', latest.id)
        return {'state':'restored' if restored else 'unchanged', 'changed':restored, 'document_id':latest.id}
    config = config_for(endpoint)
    spec = request_spec(entry.canonical_url, config, 'detail') if entry.kind=='notice' else None
    raw = RawArtifact(content, entry.canonical_url, entry.source_item_id, entry.content_type,
        retrieval_url=spec[0] if spec else None, retrieval_method='POST' if spec and spec[1] is not None else 'GET',
        retrieval_form=spec[1] if spec else None)
    success, failures = endpoint.last_success_at, endpoint.consecutive_failures
    db.info['import_mode'] = 'system'
    ingest = ingest_university_notice if config.get('topic','postgraduate') == 'postgraduate' else ingest_public_notice
    if entry.kind=='attachment':
        from .supporting_attachments import ingest_office_attachment
        result=ingest_office_attachment(db,source,endpoint,raw,entry.parent_url)
    else:
        result = ingest(db, source, endpoint, raw, {**config,'notice_scope':'university'})
    doc = db.get(DocumentVersion, result['document_version_id'])
    doc.fetched_at, doc.last_seen_at, doc.last_changed_at = entry.fetched_at, entry.fetched_at, entry.last_changed_at
    if not latest:
        doc.first_seen_at = entry.last_changed_at
    endpoint.last_success_at, endpoint.consecutive_failures = success, failures
    db.flush()
    if entry.kind=='notice' and not auto_publish(db, doc):
        raise HTTPException(422, '接收端解析结果未通过公开校验')
    # Keep it in the native frontier, due for a real first-party conditional fetch.
    resource = db.scalar(select(NoticeResource).where(NoticeResource.endpoint_id == endpoint.id,
        NoticeResource.url == entry.canonical_url))
    if resource:
        resource.document_id, resource.content_hash = doc.id, doc.content_hash
    else:
        db.add(NoticeResource(id=str(uuid4()),endpoint_id=endpoint.id,url=entry.canonical_url,
            kind='support_file' if entry.kind=='attachment' else 'detail',parent_url=entry.parent_url or '',
            status='peer_imported',document_id=doc.id,content_hash=doc.content_hash,
            discovered_at=datetime.now(UTC),next_check_at=datetime.now(UTC)))
    receipt(db, entry, 'imported', doc.id)
    state = db.get(CollectionSyncState, 'incoming')
    if not state:
        state = CollectionSyncState(name='incoming')
        db.add(state)
        db.flush()
    state.last_checked_at = state.last_success_at = datetime.now(UTC)
    state.state, state.pulled, state.error = 'ok', state.pulled + 1, ''
    audit(db, 'collection-exchange', 'public_original_imported', f'document:{doc.id}',
        {'source_code':entry.source_code,'content_hash':doc.content_hash,'source_bytes_changed':result['changed']})
    return {'state':'imported', 'changed':result['changed'], 'document_id':doc.id}


def validate_attachment_parent(db,endpoint,entry):
    if not entry.parent_url or not entry.parent_content_hash:
        raise HTTPException(422,'附件缺少官方父文档标识')
    resource=db.scalar(select(NoticeResource).where(NoticeResource.endpoint_id==endpoint.id,
        NoticeResource.url==entry.parent_url,NoticeResource.kind=='detail'))
    parent=db.get(DocumentVersion,resource.document_id) if resource else None
    pub=db.scalar(select(DataPublication).where(DataPublication.document_id==parent.id)) if parent else None
    if not parent or not pub or pub.status!='published' or parent.content_hash!=entry.parent_content_hash:
        raise HTTPException(409,'先同步已公开的最新父文档')
    snapshot,blocks=readiness(db,parent)
    if blocks or canonical(snapshot)!=pub.snapshot:raise HTTPException(409,'父文档公开校验已失效')
    from .supporting_attachments import supporting_links
    archive=db.get(DocumentArchive,parent.id)
    if entry.canonical_url not in supporting_links(archive.content,parent.canonical_url,config_for(endpoint)):
        raise HTTPException(422,'官方父文档中没有该附件链接')


def receive_transaction(entry):
    try:
        with SessionLocal.begin() as db:
            return receive(db, entry)
    except IntegrityError as exc:
        raise HTTPException(409, '同一原文正在更新，请下轮重试') from exc
    except ValueError as exc:
        raise HTTPException(422, '接收端无法按已配置的官方结构解析原文') from exc


@router.post('/receive')
async def receive_route(request: Request):
    payload = bytearray()
    async for chunk in request.stream():
        payload.extend(chunk)
        if len(payload) > MAX_WIRE_BYTES:
            raise HTTPException(413, '原文交换请求超过大小限制')
    try:
        entry = Original.model_validate_json(payload)
    except ValidationError as exc:
        raise HTTPException(422, '原文交换字段不合法') from exc
    return await run_in_threadpool(receive_transaction, entry)


def peer_request(method, path, payload=None):
    # Only read requests retry here. Writes use the persisted per-record retry queue.
    for attempt in range(2 if method == 'GET' else 1):
        try:
            return _peer_request(method,path,payload)
        except (httpx.TransportError, ExchangeHTTPError) as exc:
            transient = isinstance(exc,httpx.TransportError) or (
                exc.status_code in {502,503,504} and not exc.retry_after)
            if method != 'GET' or attempt or not transient:
                raise
            time.sleep(0.5)


def _peer_request(method, path, payload=None):
    # Exactly one configured HTTPS root. Pin DNS and forbid redirects before sending the token.
    parts = urlsplit(settings.collection_peer_url)
    if (parts.scheme != 'https' or not parts.hostname or parts.port not in (None,443)
            or parts.username or parts.password or parts.query or parts.fragment or parts.path not in ('','/')):
        raise ValueError('交换目标必须是无凭据的 HTTPS 根地址')
    ip = public_ip(parts.hostname)
    address = '[' + ip + ']' if ':' in ip else ip
    target = 'https://' + address + '/v1/collection-exchange' + path
    with httpx.Client(timeout=httpx.Timeout(150 if method == 'POST' else 40, connect=10),
            trust_env=False, follow_redirects=False) as client:
        with client.stream(method, target, json=payload, headers={'Host':parts.hostname,
                'x-collection-token':settings.collection_exchange_token,'Accept-Encoding':'identity'},
                extensions={'sni_hostname':parts.hostname}) as response:
            if response.status_code != 200:
                raise ExchangeHTTPError(response.status_code,getattr(response,'headers',{}).get('retry-after'))
            data = bytearray()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data) > MAX_WIRE_BYTES:
                    raise ValueError('交换响应超过大小限制')
            return json.loads(data)


def compare(local, remote):
    ours = {(e.source_code,e.source_item_id):e for e in local}
    theirs = {(e.source_code,e.source_item_id):e for e in remote}
    tasks = []
    for origin, target, direction in ((theirs,ours,'pull'),(ours,theirs,'push')):
        for key, entry in origin.items():
            other = target.get(key)
            if entry.status == 'withdrawn':
                if other and other.status == 'published' and other.content_hash == entry.content_hash:
                    tasks.append((direction,entry))
            elif entry.status == 'held':
                continue
            elif not other or (other.status == 'held' and other.content_hash == entry.content_hash) or (
                    other.status == 'published' and other.content_hash != entry.content_hash
                    and entry.last_changed_at > other.last_changed_at):
                tasks.append((direction,entry))
    # Oldest missing first: every successful transfer removes itself next cycle.
    return sorted(tasks,key=lambda task:(task[1].kind=='attachment',task[1].last_changed_at,task[0],task[1].source_code,task[1].source_item_id))


def run_cycle(force=False):
    if not settings.collection_peer_url or len(settings.collection_exchange_token) < 32:
        return {'state':'not_configured'}
    now = datetime.now(UTC)
    with SessionLocal.begin() as db:
        state = db.get(CollectionSyncState,'peer')
        if not state:
            state = CollectionSyncState(name='peer')
            db.add(state)
            db.flush()
        if (state.lease_until and utc(state.lease_until) > now or not force and state.last_checked_at
                and utc(state.last_checked_at) > now-timedelta(minutes=settings.collection_sync_interval_minutes)):
            return {'state':'waiting'}
        claimed = db.execute(update(CollectionSyncState).where(CollectionSyncState.name=='peer',
            (CollectionSyncState.lease_until.is_(None)) | (CollectionSyncState.lease_until <= now)).values(
                lease_until=now+timedelta(minutes=10), last_checked_at=now, state='running')
            .execution_options(synchronize_session=False))
        if not claimed.rowcount:
            return {'state':'waiting'}
    pulled = pushed = failed = processed = pending = 0
    started = time.monotonic()
    stage = '读取云端目录'
    try:
        remote = peer_request('GET','/inventory')
        stage = '校验云端目录'
        if remote.get('complete') is not True or not isinstance(remote.get('items'),list) or len(remote['items']) > 15000:
            raise ValueError('交换目录不完整或超过大小限制')
        remote = [Original.model_validate(row) for row in remote['items']]
        stage = '读取本机目录'
        with SessionLocal() as db:
            local = [Original.model_validate(row) for row in inventory(db)]
        tasks = compare(local,remote)
        pending = len(tasks)
        stage = '传递原文'
        for direction, entry in tasks:
            if processed >= settings.collection_sync_batch_size or time.monotonic()-started > 150:
                break
            with SessionLocal() as db:
                previous = db.get(CollectionSyncRecord,record_key(entry,direction))
                if (previous and previous.content_hash == entry.content_hash and previous.state in {'failed','protected','stale'}
                        and utc(previous.observed_at) > datetime.now(UTC)-timedelta(hours=1)):
                    failed += 1
                    continue
            processed += 1
            try:
                if entry.status == 'published':
                    if direction == 'pull':
                        payload = peer_request('GET', '/originals/'+str(entry.publication_id))
                    else:
                        with SessionLocal() as db:
                            payload = original(db, entry.publication_id)
                    transferred = Original.model_validate(payload)
                    if transferred.model_dump(exclude={'content'}) != entry.model_dump(exclude={'content'}):
                        raise ValueError('原文与交换目录不一致，下一轮重新检查')
                else:
                    transferred = entry
                result = receive_transaction(transferred) if direction=='pull' else peer_request(
                    'POST','/receive',transferred.model_dump(mode='json'))
                outcome = result['state']
                with SessionLocal.begin() as db:
                    receipt(db,entry,outcome,result.get('document_id') if direction=='pull' else None,direction=direction)
                if outcome in {'imported','restored','hidden','unchanged'}:
                    pending -= 1
                    if result.get('changed'):
                        pulled += direction=='pull'
                        pushed += direction=='push'
                else:
                    failed += 1
            except Exception as exc:
                failed += 1
                # Deliberately omit exception details: transport errors may contain credentials or payloads.
                with SessionLocal.begin() as db:
                    message = safe_failure(exc,'接收原文' if direction=='pull' else '发送原文')
                    receipt(db,entry,'failed',error=message.replace('下一轮','下一小时'),direction=direction)
            from .operations import heartbeat
            heartbeat('ok')
        stage = '保存同步进度'
        with SessionLocal.begin() as db:
            state = db.get(CollectionSyncState,'peer')
            state.state, state.error = ('partial','部分原文传递失败，已记录并安排重试') if failed else ('ok','')
            state.last_success_at = datetime.now(UTC) if not failed else state.last_success_at
            state.pulled, state.pushed, state.pending = state.pulled+pulled, state.pushed+pushed, pending
            state.lease_until = None
    except Exception as exc:
        with SessionLocal.begin() as db:
            state = db.get(CollectionSyncState,'peer')
            state.state, state.error, state.lease_until = 'error',safe_failure(exc,stage),None
        return {'state':'error'}
    return {'state':'partial' if failed else 'ok','pulled':pulled,'pushed':pushed,'pending':pending,'failed':failed}


def status(db):
    row = db.get(CollectionSyncState,'peer') or db.get(CollectionSyncState,'incoming')
    configured = bool(settings.collection_peer_url and len(settings.collection_exchange_token)>=32)
    if not row:
        return {'state':'pending' if configured else 'not_configured','pulled':0,'pushed':0,'pending':0,
            'last_success_at':None,'last_checked_at':None,'interval_minutes':settings.collection_sync_interval_minutes}
    current = row.state
    if configured and (not row.last_checked_at or utc(row.last_checked_at)<datetime.now(UTC)-timedelta(
            minutes=max(15,settings.collection_sync_interval_minutes*3))):
        current = 'stale'
    return {'state':current,'mode':'bidirectional' if configured else 'receiver','pulled':row.pulled,
        'pushed':row.pushed,'pending':row.pending,'last_success_at':timestamp(row.last_success_at),
        'last_checked_at':timestamp(row.last_checked_at),'error':row.error,
        'interval_minutes':settings.collection_sync_interval_minutes}

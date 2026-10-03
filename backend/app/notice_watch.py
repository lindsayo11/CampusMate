"""Continuously discover public university notices from official listing pages.

This monitor collects source text and evidence, not verified eligibility rules.
Installation is an explicit operator action. It never creates licence approvals
or endpoint calibrations. The separate qualification collector keeps its gates.
All network requests enforce the official HTTPS host, public IP and robots rules.
"""
import hashlib
import json
import re
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit
from uuid import uuid4

from bs4 import BeautifulSoup
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, or_, select, update

from .auth import require_admin
from .collector_http import FetchError, collect_bytes_conditional, validate_url
from .config import settings
from .database import SessionLocal, get_db
from .governance import audit
from .intake import ingest_university_notice
from .intake_models import DocumentVersion, NoticeResource, Source, SourceBlocker, SourceEndpoint
from .adapters.base import RawArtifact
from .adapters.notice_text import discover_notices
from .parsers import ParseError
from .source_registry import stable_id

MODE = 'public_notice_watch'
_host_last_request = {}
router = APIRouter(prefix='/v1/admin/notice-watch')


def config_for(endpoint):
    return json.loads(endpoint.adapter_config or '{}')


def timestamp(value):
    if value is None:
        return None
    return (value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)).isoformat()


def permitted(db, endpoint):
    source = db.get(Source, endpoint.source_id) if endpoint else None
    if not endpoint or not endpoint.active or not endpoint.scheduled or endpoint.manual_takeover:
        return False
    config = config_for(endpoint)
    if (not source or not source.active or not source.official or endpoint.auth_type != 'none'
            or endpoint.license_status == 'restricted'
            or set(json.loads(endpoint.access_tags or '[]')) & {'LOGIN-USER','COMMERCIAL','LICENSE','API-AUTH'}
            or config.get('collection_mode') != MODE or not config.get('authorized_by')):
        return False
    return not db.scalar(select(SourceBlocker.id).where(SourceBlocker.source_id == source.id,
        SourceBlocker.status == 'open', or_(SourceBlocker.endpoint_id.is_(None),
                                           SourceBlocker.endpoint_id == endpoint.id)))


def official_url(url, base):
    p, b = urlsplit(urljoin(base, url)), urlsplit(base)
    if (p.scheme != 'https' or p.hostname != b.hostname or p.port not in (None,443)
            or p.username or p.password or len(p.geturl()) > 500):
        return None
    return urlunsplit((p.scheme,p.netloc,p.path,p.query,''))


def add_resource(db, endpoint_id, url, kind, now, title='', parent='', depth=0):
    rid = stable_id('notice-resource:' + endpoint_id + ':' + url)
    existing = db.get(NoticeResource,rid)
    if existing:
        if existing.status == 'retired' and kind == 'index':
            existing.status,existing.next_check_at = 'queued',now
        return False
    if db.scalar(select(func.count()).select_from(NoticeResource).where(
            NoticeResource.endpoint_id == endpoint_id,NoticeResource.checked_at.is_(None),
            NoticeResource.status!='retired')) >= 200:
        raise ParseError('待采集队列达到 200 条，请先处理积压后再发现新通知')
    db.add(NoticeResource(id=rid,endpoint_id=endpoint_id,url=url,title=title[:240],kind=kind,
        parent_url=parent,depth=depth,discovered_at=now,next_check_at=now))
    db.flush()
    return True


def install(db, actor, manifest_path=None):
    """Configure listing URLs only; no hand-maintained detail links or approvals."""
    manifest = json.loads((manifest_path or Path(__file__).with_name('postgraduate_sources.json')).read_text())
    installed = 0
    for entry in manifest['sources']:
        source = db.scalar(select(Source).where(Source.source_code == entry['code']))
        if not source:
            raise ValueError('请先登记来源')
        urls = entry['index_urls']
        for url in urls:
            if not official_url(url,source.base_url):
                raise ValueError('栏目地址必须位于该来源的官方 HTTPS 主机')
            validate_url(url)
        endpoint = db.scalar(select(SourceEndpoint).where(SourceEndpoint.source_id == source.id,
            SourceEndpoint.name == 'graduate_admission_notices'))
        if not endpoint:
            raise ValueError('缺少高校通知端点')
        config = config_for(endpoint)
        # Re-installation preserves pauses and operator configuration.
        if config.get('collection_mode') != MODE:
            endpoint.adapter_config = json.dumps({'notice_scope':'university','collection_mode':MODE,
                'index_urls':urls,'interval_hours':12,'authorized_by':actor},ensure_ascii=False)
            endpoint.scheduled = True
            endpoint.manual_takeover = False
            endpoint.paused_reason = ''
            endpoint.fetch_interval = '12h'
        elif config.get('index_urls') != urls:
            config['index_urls'] = urls
            endpoint.adapter_config = json.dumps(config,ensure_ascii=False)
            # Preserve history while retiring superseded listing addresses.
            db.execute(update(NoticeResource).where(NoticeResource.endpoint_id==endpoint.id,
                NoticeResource.kind=='index').values(status='retired',
                    next_check_at=datetime(2100,1,1,tzinfo=UTC)))
        for url in urls:
            add_resource(db,endpoint.id,url,'index',datetime.now(UTC))
        installed += 1
    audit(db,actor,'notice_watch_install','source_registry',{'sources':installed})
    db.commit()
    return {'sources':installed}


def seed_frontier():
    with SessionLocal.begin() as db:
        for ep in db.scalars(select(SourceEndpoint).where(SourceEndpoint.scheduled.is_(True))).all():
            if permitted(db,ep):
                for url in config_for(ep).get('index_urls',[])[:4]:
                    if official_url(url,db.get(Source,ep.source_id).base_url):
                        add_resource(db,ep.id,url,'index',datetime.now(UTC))


def discover(db, resource, content, final_url, now):
    found = discover_notices(content,final_url,limit=30)
    structure_recognized = bool(found)
    # Admission years roll forward automatically. Dates remain parsed from the article.
    found = [x for x in found if not re.search(r'专业目录|招生目录|宣传|宣讲|咨询会|分数线',x['title'])
        and not ('博士' in x['title'] and not re.search(r'推免|免试|硕士|硕博',x['title']))
        and (not re.findall(r'20\d{2}',x['title']) or max(map(int,re.findall(r'20\d{2}',x['title']))) >= now.year-1)]
    for entry in found:
        if entry['url'] != resource.url:
            add_resource(db,resource.endpoint_id,entry['url'],'detail',now,entry['title'],resource.url)
    if resource.depth < 2:
        soup = BeautifulSoup(content,'html.parser')
        for link in soup.select('a[href]'):
            if re.fullmatch(r'\s*(?:下一页|下页|Next|›|>)\s*',link.get_text(strip=True),re.I):
                url = official_url(link['href'],final_url)
                if url and url != resource.url:
                    add_resource(db,resource.endpoint_id,url,'index',now,parent=resource.url,depth=resource.depth+1)
                    break
    if not structure_recognized:
        raise ParseError('栏目未发现可解析的考研／推免通知，请检查栏目结构')


def embedded_pdfs(content, base):
    soup = BeautifulSoup(content,'html.parser')
    result = []
    for node in soup.select('iframe[src], embed[src], object[data], [pdfsrc], a[href]'):
        raw = node.get('pdfsrc') or node.get('data') or node.get('src') or node.get('href')
        url = official_url(raw,base)
        if url and re.search(r'\.pdf(?:\?|$)',url,re.I) and url not in result:
            result.append(url)
    return result[:3]


def process_once(now=None):
    now = now or datetime.now(UTC)
    token = str(uuid4())
    with SessionLocal.begin() as db:
        # Paused sources cannot starve active ones; filter before claiming.
        ids = [ep.id for ep in db.scalars(select(SourceEndpoint).where(
            SourceEndpoint.scheduled.is_(True))).all() if permitted(db,ep)]
        row = db.scalar(select(NoticeResource).where(NoticeResource.endpoint_id.in_(ids),
            NoticeResource.status != 'retired',
            NoticeResource.next_check_at <= now,
            or_(NoticeResource.lease_until.is_(None),NoticeResource.lease_until <= now))
            .order_by(NoticeResource.next_check_at,NoticeResource.id).limit(1))
        if not row:
            return None
        claimed = db.execute(update(NoticeResource).where(NoticeResource.id == row.id,
            or_(NoticeResource.lease_until.is_(None),NoticeResource.lease_until <= now))
            .values(lease_token=token,lease_until=now+timedelta(minutes=5)))
        if not claimed.rowcount:
            return None
        rid,url,etag,last_modified = row.id,row.url,row.etag,row.last_modified
        ep = db.get(SourceEndpoint,row.endpoint_id)
        previous_config = ep.adapter_config
        source_base = db.get(Source,ep.source_id).base_url
    try:
        if not official_url(url,source_base):
            raise FetchError('来源 URL 不属于官方 HTTPS 主机')
        host = urlsplit(url).hostname
        delay = 1 - (time.monotonic() - _host_last_request.get(host,0))
        if delay > 0:
            time.sleep(delay)
        _host_last_request[host] = time.monotonic()
        response = collect_bytes_conditional(url,etag,last_modified,strict_robots=True)
        if not official_url(response['final_url'],source_base):
            raise FetchError('重定向离开官方 HTTPS 主机')
        finished = datetime.now(UTC)
        with SessionLocal.begin() as db:
            row = db.get(NoticeResource,rid)
            ep = db.get(SourceEndpoint,row.endpoint_id)
            if row.lease_token != token:
                return {'status':'lease_lost'}
            if not permitted(db,ep) or ep.adapter_config != previous_config:
                row.lease_token = row.lease_until = None
                return {'status':'cancelled'}
            source = db.get(Source,ep.source_id)
            changed = False
            if response['not_modified']:
                if not row.content_hash:
                    raise FetchError('304 响应缺少本地采集历史')
                row.status = 'unchanged' if row.status not in {'needs_review','attachments_pending'} else row.status
            else:
                content = response['data']
                if row.kind == 'index':
                    discover(db,row,content,response['final_url'],finished)
                    row.status = 'checked'
                else:
                    final_url = response['final_url']
                    item_id = final_url if len(final_url) <= 160 else hashlib.sha256(final_url.encode()).hexdigest()
                    raw = RawArtifact(content,final_url,item_id,response['content_type'],response['etag'],response['last_modified'])
                    db.info['import_mode'] = 'system'
                    try:
                        with db.begin_nested():
                            result = ingest_university_notice(db,source,ep,raw,{'notice_scope':'university'})
                    except ParseError:
                        pdfs = [] if content.startswith(b'%PDF') else embedded_pdfs(content,final_url)
                        if not pdfs:
                            raise
                        for pdf in pdfs:
                            add_resource(db,ep.id,pdf,'attachment',finished,row.title,final_url)
                        row.status = 'attachments_pending'
                    else:
                        from .data_catalog import auto_publish
                        from .source_scheduler import publish_collected_document, _change_review
                        doc = db.get(DocumentVersion,result['document_version_id'])
                        # Honour an administrator's deletion of unchanged archives.
                        if not doc.deleted_at:
                            if auto_publish(db,doc):
                                publish_collected_document(db,doc)
                        row.document_id = doc.id
                        changed = result['changed']
                        row.status = 'updated' if changed else 'unchanged'
                        if changed:
                            _change_review(db,ep,doc,doc.raw_text)
                row.content_hash = hashlib.sha256(content).hexdigest()
                row.etag = response['etag']
                row.last_modified = response['last_modified']
            row.checked_at = finished
            if changed:
                row.changed_at = finished
            row.next_check_at = finished + timedelta(hours=12 if row.kind == 'index' else 24)
            row.failures,row.error = 0,''
            row.lease_until = row.lease_token = None
            return {'url':url,'kind':row.kind,'status':row.status,'document_id':row.document_id}
    except Exception as exc:
        with SessionLocal.begin() as db:
            row = db.get(NoticeResource,rid)
            if row.lease_token != token:
                return {'status':'lease_lost'}
            row.failures += 1
            row.checked_at = datetime.now(UTC)
            row.status = 'needs_review' if isinstance(exc,ParseError) else 'retry'
            row.error = str(exc)[:300] if isinstance(exc,(FetchError,ParseError,ValueError)) else '采集或入库失败，等待重试'
            hours = 24 if isinstance(exc,ParseError) else min(12,2**(row.failures-1))
            row.next_check_at = row.checked_at + timedelta(hours=hours)
            if isinstance(exc,FetchError) and exc.retry_after:
                from .source_scheduler import retry_delay
                row.next_check_at = max(row.next_check_at,
                    row.checked_at + retry_delay(exc,row.failures,row.checked_at))
            row.lease_until = row.lease_token = None
            return {'url':url,'status':row.status,'error':row.error}


def run_cycle():
    if not settings.public_notice_watch_enabled:
        return []
    seed_frontier()
    result = []
    started = time.monotonic()
    # Bounded work lets reminders and the worker heartbeat keep running.
    for _ in range(2):
        if time.monotonic() - started > 15:
            break
        item = process_once()
        if item is None:
            break
        result.append(item)
    return result


def monitor_status(db):
    result = []
    for ep in db.scalars(select(SourceEndpoint)).all():
        if config_for(ep).get('collection_mode') != MODE:
            continue
        source = db.get(Source,ep.source_id)
        rows = db.scalars(select(NoticeResource).where(NoticeResource.endpoint_id == ep.id)).all()
        indices = [r for r in rows if r.kind == 'index' and r.url in config_for(ep).get('index_urls',[])]
        errors = [r for r in rows if r.error and r.status != 'retired']
        index_errors = [r for r in indices if r.error]
        checked = [r.checked_at for r in indices if r.checked_at]
        result.append({'endpoint_id':ep.id,'name':source.name,'source_code':source.source_code,
            'enabled':bool(settings.public_notice_watch_enabled and permitted(db,ep)),
            'columns':config_for(ep).get('index_urls',[]),
            'last_checked':timestamp(max(checked)) if checked else None,
            'next_check':timestamp(min((r.next_check_at for r in indices),default=None)),
            'discovered':sum(r.kind != 'index' for r in rows),
            'collected':sum(bool(r.document_id) for r in rows),
            'pending':sum(not r.checked_at and r.kind != 'index' for r in rows),
            'issues':len(errors),'last_error':index_errors[-1].error if index_errors else '',
            'index_healthy':bool(indices and all(r.content_hash and not r.error for r in indices)),
            'interval_hours':12})
    return sorted(result,key=lambda x:x['source_code'])


@router.get('')
def status(user=Depends(require_admin),db=Depends(get_db)):
    return {'enabled':settings.public_notice_watch_enabled,'sources':monitor_status(db),
        'resources':[{'id':r.id,'url':r.url,'title':r.title,'kind':r.kind,'status':r.status,
            'error':r.error,'checked_at':timestamp(r.checked_at),'next_check_at':timestamp(r.next_check_at)}
            for r in db.scalars(select(NoticeResource).where(NoticeResource.status!='retired')
                .order_by(NoticeResource.discovered_at.desc()).limit(200))]}


@router.post('/install')
def install_route(user=Depends(require_admin),db=Depends(get_db)):
    try:
        return install(db,user)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc


class Control(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool


@router.patch('/{endpoint_id}')
def control(endpoint_id:str,body:Control,user=Depends(require_admin),db=Depends(get_db)):
    ep = db.get(SourceEndpoint,endpoint_id)
    if not ep or config_for(ep).get('collection_mode') != MODE:
        raise HTTPException(404,'持续采集来源不存在')
    ep.scheduled = body.enabled
    audit(db,user,'notice_watch_control',endpoint_id,{'enabled':body.enabled})
    db.commit()
    return {'enabled':ep.scheduled}


@router.post('/{endpoint_id}/rescan')
def rescan(endpoint_id:str,user=Depends(require_admin),db=Depends(get_db)):
    ep = db.get(SourceEndpoint,endpoint_id)
    if not ep or not permitted(db,ep):
        raise HTTPException(422,'来源已暂停或不允许持续采集')
    if not settings.public_notice_watch_enabled:
        raise HTTPException(422,'持续采集服务未启用')
    db.execute(update(NoticeResource).where(NoticeResource.endpoint_id==endpoint_id,
        NoticeResource.kind=='index',NoticeResource.status!='retired').values(next_check_at=datetime.now(UTC)))
    audit(db,user,'notice_watch_rescan',endpoint_id)
    db.commit()
    return {'status':'queued'}

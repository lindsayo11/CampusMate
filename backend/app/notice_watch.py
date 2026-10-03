"""Continuously discover public notices from official listing pages across channels.

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
from urllib.parse import urlsplit, parse_qs
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
from .intake import ingest_university_notice, ingest_public_notice
from .intake_models import DocumentVersion, NoticeResource, Source, SourceBlocker, SourceEndpoint
from .adapters.base import RawArtifact
from .adapters.notice_text import document_base
from .adapters.index_discovery import discover_index, official_url
from .adapters.public_request import fetch_public_resource, request_spec
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
            or endpoint.automation_level == 'AUTO-4' or endpoint.agent_mode == 'USER_ACTION'
            or endpoint.license_status == 'restricted'
            or set(json.loads(endpoint.access_tags or '[]')) & {'LOGIN-USER','COMMERCIAL','LICENSE','API-AUTH'}
            or config.get('collection_mode') != MODE or not config.get('authorized_by')):
        return False
    return not db.scalar(select(SourceBlocker.id).where(SourceBlocker.source_id == source.id,
        SourceBlocker.status == 'open', or_(SourceBlocker.endpoint_id.is_(None),
                                           SourceBlocker.endpoint_id == endpoint.id)))


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
    if manifest_path is None:
        from .public_source_catalog import watch_entries
        from .source_registry import seed_registry
        seed_registry(db)
        manifest['sources'].extend(watch_entries())
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
            SourceEndpoint.name == entry.get('endpoint_name', 'graduate_admission_notices')))
        if not endpoint:
            raise ValueError('缺少公开通知端点')
        topic = entry.get('topic', 'postgraduate')
        from .adapters.notice_text import TOPIC_PATTERNS
        if topic not in TOPIC_PATTERNS:
            raise ValueError('未知的公开通知主题')
        desired = {'index_urls': urls, 'topic': topic,
                   'interval_hours': max(6, min(168, entry.get('interval_hours', 12))),
                   'detail_interval_hours': max(12, min(720, entry.get('detail_interval_hours', 24)))}
        if entry.get('path_code'):
            desired['path_code'] = entry['path_code']
        for key in ('article_selector', 'title_selector', 'discovery_format', 'json_index',
                    'index_formats', 'detail_path_prefixes', 'title_context', 'date_timezone',
                    'index_requests', 'detail_request', 'json_detail'):
            if entry.get(key):
                desired[key] = entry[key]
        if entry.get('history_index_limit'):
            desired['history_index_limit']=min(200,max(16,int(entry['history_index_limit'])))
            desired['history_depth_limit']=min(100,max(2,int(entry.get('history_depth_limit',2))))
        config = config_for(endpoint)
        # Re-installation preserves pauses and operator configuration.
        if config.get('collection_mode') != MODE:
            endpoint.adapter_config = json.dumps({'notice_scope':'university','collection_mode':MODE,
                **desired,'authorized_by':actor},ensure_ascii=False)
            endpoint.scheduled = True
            endpoint.manual_takeover = False
            endpoint.paused_reason = ''
            endpoint.fetch_interval = '12h'
        else:
            changed_urls = config.get('index_urls') != urls
            config.update(desired)
            endpoint.adapter_config = json.dumps(config,ensure_ascii=False)
            # Preserve history while retiring superseded listing addresses.
            if changed_urls:
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
    config = config_for(db.get(SourceEndpoint, resource.endpoint_id))
    topic = config.get('topic', 'postgraduate')
    # Select per-URL configuration using the original URL even after a same-host redirect.
    discovery_config = {**config, 'discovery_format': config.get('index_formats', {}).get(
        resource.url, config.get('discovery_format', 'auto')), 'index_page_url':resource.url}
    discovery_config.pop('index_formats', None)
    known_urls = set(db.scalars(select(NoticeResource.url).where(
        NoticeResource.endpoint_id==resource.endpoint_id, NoticeResource.status!='retired')))
    result = discover_index(content,final_url,discovery_config,limit=30,known_urls=known_urls)
    found = result['links']
    structure_recognized = result['recognized']
    # Admission years roll forward automatically. Dates remain parsed from the article.
    if topic == 'postgraduate':
        found = [x for x in found if not re.search(r'宣传|宣讲|咨询会|分数线', x['title'])
            and (not re.findall(r'20\d{2}',x['title']) or max(map(int,re.findall(r'20\d{2}',x['title']))) >= now.year-1)]
    pending = db.scalar(select(func.count()).select_from(NoticeResource).where(
        NoticeResource.endpoint_id==resource.endpoint_id,NoticeResource.checked_at.is_(None),
        NoticeResource.status!='retired'))
    remaining = max(0,200-pending)
    for entry in found:
        if entry['url'] != resource.url:
            if entry['url'] not in known_urls and remaining:
                add_resource(db,resource.endpoint_id,entry['url'],'detail',now,entry['title'],resource.url)
                remaining -= 1
    if resource.depth < config.get('history_depth_limit',2):
        index_count = db.scalar(select(func.count()).select_from(NoticeResource).where(
            NoticeResource.endpoint_id==resource.endpoint_id, NoticeResource.kind=='index',
            NoticeResource.status!='retired'))
        for url in result['indexes'][:min(remaining,max(0,config.get('history_index_limit',16)-index_count))]:
            add_resource(db,resource.endpoint_id,url,'index',now,parent=resource.url,depth=resource.depth+1)
    if not structure_recognized:
        raise ParseError('栏目未发现可解析的主题通知，请检查栏目结构')


def embedded_pdfs(content, base):
    soup = BeautifulSoup(content,'html.parser')
    base = document_base(soup, base)
    result = []
    # VSB publishes a literal file argument in its viewer call. Parse the URL only;
    # never execute JS or read the accompanying rendered-image arrays as text.
    for script in soup.select('script'):
        for match in re.finditer(r'''showVsbpdfIframe\(\s*(['"])([^'"\s]+)\1\s*[,)]''',script.get_text()):
            url = official_url(match[2],base)
            if url and url not in result:
                result.append(url)
    for node in soup.select('iframe[src], embed[src], object[data], [pdfsrc], a[href]'):
        raw = node.get('pdfsrc') or node.get('data') or node.get('src') or node.get('href')
        url = official_url(raw,base)
        if url and node.name in {'iframe','embed','object'}:
            files = parse_qs(urlsplit(url).query).get('file', [])
            if len(files) == 1:
                url = official_url(files[0],url)
        if url and (re.search(r'\.pdf(?:\?|$)',url,re.I) or
                    (node.name=='a' and re.search(r'\.pdf\b',node.get_text(' ',strip=True),re.I))) and url not in result:
            result.append(url)
    return result[:3]


def process_once(now=None, endpoint_ids=None):
    now = now or datetime.now(UTC)
    token = str(uuid4())
    with SessionLocal.begin() as db:
        # Paused sources cannot starve active ones; filter before claiming.
        ids = [ep.id for ep in db.scalars(select(SourceEndpoint).where(
            SourceEndpoint.scheduled.is_(True))).all() if permitted(db,ep)
            and (endpoint_ids is None or ep.id in endpoint_ids)]
        # Rotate across sources using persisted check history, including after worker restart.
        # A busy source's backlog cannot indefinitely delay another source's first check.
        history = select(NoticeResource.endpoint_id.label('endpoint_id'),
            func.max(NoticeResource.checked_at).label('last_checked')).group_by(
                NoticeResource.endpoint_id).subquery()
        row = db.scalar(select(NoticeResource).outerjoin(history,
            history.c.endpoint_id==NoticeResource.endpoint_id).where(NoticeResource.endpoint_id.in_(ids),
            NoticeResource.status != 'retired',
            NoticeResource.next_check_at <= now,
            or_(NoticeResource.lease_until.is_(None),NoticeResource.lease_until <= now))
            .order_by(history.c.last_checked.asc().nullsfirst(),NoticeResource.next_check_at,NoticeResource.id).limit(1))
        if not row:
            return None
        claimed = db.execute(update(NoticeResource).where(NoticeResource.id == row.id,
            or_(NoticeResource.lease_until.is_(None),NoticeResource.lease_until <= now))
            .values(lease_token=token,lease_until=now+timedelta(minutes=5))
            .execution_options(synchronize_session=False))
        if not claimed.rowcount:
            return None
        rid,url,etag,last_modified = row.id,row.url,row.etag,row.last_modified
        ep = db.get(SourceEndpoint,row.endpoint_id)
        previous_config = ep.adapter_config
        config = config_for(ep)
        index_format = config.get('index_formats', {}).get(url, config.get('discovery_format', 'auto'))
        if row.kind == 'index' and index_format == 'sitemap':
            # A stable map must still advance its bounded backfill after a previous batch.
            # Other indexes and all detail pages retain conditional requests.
            etag = last_modified = None
        source_base = db.get(Source,ep.source_id).base_url
    response = None
    try:
        if not official_url(url,source_base):
            raise FetchError('来源 URL 不属于官方 HTTPS 主机')
        host = urlsplit(url).hostname
        delay = 1 - (time.monotonic() - _host_last_request.get(host,0))
        if delay > 0:
            time.sleep(delay)
        _host_last_request[host] = time.monotonic()
        if request_spec(url, config, row.kind):
            response = fetch_public_resource(url, config, row.kind, etag, last_modified)
        else:
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
                    final_url = response.get('canonical_url', response['final_url'])
                    item_id = final_url if len(final_url) <= 160 else hashlib.sha256(final_url.encode()).hexdigest()
                    raw = RawArtifact(content,final_url,item_id,response['content_type'],response['etag'],response['last_modified'],
                        response.get('retrieval_url'),response.get('retrieval_method','GET'),response.get('retrieval_form'))
                    db.info['import_mode'] = 'system'
                    try:
                        with db.begin_nested():
                            config = config_for(ep)
                            if row.kind == 'support_file':
                                from .supporting_attachments import ingest_office_attachment
                                result = ingest_office_attachment(db,source,ep,raw,row.parent_url)
                            elif config.get('topic', 'postgraduate') == 'postgraduate':
                                result = ingest_university_notice(db,source,ep,raw,{**config,'notice_scope':'university'})
                            else:
                                result = ingest_public_notice(db,source,ep,raw,config)
                    except ParseError:
                        from .supporting_attachments import image_links
                        pdfs = [] if row.kind=='support_file' or content.startswith(b'%PDF') else embedded_pdfs(content,final_url)
                        images=[] if row.kind!='detail' else image_links(content,final_url,config)
                        if not pdfs and not images:
                            raise
                        for pdf in pdfs+images:
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
                        if row.kind=='attachment' and row.parent_url:
                            parent=db.scalar(select(NoticeResource).where(NoticeResource.endpoint_id==ep.id,
                                NoticeResource.url==row.parent_url,NoticeResource.status=='attachments_pending'))
                            if parent:
                                parent.document_id=doc.id;parent.status='attachment_collected'
                                parent.last_success_at=finished;parent.error=''
                        changed = result['changed']
                        row.status = 'updated' if changed else 'unchanged'
                        if row.kind=='detail' and not content.startswith(b'%PDF'):
                            from .supporting_attachments import supporting_links
                            for attachment in supporting_links(content,final_url,config):
                                count=db.scalar(select(func.count()).select_from(NoticeResource).where(
                                    NoticeResource.endpoint_id==ep.id,NoticeResource.checked_at.is_(None),
                                    NoticeResource.status!='retired'))
                                if count>=200:break
                                add_resource(db,ep.id,attachment,'support_file',finished,parent=final_url)
                        if changed:
                            _change_review(db,ep,doc,doc.raw_text)
                row.content_hash = hashlib.sha256(content).hexdigest()
                row.etag = response['etag']
                row.last_modified = response['last_modified']
            row.checked_at = finished
            if changed:
                row.changed_at = finished
            config = config_for(ep)
            interval = config.get('interval_hours', 12) if row.kind == 'index' else config.get('detail_interval_hours', 24)
            row.next_check_at = finished + timedelta(hours=max(6, min(720, interval)))
            row.failures,row.error = 0,''
            if row.status!='attachments_pending':
                row.last_success_at=finished
            from .collection_monitor import record_attempt
            record_attempt(db,row,'pending_attachment' if row.status=='attachments_pending' else 'success',response)
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
            if not isinstance(exc,(FetchError,ParseError,ValueError)):
                import logging
                logging.exception('Notice collection failed for resource %s',rid)
            hours = 24 if isinstance(exc,ParseError) else min(12,2**(row.failures-1))
            if re.search(r'登录|验证码',row.error):
                hours=168  # No repeated attempts to solve or bypass access challenges.
            row.next_check_at = row.checked_at + timedelta(hours=hours)
            if isinstance(exc,FetchError) and exc.retry_after:
                from .source_scheduler import retry_delay
                row.next_check_at = max(row.next_check_at,
                    row.checked_at + retry_delay(exc,row.failures,row.checked_at))
            row.lease_until = row.lease_token = None
            from .collection_monitor import record_attempt
            record_attempt(db,row,'failed',response,row.error)
            return {'url':url,'status':row.status,'error':row.error}


def run_cycle(endpoint_ids=None):
    if not settings.public_notice_watch_enabled:
        return []
    seed_frontier()
    result = []
    started = time.monotonic()
    # Bounded work lets reminders and the worker heartbeat keep running.
    for _ in range(settings.public_notice_watch_batch_size):
        if time.monotonic() - started > 15:
            break
        item = process_once(endpoint_ids=endpoint_ids)
        if item is None:
            break
        result.append(item)
    return result


def monitor_status(db):
    from .coverage_quality import error_category, utc
    from collections import Counter
    now = datetime.now(UTC)
    result = []
    for ep in db.scalars(select(SourceEndpoint)).all():
        if config_for(ep).get('collection_mode') != MODE:
            continue
        source = db.get(Source,ep.source_id)
        if not source or not source.active:
            continue
        rows = db.scalars(select(NoticeResource).where(NoticeResource.endpoint_id == ep.id)).all()
        indices = [r for r in rows if r.kind == 'index' and r.url in config_for(ep).get('index_urls',[])]
        errors = [r for r in rows if r.error and r.status != 'retired']
        index_errors = [r for r in indices if r.error]
        checked = [r.checked_at for r in indices if r.checked_at]
        successes = [r.last_success_at for r in indices if r.last_success_at]
        blocker = db.scalar(select(SourceBlocker).where(SourceBlocker.source_id == source.id,
            SourceBlocker.status == 'open', or_(SourceBlocker.endpoint_id.is_(None),
                                               SourceBlocker.endpoint_id == ep.id)))
        result.append({'endpoint_id':ep.id,'name':source.name,'source_code':source.source_code,
            'enabled':bool(settings.public_notice_watch_enabled and permitted(db,ep)),
            'columns':config_for(ep).get('index_urls',[]),
            'last_checked':timestamp(max(checked)) if checked else None,
            'next_check':timestamp(min((r.next_check_at for r in indices),default=None)),
            'discovered':sum(r.kind != 'index' for r in rows),
            'collected':sum(bool(r.document_id) for r in rows),
            'pending':sum(not r.checked_at and r.kind != 'index' for r in rows),
            'issues':len(errors),'last_error':(blocker.detail if blocker else index_errors[-1].error if index_errors else ''),
            'index_healthy':bool(indices and all(r.content_hash and not r.error for r in indices)),
            'interval_hours':config_for(ep).get('interval_hours', 12),
            'topic':config_for(ep).get('topic', 'postgraduate'), 'region':source.region_code})
        result[-1]['discovery_format'] = config_for(ep).get('discovery_format', 'auto')
        result[-1]['index_formats'] = config_for(ep).get('index_formats', {})
        details = [r for r in rows if r.kind == 'detail' and r.status != 'retired']
        last = max(checked) if checked else None
        age = (now-utc(last)).total_seconds()/3600 if last else None
        result[-1].update(details_discovered=len(details),
            details_collected=sum(bool(r.document_id) for r in details),
            freshness='unverified' if age is None else 'stale' if age > result[-1]['interval_hours']*2 else 'fresh',
            check_age_hours=round(age,1) if age is not None else None,
            error_categories=dict(Counter(error_category(r.error) for r in errors)))
        successful_age=max(((now-utc(r.last_success_at)).total_seconds()/3600 for r in indices
            if r.last_success_at),default=None)
        result[-1].update(last_successful_check=timestamp(min(successes)) if len(successes)==len(indices) and indices else None,
            success_freshness='never_succeeded' if len(successes)!=len(indices) or not indices else
                'stale' if successful_age>result[-1]['interval_hours']*2 else 'fresh')
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

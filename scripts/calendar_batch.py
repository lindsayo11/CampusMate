"""Reviewed official calendar batches: fetch locally, validate, then insert only.

No startup seeding, model migrations, personal-plan writes, or automatic URL discovery.
Database writes require --apply and DATABASE_URL from the operator's environment.
"""
from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[1]


def stable(value):
    return str(uuid5(NAMESPACE_URL, 'campusmate:calendar-batch:' + value))


def digest(value):
    return hashlib.sha256(value).hexdigest()


def stamp(value):
    if value is None:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError('Calendar dates must have an explicit timezone')
    return parsed.astimezone(UTC)


def facts_hash(entry):
    facts = {k: v for k, v in entry.items() if k not in {'raw_text', 'archive_base64', 'content_hash', 'fetched_at', 'content_type'}}
    return digest(json.dumps(facts, sort_keys=True, ensure_ascii=False).encode())


def validate(manifest):
    entries = manifest['entries']
    keys, urls = set(), set()
    for entry in entries:
        key, url = entry['key'], entry['url']
        if not re.fullmatch(r'[a-z0-9-]{4,60}', key) or key in keys or url in urls:
            raise ValueError('Duplicate or invalid source identity: ' + key)
        keys.add(key)
        urls.add(url)
        parts = urlsplit(url)
        if parts.scheme != 'https' or parts.username or parts.password or not parts.hostname:
            raise ValueError('Only reviewed public HTTPS sources are accepted')
        if not entry['checks'] or not entry['milestones']:
            raise ValueError('Every source needs explicit evidence and dated events')
        step_keys = set()
        for step in entry['milestones']:
            if step['key'] in step_keys:
                raise ValueError('Duplicate milestone: ' + key)
            step_keys.add(step['key'])
            start, end = stamp(step.get('start')), stamp(step.get('end'))
            if not (start or end) or (start and end and start > end):
                raise ValueError('Invalid date interval: ' + key)
            if step['precision'] not in {'day', 'time'}:
                raise ValueError('Date precision must be recorded')
        if 'archive_base64' in entry:
            raw = base64.b64decode(entry['archive_base64'], validate=True)
            if len(raw) > 3 * 1024 * 1024 or digest(raw) != entry['content_hash']:
                raise ValueError('Archived source checksum mismatch: ' + key)
            normalized = re.sub(r'\s+', '', entry['raw_text'])
            if any(re.sub(r'\s+', '', check) not in normalized for check in entry['checks']):
                raise ValueError('Date evidence missing from archived text: ' + key)
    return entries


def fetch(manifest, output, only=None):
    import httpx
    # Reuse the bounded fetcher: robots, HTTPS certificate, size and date checks.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from import_official_calendar import fetch_verified, UA
    validate(manifest)
    collected, reports = [], []
    if only and output.exists():
        previous = json.loads(gzip.decompress(output.read_bytes()))
        collected = [e for e in previous['entries'] if e['key'] != only]
    with httpx.Client(timeout=25, follow_redirects=False, trust_env=False, headers={'User-Agent': UA}) as client:
        for entry in manifest['entries']:
            if only and entry['key'] != only:
                continue
            try:
                verified = fetch_verified(client, {**entry, 'date_precision': ''})
                raw = verified['archive_bytes']
                collected.append({**entry, 'raw_text': verified['raw_text'],
                    'archive_base64': base64.b64encode(raw).decode(),
                    'content_hash': digest(raw), 'content_type': verified['content_type'],
                    'fetched_at': datetime.now(UTC).isoformat()})
                report = {'key':entry['key'], 'status':'verified', 'bytes':len(raw), 'events':len(entry['milestones'])}
            except Exception as exc:
                report = {'key':entry['key'], 'status':'failed', 'error':str(exc)[:350]}
            reports.append(report)
            print(json.dumps(report, ensure_ascii=False), flush=True)
            time.sleep(1)
    bundle = {**manifest, 'entries': collected}
    validate(bundle)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(gzip.compress(json.dumps(bundle, ensure_ascii=False).encode(), compresslevel=5))
    report_path = output.with_suffix('.report.json')
    if only and report_path.exists():
        reports = [r for r in json.loads(report_path.read_text(encoding='utf-8')) if r['key'] != only] + reports
    report_path.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'verified_sources':len(collected), 'events':sum(len(e['milestones']) for e in collected), 'bundle_bytes':output.stat().st_size}))


def import_entry(db, entry, batch):
    from sqlalchemy import select
    from app.intake_models import Source, SourceEndpoint, DocumentVersion, DocumentArchive, DevelopmentItem, DevelopmentItemPath, Evidence
    from app.models import Opportunity, Path as DevelopmentPath
    from app.sources import SourceDocument, SourceHead
    from app.knowledge import KnowledgeAccess, KnowledgePublication, DocumentChunk, split_text
    from app.data_catalog import auto_publish

    key, url = entry['key'], entry['url']
    doc_id, source_id, endpoint_id = (stable(prefix + key) for prefix in ['document:', 'source:', 'endpoint:'])
    old = db.get(DocumentVersion, doc_id)
    if old:
        endpoint = db.get(SourceEndpoint, endpoint_id)
        config = json.loads(endpoint.adapter_config) if endpoint else {}
        if old.content_hash != entry['content_hash'] or config.get('facts_hash') != facts_hash(entry):
            raise ValueError('Existing source changed; no overwrite permitted: ' + key)
        return {'key': key, 'status': 'unchanged', 'document_id': doc_id}
    if db.scalar(select(DocumentVersion.id).where(DocumentVersion.canonical_url == url, DocumentVersion.deleted_at.is_(None))):
        raise ValueError('Source URL already archived under another identity: ' + key)
    if db.get(SourceHead, digest(url.encode())):
        raise ValueError('Source head already exists; preserve it: ' + key)
    now = stamp(entry['fetched_at'])
    path = None
    if entry.get('path_code'):
        path = db.scalar(select(DevelopmentPath).where(DevelopmentPath.code == entry['path_code']))
        if path is None:
            raise ValueError('Missing development channel: ' + entry['path_code'])
    db.add(Source(id=source_id, source_code='CAL26-' + digest(key.encode())[:18],
        name=entry['source_label'], publisher=entry['source_label'], authority_level='A',
        official=True, source_class=entry.get('source_class','university'), jurisdiction_level='institution',
        supported_paths=json.dumps([entry['path_code']] if path else []),
        supported_item_types='["calendar_stage"]', base_url='https://' + urlsplit(url).netloc,
        active=True, verified_at=now))
    db.flush()
    db.add(SourceEndpoint(id=endpoint_id, source_id=source_id, name=key, endpoint_type='html',
        url=url, access_tags='["DIRECT"]', auth_type='none', format='html',
        parser_type='ReviewedCalendarBatch', automation_level='AUTO-2', agent_mode='REVIEW',
        active=True, scheduled=False, robots_status='allowed', rate_limit='1 request/second; one-off import',
        adapter_config=json.dumps({'reviewed_batch':batch,'facts_hash':facts_hash(entry)}),
        last_success_at=now))
    db.flush()
    doc = DocumentVersion(id=doc_id, source_endpoint_id=endpoint_id, canonical_url=url,
        source_item_id=key, publish_time=None, last_modified=None, content_hash=entry['content_hash'],
        first_seen_at=now, last_seen_at=now, last_changed_at=now, version_no=1, fetched_at=now,
        raw_storage_uri='db://document-archives/' + doc_id, raw_text=entry['raw_text'],
        import_mode='system', test_batch=None)
    db.add(doc)
    db.flush()
    db.add(DocumentArchive(document_id=doc_id, content=base64.b64decode(entry['archive_base64']),
        content_type=entry['content_type'], is_fixture=False))
    for step in entry['milestones']:
        item_id = stable('event:' + key + ':' + step['key'])
        precision = '原文仅精确到日；日历全天展示不代表官方公布了具体时刻。' if step['precision'] == 'day' else '时刻以原文为准；日历统一按北京时间显示。'
        db.add(DevelopmentItem(id=item_id, title=step['title'], item_type='calendar_stage', cycle_type='event',
            description=entry['summary'] + '\n' + step['note'] + '\n' + precision,
            start_time=stamp(step.get('start')), deadline=stamp(step.get('end')), location=entry['location'],
            materials=json.dumps(['查看官方原文','核对适用对象及最新安排'],ensure_ascii=False),
            status='published', source_document_id=doc_id))
        db.flush()
        if path:
            db.add(DevelopmentItemPath(development_item_id=item_id, path_id=path.id))
    db.add(Evidence(id=stable('evidence:' + key), document_version_id=doc_id, source_id=source_id,
        evidence_location='官方网页赛程/日程；采集原文保留在资料库', quote_or_normalized_fact=entry['excerpt'],
        extractor='verified-fetch', evidence_type='dom', review_status='verified',
        verified_by='calendar-review', verified_at=now))
    opportunity_id = 'cal-' + digest(key.encode())[:32]
    # Calendar stages are not necessarily open applications. Do not advertise
    # an activity-end time as a registration deadline in the opportunities API.
    db.add(Opportunity(id=opportunity_id, type='calendar', title=entry['title'], organization=entry['source_label'],
        summary=entry['summary'], location=entry['location'], deadline=None, source_url=url,
        source_label=entry['source_label'], trust_score=.98, tags='官方日程,2026年11月,' + entry['category'],
        status='published', fetched_at=now))
    db.add(SourceDocument(id=doc_id, source_url=url, content_hash=entry['content_hash'],
        raw_text=entry['raw_text'], fetched_at=now, archived_at=now))
    db.add(SourceHead(url_hash=digest(url.encode()), source_url=url, document_id=doc_id))
    for ordinal, start, end, text in split_text(entry['raw_text']):
        db.add(DocumentChunk(id=digest(f'{doc_id}:{start}:{end}'.encode()), document_id=doc_id,
            ordinal=ordinal, start_offset=start, end_offset=end, text=text))
    db.add(KnowledgePublication(document_id=doc_id, source='system', opportunity_id=None,
        title=entry['title'][:160], item_type=entry['category'][:20]))
    db.add(KnowledgeAccess(document_id=doc_id, public=True))
    db.flush()
    if not auto_publish(db, doc):
        raise ValueError('Publication gate rejected: ' + key)
    return {'key':key, 'status':'inserted', 'document_id':doc_id, 'events':len(entry['milestones'])}


def apply_bundle(bundle, commit=False):
    if not os.environ.get('DATABASE_URL'):
        raise RuntimeError('Explicit DATABASE_URL is required')
    validate(bundle)
    # Load mappings only. FastAPI startup/lifespan is never run.
    from app.main import app
    from app.database import SessionLocal
    from app.data_catalog import timeline
    from sqlalchemy import select, func
    from app.models import UserPlan
    with SessionLocal() as db:
        before_plans = db.scalar(select(func.count()).select_from(UserPlan))
        before_timeline = len({x['item_id'] for x in timeline(path=None, db=db)})
        results = [import_entry(db, entry, bundle['batch']) for entry in bundle['entries']]
        db.flush()
        nodes = timeline(path=None, db=db)
        if db.scalar(select(func.count()).select_from(UserPlan)) != before_plans:
            raise RuntimeError('Personal plan count unexpectedly changed')
        after_timeline = len({x['item_id'] for x in nodes})
        output = {'batch':bundle['batch'], 'committed':commit, 'before_public_events':before_timeline,
            'after_public_events':after_timeline, 'personal_plans_changed':0, 'results':results}
        if commit:
            db.commit()
        else:
            db.rollback()
        return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['fetch','import'])
    parser.add_argument('--manifest', type=Path, default=ROOT/'backend/app/calendar_november_2026.json')
    parser.add_argument('--bundle', type=Path, default=ROOT/'.test-runtime/november-2026.json.gz')
    parser.add_argument('--only')
    parser.add_argument('--backend', type=Path, default=ROOT/'backend')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if args.action == 'fetch':
        fetch(json.loads(args.manifest.read_text(encoding='utf-8')), args.bundle, args.only)
    else:
        sys.path.insert(0,str(args.backend))
        result = apply_bundle(json.loads(gzip.decompress(args.bundle.read_bytes())), args.apply)
        print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()

"""Configure continuous public-source discovery and process due persistent jobs.
Includes postgraduate columns and technically ready sources across all channels.
The regular app.worker polls columns every 12h and details every 24h by default.
"""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.database import SessionLocal
from app.migrate import check_schema
from app.notice_watch import install, monitor_status, run_cycle

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install',action='store_true')
    parser.add_argument('--actor',default='local-operator')
    parser.add_argument('--run',action='store_true')
    parser.add_argument('--batches',type=int,default=1,choices=range(1,51))
    parser.add_argument('--codes', nargs='+', help='Only process these installed source codes')
    parser.add_argument('--retry-issues',action='store_true',help='Recheck failed resources of explicitly selected sources after a parser/column fix')
    parser.add_argument('--refresh-indexes',action='store_true',help='Fetch selected active indexes now after a discovery configuration change')
    args=parser.parse_args()
    if (args.retry_issues or args.refresh_indexes) and not args.codes:
        parser.error('Explicit rechecks require --codes; no global retry storm')
    check_schema()
    if args.install:
        with SessionLocal() as db: print(json.dumps(install(db,args.actor)))
    selected = None
    if args.codes:
        with SessionLocal() as db:
            monitors = monitor_status(db)
        missing = set(args.codes) - {m['source_code'] for m in monitors}
        if missing:
            parser.error('Sources are not installed: ' + ', '.join(sorted(missing)))
        selected = [m['endpoint_id'] for m in monitors if m['source_code'] in args.codes]
    if args.retry_issues:
        from datetime import UTC, datetime
        from sqlalchemy import update, or_
        from app.intake_models import NoticeResource, SourceEndpoint
        from app.notice_watch import permitted
        with SessionLocal.begin() as db:
            ids=[eid for eid in selected if permitted(db,db.get(SourceEndpoint,eid))]
            now=datetime.now(UTC)
            result=db.execute(update(NoticeResource).where(NoticeResource.endpoint_id.in_(ids),
                NoticeResource.error!='',NoticeResource.status!='retired',
                or_(NoticeResource.lease_until.is_(None),NoticeResource.lease_until<=now))
                .values(next_check_at=now))
            print(json.dumps({'issues_scheduled_for_recheck':result.rowcount}),flush=True)
    if args.refresh_indexes:
        from datetime import UTC,datetime
        from sqlalchemy import update,or_
        from app.intake_models import NoticeResource,SourceEndpoint
        from app.notice_watch import permitted
        with SessionLocal.begin() as db:
            ids=[eid for eid in selected if permitted(db,db.get(SourceEndpoint,eid))]
            now=datetime.now(UTC)
            result=db.execute(update(NoticeResource).where(NoticeResource.endpoint_id.in_(ids),
                NoticeResource.kind=='index',NoticeResource.status!='retired',
                or_(NoticeResource.lease_until.is_(None),NoticeResource.lease_until<=now))
                .values(next_check_at=now,etag=None,last_modified=None))
            print(json.dumps({'indexes_scheduled_for_refresh':result.rowcount}),flush=True)
    if args.run:
        for _ in range(args.batches): print(json.dumps(run_cycle(endpoint_ids=selected),ensure_ascii=False,default=str),flush=True)
    with SessionLocal() as db: print(json.dumps(monitor_status(db),ensure_ascii=False,default=str))

if __name__=='__main__':main()

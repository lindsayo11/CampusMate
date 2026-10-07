"""Backfill official HTML/JSON DOCX/XLSX references and durable queues from archives."""
import argparse,json,sys
from datetime import UTC,datetime
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from sqlalchemy import select
from app.database import SessionLocal
from app.intake_models import NoticeResource,DocumentVersion,DocumentArchive,Source,SourceEndpoint
from app.notice_watch import add_resource,permitted,config_for
from app.supporting_attachments import supporting_links
from app.parser_upgrade import repair_json_attachments
from app.parsers import ParseError
from app.governance import audit

parser=argparse.ArgumentParser(description=__doc__)
scope=parser.add_mutually_exclusive_group(required=True)
scope.add_argument('--codes',nargs='+')
scope.add_argument('--all',action='store_true')
parser.add_argument('--apply',action='store_true')
args=parser.parse_args()
with SessionLocal() as db:
    query=select(NoticeResource,DocumentVersion,DocumentArchive,SourceEndpoint,Source).join(
        DocumentVersion,DocumentVersion.id==NoticeResource.document_id).join(
        DocumentArchive,DocumentArchive.document_id==DocumentVersion.id).join(
        SourceEndpoint,SourceEndpoint.id==NoticeResource.endpoint_id).join(Source,Source.id==SourceEndpoint.source_id).where(
        NoticeResource.kind=='detail',NoticeResource.status!='retired',DocumentVersion.import_mode=='system',
        DocumentVersion.deleted_at.is_(None),DocumentArchive.is_fixture.is_(False))
    if args.codes:query=query.where(Source.source_code.in_(args.codes))
    links,added,deferred,repaired=0,0,0,0
    for resource,doc,archive,endpoint,source in db.execute(query).all():
        if not permitted(db,endpoint):continue
        config=config_for(endpoint)
        if not config.get('json_detail') and not archive.content_type.startswith('text/html'):continue
        if config.get('json_detail'):
            result=repair_json_attachments(db,doc,config,apply=args.apply)
            repaired+=result['status'] in {'proposed','updated'}
        for url in supporting_links(archive.content,doc.canonical_url,config):
            links+=1
            if args.apply:
                try:added+=add_resource(db,endpoint.id,url,'support_file',datetime.now(UTC),parent=resource.url)
                except ParseError:deferred+=1
    result={'links':links,'queued':added,'deferred':deferred,'repaired_documents':repaired,'applied':args.apply}
    if args.apply:
        audit(db,'local-operator','office_attachments_backfill','notice-watch',result);db.commit()
    else:db.rollback()
    print(json.dumps(result))

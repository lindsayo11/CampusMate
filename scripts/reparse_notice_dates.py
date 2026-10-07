"""Preview/apply missing date extraction to already public system archives; no refetch/version fabrication."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from sqlalchemy import select
from app.database import SessionLocal
from app.intake_models import DocumentVersion,SourceEndpoint,Source
from app.notice_watch import config_for
from app.parser_upgrade import repair_notice_dates

parser=argparse.ArgumentParser(description=__doc__)
scope=parser.add_mutually_exclusive_group(required=True)
scope.add_argument('--codes',nargs='+')
scope.add_argument('--all',action='store_true')
parser.add_argument('--apply',action='store_true')
args=parser.parse_args()
with SessionLocal() as db:
    query=select(DocumentVersion).join(SourceEndpoint,SourceEndpoint.id==DocumentVersion.source_endpoint_id).join(Source,Source.id==SourceEndpoint.source_id)
    if args.codes:query=query.where(Source.source_code.in_(args.codes))
    docs=db.scalars(query).all()
    for doc in docs:
        try:
            with db.begin_nested():result=repair_notice_dates(db,doc,config_for(db.get(SourceEndpoint,doc.source_endpoint_id)),args.apply)
        except ValueError as exc:result={'document_id':doc.id,'status':'needs_review','error':str(exc)}
        print(json.dumps(result,ensure_ascii=False),flush=True)
    if args.apply:db.commit()
    else:db.rollback()

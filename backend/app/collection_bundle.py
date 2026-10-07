"""Portable official collection data only; never accounts, profiles or user plans."""
import argparse,base64,gzip,json
from datetime import datetime
from pathlib import Path
from sqlalchemy import select,DateTime,LargeBinary,insert,text
from .database import SessionLocal,Base
from .intake_models import (Source,SourceEndpoint,SourceBlocker,NoticeResource,DocumentVersion,
    DocumentArchive,Evidence,DevelopmentItem,DevelopmentItemPath,DataPublication,
    ApplicationCycle,Program,Institution)
from .models import Path as DevelopmentPath

TABLES=[DevelopmentPath,Source,SourceEndpoint,SourceBlocker,Institution,Program,ApplicationCycle,
    DocumentVersion,DocumentArchive,Evidence,DevelopmentItem,DevelopmentItemPath,DataPublication,NoticeResource]


def export_bundle(db):
    from .data_catalog import visible
    endpoints=[e for e in db.scalars(select(SourceEndpoint)).all()
        if json.loads(e.adapter_config or '{}').get('collection_mode')=='public_notice_watch'
        and e.auth_type=='none' and not e.secret_ref]
    eids={e.id for e in endpoints};sids={e.source_id for e in endpoints}
    publications=[p for p,data in visible(db) if data['document']['import_mode']=='system'
        and db.get(DocumentVersion,p.document_id).source_endpoint_id in eids]
    docs=db.scalars(select(DocumentVersion).where(DocumentVersion.source_endpoint_id.in_(eids),
        DocumentVersion.import_mode=='system',DocumentVersion.deleted_at.is_(None))).all()
    public_docs={p.document_id for p in publications}
    doc_ids={d.id for d in docs if d.id in public_docs or
        (d.raw_text.startswith('{') and json.loads(d.raw_text).get('kind')=='supporting_attachment'
            and json.loads(d.raw_text).get('parent_document_id') in public_docs)}
    # Keep byte history of current publicly visible source items.
    identities={(d.source_endpoint_id,d.source_item_id) for d in docs if d.id in doc_ids}
    doc_ids|={d.id for d in docs if (d.source_endpoint_id,d.source_item_id) in identities}
    doc_ids={id for id in doc_ids if (a:=db.get(DocumentArchive,id)) and not a.is_fixture}
    items=db.scalars(select(DevelopmentItem).where(DevelopmentItem.source_document_id.in_(doc_ids))).all()
    relations=db.scalars(select(DevelopmentItemPath).where(DevelopmentItemPath.development_item_id.in_([i.id for i in items]))).all()
    path_ids={r.path_id for r in relations}
    for pid in list(path_ids):
        p=db.get(DevelopmentPath,pid)
        while p and p.parent_id:
            path_ids.add(p.parent_id);p=db.get(DevelopmentPath,p.parent_id)
    cycles=db.scalars(select(ApplicationCycle).where(ApplicationCycle.id.in_([i.cycle_id for i in items if i.cycle_id]))).all()
    programs=db.scalars(select(Program).where(Program.id.in_([c.program_id for c in cycles]))).all()
    institutions=db.scalars(select(Institution).where(Institution.id.in_([p.institution_id for p in programs]))).all()
    resources=db.scalars(select(NoticeResource).where(NoticeResource.endpoint_id.in_(eids))).all()
    data={DevelopmentPath:db.scalars(select(DevelopmentPath).where(DevelopmentPath.id.in_(path_ids))).all(),
        Source:db.scalars(select(Source).where(Source.id.in_(sids))).all(),SourceEndpoint:endpoints,
        SourceBlocker:db.scalars(select(SourceBlocker).where(SourceBlocker.source_id.in_(sids))).all(),
        Institution:institutions,Program:programs,ApplicationCycle:cycles,
        DocumentVersion:[d for d in docs if d.id in doc_ids],
        DocumentArchive:db.scalars(select(DocumentArchive).where(DocumentArchive.document_id.in_(doc_ids))).all(),
        Evidence:db.scalars(select(Evidence).where(Evidence.document_version_id.in_(doc_ids))).all(),
        DevelopmentItem:items,DevelopmentItemPath:relations,DataPublication:publications,NoticeResource:resources}
    import io
    output=io.BytesIO()
    with gzip.GzipFile(fileobj=output,mode='wb',compresslevel=6) as stream:
        stream.write((json.dumps({'schema':2,'tables':[m.__tablename__ for m in TABLES]})+'\n').encode())
        for model in TABLES:
            for row in data[model]:
                value={c.name:getattr(row,c.name) for c in model.__table__.columns}
                if model is NoticeResource:
                    value.update(lease_token=None,lease_until=None)
                    if value['document_id'] not in doc_ids:value['document_id']=None
                for key,v in value.items():
                    if isinstance(v,bytes):value[key]=base64.b64encode(v).decode()
                    elif isinstance(v,datetime):value[key]=v.isoformat()
                stream.write((json.dumps({'table':model.__tablename__,'row':value},ensure_ascii=False)+'\n').encode())
    return output.getvalue()


def import_bundle(db,content):
    # Stream rows instead of loading all original files and snapshots at once.
    if len(content)>128*1024*1024:raise ValueError('Collection bundle exceeds 128 MiB')
    import io
    tables={m.__tablename__:m.__table__ for m in TABLES}
    counts={key:0 for key in tables};pending={key:[] for key in tables}
    existing={key:set(db.execute(select(*table.primary_key.columns)).all()) for key,table in tables.items()}
    expanded=0
    previous=None
    with gzip.GzipFile(fileobj=io.BytesIO(content)) as source:
        header=json.loads(source.readline(4096))
        if header.get('schema')!=2 or set(header['tables'])!=set(tables):
            raise ValueError('Unsupported collection bundle table set')
        while line:=source.readline(24*1024*1024+1):
            expanded+=len(line)
            if len(line)>24*1024*1024 or expanded>512*1024*1024:
                raise ValueError('Expanded collection bundle exceeds bounded limits')
            record=json.loads(line);name=record['table'];table=tables[name];row=record['row']
            if previous and previous!=name and pending[previous]:
                db.execute(insert(tables[previous]),pending[previous]);pending[previous]=[]
            previous=name
            if set(row)!={c.name for c in table.columns}:raise ValueError('Invalid collection columns')
            identity=tuple(row[c.name] for c in table.primary_key.columns)
            if identity in existing[name]:continue
            for column in table.columns:
                if row[column.name] is None:continue
                if isinstance(column.type,DateTime):row[column.name]=datetime.fromisoformat(row[column.name])
                elif isinstance(column.type,LargeBinary):row[column.name]=base64.b64decode(row[column.name],validate=True)
            existing[name].add(identity);pending[name].append(row);counts[name]+=1
            if len(pending[name])>=20:
                db.execute(insert(table),pending[name]);pending[name]=[]
        for name,rows in pending.items():
            if rows:db.execute(insert(tables[name]),rows)
    reset_import_sequences(db)
    return counts


def reset_import_sequences(db):
    """Explicit imported integer IDs must not collide with future Postgres inserts."""
    if db.get_bind().dialect.name!='postgresql':return
    quote=db.get_bind().dialect.identifier_preparer.quote
    for model in TABLES:
        table=model.__table__
        for column in table.primary_key.columns:
            sequence=db.scalar(text('SELECT pg_get_serial_sequence(:table, :column)'),
                {'table':table.name,'column':column.name})
            if not sequence:continue
            # Never move a live sequence backwards, including on idempotent re-import.
            db.execute(text(f'SELECT setval(CAST(:sequence AS regclass), '
                f'GREATEST(COALESCE((SELECT MAX({quote(column.name)}) FROM {quote(table.name)}),0), '
                'nextval(CAST(:sequence AS regclass))), true)'),{'sequence':sequence})


def main():
    parser=argparse.ArgumentParser();scope=parser.add_mutually_exclusive_group(required=True)
    scope.add_argument('--export');scope.add_argument('--import-file')
    args=parser.parse_args()
    with SessionLocal.begin() as db:
        if args.export:
            content=export_bundle(db);Path(args.export).write_bytes(content);print(json.dumps({'bytes':len(content)}))
        else:print(json.dumps(import_bundle(db,Path(args.import_file).read_bytes())))


if __name__=='__main__':main()

"""Re-extract missing dates from unchanged archives, with a separate audit trail."""
import json
from sqlalchemy import select

from .adapters.base import RawArtifact
from .adapters.education import PublicNoticeAdapter, UniversityNoticeAdapter
from .data_catalog import readiness, canonical, auto_publish
from .governance import audit
from .intake import _date, _persist_evidence
from .intake_models import DataPublication, DevelopmentItem, DocumentArchive, SourceEndpoint, Source, Evidence


def repair_json_attachments(db, doc, config, apply=False):
    """Fill verified missing attachment references without pretending the original changed."""
    pub=db.scalar(select(DataPublication).where(DataPublication.document_id==doc.id))
    if (not config.get('json_detail') or doc.deleted_at or doc.import_mode!='system' or not pub
            or pub.status!='published' or pub.submitted_by!='system-ingestion'
            or pub.first_reviewed_by or pub.second_reviewed_by):
        return {'document_id':doc.id,'status':'skipped'}
    snapshot,blocks=readiness(db,doc)
    if blocks or canonical(snapshot)!=pub.snapshot:
        return {'document_id':doc.id,'status':'skipped'}
    archive=db.get(DocumentArchive,doc.id)
    from .adapters.public_json_notice import PublicJSONNoticeAdapter
    parsed=PublicJSONNoticeAdapter(config['topic'],config['json_detail']).parse(
        RawArtifact(archive.content,doc.canonical_url,doc.source_item_id,archive.content_type))
    items=db.scalars(select(DevelopmentItem).where(DevelopmentItem.source_document_id==doc.id)).all()
    if len(items)!=1 or items[0].title!=parsed.records[0]['title'][:200]:
        return {'document_id':doc.id,'status':'skipped'}
    materials=json.loads(items[0].materials or '[]')
    known={row.get('url') for row in materials if isinstance(row,dict)}
    additions=[row for row in parsed.records[0]['attachments'] if row['url'] not in known]
    if not additions:return {'document_id':doc.id,'status':'unchanged'}
    if apply:
        endpoint=db.get(SourceEndpoint,doc.source_endpoint_id)
        source=db.get(Source,endpoint.source_id)
        _persist_evidence(db,source,doc,[p for p in parsed.evidence if p['field']=='attachments'])
        items[0].materials=json.dumps(materials+additions,ensure_ascii=False)
        normalized=json.loads(doc.raw_text)
        previous=normalized[0].get('attachments',[])
        existing={row.get('url') for row in previous if isinstance(row,dict)}
        normalized[0]['attachments']=previous+[row for row in additions if row['url'] not in existing]
        doc.raw_text=json.dumps(normalized,ensure_ascii=False)
        db.flush()
        if not auto_publish(db,doc):raise ValueError('附件证据修复后的公开快照无法刷新')
        audit(db,'system-parser-upgrade','json_attachments_repaired',f'document:{doc.id}',
            {'attachments':len(additions),'source_bytes_changed':False})
    return {'document_id':doc.id,'status':'updated' if apply else 'proposed','attachments':len(additions)}


def repair_json_title_provenance(db, doc, config, apply=False):
    """Repair the old missing nested JSON prefix only after checking archived bytes."""
    mapping=config.get('json_detail',{})
    publication=db.scalar(select(DataPublication).where(DataPublication.document_id==doc.id))
    if (not mapping.get('items_path') or doc.deleted_at or doc.import_mode!='system' or not publication
            or publication.status!='published' or publication.submitted_by!='system-ingestion'
            or publication.first_reviewed_by or publication.second_reviewed_by):
        return {'document_id':doc.id,'status':'skipped'}
    snapshot,blocks=readiness(db,doc)
    if blocks or canonical(snapshot)!=publication.snapshot:
        return {'document_id':doc.id,'status':'skipped'}
    archive=db.get(DocumentArchive,doc.id)
    if not archive or archive.is_fixture:
        return {'document_id':doc.id,'status':'skipped'}
    from .adapters.public_json_notice import PublicJSONNoticeAdapter
    parsed=PublicJSONNoticeAdapter(config['topic'],mapping).parse(RawArtifact(
        archive.content,doc.canonical_url,doc.source_item_id,archive.content_type))
    title=next(proof for proof in parsed.evidence if proof['field']=='title')
    proofs=db.scalars(select(Evidence).where(Evidence.document_version_id==doc.id,
        Evidence.evidence_type=='json',Evidence.extractor=='parser',
        Evidence.evidence_location=='json=$.'+mapping['title_field'],
        Evidence.quote_or_normalized_fact==title['quote_or_normalized_fact'])).all()
    if not proofs:return {'document_id':doc.id,'status':'unchanged'}
    if apply:
        for proof in proofs:proof.evidence_location=title['evidence_location']
        db.flush()
        if not auto_publish(db,doc):raise ValueError('证据定位修复后的公开快照无法刷新')
        audit(db,'system-parser-upgrade','json_title_provenance_repaired',f'document:{doc.id}',
            {'location':title['evidence_location'],'proofs':len(proofs),'source_bytes_changed':False})
    return {'document_id':doc.id,'status':'updated' if apply else 'proposed','proofs':len(proofs)}


def repair_notice_dates(db, doc, config, apply=False):
    publication=db.scalar(select(DataPublication).where(DataPublication.document_id==doc.id))
    if (doc.deleted_at or doc.import_mode!='system' or not publication or publication.status!='published'
            or publication.submitted_by!='system-ingestion' or publication.first_reviewed_by
            or publication.second_reviewed_by):
        return {'document_id':doc.id,'status':'skipped'}
    snapshot, blocks=readiness(db,doc)
    if blocks or canonical(snapshot)!=publication.snapshot:
        return {'document_id':doc.id,'status':'skipped'}
    archive=db.get(DocumentArchive,doc.id)
    if not archive or archive.is_fixture:
        return {'document_id':doc.id,'status':'skipped'}
    if config.get('json_detail'):
        from .adapters.public_json_notice import PublicJSONNoticeAdapter
        adapter=PublicJSONNoticeAdapter(config['topic'],config['json_detail'])
    elif config.get('topic','postgraduate')=='postgraduate':
        adapter=UniversityNoticeAdapter(article_selector=config.get('article_selector'),title_selector=config.get('title_selector'))
    else:
        adapter=PublicNoticeAdapter(config['topic'],config.get('article_selector'),config.get('title_selector'),
            config.get('title_context',''),config.get('date_timezone'))
    parsed=adapter.parse(RawArtifact(archive.content,doc.canonical_url,doc.source_item_id,archive.content_type))
    values=parsed.records[0]
    items=db.scalars(select(DevelopmentItem).where(DevelopmentItem.source_document_id==doc.id)).all()
    if len(items)!=1 or values['title'][:200]!=items[0].title:
        return {'document_id':doc.id,'status':'skipped'}
    item=items[0]
    changes={target:_date(values[field]) for field,target in [('open_at','start_time'),('deadline_at','deadline')]
        if values.get(field) and getattr(item,target) is None}
    if not changes:
        return {'document_id':doc.id,'status':'unchanged'}
    result={'document_id':doc.id,'status':'updated' if apply else 'proposed',
            'fields':{k:v.isoformat() for k,v in changes.items()},'source_bytes_changed':False}
    if apply:
        endpoint=db.get(SourceEndpoint,doc.source_endpoint_id)
        source=db.get(Source,endpoint.source_id)
        fields={'open_at' if k=='start_time' else 'deadline_at' for k in changes}
        proofs=[p for p in parsed.evidence if p['field'] in fields]
        if fields!={p['field'] for p in proofs}:
            raise ValueError('解析升级缺少原文明示日期证据')
        _persist_evidence(db,source,doc,proofs)
        for k,v in changes.items():setattr(item,k,v)
        normalized=json.loads(doc.raw_text)
        for field in fields:normalized[0][field]=values[field]
        doc.raw_text=json.dumps(normalized,ensure_ascii=False)
        db.flush()
        if not auto_publish(db,doc):
            raise ValueError('解析升级后的公开快照无法刷新')
        audit(db,'system-parser-upgrade','notice_dates_reparsed',f'document:{doc.id}',result)
    return result

import io,json,zipfile
from datetime import UTC,datetime
from fastapi.testclient import TestClient
from sqlalchemy import select,func
import pytest

from app import notice_watch as watch
from app.adapters.base import RawArtifact
from app.database import SessionLocal
from app.intake import ingest_public_notice
from app.intake_models import Source,SourceEndpoint,DocumentVersion,DocumentArchive,DataPublication,DevelopmentItem,Evidence
from app.data_catalog import auto_publish
from app.main import app
from app.parsers import extract,ParseError
from app.parser_upgrade import repair_notice_dates
from app.supporting_attachments import office_links
from test_notice_watch import setup,response


def word(xml=None,macro=False):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        z.writestr('word/document.xml',xml or '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>申请人应填写官方申请表，并核对所需材料和提交方式，所有信息以学校正式通知为准。</w:t></w:r></w:p></w:body></w:document>')
        if macro:z.writestr('word/vbaProject.bin',b'blocked')
    return out.getvalue()


def test_office_positions_and_macros_are_not_executed():
    parsed=extract(word(),'docx')
    assert parsed.text.startswith('[段落 1]')
    with pytest.raises(ParseError,match='宏'):extract(word(macro=True),'docx')
    with pytest.raises(ParseError,match='实体'):extract(word('<!DOCTYPE x [<!ENTITY a "bad">]><x/>'),'docx')
    from openpyxl import Workbook
    book=Workbook();book.active.title='申请表';book.active.append(['专业','要求']);book.active.append(['材料','=1+1'])
    out=io.BytesIO();book.save(out)
    parsed=extract(out.getvalue(),'xlsx_attachment')
    assert '[工作表：申请表]' in parsed.text and '[行 2]' in parsed.text and '[公式，需人工核对]' in parsed.text
    assert office_links('<a href="/download?id=1">申请表.docx</a><a href="https://elsewhere.example/f.xlsx">岗位表.xlsx</a><a href="/names.docx">名单公示.docx</a>',
        'https://official.example/page')==['https://official.example/download?id=1']


def test_support_file_keeps_raw_archive_and_parent_without_creating_opportunities(monkeypatch):
    with TestClient(app):
        eid,base=setup(monkeypatch)
        title='2027年硕士研究生招生报名通知'
        html=f'<h1>{title}</h1><article><p>申请人应填写官方申请表，并核对所需材料和提交方式，所有信息以学校正式通知为准。</p><a href="/form.docx">申请表.docx</a></article>'.encode()
        payload=word()
        def fetch(url,*args,**kwargs):
            return response(url,f'<a href="/notice">{title}</a>'.encode() if url.endswith('list') else payload if url.endswith('docx') else html)
        monkeypatch.setattr(watch,'collect_bytes_conditional',fetch)
        assert watch.process_once(endpoint_ids=[eid])['kind']=='index'
        assert watch.process_once(endpoint_ids=[eid])['kind']=='detail'
        assert watch.process_once(endpoint_ids=[eid])['kind']=='support_file'
        with SessionLocal.begin() as db:
            docs=db.scalars(select(DocumentVersion).where(DocumentVersion.source_endpoint_id==eid)).all()
            attachment=next(d for d in docs if d.canonical_url.endswith('docx'))
            assert db.get(DocumentArchive,attachment.id).content==payload
            assert json.loads(attachment.raw_text)['parent_document_id'] in {d.id for d in docs}
            assert db.scalar(select(func.count()).select_from(DevelopmentItem).where(DevelopmentItem.source_document_id.in_([d.id for d in docs])))==1
            assert not db.scalar(select(DataPublication).where(DataPublication.document_id==attachment.id))
            proof=db.scalar(select(Evidence).where(Evidence.document_version_id==attachment.id))
            assert proof.evidence_location=='part=word/document.xml;paragraph=1'
            db.get(SourceEndpoint,eid).scheduled=False


def test_reparse_missing_dates_preserves_source_version_and_withdrawal(monkeypatch):
    with TestClient(app):
        eid,base=setup(monkeypatch)
        config={'topic':'funding','path_code':'domestic_study','date_timezone':None}
        html=b'<h1>Funding opportunity: doctoral training grant</h1><article><p>Eligible institutions should read the complete opportunity and follow the official application instructions.</p><dl><dt>Closing date</dt><dd><time datetime="2026-12-01T16:00:00">1 December 2026 4:00pm</time></dd></dl></article>'
        with SessionLocal.begin() as db:
            ep=db.get(SourceEndpoint,eid);source=db.get(Source,ep.source_id);db.info['import_mode']='system'
            result=ingest_public_notice(db,source,ep,RawArtifact(html,base+'grant','grant','text/html'),config)
            doc=db.get(DocumentVersion,result['document_version_id']);assert auto_publish(db,doc)
            item=db.scalar(select(DevelopmentItem).where(DevelopmentItem.source_document_id==doc.id));assert item.deadline is None
            original=(doc.version_no,doc.content_hash,doc.fetched_at,doc.last_changed_at)
            upgraded={**config,'date_timezone':'Europe/London'}
            assert repair_notice_dates(db,doc,upgraded)['status']=='proposed' and item.deadline is None
            assert repair_notice_dates(db,doc,upgraded,True)['status']=='updated'
            assert item.deadline==datetime(2026,12,1,16,tzinfo=UTC)
            assert (doc.version_no,doc.content_hash,doc.fetched_at,doc.last_changed_at)==original
            assert db.get(DocumentArchive,doc.id).content==html
            assert repair_notice_dates(db,doc,upgraded,True)['status']=='unchanged'
            pub=db.scalar(select(DataPublication).where(DataPublication.document_id==doc.id));pub.status='withdrawn';db.flush()
            assert repair_notice_dates(db,doc,upgraded,True)['status']=='skipped' and pub.status=='withdrawn'
            ep.scheduled=False

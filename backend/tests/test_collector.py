import base64
import io
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app import collector, collector_http
from app.collector import CollectionRun, CollectionSource, process_one, schedule_due
from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.parsers import MAX_BYTES, ParseError, extract, extract_isolated
from app.sources import SourceHead

TEXT = '本公告用于采集测试。仅限大三报名，真实截止时间由管理员核对填写。'


def make_source(c, monkeypatch):
    monkeypatch.setattr(settings, 'collector_allowed_hosts', 'example.edu')
    result = c.post('/v1/admin/collector/sources', json={'url': 'https://example.edu/'+str(uuid4()),
        'label': '测试来源', 'format': 'html', 'interval_minutes': 60, 'permission_note': '测试模拟数据，已获授权'})
    assert result.status_code == 201, result.text
    return result.json()


def test_html_xlsx_pdf_parsers_and_bounds():
    html = ('<html><title>公告</title><script>evil()</script><nav>菜单</nav><article>'+TEXT+'</article></html>').encode()
    result = extract_isolated(html, 'html')
    assert result.title == '公告' and result.text == TEXT
    book = Workbook();book.active.append(['职位', '人数', '计算']);book.active.append([TEXT, 0, '=1+1'])
    buf = io.BytesIO();book.save(buf)
    parsed = extract_isolated(buf.getvalue(), 'xlsx')
    assert '0 | [公式，需人工核对]' in parsed.text
    writer = PdfWriter();page = writer.add_blank_page(width=300, height=300)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
    stream = DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 30 150 Td (Official fixture announcement for testing only.) Tj ET')
    page[NameObject('/Contents')] = writer._add_object(stream)
    pdf=io.BytesIO();writer.write(pdf)
    assert 'Official fixture announcement' in extract_isolated(pdf.getvalue(), 'pdf').text
    blank = PdfWriter();blank.add_blank_page(width=100,height=100);out=io.BytesIO();blank.write(out)
    with pytest.raises(ParseError, match='OCR'):extract_isolated(out.getvalue(), 'pdf')
    with pytest.raises(ParseError):extract(b'x'*(MAX_BYTES+1), 'text')
    with pytest.raises(ParseError):extract(b'short', 'text')


def test_url_policy_and_pinned_redirects(monkeypatch):
    monkeypatch.setattr(settings,'collector_allowed_hosts','example.edu')
    for url in ['http://example.edu/a','https://evil.test/','https://user@example.edu/','https://example.edu:444/a','https://example.edu/a#x']:
        with pytest.raises(ValueError):collector_http.validate_url(url)
    monkeypatch.setattr(collector_http.socket,'getaddrinfo',lambda *a,**kw:[(2,1,6,'',('127.0.0.1',443))])
    with pytest.raises(collector_http.FetchError):collector_http.public_ip('example.edu')
    monkeypatch.setattr(collector_http,'public_ip',lambda host:'93.184.216.34')
    calls=[]
    def handle(req):
        calls.append(req)
        assert req.url.host=='93.184.216.34' and req.headers['host']=='example.edu'
        assert req.extensions['sni_hostname']=='example.edu'
        return httpx.Response(302,headers={'location':'https://evil.test/private'})
    client=httpx.Client(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(collector_http.httpx,'Client',lambda **kw:client)
    with pytest.raises(collector_http.FetchError):collector_http.fetch_url('https://example.edu/a')
    assert len(calls)==1


def test_robots_denial_prevents_page_request(monkeypatch):
    monkeypatch.setattr(settings,'collector_allowed_hosts','example.edu')
    monkeypatch.setattr(collector_http,'public_ip',lambda host:'93.184.216.34')
    calls=[]
    original_client=httpx.Client
    def handle(req):
        calls.append(req.url.path)
        assert req.url.path=='/robots.txt'
        return httpx.Response(200,stream=httpx.ByteStream(b'User-agent: *\nDisallow: /'))
    monkeypatch.setattr(collector_http.httpx,'Client',lambda **kw:original_client(transport=httpx.MockTransport(handle)))
    with pytest.raises(collector_http.FetchError,match='robots'):collector_http.collect_bytes('https://example.edu/notice')
    assert calls==['/robots.txt']


def test_conditional_fetch_preserves_etag_and_handles_304(monkeypatch):
    monkeypatch.setattr(settings, 'collector_allowed_hosts', 'example.edu')
    monkeypatch.setattr(collector_http, 'assert_robots', lambda url: None)
    monkeypatch.setattr(collector_http, 'public_ip', lambda host: '93.184.216.34')
    original_client = httpx.Client
    def handle(request):
        assert request.headers['if-none-match'] == '"fixture-v1"'
        assert request.headers['if-modified-since'] == 'Mon, 28 Sep 2026 00:00:00 GMT'
        return httpx.Response(304)
    monkeypatch.setattr(collector_http.httpx, 'Client',
                        lambda **kw: original_client(transport=httpx.MockTransport(handle)))
    result = collector_http.collect_bytes_conditional(
        'https://example.edu/notice', etag='"fixture-v1"',
        last_modified='Mon, 28 Sep 2026 00:00:00 GMT')
    assert result['not_modified'] and result['status_code'] == 304 and result['data'] == b''


def test_job_dedup_retries_and_permission(monkeypatch):
    with TestClient(app) as c:
        source=make_source(c,monkeypatch);path=f'/v1/admin/collector/sources/{source["id"]}/run'
        assert c.get('/v1/admin/collector/runs',headers={'X-User-Id':'outsider'}).status_code==403
        first=c.post(path).json()
        assert c.post(path).json()['id']==first['id']
        monkeypatch.setattr(collector,'collect_bytes',lambda url: (f'<article>{TEXT}</article>'.encode(),'text/html'))
        assert process_one()
        with SessionLocal() as db:
            run=db.get(CollectionRun,first['id']);assert run.status=='succeeded';doc_id=run.document_id
        second=c.post(path).json();assert process_one()
        with SessionLocal() as db:
            run=db.get(CollectionRun,second['id']);assert run.status=='unchanged' and run.document_id==doc_id
        def fail(url):raise collector_http.FetchError('测试来源不可用')
        monkeypatch.setattr(collector,'collect_bytes',fail)
        third=c.post(path).json()
        for attempt in range(1,4):
            assert process_one()
            with SessionLocal.begin() as db:
                run=db.get(CollectionRun,third['id']);assert run.attempts==attempt
                assert run.status==('retry' if attempt<3 else 'failed')
                run.ready_at=datetime.now(UTC)-timedelta(seconds=1)
        assert c.post(path).json()['id']!=third['id']
        c.patch(f'/v1/admin/collector/sources/{source["id"]}',json={'enabled':False})
        assert process_one()
        assert c.post(path).status_code==404


def test_manual_file_to_review_preserves_old_version_head(monkeypatch):
    with TestClient(app) as c:
        url='https://example.edu/'+str(uuid4())
        def upload(text):return c.post('/v1/admin/collector/files',json={'source_url':url,'format':'text','content_base64':base64.b64encode(text.encode()).decode()})
        old=upload(TEXT);assert old.status_code==201,old.text
        new=upload(TEXT+'这是新版补充说明。').json()
        payload={'type':'contest','title':'采集测试竞赛','organization':'测试单位','summary':'人工核对摘要','location':'线上','source_url':url,'source_label':'测试来源',
            'fetched_at':datetime.now(UTC).isoformat(),'deadline':(datetime.now(UTC)+timedelta(days=5)).isoformat(),
            'rules':[{'field':'grade','operator':'in','expected':'大三','label':'年级','source_url':url,'evidence':'仅限大三报名'}]}
        path=f'/v1/admin/collector/documents/{old.json()["document_id"]}/review'
        submitted=c.post(path,json=payload);assert submitted.status_code==201,submitted.text
        assert c.post(path,json=payload).json()['duplicate']
        with SessionLocal() as db:
            head=db.query(SourceHead).filter_by(source_url=url).one()
            assert head.document_id==new['document_id']
        assert c.post(f'/v1/admin/reviews/{submitted.json()["review_id"]}/approve').status_code==200
        payload['rules'][0]['evidence']='编造条件'
        assert c.post(path,json=payload).status_code==422


def test_scheduler_lease_reclaim_and_concurrent_claim(monkeypatch):
    with TestClient(app) as c:
        source=make_source(c,monkeypatch)
        with SessionLocal.begin() as db:
            # Isolate schedules from fixtures of other tests.
            db.query(CollectionSource).filter(CollectionSource.id!=source['id']).update({'enabled':False})
        schedule_due();schedule_due()
        with SessionLocal.begin() as db:
            jobs=db.query(CollectionRun).filter_by(source_id=source['id']).all();assert len(jobs)==1
            job=jobs[0];job.status='running';job.lease_token='lost';job.lease_until=datetime.now(UTC)-timedelta(minutes=1)
        monkeypatch.setattr(collector,'collect_bytes',lambda url:(TEXT.encode(),'text/plain'))
        # Source html parser also accepts plain text.
        with ThreadPoolExecutor(2) as pool:list(pool.map(lambda _:process_one(),range(2)))
        with SessionLocal() as db:
            run=db.get(CollectionRun,job.id);assert run.status=='succeeded' and run.attempts==1

"""Alternate public indexes discover full articles without expanding trust boundaries."""
import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.adapters.index_discovery import discover_index, official_url
from app.database import SessionLocal
from app.intake_models import DocumentVersion, NoticeResource, SourceEndpoint
from app.main import app
from app.parsers import ParseError
from app.adapters.education import PublicNoticeAdapter
from app.adapters.base import RawArtifact
from app import notice_watch as watch
from test_notice_watch import setup, response, article, due

BASE = 'https://official.example/'
TITLE = '2027年度大学毕业生就业支持政策通知'


def test_rss_and_atom_filter_hosts_entities_and_use_actual_article_links():
    rss = ('<rss><channel><item><title>'+TITLE+'</title><link>/a#section</link></item>'
        '<item><title>'+TITLE+'</title><link>https://elsewhere.example/b</link></item>'
        '<item><title>申请人员名单公示</title><link>/private</link></item></channel></rss>')
    result = discover_index(rss.encode(), BASE, {'topic':'policy'})
    assert result['links'] == [{'url':BASE+'a', 'title':TITLE}]
    atom = ('<feed xmlns="http://www.w3.org/2005/Atom" xml:base="https://attacker.example/">'
        '<entry><title>'+TITLE+'</title><link rel="self" href="/feed/1"/>'
        '<link href="/b"/></entry></feed>')
    assert discover_index(atom.encode(), BASE, {'topic':'policy'})['links'][0]['url'] == BASE+'b'
    with pytest.raises(ParseError, match='实体'):
        discover_index(b'<!DOCTYPE rss [<!ENTITY secret SYSTEM "file:///etc/passwd">]><rss/>', BASE, {'discovery_format':'rss'})
    with pytest.raises(ParseError, match='实体'):
        discover_index('<!DOCTYPE rss [<!ENTITY internal "text">]><rss/>'.encode('utf-16'), BASE, {'discovery_format':'rss'})


def test_empty_feeds_are_healthy_but_html_and_wrong_xml_are_not():
    assert discover_index(b'<rss><channel/></rss>', BASE, {})['recognized']
    assert discover_index(b'<feed xmlns="http://www.w3.org/2005/Atom"/>', BASE, {})['recognized']
    assert not discover_index(b'<h1>Maintenance</h1>', BASE, {})['recognized']
    with pytest.raises(ParseError):
        discover_index(b'<html/>', BASE, {'discovery_format':'rss'})


def test_json_requires_explicit_mapping_and_validates_structure():
    config = {'topic':'policy','discovery_format':'json','json_index':
        {'items_path':['data','items'],'title_field':'title','url_field':'uri'}}
    content = json.dumps({'data':{'items':[{'title':TITLE,'uri':'/a'},
        {'title':TITLE,'uri':'http://official.example/b'},
        {'title':TITLE,'uri':'https://user:password@official.example/c'}]}}).encode()
    assert discover_index(content, BASE, config)['links'] == [{'url':BASE+'a','title':TITLE}]
    assert discover_index(b'{"data":{"items":[]}}', BASE, config)['recognized']
    for content in (b'{"error":"service unavailable"}', b'{"data":{"items":[{"other":"value"}]}}', b'callback([])'):
        with pytest.raises(ParseError):
            discover_index(content, BASE, config)
    with pytest.raises(ParseError, match='映射'):
        discover_index(b'[]', BASE, {'discovery_format':'json'})


def test_sitemap_backfills_only_configured_paths_and_most_recent_first():
    content = b'''<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://official.example/opportunity/old</loc><lastmod>2024-01-01</lastmod></url>
      <url><loc>https://official.example/login</loc><lastmod>2026-10-02</lastmod></url>
      <url><loc>https://external.example/opportunity/new</loc></url>
      <url><loc>https://official.example/opportunity/new</loc><lastmod>2026-10-01</lastmod></url>
      <url><loc>https://official.example/opportunity/new#duplicate</loc><lastmod>2026-10-01</lastmod></url>
    </urlset>'''
    config = {'discovery_format':'sitemap','detail_path_prefixes':['/opportunity/']}
    assert discover_index(content, BASE, config, limit=2)['links'] == [
        {'url':BASE+'opportunity/new','title':''}, {'url':BASE+'opportunity/old','title':''}]
    assert discover_index(content, BASE, config, known_urls={BASE+'opportunity/new'})['links'] == [
        {'url':BASE+'opportunity/old','title':''}]
    with pytest.raises(ParseError, match='路径'):
        discover_index(content, BASE, {'discovery_format':'sitemap'})


def test_html_discovers_subscription_and_observed_next_page_only():
    html = f'''<base href="https://official.example/"><link rel="alternate" type="application/rss+xml" href="feed/">
      <link rel="alternate" type="application/atom+xml" href="https://external.example/feed">
      <a href="a">{TITLE}</a><a rel="next" href="page2">2</a>'''
    result = discover_index(html.encode(), BASE+'column/', {'topic':'policy'})
    assert result['indexes'] == [BASE+'feed/', BASE+'page2']
    assert result['links'][0]['url'] == BASE+'a'
    malformed = f'<base href="https://[broken/"><a href="https://official.example:bad/a">{TITLE}</a><a href="/b">{TITLE}</a>'
    assert discover_index(malformed.encode(), BASE, {'topic':'policy'})['links'][0]['url'] == BASE+'b'


@pytest.mark.parametrize('url', ['https://official.example:bad/a', 'https://[broken/a',
    'http://official.example/a', 'https://official.example:8443/a', 'https://evil.example/a'])
def test_malformed_or_unsafe_index_links_are_ignored(url):
    assert official_url(url, BASE) is None


def test_rss_fetches_full_original_then_keeps_checking_details_after_304(monkeypatch):
    with TestClient(app):
        eid, base = setup(monkeypatch)
        with SessionLocal.begin() as db:
            ep = db.get(SourceEndpoint,eid)
            config = watch.config_for(ep); config['discovery_format']='rss'
            ep.adapter_config=json.dumps(config)
        feed = ('<rss><channel><item><title>2027年硕士招生报名通知</title><link>'+base+'article</link>'
            '<description>摘要不包含完整材料要求</description></item></channel></rss>').encode()
        pages={base+'list':response(base+'list',feed),base+'article':response(base+'article',article())}
        monkeypatch.setattr(watch,'collect_bytes_conditional',lambda url,*a,**kw:pages[url])
        assert watch.process_once(endpoint_ids=[eid])['kind']=='index'
        assert watch.process_once(endpoint_ids=[eid])['status']=='updated'
        with SessionLocal() as db:
            doc = db.scalar(select(DocumentVersion).where(DocumentVersion.source_endpoint_id==eid))
            assert '材料和报名安排' in doc.raw_text and '摘要不包含' not in doc.raw_text
        pages[base+'list']=response(base+'list',not_modified=True)
        due(eid,'index'); assert watch.process_once(endpoint_ids=[eid])['status']=='unchanged'
        pages[base+'article']=response(base+'article',article('正文修改后仍需按学校要求核对申请条件及材料，报名安排以本通知为准。'))
        due(eid,'detail'); assert watch.process_once(endpoint_ids=[eid])['status']=='updated'
        with SessionLocal.begin() as db:
            assert len(db.scalars(select(DocumentVersion).where(DocumentVersion.source_endpoint_id==eid)).all())==2
            db.get(SourceEndpoint,eid).scheduled=False


def test_scheduler_rotates_to_unchecked_source_before_drain_of_busy_source(monkeypatch):
    with TestClient(app):
        busy,base=setup(monkeypatch)
        fresh,_=setup(monkeypatch)
        now=datetime.now(UTC)
        with SessionLocal.begin() as db:
            db.execute(update(NoticeResource).where(NoticeResource.endpoint_id==busy).values(next_check_at=now-timedelta(days=1)))
            for i in range(3):
                watch.add_resource(db,busy,base+f'backlog-{i}','index',now-timedelta(days=1))
        monkeypatch.setattr(watch,'collect_bytes_conditional',lambda url,*a,**kw:response(url,
            b'<a href="article">'+ '2027年硕士招生报名通知'.encode()+b'</a>'))
        watch.process_once(endpoint_ids=[busy,fresh])
        with SessionLocal() as db:
            assert not db.scalar(select(NoticeResource).where(NoticeResource.endpoint_id==fresh)).checked_at
        watch.process_once(endpoint_ids=[busy,fresh])
        with SessionLocal.begin() as db:
            assert db.scalar(select(NoticeResource).where(NoticeResource.endpoint_id==fresh)).checked_at
            assert len(db.scalars(select(NoticeResource).where(NoticeResource.endpoint_id==busy,
                NoticeResource.checked_at.is_(None))).all())>=2
            db.get(SourceEndpoint,busy).scheduled=False
            db.get(SourceEndpoint,fresh).scheduled=False


def test_unchanged_sitemap_advances_backfill_without_conditional_304(monkeypatch):
    with TestClient(app):
        eid,base=setup(monkeypatch)
        with SessionLocal.begin() as db:
            ep=db.get(SourceEndpoint,eid)
            ep.adapter_config=json.dumps({**watch.config_for(ep),'discovery_format':'sitemap',
                'detail_path_prefixes':['/opportunity/']})
        xml=('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+ ''.join(
            f'<url><loc>{base}opportunity/{i}</loc><lastmod>2026-09-{i:02}</lastmod></url>' for i in range(1,32))+'</urlset>').encode()
        calls=[]
        def fetch(url,*args,**kwargs):
            calls.append(args)
            return response(url,xml)
        monkeypatch.setattr(watch,'collect_bytes_conditional',fetch)
        assert watch.process_once(endpoint_ids=[eid])['status']=='checked'
        with SessionLocal.begin() as db:
            assert len(db.scalars(select(NoticeResource).where(NoticeResource.endpoint_id==eid,
                NoticeResource.kind=='detail')).all())==30
            db.execute(update(NoticeResource).where(NoticeResource.endpoint_id==eid,
                NoticeResource.kind=='detail').values(next_check_at=datetime.now(UTC)+timedelta(days=2)))
        due(eid,'index')
        assert watch.process_once(endpoint_ids=[eid])['status']=='checked'
        assert calls==[(None,None),(None,None)]
        with SessionLocal.begin() as db:
            assert len(db.scalars(select(NoticeResource).where(NoticeResource.endpoint_id==eid,
                NoticeResource.kind=='detail')).all())==31
            db.get(SourceEndpoint,eid).scheduled=False


def test_full_queue_defers_new_links_without_failing_healthy_index(monkeypatch):
    with TestClient(app):
        eid,base=setup(monkeypatch)
        with SessionLocal.begin() as db:
            for i in range(199):
                watch.add_resource(db,eid,base+f'detail/{i}','detail',datetime.now(UTC))
        monkeypatch.setattr(watch,'collect_bytes_conditional',lambda url,*args,**kwargs:response(url,
            '<a href="new">2027年硕士招生报名通知</a>'.encode()))
        assert watch.process_once(endpoint_ids=[eid])['status']=='checked'
        with SessionLocal.begin() as db:
            assert len(db.scalars(select(NoticeResource).where(NoticeResource.endpoint_id==eid)).all())==200
            db.get(SourceEndpoint,eid).scheduled=False


def test_funding_definition_dates_keep_source_timezone_and_evidence():
    html=b'''<h1>Funding opportunity: Doctoral training award</h1><article><dl>
      <div><dt>Funders:</dt><dd>UK Research and Innovation</dd></div>
      <div><dt>Publication date:</dt><dd>1 October 2026</dd></div>
      <div><dt>Opening date:</dt><dd><time datetime="2026-10-01T09:00:00">1 October 2026 9am UK time</time></dd></div>
      <div><dt>Closing date:</dt><dd><time datetime="2026-12-15T16:00:00">15 December 2026 4pm UK time</time></dd></div>
      </dl><p>Eligible organisations should review the full application conditions before applying for this funding opportunity.</p></article>'''
    parsed=PublicNoticeAdapter('funding',date_timezone='Europe/London').parse(RawArtifact(html,BASE+'award','award'))
    assert parsed.records[0]['open_at']=='2026-10-01T09:00:00+01:00'
    assert parsed.records[0]['deadline_at']=='2026-12-15T16:00:00+00:00'
    assert parsed.metadata['publish_time']=='2026-10-01T00:00:00+01:00'
    assert 'Funders: UK Research and Innovation' in parsed.records[0]['body']
    proof=next(e for e in parsed.evidence if e['field']=='deadline_at')
    assert '15 December 2026' in proof['quote_or_normalized_fact'] and 'dd' in proof['evidence_location']
    without_timezone=PublicNoticeAdapter('funding').parse(RawArtifact(html,BASE+'award','award'))
    assert 'deadline_at' not in without_timezone.records[0]


@pytest.mark.parametrize('clock',['2026-03-29T01:30:00','2026-10-25T01:30:00','invalid'])
def test_ambiguous_missing_or_invalid_local_funding_deadline_stays_unknown(clock):
    html=f'<h1>Funding opportunity: Doctoral training award</h1><article><dl><dt>Closing date:</dt><dd><time datetime="{clock}">UK time</time></dd></dl><p>Applicants must read the original conditions and check their eligibility before submitting materials.</p></article>'.encode()
    parsed=PublicNoticeAdapter('funding',date_timezone='Europe/London').parse(RawArtifact(html,BASE+'award','award'))
    assert 'deadline_at' not in parsed.records[0]

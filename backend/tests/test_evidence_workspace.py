"""Isolated fixtures: no network calls or writes to local preview data."""
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.main import eligibility_check, eligibility_options
from app.knowledge import (KnowledgeAccess, KnowledgePublication, SearchIn,
    browse_documents, index_document, read_document, search_documents)
from app.models import EligibilityRule, Opportunity
from app.schemas import EligibilityCheckIn
from app.sources import SourceDocument, SourceHead


@pytest.fixture
def db():
    engine = create_engine('sqlite://', poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


def document(db, key, kind='contest', public=True, text=None):
    text = text or ('报名材料包括官方申请表。条件以原文为准。\n' * 75)
    url = 'https://university.edu.cn/notices/' + key
    now = datetime.now(UTC)
    doc = SourceDocument(id=key, source_url=url, content_hash=sha256(text.encode()).hexdigest(),
                         raw_text=text, fetched_at=now, archived_at=now)
    db.add(doc)
    db.add(SourceHead(url_hash=sha256(url.encode()).hexdigest(), source_url=url, document_id=key))
    db.add(KnowledgePublication(document_id=key, source='system', title='测试原文 '+key, item_type=kind))
    db.add(KnowledgeAccess(document_id=key, public=public))
    db.flush()
    index_document(db, doc)
    return doc


def test_directory_counts_documents_not_chunks_and_pages_stably(db):
    for i in range(11):
        document(db, str(i), kind='policy' if i < 2 else 'contest')
    document(db, 'private', public=False)
    first = browse_documents(None, 0, 9, 'reader', db)
    second = browse_documents(None, 9, 9, 'reader', db)
    assert first['total'] == first['library_total'] == 11
    assert first['chunk_total'] > first['total']
    assert first['by_type'] == {'contest':9, 'policy':2}
    assert len(first['items']) == 9 and len(second['items']) == 2
    assert not {x['document_id'] for x in first['items']} & {x['document_id'] for x in second['items']}
    policies = browse_documents('policy', 0, 9, 'reader', db)
    assert policies['total'] == 2 and len(policies['items']) == 2


def test_reader_and_directory_share_revocation_and_current_version_gate(db):
    doc = document(db, 'source')
    assert read_document(doc.id, 'reader', db)['text'] == doc.raw_text
    access = db.get(KnowledgeAccess, doc.id)
    access.public = False
    db.flush()
    assert browse_documents(None, 0, 9, 'reader', db)['total'] == 0
    with pytest.raises(HTTPException) as hidden:
        read_document(doc.id, 'reader', db)
    assert hidden.value.status_code == 404
    access.public = True
    head = db.get(SourceHead, sha256(doc.source_url.encode()).hexdigest())
    head.document_id = 'newer-private-version'
    db.flush()
    assert browse_documents(None, 0, 9, 'reader', db)['total'] == 0
    with pytest.raises(HTTPException):
        read_document(doc.id, 'reader', db)


def test_extended_types_search_actual_chunks_and_reader_is_bounded(db):
    document(db, 'policy', kind='education_policy', text='报名材料仅为测试原文。'*15000)
    results = search_documents(SearchIn(query='报名材料', type='education_policy'), db)
    assert results['items'] and results['items'][0]['opportunity_id'] is None
    assert results['items'][0]['source_url'].endswith('/policy')
    reading = read_document('policy', 'reader', db)
    assert reading['truncated'] is True and len(reading['text']) == 120000
    assert reading['character_count'] > 120000


def test_reading_formats_collector_container_without_changing_evidence(db):
    import json
    body = '报名要求\n申请人应核对本次公告。\n这是独立测试文本，不发布到本地资料库。'
    raw = json.dumps([{'title':'测试正文', 'body':body}], ensure_ascii=False)
    doc = document(db, 'wrapped', text=raw)
    result = read_document('wrapped', 'reader', db)
    assert result['display_text'] == '测试正文\n\n'+body
    assert result['is_formatted'] is True
    assert result['text'] == doc.raw_text == raw
    assert result['content_hash'] == sha256(raw.encode()).hexdigest()


def opportunity(db, key, kind='contest', host='university.edu.cn'):
    row = Opportunity(id=key,type=kind,title='真实来源测试 '+key,organization='隔离测试',summary='测试摘要',
        location='线上',deadline=datetime.now(UTC)+timedelta(days=5),source_url='https://'+host+'/'+key,
        source_label='测试来源',trust_score=1,tags='',status='published',fetched_at=datetime.now(UTC))
    db.add(row)
    db.flush()
    return row


def test_options_exclude_demo_and_policy_and_count_only_verified(db):
    opportunity(db,'contest')
    opportunity(db,'policy','policy')
    opportunity(db,'fixture',host='example.edu')
    db.add_all([EligibilityRule(opportunity_id='contest',field='degree',operator='equals',expected='本科',
        label='学历',source_url='https://university.edu.cn/contest',review_status=status) for status in ['verified','pending']])
    db.flush()
    data = eligibility_options('user', db)
    assert data['total'] == data['with_rules'] == 1
    assert data['items'][0]['rule_count'] == 1 and data['items'][0]['pending_count'] == 1


def test_no_verified_conditions_never_becomes_a_pass(db):
    opportunity(db,'waiting')
    rule = EligibilityRule(opportunity_id='waiting',field='degree',operator='equals',expected='本科',
        label='学历',source_url='https://university.edu.cn/waiting',review_status='pending')
    db.add(rule); db.flush()
    result = eligibility_check(EligibilityCheckIn(opportunity_id='waiting'), 'user', db)
    assert result.eligible is None and result.results == []
    rule.review_status = 'verified'; db.flush()
    assert eligibility_check(EligibilityCheckIn(opportunity_id='waiting'), 'user', db).eligible is True
    rule.logic_group = 'unsupported-or-group'; db.flush()
    assert eligibility_check(EligibilityCheckIn(opportunity_id='waiting'), 'user', db).eligible is None


def test_explicit_editorial_approval_makes_evidenced_conditions_usable(db):
    from sqlalchemy import select
    from app.governance import EditorialImport, import_content, review
    body = EditorialImport(
        type='contest', title='隔离测试：已核验的比赛条件', organization='测试主办方',
        summary='仅供内存数据库回归测试', location='线上',
        deadline=datetime.now(UTC)+timedelta(days=7), fetched_at=datetime.now(UTC),
        source_url='https://university.edu.cn/verified', source_label='测试原文',
        rules=[dict(field='major', operator='contains_any', expected='计算机',
                    label='专业', evidence='仅供测试：计算机相关专业',
                    source_url='https://university.edu.cn/verified')],
    )
    pending = import_content(body, 'test-admin', db)
    assert db.scalar(select(EligibilityRule)) is None
    review(pending.id, 'approve', 'test-admin', db)
    rule = db.scalar(select(EligibilityRule))
    assert rule.review_status == 'verified' and rule.extractor == 'editorial'
    assert eligibility_options('reader', db)['with_rules'] == 1
    result = eligibility_check(EligibilityCheckIn(opportunity_id=rule.opportunity_id), 'reader', db)
    assert result.eligible is True and len(result.results) == 1

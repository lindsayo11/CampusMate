"""Bounded fallback distinguishes real ingestion from reachable listing pages."""
import importlib.util
from pathlib import Path

import pytest

from app.adapters.notice_text import discover_notices
from app.adapters.education import PublicNoticeAdapter
from app.adapters.base import RawArtifact
from app.notice_watch import embedded_pdfs

SPEC = importlib.util.spec_from_file_location('source_probe',
    Path(__file__).resolve().parents[2] / 'scripts/probe_public_sources.py')
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)
TITLE = '2027年秋季学期本科生境外交换项目申请通知'


def response(url, html):
    return {'data': html.encode(), 'final_url': url, 'status_code': 200,
            'content_type': 'text/html'}


def test_probe_tries_other_columns_and_retains_all_usable_columns(monkeypatch):
    base = 'https://official.example/'
    calls = []
    def fetch(url):
        calls.append(url)
        if url.endswith('missing'):
            raise ValueError('404')
        if url.endswith(('column', 'additional')):
            return response(url, f'<a href="/article">{TITLE}</a>')
        return response(url, f'<h1>{TITLE}</h1><article><p>本校在校学生可依照官方项目要求提交申请材料，交换安排和报名方式均以本通知为准。</p></article>')
    monkeypatch.setattr(probe, 'fetch_public', fetch)
    row = probe.probe({'code': 'sample', 'name': 'Sample', 'topic': 'overseas',
        'base_url': base, 'index_urls': [base+'missing', base+'column', base+'additional']})
    assert row['status'] == 'ready' and row['sample']['evidence'] > 0
    assert row['index_urls'] == [base+'column', base+'additional']
    assert calls.count(base+'article') == 1
    assert row['attempts'][0]['error'] == '404'


def test_probe_tries_another_template_and_never_fetches_external_base(monkeypatch):
    base = 'https://official.example/'
    calls = []
    def fetch(url):
        calls.append(url)
        if url == base:
            return response(url, '<base href="https://attacker.example/">' + ''.join(
                f'<a href="{i}">{TITLE}</a>' for i in range(10)))
        if url.endswith('/2'):
            return response(url, f'<h1>{TITLE}</h1><article>学生应按校内通知参加境外交流申请，并核对项目安排和报名材料要求。</article>')
        return response(url, '<h1>系统提示</h1>')
    monkeypatch.setattr(probe, 'fetch_public', fetch)
    row = probe.probe({'code':'sample','name':'Sample','topic':'overseas',
        'base_url':base,'index_urls':[base]})
    assert row['status'] == 'ready' and row['sample']['url'] == base+'2'
    assert len(calls) == 4 and all(url.startswith(base) for url in calls)


@pytest.mark.parametrize('tag,expected', [
    ('<base href="https://official.example/">', 'https://official.example/content_1.html'),
    ('<base href="https://attacker.example/">', 'https://official.example/student/content_1.html'),
    ('<base href="http://official.example/">', 'https://official.example/student/content_1.html'),
    ('<base href="https://user:pass@official.example/">', 'https://official.example/student/content_1.html'),
    ('<base href="https://official.example:8080/">', 'https://official.example/student/content_1.html'),
])
def test_document_base_resolves_only_same_host_https(tag, expected):
    assert discover_notices(tag+f'<a href="content_1.html">{TITLE}</a>',
        'https://official.example/student/', topic='overseas')[0]['url'] == expected


@pytest.mark.parametrize('topic,title', [
    ('overseas', TITLE),
    ('overseas', '2027年春季学期国际交流（交换）项目报名通知'),
    ('funding', '2026年度本科生国家级奖助项目评选工作的通知'),
    ('funding', '2026-2027学年家庭经济困难学生认定及补核查工作的通知'),
    ('funding', '2026年度基层就业学费补偿代偿申报通知'),
])
def test_new_topics_are_discovered_without_private_name_lists(topic, title):
    result = discover_notices(f'<a href="/article">{title}</a><a href="/private">{title}名单公示</a>',
        'https://official.example/', topic=topic)
    assert len(result) == 1 and result[0]['url'].endswith('/article')


def test_first_party_base_resolves_original_attachments_and_pdf_wrappers():
    base = 'https://official.example/student/content_1.html'
    html = ('<base href="https://official.example/"><h1>2026年度本科生奖学金申请通知</h1>'
        '<article><p>本年度奖学金申请者应按学校要求提交申请材料，并核对各项条件及报名日期。</p>'
        '<a href="files/materials.pdf">申请材料</a></article><iframe src="files/notice.pdf"></iframe>')
    parsed = PublicNoticeAdapter('funding').parse(RawArtifact(html.encode(), base, 'sample'))
    assert parsed.records[0]['attachments'][0]['url'] == 'https://official.example/files/materials.pdf'
    assert set(embedded_pdfs(html, base)) == {'https://official.example/files/materials.pdf',
        'https://official.example/files/notice.pdf'}

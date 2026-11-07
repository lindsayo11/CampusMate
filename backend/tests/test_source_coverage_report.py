"""Coverage gaps must not disappear behind unrelated university/city sources."""
import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location('coverage_report',
    Path(__file__).resolve().parents[2] / 'scripts/source_coverage_report.py')
reporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reporter)


def test_city_and_university_recruitment_do_not_fill_provincial_authority_gap():
    def source(code, topic, status):
        return {'code': code, 'name': code, 'topic': topic, 'status': status,
                'region_code': 'CN-FJ', 'index_urls': ['https://official.example/list'],
                'probe': {'checked_at': '2026-10-01', 'error': '需适配正文'}}
    catalog = {'checked_at': '2026-10-01', 'sources': [
        source('CM-HRSS-FJ', 'recruitment', 'index_ready'),
        source('CM-PUBLIC-RECRUIT-FUZHOU', 'recruitment', 'ready'),
        source('CM-EXAM-FJ', 'examination', 'blocked'),
    ]}
    # Duplicate source IDs in legacy/current config are counted once.
    result = reporter.coverage_report(catalog, {'sources': [catalog['sources'][1]]})
    assert result['configured_sources'] == 1
    fj = [r for r in result['provincial_authorities'] if r['region'] == 'CN-FJ']
    assert len(fj) == 2 and all(r['ready'] == 0 for r in fj)
    assert {r['code'] for r in result['gaps']} == {'CM-HRSS-FJ', 'CM-EXAM-FJ'}

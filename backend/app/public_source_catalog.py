"""Versioned source inventory; technical probes are distinct from operator permission."""
import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

TOPIC_LABELS = {
    'postgraduate': '考研与推免', 'examination': '教育考试', 'employment': '实习与就业',
    'recruitment': '考公与考编', 'overseas': '留学与奖学金',
    'entrepreneurship': '创业与竞赛', 'policy': '政策与支持', 'funding': '资助与科研',
}


def load_catalog():
    return json.loads(Path(__file__).with_name('public_sources.json').read_text(encoding='utf-8'))


def registry_sources():
    """Only reachable sources enter the registry; probes do not enable scheduling."""
    result = []
    for entry in load_catalog()['sources']:
        if entry['status'] not in {'ready', 'index_ready'}:
            continue
        graduate = entry['topic'] == 'postgraduate'
        paths = (['domestic_postgraduate_exam', 'recommendation_exemption'] if graduate
                 else ([entry['path_code']] if entry.get('path_code') else ['domestic_study']))
        result.append({
            'code': entry['code'], 'name': entry['name'], 'publisher': entry['publisher'],
            'authority_level': 'A', 'source_class': entry['source_class'],
            'jurisdiction_level': ('foreign' if entry['region_code'] not in {'CN'} and not entry['region_code'].startswith('CN-')
                else 'school' if entry['source_class'] == 'university'
                else 'province' if entry['region_code'].startswith('CN-') else 'national'),
            'region_code': entry['region_code'], 'supported_paths': paths,
            'supported_item_types': ['public_notice'], 'base_url': entry['base_url'],
            'verified_at': entry['probe']['checked_at'],
            'endpoints': [{
                'name': entry['endpoint_name'], 'type': 'html', 'url': entry['index_urls'][0],
                'access_tags': ['DIRECT', 'FILE'], 'format': 'html',
                'parser_type': 'UniversityNoticeAdapter' if graduate else 'PublicNoticeAdapter',
                'automation_level': 'AUTO-2', 'agent_mode': 'EXTRACT', 'fetch_interval': '12h',
                'license_status': 'unknown', 'scheduled': False,
                'license_note': '匿名公开通知；技术探测不等于条款或许可证批准。持续采集需运营者显式安装，并始终检查 robots。',
                'paused_reason': '待运营者安装公开栏目监测' if entry['status'] == 'ready' else '栏目可发现，正文结构待适配',
            }],
        })
    return result


def watch_entries():
    return [s for s in load_catalog()['sources'] if s['status'] == 'ready']


def allowed_hosts():
    legacy = json.loads(Path(__file__).with_name('postgraduate_sources.json').read_text(encoding='utf-8'))
    return sorted({urlsplit(url).hostname for source in legacy['sources'] + watch_entries()
                   for url in source['index_urls']})


def catalog_status(monitors):
    catalog = load_catalog()
    runtime = {m['source_code']: m for m in monitors}
    entries = []
    for source in catalog['sources']:
        monitor = runtime.get(source['code'])
        probe = source.get('probe', {})
        entries.append({
            'code': source['code'], 'name': source['name'], 'topic': source['topic'],
            'topic_label': TOPIC_LABELS[source['topic']], 'region': source['region_code'],
            'status': source['status'], 'index_urls': source['index_urls'],
            'discovery_format': source.get('discovery_format', 'auto'),
            'index_formats': source.get('index_formats', {}),
            'checked_at': probe.get('checked_at'),
            'error': probe.get('error') or probe.get('detail_error') or '',
            'sample_url': probe.get('sample', {}).get('url'),
            'installed': bool(monitor), 'enabled': bool(monitor and monitor['enabled']),
        })
    return {'checked_at': catalog['checked_at'], 'total': len(entries),
            'statuses': dict(Counter(e['status'] for e in entries)),
            'topics': [{'topic': topic, 'label': TOPIC_LABELS[topic],
                'total': sum(e['topic'] == topic for e in entries),
                'ready': sum(e['topic'] == topic and e['status'] == 'ready' for e in entries)}
                for topic in TOPIC_LABELS], 'sources': entries}

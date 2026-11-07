"""Report configured coverage and gaps without claiming live collection health."""
import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.public_source_catalog import TOPIC_LABELS

# Mainland provincial divisions: a province with one source is still only
# represented, never declared fully covered.
REGIONS = dict(zip(
    'BJ TJ HE SX NM LN JL HL SH JS ZJ AH FJ JX SD HA HB HN GD GX HI CQ SC GZ YN XZ SN GS QH NX XJ'.split(),
    '北京 天津 河北 山西 内蒙古 辽宁 吉林 黑龙江 上海 江苏 浙江 安徽 福建 江西 山东 河南 湖北 湖南 广东 广西 海南 重庆 四川 贵州 云南 西藏 陕西 甘肃 青海 宁夏 新疆'.split(),
))


def coverage_report(catalog, legacy):
    configured = {s['code']: s for s in legacy['sources']}
    configured.update({s['code']: s for s in catalog['sources'] if s['status'] == 'ready'})
    issues = []
    for source in catalog['sources']:
        probe = source.get('probe', {})
        if source['status'] != 'ready':
            issues.append({
                'code': source['code'], 'name': source['name'], 'topic': source['topic'],
                'region': source['region_code'], 'status': source['status'],
                'reason': probe.get('detail_error') or probe.get('error') or '尚未验证正文',
                'checked_at': probe.get('checked_at'), 'index_urls': source['index_urls'],
            })
    topics = []
    for topic, label in TOPIC_LABELS.items():
        candidates = [s for s in catalog['sources'] if s['topic'] == topic]
        ready = [s for s in configured.values() if s.get('topic', 'postgraduate') == topic]
        topics.append({'topic': topic, 'label': label, 'candidates': len(candidates),
                       'statuses': dict(Counter(s['status'] for s in candidates)),
                       'configured_sources': len(ready)})
    provincial = []
    for topic in ('examination', 'recruitment'):
        # University recruitment and city notices do not stand in for a
        # missing provincial education-exam or HR authority.
        prefix = 'CM-EXAM-' if topic == 'examination' else 'CM-HRSS-'
        authorities = [s for s in catalog['sources'] if s['code'].startswith(prefix)]
        for region, label in REGIONS.items():
            sources = [s for s in authorities if s['region_code'] == 'CN-' + region]
            provincial.append({'topic': topic, 'region': 'CN-' + region, 'label': label,
                               'candidates': len(sources),
                               'ready': sum(s['status'] == 'ready' for s in sources),
                               'codes': [s['code'] for s in sources]})
    return {
        'generated_at': datetime.now(UTC).isoformat(),
        'catalog_checked_at': catalog['checked_at'],
        'scope': '配置及正文探测快照；不表示已安装、正在运行或全国完整覆盖',
        'catalog_sources': len(catalog['sources']),
        'statuses': dict(Counter(s['status'] for s in catalog['sources'])),
        'configured_sources': len(configured),
        'topics': topics, 'provincial_authorities': provincial,
        'gaps': sorted(issues, key=lambda s: (s['topic'], s['region'], s['code'])),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='Save the full JSON gap inventory')
    args = parser.parse_args()
    catalog = json.loads((ROOT / 'backend/app/public_sources.json').read_text())
    legacy = json.loads((ROOT / 'backend/app/postgraduate_sources.json').read_text())
    report = coverage_report(catalog, legacy)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(report['scope'])
    print(f"候选 {report['catalog_sources']}；配置可接入 {report['configured_sources']}；状态 {report['statuses']}")
    for topic in report['topics']:
        print(f"{topic['label']}：候选 {topic['candidates']}，配置可接入 {topic['configured_sources']}")
    for topic in ('examination', 'recruitment'):
        missing = [r['label'] for r in report['provincial_authorities']
                   if r['topic'] == topic and r['ready'] == 0]
        print(f"{TOPIC_LABELS[topic]}省级正文待接入：{'、'.join(missing) or '无'}")


if __name__ == '__main__':
    main()

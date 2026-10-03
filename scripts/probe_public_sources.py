"""Probe public columns with the production HTTPS/robots collector; never approve licences.
One host is processed serially; distinct hosts may be probed concurrently.
"""
import argparse
import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'backend'))
from app.adapters.base import RawArtifact
from app.adapters.education import UniversityNoticeAdapter
from app.adapters.notice_text import document_base
from app.adapters.index_discovery import discover_index
from app.adapters.public_request import fetch_public_resource
from app.adapters.public_json_notice import PublicJSONNoticeAdapter
from app.collector_http import collect_bytes_conditional
from app.config import settings
from app.notice_watch import official_url, embedded_pdfs
from app.parsers import ParseError
from bs4 import BeautifulSoup

MANIFEST = ROOT/'backend/app/public_sources.json'
_last_request = {}


def fetch_public(url, config=None, kind='index'):
    host = urlsplit(url).hostname
    delay = 1 - (time.monotonic() - _last_request.get(host, 0))
    if delay > 0:
        time.sleep(delay)
    _last_request[host] = time.monotonic()
    return fetch_public_resource(url, config or {}, kind)

NAVIGATION_LABELS = ('硕士招生', '硕士生招生', '推免', '招生信息', '招生工作',
    '研究生招生', '通知公告', '通知通告', '公告通知', '招聘信息', '招考公告',
    '政策法规', '奖学金', '出国留学', '海外学习', '学生交流', '国际项目',
    '赛事通知', '大赛通知', '资助政策', '奖助学金', '信息公告')


def probe(entry):
    row = {'code': entry['code'], 'name': entry['name'], 'topic': entry['topic'],
           'checked_at': datetime.now(UTC).isoformat(), 'status': 'blocked', 'attempts': []}
    base = entry['base_url']
    # Failed columns and unsupported article templates must not hide healthy alternatives.
    urls = [(url, 0) for url in dict.fromkeys(entry['index_urls'])][:4]
    pages, seen_articles, usable_indexes = {}, set(), []
    def fetch_page(url, kind='index'):
        if url not in pages:
            pages[url] = (fetch_public(url, entry, kind) if entry.get('index_requests') or entry.get('detail_request')
                          else fetch_public(url))
        return pages[url]
    discovered = set()
    position = 0
    while position < len(urls) and position < 4:
        url, depth = urls[position]
        position += 1
        try:
            if not official_url(url, base):
                raise ValueError('栏目离开配置的 HTTPS 官方主机')
            page = fetch_page(url)
            if not official_url(page['final_url'], base):
                raise ValueError('重定向离开配置的 HTTPS 官方主机')
            discovery_config = {**entry,
                'index_page_url':page.get('canonical_url',page['final_url']),
                'discovery_format': entry.get('index_formats', {}).get(url,
                    entry.get('discovery_format', 'auto'))}
            discovery_config.pop('index_formats', None)
            links = discover_index(page['data'], page['final_url'], discovery_config)['links']
            row['attempts'].append({'url': url, 'final_url': page['final_url'],
                'status': page['status_code'], 'sha256': hashlib.sha256(page['data']).hexdigest(),
                'discovered': len(links)})
            if links:
                canonical_index = page.get('canonical_url',page['final_url'])
                if canonical_index not in usable_indexes:
                    usable_indexes.append(canonical_index)
                discovered.update(link['url'] for link in links)
                row['discovered'] = len(discovered)
                row['examples'] = links[:3]
                if row['status'] != 'ready':
                    row['status'] = 'index_ready'
                # Six distinct samples per source, at most four columns and one navigation hop.
                for link in links[:3]:
                    if row['status'] == 'ready' or len(seen_articles) >= 6:
                        break
                    if link['url'] in seen_articles:
                        continue
                    seen_articles.add(link['url'])
                    try:
                        article = fetch_page(link['url'], 'detail')
                        if not official_url(article['final_url'], base):
                            raise ValueError('正文重定向离开官方主机')
                        adapter = (PublicJSONNoticeAdapter(entry['topic'],entry['json_detail']) if entry.get('json_detail') else
                            UniversityNoticeAdapter(entry['topic'], entry.get('article_selector'),
                                entry.get('title_selector'),entry.get('title_context', ''),entry.get('date_timezone')))
                        try:
                            parsed = adapter.parse(RawArtifact(article['data'],article.get('canonical_url',article['final_url']),
                                link['url'],article['content_type'],retrieval_url=article.get('retrieval_url'),
                                retrieval_method=article.get('retrieval_method','GET'),retrieval_form=article.get('retrieval_form')))
                        except ParseError:
                            # An official PDF viewer is a real document, not an empty HTML body.
                            pdfs = embedded_pdfs(article['data'],article['final_url']) if not entry.get('json_detail') else []
                            if not pdfs:
                                raise
                            pdf = fetch_page(pdfs[0], 'attachment')
                            if not official_url(pdf['final_url'],base):
                                raise ValueError('PDF 重定向离开官方主机')
                            parsed = adapter.parse(RawArtifact(pdf['data'],pdf['final_url'],pdfs[0],pdf['content_type']))
                            article = pdf
                        row.update(status='ready', sample={'url': article.get('canonical_url',article['final_url']),
                            'title': parsed.records[0]['title'], 'evidence': len(parsed.evidence),
                            'sha256': hashlib.sha256(article['data']).hexdigest()})
                        row.pop('detail_error', None)
                    except (ValueError, TypeError, OSError) as exc:
                        row['attempts'].append({'url': link['url'], 'kind': 'detail', 'error': str(exc)[:250]})
                        row['detail_error'] = str(exc)[:250]
            elif depth == 0:
                soup = BeautifulSoup(page['data'], 'html.parser')
                for anchor in soup.select('a[href]'):
                    if any(label in anchor.get_text(' ', strip=True) for label in NAVIGATION_LABELS):
                        candidate = official_url(anchor['href'].strip(), document_base(soup, page['final_url']))
                        if candidate and candidate not in {item[0] for item in urls} and len(urls) < 4:
                            urls.append((candidate, 1))
        except (ValueError, TypeError, OSError) as exc:
            row['attempts'].append({'url': url, 'error': str(exc)[:250]})
    if usable_indexes:
        row['index_urls'] = usable_indexes
        row['error'] = ''
    else:
        row['error'] = next((a['error'] for a in row['attempts'] if 'error' in a),
            '静态栏目未发现主题详情链接；需校准栏目或动态页面')
    return row

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-manifest', action='store_true')
    parser.add_argument('--workers', type=int, default=12, choices=range(1,17))
    parser.add_argument('--codes', nargs='*')
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    entries = [s for s in manifest['sources'] if not args.codes or s['code'] in args.codes]
    settings.collector_allowed_hosts = ','.join(sorted({urlsplit(s['base_url']).hostname for s in entries}))
    settings.collector_allow_plaintext_hosts = ''
    settings.collector_skip_robots = False
    groups = defaultdict(list)
    for entry in entries:
        groups[urlsplit(entry['base_url']).hostname].append(entry)
    def host_group(rows):
        results = []
        for entry in rows:
            result = probe(entry)
            print(json.dumps({k: result.get(k) for k in ('code','status','discovered','error','detail_error')}, ensure_ascii=False), flush=True)
            results.append(result)
        return results
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed([pool.submit(host_group, rows) for rows in groups.values()]):
            results.extend(future.result())
    report_path = ROOT/'artifacts/source-expansion/probe-report.json'
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {'checked_at': datetime.now(UTC).isoformat(), 'summary': dict(Counter(r['status'] for r in results)),
        'checks': 'HTTPS TLS / public IP / exact host / strict robots / bounded column discovery / real article parser',
        'license_approval': False, 'results': sorted(results, key=lambda r: r['code'])}
    if args.codes and report_path.exists():
        previous = json.loads(report_path.read_text(encoding='utf-8'))
        active_codes = {s['code'] for s in manifest['sources']}
        merged = {r['code']: r for r in previous['results'] if r['code'] in active_codes}
        merged.update({r['code']: r for r in results})
        report['results'] = sorted(merged.values(), key=lambda r: r['code'])
        report['summary'] = dict(Counter(r['status'] for r in report['results']))
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    if args.write_manifest:
        by_code = {r['code']: r for r in results}
        for entry in manifest['sources']:
            if entry['code'] not in by_code:
                continue
            row = by_code[entry['code']]
            entry['status'] = row['status']
            entry['probe'] = {k: v for k, v in row.items() if k not in {'code','name','topic','attempts','index_urls','examples'}}
            if row.get('index_urls'):
                entry['index_urls'] = row['index_urls']
        manifest['checked_at'] = report['checked_at']
        MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report['summary']))

if __name__ == '__main__':
    main()

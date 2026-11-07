"""Bounded first-party discovery; list metadata is never archived as article evidence."""
import json
import re
from datetime import datetime
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qs, urlencode
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup

from ..parsers import MAX_BYTES, ParseError
from .notice_text import discover_notices, document_base, matches_topic


def official_url(url, base):
    try:
        if not isinstance(url, str) or not url.strip():
            return None
        p, b = urlsplit(urljoin(base, url.strip())), urlsplit(base)
        if (p.scheme != 'https' or p.hostname != b.hostname or p.port not in (None, 443)
                or p.username or p.password or len(p.geturl()) > 500):
            return None
        return urlunsplit((p.scheme, p.netloc, p.path, p.query, ''))
    except ValueError:
        return None


def discover_index(content, base, config, limit=30, known_urls=None):
    if not content or len(content) > MAX_BYTES:
        raise ParseError('索引为空或超过大小限制')
    topic = config.get('topic', 'postgraduate')
    mode = config.get('index_formats', {}).get(base, config.get('discovery_format', 'auto'))
    links, indexes, seen = [], [], set()
    recognized = False

    def add(raw_url, title='', context='', scoped=False):
        url = official_url(raw_url, base)
        title = ' '.join(BeautifulSoup(str(title), 'html.parser').get_text(' ', strip=True).split())
        if not url or url == base or url in seen:
            return
        if not scoped and (len(title) < 8 or not matches_topic(title + ' ' + context, topic)
                or re.search(r'名单|成绩查询|登录|公示|拟录取|隐私', title)):
            return
        seen.add(url)
        if len(links) < limit:
            links.append({'url': url, 'title': title[:240]})

    stripped = content.lstrip() if isinstance(content, bytes) else content.lstrip().encode()
    if mode == 'json':
        mapping = config.get('json_index', {})
        if not mapping.get('title_field') or not (mapping.get('url_field') or
                (mapping.get('id_field') and mapping.get('url_template'))):
            raise ParseError('公开 JSON 索引缺少显式字段映射')
        try:
            payload = rows = json.loads(content)
            for key in mapping.get('items_path', []):
                rows = rows[key]
            if not isinstance(rows, list) or any(not isinstance(x, dict) for x in rows[:200]):
                raise ValueError('not an item list')
            for row in rows[:200]:
                if not isinstance(row.get(mapping['title_field']), str):
                    raise ValueError('missing title or URL')
                if mapping.get('url_field'):
                    raw_url = row.get(mapping['url_field'])
                    if not isinstance(raw_url, str):
                        raise ValueError('missing URL')
                else:
                    item_id = str(row.get(mapping['id_field'], ''))
                    if not re.fullmatch(r'[0-9]{1,16}', item_id):
                        raise ValueError('invalid public item ID')
                    raw_url = mapping['url_template'].replace('{id}', item_id)
                add(raw_url, row[mapping['title_field']])
            pagination = mapping.get('pagination')
            if pagination:
                count = payload[pagination['page_count_field']]
                if isinstance(count,bool) or not re.fullmatch(r'[0-9]{1,6}',str(count)):
                    raise ValueError('invalid page count')
                page_url=config.get('index_page_url',base)
                parts=urlsplit(page_url)
                parameter=pagination['page_parameter']
                current=int(parse_qs(parts.query).get(parameter,['1'])[0])
                maximum=min(100,max(1,int(pagination.get('max_pages',3))))
                if 1<=current<min(int(count),maximum):
                    next_url=urlunsplit((parts.scheme,parts.netloc,parts.path,urlencode({parameter:current+1}),''))
                    url=official_url(next_url,base)
                    if url:indexes.append(url)
            recognized = True  # An explicitly mapped empty list is a healthy index.
        except (ValueError, TypeError, KeyError) as exc:
            raise ParseError('公开 JSON 索引结构与字段映射不符') from exc
    elif mode in {'rss', 'atom', 'sitemap'} or (mode == 'auto' and
            re.search(br'<(?:rss\b|feed\b|urlset\b|sitemapindex\b)', stripped[:2000], re.I)):
        # Do not resolve XML entities, external DTDs or xml:base host changes.
        if re.search(br'<!\s*(?:DOCTYPE|ENTITY)', stripped.replace(b'\x00', b''), re.I):
            raise ParseError('XML 索引包含不支持的实体声明')
        try:
            root = ET.fromstring(content)
        except ET.ParseError as exc:
            raise ParseError('XML 索引格式错误') from exc
        tag = root.tag.rsplit('}', 1)[-1]
        if tag == 'rss':
            channel = root.find('channel')
            if channel is None:
                raise ParseError('RSS 索引缺少 channel')
            for item in channel.findall('item')[:200]:
                add(item.findtext('link'), item.findtext('title', ''), item.findtext('description', '') + ' ' + config.get('title_context', ''))
            recognized = True
        elif tag == 'feed':
            ns = '{http://www.w3.org/2005/Atom}'
            if root.tag != ns + 'feed':
                raise ParseError('Atom 索引命名空间不符')
            for item in root.findall(ns + 'entry')[:200]:
                link = next((n for n in item.findall(ns + 'link') if n.get('rel', 'alternate') == 'alternate'), None)
                if link is not None:
                    add(link.get('href'), ''.join(item.find(ns+'title').itertext()) if item.find(ns+'title') is not None else '',
                        item.findtext(ns + 'summary', '') + ' ' + config.get('title_context', ''))
            recognized = True
        elif tag == 'urlset':
            prefixes = config.get('detail_path_prefixes', [])
            if not prefixes or any(not p.startswith('/') or p == '/' for p in prefixes):
                raise ParseError('网站地图必须显式限定正文路径')
            candidates = []
            for node in root:
                fields = {n.tag.rsplit('}', 1)[-1]: n.text or '' for n in node}
                url = official_url(fields.get('loc'), base)
                if not url or url in (known_urls or set()) or not any(urlsplit(url).path.startswith(p) for p in prefixes):
                    continue
                try:
                    modified = datetime.fromisoformat(fields.get('lastmod', '').replace('Z', '+00:00')).isoformat()
                except ValueError:
                    modified = ''
                candidates.append((modified, url))
            for _, url in sorted(candidates, reverse=True):
                add(url, scoped=True)
                if len(links) >= limit:
                    break
            recognized = True
        else:
            raise ParseError('不支持的 XML 索引；请配置具体栏目网站地图')
    elif mode in {'auto', 'html'}:
        links = discover_notices(content, base, limit=limit, topic=topic)
        soup = BeautifulSoup(content, 'html.parser')
        link_base = document_base(soup, base)
        for node in soup.select('link[rel][href]'):
            rel = node.get('rel', [])
            if 'alternate' in rel and node.get('type', '').lower() in {'application/rss+xml', 'application/atom+xml'}:
                url = official_url(node['href'], link_base)
                if url and url != base and url not in indexes:
                    indexes.append(url)
        for node in soup.select('a[href], link[rel="next"][href]'):
            if 'next' in node.get('rel', []) or re.fullmatch(r'\s*(?:下一页|下页|Next(?:\s+page)?|›|>)\s*', node.get_text(strip=True), re.I):
                url = official_url(node['href'], link_base)
                if url and url != base and url not in indexes:
                    indexes.append(url)
                    break
        indexes = indexes[:3]
        recognized = bool(links or indexes)
    else:
        raise ParseError('未知索引格式')
    if config.get('detail_path_prefixes') and mode!='sitemap':
        links=[link for link in links if any(urlsplit(link['url']).path.startswith(prefix)
            for prefix in config['detail_path_prefixes'])]
    return {'links': links, 'indexes': indexes, 'recognized': recognized}

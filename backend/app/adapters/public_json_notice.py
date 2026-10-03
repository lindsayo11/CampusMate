"""Full public JSON details with field-level provenance, never list summaries."""
import json
import re
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup

from .base import ParsedDocument
from .education import PublicNoticeAdapter, clean
from .notice_text import matches_topic, registration_dates
from ..parsers import MAX_BYTES, ParseError


def attachment_records(value, soup, base, mapping, body_location):
    """Only configured public file fields and same-host body links are discoverable."""
    from .index_discovery import official_url
    found, proofs = [], []

    def add(url, title, location):
        url = official_url(url, base)
        title = clean(str(title))[:240]
        if (not url or re.search(r'名单|公示|拟录取', title)
                or not re.search(r'\.(?:pdf|docx?|xlsx?)(?:\?|$|\b)', url+' '+title, re.I)
                or any(row['url'] == url for row in found) or len(found) >= 20):
            return
        row = {'title': title or '原文附件', 'url': url}
        found.append(row)
        proofs.append({'record_key':'notice','field':'attachments','evidence_location':location,
            'quote_or_normalized_fact':json.dumps(row,ensure_ascii=False),
            'extractor':'parser','evidence_type':'json'})

    for link in soup.select('a[href]')[:200]:
        add(link['href'], link.get_text(' ',strip=True), body_location)
    spec = mapping.get('attachments')
    if not spec:
        return found, proofs
    rows = value.get(spec['field'], [])
    if spec.get('encoding') == 'json_string' and isinstance(rows, str) and len(rows) <= 100000:
        try: rows = json.loads(rows)
        except ValueError: rows = []
    if not isinstance(rows, list):
        return found, proofs
    prefix = spec.get('url_prefix', '')
    if prefix and (not re.fullmatch(r'(?:/[A-Za-z0-9_-]+)+',prefix)):
        raise ParseError('附件 URL 前缀配置不符')
    location = 'json=$.'+'.'.join(mapping.get('items_path',[])+[spec['field']])
    for index, row in enumerate(rows[:20]):
        if not isinstance(row, dict): continue
        url, title = row.get(spec['url_field']), row.get(spec['title_field'])
        if not isinstance(url,str) or not isinstance(title,str): continue
        # A configured context prefix cannot turn external or arbitrary action URLs into downloads.
        if prefix:
            path = spec.get('url_path_prefix', '')
            if (not path.startswith('/') or path.startswith('//') or '..' in path
                    or not url.startswith(path) or '..' in url or '\\' in url
                    or re.search(r'%(?:2e|2f|5c)',url,re.I) or urlsplit(url).scheme
                    or urlsplit(url).netloc):
                continue
            url = prefix + url
        suffix = f';json-string-index={index}' if spec.get('encoding')=='json_string' else f'[{index}]'
        add(url,title,location+suffix)
    return found, proofs


class PublicJSONNoticeAdapter(PublicNoticeAdapter):
    def __init__(self, topic, mapping):
        super().__init__(topic)
        self.mapping = mapping

    def parse(self, raw):
        if not raw.content or len(raw.content) > MAX_BYTES:
            raise ParseError('公开 JSON 正文为空或超出限制')
        try:
            value = json.loads(raw.content)
            if self.mapping.get('success_field') and value[self.mapping['success_field']] != self.mapping['success_value']:
                raise ValueError('unsuccessful response')
            for key in self.mapping.get('items_path', []):
                value = value[key]
            title=value[self.mapping['title_field']]
            body_path=self.mapping.get('body_path',[self.mapping.get('body_field','content')])
            if not isinstance(body_path,list) or len(body_path)>8:raise ValueError('invalid body path')
            html=value;segments=[]
            for part in body_path:
                if isinstance(part,dict):
                    if not isinstance(html,list) or len(html)>200 or set(part)!={'field','equals'}:raise ValueError('invalid body selector')
                    matches=[(i,r) for i,r in enumerate(html) if isinstance(r,dict) and r.get(part['field'])==part['equals']]
                    if len(matches)!=1:raise ValueError('ambiguous body selector')
                    index,html=matches[0];segments[-1]+=f'[{index}]'
                else:
                    html=html[part];segments.append(str(part))
            if not isinstance(title, str) or not isinstance(html, str):
                raise ValueError('invalid body')
            if self.mapping.get('id_field'):
                if self.mapping.get('page_path_pattern'):
                    match=re.fullmatch(self.mapping['page_path_pattern'],urlsplit(raw.canonical_url).path)
                    expected=[match.group('id')] if match else []
                else:
                    expected = parse_qs(urlsplit(raw.canonical_url).query).get(self.mapping['query_parameter'], [])
                if len(expected) != 1 or str(value[self.mapping['id_field']]) != expected[0]:
                    raise ValueError('detail ID mismatch')
        except (ValueError, KeyError, TypeError) as exc:
            raise ParseError('公开 JSON 正文结构或条目编号不符') from exc
        title = clean(BeautifulSoup(title, 'html.parser').get_text(' ', strip=True))
        if not matches_topic(title, self.topic):
            raise ParseError('公开 JSON 正文标题与主题不符')
        soup = BeautifulSoup(html, 'html.parser')
        for node in soup(['script', 'style', 'noscript']):
            node.decompose()
        body = soup.get_text('\n', strip=True)
        if len(body) < 30 or len(body) > 200000:
            raise ParseError('公开 JSON 正文不足或超出限制')
        location = 'json=$.' + '.'.join(map(str,self.mapping.get('items_path', []) + segments))
        evidence = [{'record_key':'notice', 'field':'body', 'evidence_location':location,
                     'quote_or_normalized_fact':body, 'extractor':'parser', 'evidence_type':'json'},
                    {'record_key':'notice', 'field':'title',
                     'evidence_location':'json=$.' + '.'.join(map(str,self.mapping.get('items_path', []) + [self.mapping['title_field']])),
                     'quote_or_normalized_fact':title, 'extractor':'parser', 'evidence_type':'json'}]
        values = {'title':title, 'body':body, 'attachments':[], 'material_quotes':[],
                  'retrieval':{'url':raw.retrieval_url, 'method':raw.retrieval_method, 'form':raw.retrieval_form}}
        values['attachments'], attachment_proofs = attachment_records(value,soup,raw.canonical_url,self.mapping,location)
        evidence.extend(attachment_proofs)
        # UpdateTime is not publication time or a deadline. Only explicit body dates count.
        start, finish = registration_dates(clean(body), None)
        for field, date in (('open_at',start), ('deadline_at',finish)):
            if date:
                values[field] = date
                evidence.append({**evidence[0], 'field':field})
        publish_time=None
        from datetime import datetime
        from zoneinfo import ZoneInfo
        for field,key in self.mapping.get('date_fields',{}).items():
            text=value.get(key)
            if field not in {'publish_time','open_at','deadline_at'} or not isinstance(text,str):continue
            if not re.fullmatch(r'20\d{2}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}:\d{2})?',text):continue
            try:
                date=datetime.fromisoformat(text).replace(tzinfo=ZoneInfo(self.mapping['date_timezone']))
                if field=='deadline_at':date=date.replace(hour=23,minute=59)
            except (ValueError,KeyError):continue
            if field=='publish_time':publish_time=date.isoformat()
            else:values[field]=date.isoformat()
            evidence.append({**evidence[0],'field':field,'evidence_location':'json=$.'+'.'.join(self.mapping.get('items_path',[])+[key]),
                'quote_or_normalized_fact':text})
        return ParsedDocument(records=[values], evidence=evidence,
                              metadata={'canonical_url':raw.canonical_url, 'publish_time':publish_time})

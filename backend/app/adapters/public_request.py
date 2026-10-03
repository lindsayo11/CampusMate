"""Explicit first-party read-only form endpoints; discovered links cannot choose actions."""
import re
from urllib.parse import parse_qs, urlsplit, urlencode, urlunsplit

from ..collector_http import FetchError, collect_bytes_conditional, collect_public_form
from .index_discovery import official_url


def request_spec(url, config, kind='index'):
    spec = config.get('index_requests', {}).get(url) if kind == 'index' else None
    form = None
    pagination = config.get('json_index', {}).get('pagination', {})
    if kind == 'index' and not spec and pagination:
        # Only the explicit listing path and its single configured page parameter
        # may reuse a read-only form; arbitrary discovered URLs cannot do so.
        for root, candidate in config.get('index_requests', {}).items():
            page, first = urlsplit(url), urlsplit(root)
            query = parse_qs(page.query,keep_blank_values=True)
            parameter = pagination.get('page_parameter')
            values = query.get(parameter, [])
            maximum = min(100,max(1,int(pagination.get('max_pages',3))))
            if (page.scheme==first.scheme and page.netloc==first.netloc and page.path==first.path
                    and not first.query and set(query)=={parameter} and len(values)==1
                    and re.fullmatch(r'[0-9]{1,3}',values[0]) and 1<=int(values[0])<=maximum):
                spec=candidate
                form={**candidate.get('form',{}),parameter:int(values[0])}
                break
    if kind == 'detail' and config.get('detail_request'):
        spec = config['detail_request']
        if spec.get('page_path_pattern'):
            match=re.fullmatch(spec['page_path_pattern'],urlsplit(url).path)
            if not match or not re.fullmatch(r'[0-9]{1,24}',match.group('id')):
                raise FetchError('正文路径与公开接口配置不符')
            spec={**spec,'url':spec['url'].replace('{id}',match.group('id'))}
            form=spec.get('form',{})
            if spec.get('method')=='GET' and spec.get('id_parameter'):
                form={**form,spec['id_parameter']:match.group('id')}
        else:
            if urlsplit(url).path != spec.get('page_path'):
                raise FetchError('正文路径与公开接口配置不符')
            ids = parse_qs(urlsplit(url).query).get(spec.get('query_parameter'), [])
            if len(ids) != 1 or not re.fullmatch(r'[0-9]{1,16}', ids[0]):
                raise FetchError('公开正文接口缺少有效条目编号')
            form = {**spec.get('form', {}), spec['id_parameter']:ids[0]}
    if not spec:
        return None
    target = official_url(spec.get('url'), url)
    if not target or spec.get('method') not in {'GET','POST'} or spec.get('read_only') is not True:
        raise FetchError('只允许显式声明的官方匿名只读接口')
    if spec['method']=='GET':
        values={**spec.get('params',{}),**(form or {})}
        if len(values)>16 or any(not isinstance(k,str) or not isinstance(v,(str,int)) or len(k)>80 or len(str(v))>200 for k,v in values.items()):
            raise FetchError('公开 GET 参数超出限制')
        parts=urlsplit(target)
        if parts.query:raise FetchError('公开 GET 地址不能附带未映射参数')
        return urlunsplit((parts.scheme,parts.netloc,parts.path,urlencode(values),'')),None
    return target, form if form is not None else spec.get('form', {})


def fetch_public_resource(url, config, kind='index', etag=None, last_modified=None):
    spec = request_spec(url, config, kind)
    if spec:
        target, form = spec
        result = collect_public_form(target, form) if form is not None else collect_bytes_conditional(target,etag,last_modified,strict_robots=True)
        # Preserve the human-facing official page; archive the actual JSON bytes.
        return {**result, 'canonical_url':url, 'retrieval_url':target,
                'retrieval_method':'POST' if form is not None else 'GET', 'retrieval_form':form}
    return collect_bytes_conditional(url, etag, last_modified, strict_robots=True)

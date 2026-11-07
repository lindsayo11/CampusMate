"""Allowlisted, IP-pinned fetches for official sources, including redirects."""
import ipaddress
import socket
import time
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from .config import settings
from .parsers import MAX_BYTES

USER_AGENT = "CampusMateCollector/1.0"
_robots_cache = {}


class FetchError(ValueError):
    def __init__(self, message, status_code=None, retry_after=None):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


def _plaintext_allowed(hostname: str) -> bool:
    """Whether an explicit local-dev exception permits HTTP on this host."""
    allowed = {h.strip().lower()
               for h in settings.collector_allow_plaintext_hosts.split(",") if h.strip()}
    host = (hostname or "").lower()
    return bool(host and (host in allowed or any(host.endswith("." + item) for item in allowed)))


def validate_url(url):
    parts = urlsplit(url)
    allowed = {h.strip().lower() for h in settings.collector_allowed_hosts.split(",") if h.strip()}
    if (not parts.hostname or parts.hostname.lower() not in allowed
            or parts.username or parts.password or parts.fragment or len(url) > 500):
        raise FetchError("仅允许配置白名单中的官方源（无凭据和片段）")
    if _plaintext_allowed(parts.hostname):
        # Explicit per-host exception: some official portals serve content
        # only over plaintext HTTP (see Settings.collector_allow_plaintext_hosts).
        if parts.scheme not in ("http", "https") or parts.port not in (None, 80, 443):
            raise FetchError("已授权的明文来源也仅允许 80/443 端口")
    elif parts.scheme != "https" or parts.port not in (None, 443):
        raise FetchError("仅允许配置白名单中的 HTTPS 官方源（443 端口，无凭据和片段）")
    return parts


def public_ip(host, port=None):
    """Resolve ``host`` and require every answer to be a public address.

    ``port`` is optional so the anti-DNS-rebinding helper keeps its historical
    single-argument call shape; resolution is port-independent in practice and
    callers that care pass the real port (80 for plaintext exceptions).
    """
    if port is None:
        port = 443
    try:
        addresses = sorted({item[4][0] for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)})
    except OSError as exc:
        raise FetchError("来源域名解析失败") from exc
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise FetchError("来源必须解析为公网地址，禁止内网和保留地址")
    return addresses[0]


def fetch_url(url, max_bytes=MAX_BYTES, check_robots=False, conditional_headers=None,
              return_headers=False, strict_robots=False, method='GET', form_data=None):
    if method not in {'GET', 'POST'} or (method == 'POST' and
            (not check_robots or not strict_robots or not isinstance(form_data, dict)
             or len(form_data) > 16
             or any(not isinstance(k, str) or not isinstance(v, (str, int))
                    or len(k) > 80 or len(str(v)) > 200 for k, v in form_data.items()))):
        raise FetchError('公开只读 POST 需要有界表单及严格 robots 检查')
    deadline = time.monotonic() + 45
    with httpx.Client(timeout=10, follow_redirects=False, trust_env=False) as client:
        for _ in range(4):
            parts = validate_url(url)
            if check_robots:
                if strict_robots:
                    assert_robots(url, strict=True)
                else:
                    assert_robots(url)
            scheme = parts.scheme
            port = parts.port or (443 if scheme == "https" else 80)
            # Call with the hostname only: keeps the helper call shape stable and
            # the resolved address set is identical for a given name.
            ip = public_ip(parts.hostname)
            address = f"[{ip}]" if ":" in ip else ip
            pinned = f"{scheme}://{address}{parts.path or '/'}" + (f"?{parts.query}" if parts.query else "")
            try:
                request_headers = {"Host": parts.hostname, "User-Agent": USER_AGENT,
                                   "Accept-Encoding": "identity"}
                request_headers.update(conditional_headers or {})
                extensions = {"sni_hostname": parts.hostname} if scheme == "https" else None
                with client.stream(method, pinned, headers=request_headers,
                    extensions=extensions, **({'data':form_data} if method == 'POST' else {})) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        if method == 'POST':
                            raise FetchError('公开只读 POST 不跟随重定向，请重新核对官方接口')
                        url = urljoin(url, response.headers.get("location", ""))
                        if time.monotonic() > deadline:
                            raise FetchError("采集总时限已超出")
                        continue
                    if response.status_code == 404:
                        result = (b"", "", url, 404)
                        return (*result, dict(response.headers)) if return_headers else result
                    if response.status_code == 304:
                        result = (b"", response.headers.get("content-type", ""), url, 304)
                        return (*result, dict(response.headers)) if return_headers else result
                    if response.status_code in (429, 503):
                        raise FetchError("来源限流或暂时不可用", response.status_code,
                                         response.headers.get("retry-after"))
                    response.raise_for_status()
                    if response.headers.get("content-encoding", "identity").lower() not in ("identity", ""):
                        raise FetchError("来源忽略压缩协商，请改用文件导入")
                    data = bytearray()
                    for chunk in response.iter_raw():
                        data.extend(chunk)
                        if len(data) > max_bytes or time.monotonic() > deadline:
                            raise FetchError("来源内容超过大小或时间限制")
                    result = (bytes(data), response.headers.get("content-type", ""), url,
                              response.status_code)
                    return (*result, dict(response.headers)) if return_headers else result
            except FetchError:
                raise
            except httpx.HTTPError as exc:
                raise FetchError("来源 HTTP 请求失败或超时") from exc
    raise FetchError("来源重定向次数过多")


def assert_robots(url, strict=False):
    if settings.collector_skip_robots and not strict:
        # LOCAL-DEV OVERRIDE: see Settings.collector_skip_robots. Every other
        # control (allowlist, public-IP pinning, official-host redirect check,
        # calibration evidence) still applies.
        return
    parts = validate_url(url)
    scheme = parts.scheme
    origin = f"{scheme}://{parts.hostname}"
    cached = _robots_cache.get(origin) if strict else None
    if cached and time.monotonic() - cached[0] < 600:
        _, data, code = cached
    else:
        try:
            data, _, _, code = fetch_url(origin + '/robots.txt', 128 * 1024)
        except FetchError as exc:
            raise FetchError('无法确认官方 robots 规则（网络或重定向异常），等待重试',
                             exc.status_code, exc.retry_after) from exc
        if strict:
            _robots_cache[origin] = (time.monotonic(), data, code)
    if code != 404:
        robots = RobotFileParser()
        robots.parse(data.decode("utf-8", errors="replace").splitlines())
        if not robots.can_fetch(USER_AGENT, url):
            raise FetchError("来源 robots.txt 不允许采集")


def collect_bytes(url):
    data, content_type, _, code = fetch_url(url, check_robots=True)
    if code == 404:
        raise FetchError("来源页面不存在（404）")
    return data, content_type


def collect_bytes_conditional(url, etag=None, last_modified=None, strict_robots=False):
    """Fetch a governed URL using standard conditional request headers."""
    headers = {}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    data, content_type, final_url, code, response_headers = fetch_url(
        url, check_robots=True, conditional_headers=headers, return_headers=True,
        strict_robots=strict_robots)
    if code == 404:
        raise FetchError("来源页面不存在（404）")
    return {"not_modified": code == 304, "data": data, "content_type": content_type,
            "final_url": final_url, "status_code": code,
            "etag": response_headers.get("etag"),
            "last_modified": response_headers.get("last-modified")}


def collect_public_form(url, form):
    """For operator-configured anonymous read-only lists/details, never arbitrary actions."""
    data, content_type, final_url, code, headers = fetch_url(url, check_robots=True,
        strict_robots=True, return_headers=True, method='POST', form_data=form)
    if code != 200:
        raise FetchError('公开只读接口没有返回完整正文', code)
    return {'not_modified':False, 'data':data, 'content_type':content_type,
            'final_url':final_url, 'status_code':code, 'etag':None, 'last_modified':None}

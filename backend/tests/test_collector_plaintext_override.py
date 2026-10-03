"""Local-dev collector overrides: per-host plaintext HTTP and robots skip.

Both flags exist because real official portals break the collector's defaults:

* www.moe.gov.cn sits behind TencentEdgeOne and answers every https:// request
  with "302 Found -> http://..." (verified live 2026-09-29), so its content is
  only reachable over plaintext HTTP.
* The same host serves no robots.txt at all, while some government portals
  serve a full HTML page on /robots.txt, which CPython's RobotFileParser reads
  as "disallow everything".

The tests below pin the important property: these are narrow, explicit,
per-host exceptions. The default stays HTTPS-only, and nothing else about the
governance chain is relaxed.
"""
import pytest

from app.collector_http import FetchError, validate_url
from app.config import settings
from app.intake_governance import official_https_ok
from urllib.parse import urlsplit


@pytest.fixture
def plaintext_off(monkeypatch):
    monkeypatch.setattr(settings, "collector_allowed_hosts", "www.moe.gov.cn,www.gov.cn")
    monkeypatch.setattr(settings, "collector_allow_plaintext_hosts", "")
    yield


def test_http_rejected_by_default(plaintext_off):
    """With no exception configured, plaintext HTTP is refused."""
    with pytest.raises(FetchError):
        validate_url("http://www.moe.gov.cn/jyb_sjzl/")


def test_https_accepted_by_default(plaintext_off):
    parts = validate_url("https://www.moe.gov.cn/jyb_sjzl/")
    assert parts.scheme == "https"


def test_http_allowed_only_for_listed_host(monkeypatch):
    """Only the explicitly listed host may use plaintext; others still fail."""
    monkeypatch.setattr(settings, "collector_allowed_hosts", "www.moe.gov.cn,www.gov.cn")
    monkeypatch.setattr(settings, "collector_allow_plaintext_hosts", "www.moe.gov.cn")
    # listed host -> permitted
    assert validate_url("http://www.moe.gov.cn/jyb_sjzl/").scheme == "http"
    # different allowlisted host -> still refused
    with pytest.raises(FetchError):
        validate_url("http://www.gov.cn/zhengce/")


def test_https_still_required_for_unlisted_host(monkeypatch):
    monkeypatch.setattr(settings, "collector_allowed_hosts", "www.moe.gov.cn,www.gov.cn")
    monkeypatch.setattr(settings, "collector_allow_plaintext_hosts", "www.moe.gov.cn")
    assert validate_url("https://www.gov.cn/zhengce/").scheme == "https"


def test_non_allowlisted_host_refused_regardless_of_plaintext_list(monkeypatch):
    """The plaintext exception must not widen the allowlist itself."""
    monkeypatch.setattr(settings, "collector_allowed_hosts", "www.moe.gov.cn")
    monkeypatch.setattr(settings, "collector_allow_plaintext_hosts", "www.moe.gov.cn")
    with pytest.raises(FetchError):
        validate_url("http://evil.example/x")
    with pytest.raises(FetchError):
        validate_url("https://evil.example/x")


def test_credentials_and_fragments_always_refused(plaintext_off):
    with pytest.raises(FetchError):
        validate_url("https://user:pw@www.moe.gov.cn/x")
    with pytest.raises(FetchError):
        validate_url("https://www.moe.gov.cn/x#frag")


def test_governance_gate_mirrors_the_same_rule(monkeypatch):
    """The gate must agree with the collector, host by host."""
    monkeypatch.setattr(settings, "collector_allow_plaintext_hosts", "")
    http_url = urlsplit("http://www.moe.gov.cn/jyb_sjzl/")
    https_url = urlsplit("https://www.moe.gov.cn/jyb_sjzl/")
    base = urlsplit("http://www.moe.gov.cn/")
    assert official_https_ok(https_url, base) is True
    assert official_https_ok(http_url, base) is False

    monkeypatch.setattr(settings, "collector_allow_plaintext_hosts", "www.moe.gov.cn")
    assert official_https_ok(http_url, base) is True

    # A non-official host is refused even with the plaintext exception on.
    other = urlsplit("http://www.gov.cn/zhengce/")
    assert official_https_ok(other, base) is False


def test_governance_gate_rejects_credentials(monkeypatch):
    monkeypatch.setattr(settings, "collector_allow_plaintext_hosts", "www.moe.gov.cn")
    base = urlsplit("http://www.moe.gov.cn/")
    assert official_https_ok(urlsplit("http://u:p@www.moe.gov.cn/x"), base) is False
    assert official_https_ok(urlsplit("http://www.moe.gov.cn/x#f"), base) is False

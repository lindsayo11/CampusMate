"""Regression tests for the calibrated MoEPolicyAdapter selectors.

Background: the seeded endpoints pointed at site homepages, which the adapter
turned into a *silent* success (title present, empty body, zero evidence). The
real policy detail pages under /srcsite/ use `div.moe-detail-box` rather than
`article` / `.TRS_Editor` / `main`, so the adapter raised ParseError even though
the page was perfectly parseable. These tests pin both behaviours down.
"""
from pathlib import Path

import pytest

from app.adapters.base import RawArtifact
from app.adapters.education import CONTENT_SELECTORS, MoEPolicyAdapter
from app.parsers import ParseError

FIXTURES = Path(__file__).with_name("fixtures")


def parse_fixture(filename, url="https://www.moe.gov.cn/"):
    content = (FIXTURES / filename).read_bytes()
    return MoEPolicyAdapter().parse(RawArtifact(
        content=content, canonical_url=url, source_item_id="test",
        content_type="text/html"))


def test_srcsite_policy_page_is_parsed_via_moe_detail_box():
    """The real /srcsite/ structure must parse without relying on `article`."""
    parsed = parse_fixture("moe_srcsite_policy.html",
                           "https://www.moe.gov.cn/srcsite/A15/moe_778/s3261/"
                           "202609/t20260923_1451734.html")
    assert len(parsed.records) == 1
    record = parsed.records[0]
    assert "2027年全国硕士研究生" in record["title"]
    assert "教学〔2026〕2号" in record["body"]
    assert "第一条" in record["body"]
    # `div.moe-page-set` is the outermost wrapper and would drag in the
    # header/footer chrome, so the inner detail box must win.
    assert "版权所有" not in record["body"]
    assert len(parsed.evidence) >= 6
    assert all(item["evidence_location"].startswith("dom=") for item in parsed.evidence)


def test_inner_container_wins_over_outer_wrapper():
    """`.moe-page-set` must not shadow the more specific inner containers."""
    assert CONTENT_SELECTORS.index(".moe-detail-box") < CONTENT_SELECTORS.index(".moe-page-set")
    assert CONTENT_SELECTORS.index("#downloadContent") < CONTENT_SELECTORS.index(".moe-page-set")


def test_existing_article_fixture_still_parses():
    """The original fixture relies on `article`; the new order must not break it."""
    parsed = parse_fixture("moe_policy.html")
    assert len(parsed.records) == 1
    assert "全国硕士研究生招生工作管理规定" in parsed.records[0]["title"]
    assert "报名日期和考试日期必须回到正式发布的官方原文核验" in parsed.records[0]["body"]
    assert parsed.evidence


def test_homepage_without_content_container_is_rejected_not_silently_empty():
    """A homepage must fail loudly rather than yield an empty body."""
    html = b"<html><head><title>\xe4\xb8\xad\xe5\x9b\xbd</title></head><body><nav>menu</nav></body></html>"
    with pytest.raises(ParseError):
        MoEPolicyAdapter().parse(RawArtifact(
            content=html, canonical_url="https://www.moe.gov.cn/",
            source_item_id="test", content_type="text/html"))


def test_content_container_without_paragraphs_is_rejected():
    """A container that holds only chrome text must be rejected, not emitted."""
    html = b"<html><body><main><span>nothing</span></main></body></html>"
    with pytest.raises(ParseError):
        MoEPolicyAdapter().parse(RawArtifact(
            content=html, canonical_url="https://www.moe.gov.cn/",
            source_item_id="test", content_type="text/html"))

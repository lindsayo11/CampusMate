"""A collected policy must carry dates, or the student timeline stays empty.

`/v1/data/timeline` only renders items that carry `start_time` or `deadline`, and
`ingest_moe_policy` used to leave both unset. The policy therefore sat in the
database, was visible in the catalog, yet never appeared on the student home page
- which reads as "the data was never imported".

The fix derives two things from the policy text itself:

  * 成文日期 (a standalone "2026年9月21日" paragraph) - the fallback date
  * 报名窗口 ("报名时间为2026年10月15日至10月24日") - what a student actually needs

These tests pin the parsing rules against real page shapes.
"""
from datetime import UTC, datetime

from bs4 import BeautifulSoup

from app.adapters.education import content_container, document_date, registration_window, year_from_url
from app.intake import _parse_date


def paragraphs_from(html):
    soup = BeautifulSoup(html, "html.parser")
    article = content_container(soup)
    return [node for node in article.select("p, li")]


def test_document_date_requires_a_standalone_date_paragraph():
    """A date embedded inside prose must not be mistaken for the 成文日期."""
    body = """
    <div class="moe-detail-box">
      <p>第十九条 考生应在规定时间登录“中国研究生招生信息网”参加报名，报名时间为2026年10月15日至10月24日。</p>
      <p>教 育 部</p>
      <p>2026年9月21日</p>
    </div>
    """
    assert document_date(paragraphs_from(body)) == "2026-09-21"


def test_document_date_is_none_when_only_prose_dates_exist():
    body = """
    <div class="moe-detail-box">
      <p>报名时间为2026年10月15日至10月24日，逾期不再补报。</p>
    </div>
    """
    assert document_date(paragraphs_from(body)) is None


def test_registration_window_handles_a_missing_end_year():
    body = """
    <div class="moe-detail-box">
      <p>报名时间为2026年10月15日至10月24日（预报名时间为2026年10月9日至10月12日）。</p>
    </div>
    """
    assert registration_window(paragraphs_from(body)) == ("2026-10-15", "2026-10-24")


def test_registration_window_accepts_an_explicit_end_year():
    body = """
    <div class="moe-detail-box">
      <p>报名时间为2026年12月28日至2027年1月5日。</p>
    </div>
    """
    assert registration_window(paragraphs_from(body)) == ("2026-12-28", "2027-01-05")


def test_registration_window_is_absent_when_the_policy_has_no_window():
    body = """
    <div class="moe-detail-box">
      <p>第八十九条 本规定自印发之日起施行。</p>
      <p>2026年9月21日</p>
    </div>
    """
    assert registration_window(paragraphs_from(body)) == (None, None)


def test_parse_date_rejects_junk_instead_of_raising():
    assert _parse_date(None) is None
    assert _parse_date("") is None
    assert _parse_date("不是日期") is None
    assert _parse_date("2026-10-24") == datetime(2026, 10, 24, tzinfo=UTC)


# --- 省级考试院的写法：年份整体省略，分隔符和提示词都比教育部宽 ---

def test_bare_registration_window_uses_the_url_year():
    """「报名时间：9月21日-10月21日」——年份只在发布页 URL 里。"""
    body = """
    <div class="moe-detail-box">
      <p>四、报名及缴费时间 1.报名时间：9月21日-10月21日，报名截止时间为10月21日17:00</p>
    </div>
    """
    assert registration_window(paragraphs_from(body), 2026) == ("2026-09-21", "2026-10-21")


def test_bare_registration_window_tolerates_time_and_trailing_stop():
    """「报名时间为9月16日12:00至9月22日17:00止」——带时刻和结尾「止」。"""
    body = """
    <div class="moe-detail-box">
      <p>江苏省报名时间为9月16日12:00至9月22日17:00止，具体安排见学校通知。</p>
    </div>
    """
    assert registration_window(paragraphs_from(body), 2026) == ("2026-09-16", "2026-09-22")


def test_bare_registration_window_needs_a_year_to_be_usable():
    """没有 URL 年份就不猜——宁可不给日期，也不能编一个。"""
    body = """
    <div class="moe-detail-box">
      <p>报名时间为9月21日-10月21日。</p>
    </div>
    """
    assert registration_window(paragraphs_from(body)) == (None, None)


def test_deadline_only_notice_yields_a_deadline_without_a_start():
    body = """
    <div class="moe-detail-box">
      <p>请于规定时间内完成，报名截止时间为10月21日17:00。</p>
    </div>
    """
    assert registration_window(paragraphs_from(body), 2026) == (None, "2026-10-21")


def test_year_from_url():
    assert year_from_url("https://www.jseea.cn/webfile/index/index_zkxx/2026-09-21/123.html") == 2026
    assert year_from_url("https://example.edu/policy") is None
    assert year_from_url(None) is None


def test_title_suffix_is_stripped_for_title_tag_pages():
    """`<title>` 常带站点后缀；`<h1>` 一般不带，所以只对 title 生效。"""
    from app.adapters.education import MoEPolicyAdapter, TITLE_SUFFIX

    assert TITLE_SUFFIX.sub("", "书法艺术水平考级报名通告  - 招考信息").strip() == "书法艺术水平考级报名通告"
    assert TITLE_SUFFIX.sub("", "江苏省2027年硕士研究生报考点设置  - 招考信息").strip() == "江苏省2027年硕士研究生报考点设置"
    # 不含站点后缀的标题不应被改动
    plain = "教育部关于印发《2027年全国硕士研究生招生工作管理规定》的通知"
    assert TITLE_SUFFIX.sub("", plain).strip() == plain
    assert MoEPolicyAdapter is not None

"""Conservative extraction of first-party notices; missing dates stay missing."""
import re
from datetime import datetime
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from ..parsers import ParseError

ARTICLE_SELECTORS = ('article', '.v_news_content', '.wp_articlecontent', '.mce-content-body', '#vsb_content',
                     '#article', '.article-content', '.article_content', '.TRS_Editor',
                     '#downloadContent', '.moe-detail-box', 'main', '.list-right')
DATE = re.compile(r'(20\d{2})\s*[年./-]\s*(\d{1,2})\s*[月./-]\s*(\d{1,2})(?:日)?')


def iso_date(year, month, day, hour=0, minute=0):
    try:
        # Official Chinese notice times are Beijing time, never server-local time.
        return datetime(int(year), int(month), int(day), int(hour), int(minute)).isoformat() + '+08:00'
    except (ValueError, TypeError):
        return None


def published_date(soup):
    for node in soup.select('meta[name], meta[property]'):
        key = (node.get('name') or node.get('property') or '').lower()
        if key in {'article:published_time', 'pubdate', 'publishdate', 'date', 'dc.date', 'citation_date'}:
            match = DATE.search(node.get('content', ''))
            if match:
                return iso_date(*match.groups())
    for node in soup.select('.arti_update, .arti-metas, .article-info, .article_info, .page-info, .date, .news-date, .info, time'):
        match = DATE.search(node.get_text(' ', strip=True))
        if match:
            return iso_date(*match.groups())
    match = re.search(r'(?:发布时间|发布日期|发布于|时间)\s*[:：]\s*' + DATE.pattern,
                      soup.get_text(' ', strip=True))
    if match:
        return iso_date(*match.groups())
    for node in soup.select('p'):
        match = DATE.fullmatch(node.get_text('',strip=True))
        if match:
            return iso_date(*match.groups())
    return None


def article_parts(soup):
    for selector in ARTICLE_SELECTORS:
        node = soup.select_one(selector)
        if node and len(node.get_text(' ', strip=True)) >= 30:
            return node
    raise ParseError('未找到可定位的通知正文，请人工核对页面结构')


def notice_title(soup):
    for selector in ('.zkd-title', 'h1', '.arti_title', '.arti-title', '.article-title', '#art_title', '.news-title', '.detail .tit', 'h2', 'h3', 'title'):
        for node in soup.select(selector):
            value = re.sub(r'\s+', ' ', node.get_text(' ', strip=True)).strip()
            value = re.split(r'发布时间|发布日期|点击数|分享至', value)[0].strip()
            if len(value) >= 12 and re.search(r'推免|免试|硕士|研究生|招生|报名', value):
                # Only remove the final website suffix; a joint programme may
                # contain hyphens and university names inside its real title.
                value = re.sub(r'\s*[-|｜]\s*[^-|｜]{0,60}(?:研究生招生网|研究生院|招生网)$','',value)
                if re.search(r'20\d{2}|办法|章程|通知|简章|要求|细则', value):
                    return value
    raise ParseError('未找到通知标题')


def discover_notices(content, base_url, year=None, limit=30):
    """Find same-host public detail links without fetching them or trusting list titles as facts."""
    soup = BeautifulSoup(content, 'html.parser')
    host = urlsplit(base_url).hostname
    result, seen = [], set()
    for a in soup.select('a[href], [onclick]'):
        title = ' '.join((a.get('title') or a.get_text(' ', strip=True)).split())
        if not re.search(r'推免|免试|硕士.*(?:招生|报考|章程|简章|办法|考试)|研究生.*(?:招生|接收|报名|章程|简章)', title):
            continue
        if re.search(r'名单|成绩查询|登录|公示|拟录取', title):
            continue
        years = re.findall(r'20\d{2}', title)
        if year and years and str(year) not in years:
            continue
        href = a.get('href', '')
        if not href or href.startswith('javascript:'):
            # Parse only a literal URL; never execute website JavaScript.
            match = re.fullmatch(r"\s*(?:window\.)?open\(\s*['\"]([^'\"]+)['\"]\s*(?:,\s*['\"]_blank['\"])?\s*\)\s*;?\s*", a.get('onclick',''))
            if not match:
                continue
            href = match.group(1)
        parts = urlsplit(urljoin(base_url, href))
        if (parts.scheme != 'https' or parts.hostname != host or parts.username or parts.password
                or parts.port not in (None, 443) or not parts.path or len(title) < 12):
            continue
        url = urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ''))
        if url not in seen:
            result.append({'title': title, 'url': url})
            seen.add(url)
        if len(result) >= limit:
            break
    return result


def content_kind(title):
    if re.search(r'顺利举办|成功举办|圆满落幕|圆满结束|齐亮相|新闻通气会|开赛！|DAY\d', title):
        return 'news_report'
    if re.search(r'报名|申请|接收|报考|招收|招聘|征集|选拔|招生简章|招生章程|招生办法|招生的第[一二三四五六七八九十0-9]+号通知', title):
        return 'application_notice'
    return 'reference'


def registration_dates(text, year=None):
    """Extract explicit registration dates. Date-only deadlines use the end of that day."""
    text = re.sub(r'(?<=\d)\s+(?=\d|年|月|日|:|：)', '', text)
    token = r'(?:(20\d{2})年)?\s*(\d{1,2})月\s*(\d{1,2})日'
    clock = r'(?:\s*(上午|中午|下午|晚上)?\s*(\d{1,2})[:：](\d{2}))?'

    def stamp(y, m, d, period, hour, minute, end=False):
        if hour and period in {'下午', '晚上'} and int(hour) < 12:
            hour = int(hour) + 12
        if hour and period == '上午' and int(hour) == 12:
            hour = 0
        return iso_date(y, m, d, hour if hour is not None else (23 if end else 0),
                        minute if minute is not None else (59 if end else 0)) if y else None

    # Restrict each match to registration context, including date-first wording.
    for match in re.finditer(token + clock + r'\s*[-—–至到]\s*' + token + clock, text):
        context = text[max(0, match.start()-45):match.end()+45]
        if not re.search(r'报名|申请|申报', context):
            continue
        y,m,d,period,h,minute,ey,em,ed,eperiod,eh,emin = match.groups()
        y = y or year
        ey = ey or (int(y) + (int(em)<int(m)) if y else None)
        return stamp(y,m,d,period,h,minute), stamp(ey,em,ed,eperiod,eh,emin,True)
    # A repeated month/year can be omitted: 2026年9月1日10:00-8日10:00.
    for match in re.finditer(token + clock + r'\s*[-—–至到]\s*(\d{1,2})日' + clock, text):
        context = text[max(0, match.start()-45):match.end()+45]
        if not re.search(r'报名|申请|申报', context):
            continue
        y,m,d,period,h,minute,ed,eperiod,eh,emin = match.groups()
        if int(ed) < int(d):
            continue  # No guessing the omitted month across a boundary.
        return stamp(y or year,m,d,period,h,minute), stamp(y or year,m,ed,eperiod,eh,emin,True)
    for match in re.finditer(token + clock, text):
        before = text[max(0,match.start()-24):match.start()]
        after = text[match.end():match.end()+26]
        if (re.search(r'(?:报名|申请)(?:截止(?:时间|日期)?|时间截止)\s*[:：为是]?\s*$', before)
                or re.match(r'前.{0,12}(?:完成|提交|进行).{0,8}(?:报名|申请)', after)):
            y,m,d,period,h,minute = match.groups()
            return None, stamp(y or year,m,d,period,h,minute,True)
    return None, None

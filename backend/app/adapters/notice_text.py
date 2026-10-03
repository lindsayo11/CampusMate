"""Conservative extraction of first-party notices; missing dates stay missing."""
import re
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from ..parsers import ParseError

ARTICLE_SELECTORS = ('article', '.v_news_content', '.wp_articlecontent', '.mce-content-body', '#vsb_content',
                     '#article', '.article-content', '.article_content', '.TRS_Editor',
                     '#downloadContent', '.moe-detail-box', '#content', '.news_content',
                     '.news-content', '.content-con', '.detail_content', '.articleDiv',
                     '.pageArticle', '.artcle-detail', '.article', '.articleCon',
                     '.news_con', '.txtcon', '.TRS_UEDITOR', '.ck-content',
                     '#UCAP-CONTENT', '#art_content', '#mainTextZoom', '#Zoom',
                     '.detail_article', '.ls-article-info', '.article-detail',
                     '.sp-content', '.blog-inner-text', '.content-l',
                     '[role="article"]', 'main', '.list-right')
DATE = re.compile(r'(20\d{2})\s*[年./-]\s*(\d{1,2})\s*[月./-]\s*(\d{1,2})(?:日)?')
TOPIC_PATTERNS = {
    'postgraduate': r'推免|免试|夏令营|硕士.*(?:招生|报考|章程|简章|办法|考试|复试|调剂)|研究生.*(?:招生|接收|报名|章程|简章)',
    'examination': r'研究生|硕士|考研|报考点|专升本|自学考试|四六级|英语四|英语六|计算机等级|职业资格',
    'employment': r'招聘|就业|实习|双选|宣讲|见习|西部计划|三支一扶',
    'recruitment': r'招聘|招考|公务员|选调|事业单位|三支一扶|人才引进',
    'overseas': r'留学|奖学金|公派|出国|境外|海外|交换生|交换项目|校际交换|短期访学|国际合作培养|国际交流.*(?:项目|报名)|scholarship|fellowship|study abroad',
    'entrepreneurship': r'创业|创新|挑战杯|竞赛|大赛|申报|征集|孵化',
    'policy': r'就业|创业|毕业生|人才|教育|科技|创新|企业|补贴|税费',
    'funding': r'资助|奖学金|奖助|助学|勤工|困难补助|困难认定|经济困难|补偿代偿|基金|申报|申请|项目指南|funding|scholarship|fellowship|grant|doctoral|studentship',
}


def matches_topic(title, topic='postgraduate'):
    if topic not in TOPIC_PATTERNS:
        raise ParseError('未知的公开通知主题')
    if re.search(r'采购|招标|决算|预算公开|图像采集|毕业证书|重修|重考|平稳顺利|顺利结束|顺利举行|宣讲回放|名单|公示|拟录取', title):
        return False
    if topic == 'postgraduate' and re.search(r'导师.*(?:资格审核|遴选)|指导教师.*(?:遴选|资格)|考点.*圆满完成',title):
        return False
    if topic == 'postgraduate' and ('博士' in title and not re.search(r'推免|免试|硕士|硕博', title)):
        return False
    return bool(re.search(TOPIC_PATTERNS[topic], title, re.I))


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


def article_parts(soup, article_selector=None):
    for selector in ((article_selector,) if article_selector else ARTICLE_SELECTORS):
        node = soup.select_one(selector)
        if node and len(node.get_text(' ', strip=True)) >= 30:
            return node
    raise ParseError('未找到可定位的通知正文，请人工核对页面结构')


def definition_fields(article, timezone=None):
    """Read labelled detail tables; subscription publication dates are not deadlines."""
    pairs, dates = [], {}
    try:
        zone = ZoneInfo(timezone) if timezone else None
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise ParseError('来源日期时区配置无效') from exc
    labels = {'opening date':'open_at','closing date':'deadline_at','publication date':'publish_time'}
    months = {name:i for i,name in enumerate(('January','February','March','April','May','June',
        'July','August','September','October','November','December'),1)}
    for label in article.select('dl dt')[:64]:
        value = label.find_next_sibling('dd')
        if value is None or not value.get_text(' ',strip=True):
            continue
        text = value.get_text(' ',strip=True)
        name = label.get_text(' ',strip=True).rstrip(' :：').lower()
        pair = {'node':value,'quote':label.get_text(' ',strip=True)+' '+text}
        pairs.append(pair)
        field = labels.get(name)
        if not field or not zone:
            continue
        time_node = value.select_one('time[datetime]')
        try:
            if time_node and re.fullmatch(r'20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2})?',time_node['datetime']):
                date = datetime.fromisoformat(time_node['datetime'].replace('Z','+00:00'))
            elif field=='publish_time':
                match = re.fullmatch(r'(\d{1,2}) ([A-Za-z]+) (20\d{2})',text)
                if not match or match[2] not in months:
                    continue
                date = datetime(int(match[3]),months[match[2]],int(match[1]))
            else:
                continue
            # Local clocks in the repeated/missing DST hour cannot determine one instant.
            if date.tzinfo is None:
                first,second=date.replace(tzinfo=zone,fold=0),date.replace(tzinfo=zone,fold=1)
                if first.utcoffset()!=second.utcoffset():
                    continue
                date=first
            dates[field] = {'value':date.isoformat(),**pair}
        except ValueError:
            continue
    return pairs, dates


def notice_title(soup, topic='postgraduate', title_selector=None, title_context=''):
    if isinstance(title_selector,dict):
        limit=title_selector.get('limit',2)
        if not isinstance(limit,int) or not 1<=limit<=3 or not isinstance(title_selector.get('join'),str):
            raise ParseError('分段标题配置无效')
        nodes=soup.select(title_selector['join'])[:limit]
        joined=''.join(node.get_text('',strip=True) for node in nodes)
        if nodes and len(joined)<=200:
            synthetic=BeautifulSoup('<h1></h1>','html.parser');synthetic.h1.string=joined
            try:return notice_title(synthetic,topic,'h1',title_context)
            except ParseError:pass
        return notice_title(soup,topic,None,title_context)
    selectors = ('.zkd-title', 'h1', '.arti_title', '.arti-title', '.article-title', '#art_title', '.news-title', '.articleTitle', '.news_tit', '.detail .tit', 'h2', 'h3', '.title', 'title')
    for selector in ((title_selector,) if title_selector else selectors):
        for node in soup.select(selector):
            value = re.sub(r'\s+', ' ', node.get_text(' ', strip=True)).strip()
            if re.search(r'名单|公示|拟录取',value):
                continue
            value = re.split(r'发布时间|发布日期|点击数|分享至', value)[0].strip()
            relevant = (re.search(r'推免|免试|硕士|研究生|招生|报名|夏令营', value)
                        if topic == 'postgraduate' else matches_topic(value + ' ' + title_context, topic))
            if 8 <= len(value) <= 200 and relevant:
                # Only remove the final website suffix; a joint programme may
                # contain hyphens and university names inside its real title.
                value = re.sub(r'\s*[-|｜]\s*[^-|｜]{0,60}(?:研究生招生网|研究生院|招生网)$','',value)
                if topic != 'postgraduate' or re.search(r'20\d{2}|办法|章程|通知|简章|要求|细则|公告|政策|指南|项目', value):
                    return value
    raise ParseError('未找到通知标题')


def document_base(soup, base_url):
    """Honour a first-party HTML base without expanding the official host boundary."""
    node = soup.select_one('base[href]')
    if node:
        try:
            candidate = urlsplit(urljoin(base_url, node['href'].strip()))
            if (candidate.scheme == 'https' and candidate.hostname == urlsplit(base_url).hostname
                    and not candidate.username and not candidate.password and candidate.port in (None, 443)):
                return urlunsplit((candidate.scheme, candidate.netloc, candidate.path, candidate.query, ''))
        except ValueError:
            pass
    return base_url


def discover_notices(content, base_url, year=None, limit=30, topic='postgraduate'):
    """Find same-host public detail links without fetching them or trusting list titles as facts."""
    soup = BeautifulSoup(content, 'html.parser')
    host = urlsplit(base_url).hostname
    base_url = document_base(soup, base_url)
    result, seen = [], set()
    for a in soup.select('a[href], [onclick]'):
        title = ' '.join((a.get('title') or a.get_text(' ', strip=True)).split())
        if not matches_topic(title, topic):
            continue
        # A site logo or category such as “硕士招生” is not an article.
        if not re.search(r'20\d{2}|通知|公告|办法|章程|简章|规定|政策|指南|须知|细则|要求|安排|计划|项目|报名|申请|scholarship|fellowship', title, re.I):
            continue
        if re.search(r'名单|成绩查询|登录|公示|拟录取|录取通知书|隐私', title):
            continue
        years = re.findall(r'20\d{2}', title)
        if year and years and str(year) not in years:
            continue
        href = a.get('href', '').strip()
        if not href or href.startswith('javascript:'):
            # Parse only a literal URL; never execute website JavaScript.
            match = re.fullmatch(r"\s*(?:(?:window\.)?open|windowOpen)\(\s*['\"]([^'\"]+)['\"]\s*(?:,\s*['\"]_blank['\"])?\s*\)\s*;?\s*", a.get('onclick','').replace('\\"','"'))
            if not match:
                continue
            href = match.group(1).replace('\\/','/')
        try:
            parts = urlsplit(urljoin(base_url, href))
            valid = (parts.scheme == 'https' and parts.hostname == host and not parts.username and not parts.password
                and parts.port in (None, 443) and bool(parts.path) and len(title) >= 8)
        except ValueError:
            valid = False
        if not valid:
            continue
        if re.search(r'/(?:index|main|list|default)\.(?:html?|psp|aspx)$', parts.path, re.I):
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
    if re.search(r'报名|申请|接收|报考|招收|招聘|征集|选拔|招生简章|招生章程|招生办法|招生的第[一二三四五六七八九十0-9]+号通知|^Funding opportunity:', title, re.I):
        return 'application_notice'
    return 'reference'


def registration_dates(text, year=None):
    """Extract explicit registration dates. Date-only deadlines use the end of that day."""
    text = re.sub(r'(?<=\d)\s+(?=年|月|日|:|：)', '', text)
    text = re.sub(r'(20\d{2})[./-](\d{1,2})[./-](\d{1,2})(?!\d)',r'\1年\2月\3日',text)
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
        if (re.search(r'(?:报名|申请|申报|提交)(?:材料)?(?:截止(?:时间|日期)?|时间截止)\s*[:：为是]?\s*$', before)
                or (re.search(r'(?:截至|截止(?:时间|日期)?[：:]?)\s*$',before)
                    and re.search(r'报名|申请|申报|提交材料',text[max(0,match.start()-50):match.end()+35]))
                or re.match(r'(?:之)?前.{0,12}(?:完成|提交|进行).{0,8}(?:报名|申请|申报)', after)):
            y,m,d,period,h,minute = match.groups()
            return None, stamp(y or year,m,d,period,h,minute,True)
    return None, None

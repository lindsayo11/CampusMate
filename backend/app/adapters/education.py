"""Deterministic adapters for public postgraduate policy and admission pages."""
import re
from typing import Any

from bs4 import BeautifulSoup

from ..parsers import MAX_BYTES, ParseError
from .base import ParsedDocument, RawArtifact, SourceAdapter, ValidationResult
from .notice_text import article_parts, notice_title, published_date, registration_dates, document_base, definition_fields

PROGRAM_ALIASES = {
    "institution_code": ("院校代码", "招生单位代码"),
    "institution_name": ("招生单位", "院校名称", "学校名称"),
    "program_code": ("专业代码",),
    "program_name": ("专业名称", "招生专业"),
    "degree_level": ("学位类型", "培养层次"),
    "study_mode": ("学习方式",),
    "cycle_year": ("招生年份", "年份"),
    "open_at": ("报名开始", "申请开始"),
    "deadline_at": ("报名截止", "申请截止", "截止日期"),
    "exam_at": ("初试日期", "考试日期"),
    "application_url": ("申请地址", "报名地址"),
}
NOTICE_ALIASES = {
    "open_at": ("报名开始", "申请开始"),
    "deadline_at": ("报名截止", "申请截止", "截止日期"),
    "exam_at": ("考试日期", "初试日期"),
    "interview_at": ("面试日期", "复试日期"),
    "degree": ("学历要求", "学历"),
    "gpa": ("GPA要求", "平均成绩要求"),
    "ranking": ("排名要求", "专业排名"),
    "language": ("语言要求", "外语要求"),
    "materials": ("申请材料", "材料要求"),
}


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def selector_for(element) -> str:
    if element.get("id"):
        return "#" + element["id"]
    parts = []
    node = element
    while node and getattr(node, "name", None) not in {None, "[document]"} and len(parts) < 5:
        siblings = [item for item in node.parent.find_all(node.name, recursive=False)] if node.parent else []
        index = siblings.index(node) + 1 if len(siblings) > 1 else None
        parts.append(f"{node.name}:nth-of-type({index})" if index else node.name)
        node = node.parent
    return " > ".join(reversed(parts))


def reject_login_page(soup: BeautifulSoup):
    text = soup.get_text(" ", strip=True).lower()
    if soup.select_one('input[type="password"]') or "验证码" in text or "captcha" in text:
        raise ParseError("检测到登录或验证码页面，不得作为后台采集来源")
    if '您没有访问当前栏目的权限' in text:
        raise ParseError('检测到访问权限限制页面，不得作为后台采集来源')


# 正文容器候选，按优先级排列。真实政府站点结构不统一：
# - article / .TRS_Editor / main 是通用约定，见于部分省政府与旧式栏目页
# - .moe-detail-box / #downloadContent / .moe-page-set 是教育部 srcsite/ 政策详情页的真实结构
#   （h1 存在但 article/.TRS_Editor/main 均为 0，只靠通用选择器会整体漏采）
CONTENT_SELECTORS = (
    "article",
    ".TRS_Editor",
    "#downloadContent",
    ".moe-detail-box",
    "main",
    ".moe-page-set",
    # 教育涉外监管信息网（jsj.moe.gov.cn）的详情页正文在 .list-right 里，
    # 上面几个都不命中。放在最后，只有前面全落空时才轮到它。
    ".list-right",
)


def content_container(soup: BeautifulSoup):
    """返回首个命中的正文容器。

    必须按顺序取「含有段落文本」的容器：`.moe-page-set` 是最外层包装，会同时
    包住页眉/页脚导航，因此必须排在 `.moe-detail-box`、`#downloadContent` 之后。
    """
    for selector in CONTENT_SELECTORS:
        node = soup.select_one(selector)
        if node is not None and clean(node.get_text(" ", strip=True)):
            return node
    return None


# 成文日期，形如「2026年9月21日」，在教育部政策页里是独立一段。
DOCUMENT_DATE = re.compile(r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")

# 报名窗口，形如「报名时间为2026年10月15日至10月24日」（结束日期常省略年份）。
# 分隔符与提示词都放宽：实际站点会写「报名时间：9月21日-10月21日」
# 「报名时间为9月16日12:00至9月22日17:00止」，带全角冒号、时刻和结尾「止」。
_WINDOW_TAIL = (r"(?:\s*\d{1,2}\s*[:：]\s*\d{2})?\s*[-–—~～至到]\s*"
                r"(?:(\d{1,2})\s*月\s*(\d{1,2})\s*日)")
REGISTRATION_WINDOW = re.compile(
    r"报名时间\s*[:：是为]?\s*(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"
    r"(?:\s*\d{1,2}\s*[:：]\s*\d{2})?\s*[-–—~～至到]\s*"
    r"(?:(20\d{2})\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*日")

# 年份整体省略的写法，省级考试院常见：「报名时间：9月21日-10月21日」。
# 年份由发布页 URL 补全（见 year_from_url）。
BARE_REGISTRATION_WINDOW = re.compile(
    r"报名时间\s*[:：是为]?\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日" + _WINDOW_TAIL)

# 只写了截止时间的写法：「报名截止时间为10月21日17:00」。
BARE_DEADLINE = re.compile(
    r"报名截止时间\s*[:：是为]?\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")

# <title> 里附带的站点后缀，例如「……问答  - 招考信息」。
TITLE_SUFFIX = re.compile(r"\s*[-–—|｜]\s*[^-–—|｜]{0,12}(招考信息|研究生考试|自学考试|"
                          r"教育考试院|政府门户网站|官方网站)\s*$")


def _iso(year, month, day):
    from datetime import date
    try:
        return date(int(year), int(month), int(day)).isoformat()
    except (ValueError, TypeError):
        return None


def document_date(paragraphs):
    """政策成文日期，返回 ``YYYY-MM-DD`` 字符串；找不到返回 None。

    政策文件没有报名截止日，但有成文日期。学生端时间线只渲染带日期的条目，
    缺了它，采集到的政策永远不会出现在时间线上——数据在库里却"看不见"。
    这里只认「整段就是日期」的段落，避免把正文里的相对表述误当成日期。
    """
    for node in paragraphs:
        match = DOCUMENT_DATE.fullmatch(clean(node.get_text(" ", strip=True)))
        if match:
            return _iso(*match.groups())
    return None


def registration_window(paragraphs, fallback_year=None):
    """从正文找报名起止日期，返回 ``(开始, 截止)`` 两个 ``YYYY-MM-DD``。

    政策本身没有截止日期，但正文常写明报名窗口——这才是学生真正需要的时间节点。
    结束日期缺年份时沿用开始日期的年份。

    省级考试院的通知常写「报名时间为9月21日—10月21日」——**年份整个省略**，
    年份只在发布页 URL（``/2026-09-21/``）里。因此接受 ``fallback_year``，
    由调用方从 ``raw.canonical_url`` 取。
    """
    for node in paragraphs:
        match = REGISTRATION_WINDOW.search(clean(node.get_text(" ", strip=True)))
        if not match:
            continue
        year, month, day, end_year, end_month, end_day = match.groups()
        start = _iso(year, month, day)
        finish = _iso(end_year or year, end_month, end_day)
        if start and finish:
            return start, finish
    if fallback_year:
        for node in paragraphs:
            text = clean(node.get_text(" ", strip=True))
            match = BARE_REGISTRATION_WINDOW.search(text)
            if match:
                start = _iso(fallback_year, match.group(1), match.group(2))
                finish = _iso(fallback_year, match.group(3), match.group(4))
                if start and finish:
                    return start, finish
            # 有些通知只写「报名截止时间为10月21日17:00」，没有起始日。
            only_deadline = BARE_DEADLINE.search(text)
            if only_deadline:
                finish = _iso(fallback_year, only_deadline.group(1), only_deadline.group(2))
                if finish:
                    return None, finish
    return None, None


# 通知内容 → 发展频道路径。
#
# 发展频道的六个入口（保研推免/国内考研/境外留学/考公考编/实习就业/创新创业）
# 各自按自己的 path code 过滤，而 `data_catalog.path_codes()` 只从该 code **向下**
# 找子孙路径。因此条目必须挂在**叶子路径**上：只挂父路径 `domestic_study` 会让
# 六个频道全部为空，数据在库里却一个频道都点不开。
#
# 顺序敏感：先匹配更具体的（推免/考研/留学），再落到宽泛的（就业/证书）。
PATH_KEYWORDS = (
    ("recommendation_exemption", ("推免", "保研", "推荐免试", "免试", "推免生", "直博")),
    ("domestic_postgraduate_exam", ("硕士", "研究生", "考研", "初试", "复试", "调剂", "报考点")),
    ("overseas_study", ("留学", "境外", "出国", "雅思", "托福", "GRE", "留服")),
    ("national_civil_service", ("公务员", "选调", "国考", "省考", "事业单位", "编制")),
    ("entrepreneurship", ("创业", "众创", "孵化", "创新大赛", "挑战杯")),
    ("employment", ("招聘", "就业", "实习", "四、六级", "四六级", "计算机等级",
                    "英语等级", "职业资格", "证书", "专升本", "自学考试")),
)


def classify_path(title, body=""):
    """把一条通知映射到发展频道路径 code；匹配不到返回 None（只进信息中心）。

    **只看标题，不看正文。** 实测用全文匹配会大量假阳性：《2027年全国硕士研究生
    招生工作管理规定》正文提到"推免"，就被误判成保研推免；《成人高考专升本
    特别提醒》正文提到"留学"（学历认证场景），被误判成境外留学。标题是这条通知
    的主题，正文里的顺带提及不是。

    宁可不挂路径，也不硬塞：挂错频道比不挂更容易误导用户。
    """
    text = title or ""
    for code, keywords in PATH_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return code
    return None


def year_from_url(url):
    """从形如 ``/2026-09-21/`` 的路径里取年份，供无年份日期补全。"""
    match = re.search(r"/(20\d{2})-\d{2}-\d{2}/", url or "")
    return int(match.group(1)) if match else None


class MoEPolicyAdapter(SourceAdapter):
    source_code = "CM-GR-001"

    def parse(self, raw: RawArtifact) -> ParsedDocument:
        if not raw.content or len(raw.content) > MAX_BYTES:
            raise ParseError("HTML 文件为空或超过限制")
        soup = BeautifulSoup(raw.content, "html.parser")
        reject_login_page(soup)
        title_node = soup.select_one("h1") or soup.select_one("title")
        article = content_container(soup)
        if not title_node or article is None:
            raise ParseError("未找到政策标题或正文")
        title = clean(title_node.get_text(" ", strip=True))
        # <title> 常带站点后缀（「……问答  - 招考信息」），h1 一般不带。
        if title_node.name != "h1":
            title = TITLE_SUFFIX.sub("", title).strip() or title
        paragraphs = [node for node in article.select("p, li") if clean(node.get_text(" ", strip=True))]
        if not paragraphs:
            raise ParseError("正文容器内没有可定位的段落文本")
        evidence = [{"record_key": "policy", "field": "body",
                     "evidence_location": "dom=" + selector_for(node),
                     "quote_or_normalized_fact": clean(node.get_text(" ", strip=True)), "extractor": "parser"}
                    for node in paragraphs]
        record = {"title": title, "body": "\n".join(
            item["quote_or_normalized_fact"] for item in evidence)}
        issued = document_date(paragraphs)
        if issued:
            # 成文日期：政策生效参考，也是学生端时间线渲染该条目的兜底依据。
            record["issued_at"] = issued
        start, finish = registration_window(paragraphs, year_from_url(raw.canonical_url))
        if start and finish:
            # 报名窗口比成文日期对学生有用得多，优先作为时间节点。
            record["registration_start"], record["registration_deadline"] = start, finish
        return ParsedDocument(records=[record], evidence=evidence,
                              metadata={"canonical_url": raw.canonical_url, "publish_time": published_date(soup)})

    def normalize(self, parsed: ParsedDocument):
        return parsed.records

    def extract_rules(self, parsed: ParsedDocument):
        return []

    def validate(self, record) -> ValidationResult:
        return ValidationResult(valid=bool(record.get("title") and record.get("body")))


class YZChsiAdapter(SourceAdapter):
    source_code = "CM-GR-002"

    def parse(self, raw: RawArtifact) -> ParsedDocument:
        if not raw.content or len(raw.content) > MAX_BYTES:
            raise ParseError("HTML 文件为空或超过限制")
        soup = BeautifulSoup(raw.content, "html.parser")
        reject_login_page(soup)
        records, evidence = [], []
        for table_index, table in enumerate(soup.select("table"), start=1):
            rows = table.select("tr")
            if not rows:
                continue
            headers = [clean(cell.get_text(" ", strip=True)) for cell in rows[0].select("th, td")]
            columns = {}
            for field, aliases in PROGRAM_ALIASES.items():
                for index, header in enumerate(headers):
                    if header in aliases:
                        columns[field] = index
                        break
            required = {"institution_code", "institution_name", "program_code", "program_name", "cycle_year"}
            if not required.issubset(columns):
                continue
            for row_index, row in enumerate(rows[1:], start=2):
                cells = row.select("th, td")
                evidence_start = len(evidence)
                provisional_key = f"table-{table_index}-row-{row_index}"
                values = {}
                for field, column in columns.items():
                    if column >= len(cells):
                        continue
                    cell = cells[column]
                    link = cell.select_one("a[href]")
                    values[field] = clean(link.get("href") if field == "application_url" and link else
                                          cell.get_text(" ", strip=True))
                    if values[field]:
                        evidence.append({"record_key": provisional_key,
                                         "field": field,
                                         "evidence_location": f"dom=table:nth-of-type({table_index}) tr:nth-of-type({row_index}) {cells[column].name}:nth-of-type({column + 1})",
                                         "quote_or_normalized_fact": f"{field}={values[field]}", "extractor": "parser"})
                if required.issubset(values) and all(values[key] for key in required):
                    key = f"{values['institution_code']}:{values['program_code']}:{row_index}"
                    for item in evidence[evidence_start:]:
                        item["record_key"] = key
                    records.append({**values, "_record_key": key})
        if not records:
            raise ParseError("未找到公开专业目录表；登录页和个人业务页不会被解析")
        return ParsedDocument(records=records, evidence=evidence,
                              metadata={"canonical_url": raw.canonical_url})

    def normalize(self, parsed: ParsedDocument):
        return [{key: value for key, value in row.items() if not key.startswith("_")} for row in parsed.records]

    def extract_rules(self, parsed: ParsedDocument):
        rules = []
        for row in parsed.records:
            for field in ("open_at", "deadline_at", "exam_at"):
                if row.get(field):
                    rules.append({"record_key": row["_record_key"], "field": field,
                                  "operator": "equals", "expected": row[field], "extractor": "parser",
                                  "confidence": 1.0, "review_status": "pending"})
        return rules

    def validate(self, record) -> ValidationResult:
        missing = [field for field in ("institution_code", "institution_name", "program_code",
                                       "program_name", "cycle_year") if not record.get(field)]
        return ValidationResult(valid=not missing, errors=["缺少字段：" + ",".join(missing)] if missing else [])


class UniversityNoticeAdapter(SourceAdapter):
    def __init__(self, topic='postgraduate', article_selector=None, title_selector=None, title_context='', date_timezone=None):
        self.topic = topic
        self.title_context = title_context
        self.date_timezone = date_timezone
        self.article_selector, self.title_selector = article_selector, title_selector
    source_code = "CM-GR-004"

    def parse(self, raw: RawArtifact) -> ParsedDocument:
        if not raw.content or len(raw.content) > MAX_BYTES:
            raise ParseError("HTML 文件为空或超过限制")
        if raw.content.startswith(b'%PDF'):
            return self.parse_pdf(raw)
        if raw.content.startswith((b'\x89PNG\r\n\x1a\n',b'\xff\xd8\xff')) or raw.content[:4]==b'RIFF' and raw.content[8:12]==b'WEBP':
            return self.parse_pdf(raw,format='image')
        soup = BeautifulSoup(raw.content, "html.parser")
        reject_login_page(soup)
        values, evidence = {"title": notice_title(soup, self.topic, self.title_selector, self.title_context)}, []
        if isinstance(self.title_selector,dict):
            nodes=soup.select(self.title_selector['join'])[:self.title_selector.get('limit',2)]
            if clean(''.join(node.get_text('',strip=True) for node in nodes))==values['title']:
                evidence.extend({'record_key':'notice','field':'title','evidence_location':'dom='+selector_for(node),
                    'quote_or_normalized_fact':node.get_text('',strip=True),'extractor':'parser'} for node in nodes)
        for row_index, row in enumerate(soup.select("table tr"), start=1):
            cells = row.select("th, td")
            if len(cells) < 2:
                continue
            label, value = clean(cells[0].get_text(" ", strip=True)).rstrip("：:"), clean(
                cells[1].get_text(" ", strip=True))
            for field, aliases in NOTICE_ALIASES.items():
                if label in aliases and value:
                    values[field] = value
                    evidence.append({"record_key": "notice", "field": field,
                                     "evidence_location": f"dom=table tr:nth-of-type({row_index}) td:nth-of-type(2)",
                                     "quote_or_normalized_fact": f"{label}={value}", "extractor": "parser"})
                    break
        article = article_parts(soup, self.article_selector)
        paragraph_nodes = article.select('p, li')
        values["body"] = '\n'.join(node.get_text('',strip=True) for node in paragraph_nodes) if paragraph_nodes else article.get_text('\n',strip=True)
        publish_time = published_date(soup)
        pairs, dates = definition_fields(article,self.date_timezone)
        if 'publish_time' in dates:
            publish_time = dates['publish_time']['value']
        year = int(publish_time[:4]) if publish_time else year_from_url(raw.canonical_url)
        # Read paragraphs when a real notice has no key/value table. Never invent
        # numeric eligibility thresholds or dates from a target admission year.
        if not any(proof.get('field')!='title' for proof in evidence):
            paragraphs = article.select('p, li') or [article]
            for node in paragraphs:
                quote = clean(node.get_text(' ', strip=True))
                if not quote:
                    continue
                evidence.append({'record_key':'notice', 'field':'body',
                    'evidence_location':'dom='+selector_for(node),
                    'quote_or_normalized_fact':quote, 'extractor':'parser'})
            start, finish = registration_dates(clean(values['body']), year)
            for field, value in (('open_at',start),('deadline_at',finish)):
                if value:
                    values[field] = value
                    evidence.append({'record_key':'notice','field':field,
                        'evidence_location':'dom='+selector_for(article),
                        'quote_or_normalized_fact':clean(values['body']), 'extractor':'parser'})
        # A key/value table must not suppress explicit registration dates elsewhere.
        start, finish = registration_dates(clean(values['body']),year)
        for field,value in (('open_at',start),('deadline_at',finish)):
            if value and not values.get(field):
                values[field]=value
                evidence.append({'record_key':'notice','field':field,'evidence_location':'dom='+selector_for(article),
                    'quote_or_normalized_fact':clean(values['body']),'extractor':'parser'})
        values['material_quotes'] = []
        collecting = False
        for line in values['body'].splitlines():
            if re.search(r'申请材料|提交材料|报名材料', line):
                collecting = True
            elif collecting and re.match(r'^[一二三四五六七八九十]+[、.．]', line):
                collecting = False
            if collecting and 6 < len(line) < 1000 and len(values['material_quotes']) < 16:
                values['material_quotes'].append(line)
        values['attachments'] = []
        from urllib.parse import urljoin, urlsplit
        link_base = document_base(soup, raw.canonical_url)
        for link in article.select('a[href]'):
            url = urljoin(link_base, link['href'].strip())
            if re.search(r'\.(?:pdf|docx?|xlsx?)(?:\?|$)', url, re.I) and urlsplit(url).scheme in {'https','http'}:
                values['attachments'].append({'title':clean(link.get_text(' ',strip=True)) or '原文附件','url':url})
        if not evidence or len(values['body']) < 30:
            raise ParseError('通知正文不足，需人工核对')
        if pairs:
            values['body'] = '\n'.join(p['quote'] for p in pairs) + '\n' + values['body']
            evidence.extend({'record_key':'notice','field':'body','evidence_location':'dom='+selector_for(p['node']),
                'quote_or_normalized_fact':p['quote'],'extractor':'parser'} for p in pairs)
        for field, fact in dates.items():
            if field in {'open_at','deadline_at'}:
                values[field]=fact['value']
                evidence.append({'record_key':'notice','field':field,'evidence_location':'dom='+selector_for(fact['node']),
                    'quote_or_normalized_fact':fact['quote'],'extractor':'parser'})
        return ParsedDocument(records=[values], evidence=evidence,
                              metadata={"canonical_url": raw.canonical_url, "publish_time": publish_time})

    def parse_pdf(self, raw, format='pdf'):
        from ..parsers import extract_isolated
        from .notice_text import DATE, iso_date
        extraction = extract_isolated(raw.content, format)
        text = extraction.text
        pages = re.split(r'\[第 (\d+) 页\]\n', text)
        first = pages[2] if len(pages) > 2 else text
        lines = [line.strip() for line in first.splitlines() if line.strip() and not re.fullmatch(r'\d+(?:\s*/\s*\d+)?',line.strip())]
        title_lines = []
        for line in lines[:6]:
            title_lines.append(line)
            if re.search(r'办法|章程|通知|简章|细则|公告|notice|announcement|guidelines', line,re.I):
                break
        title = clean(''.join(title_lines))
        from .notice_text import matches_topic
        for index,line in enumerate(lines[:16]):
            if re.match(r'^(?:关于|20\d{2}|第[一二三四五六七八九十0-9]+届)',line):
                for length in range(1,4):
                    candidate=clean(''.join(lines[index:index+length]))
                    if len(candidate)<=200 and matches_topic(candidate,self.topic) and re.search(r'通知|公告|办法|章程|简章|细则|指南|notice|announcement|guidelines',candidate,re.I):
                        title=candidate;break
                else:continue
                break
        if not 8<=len(title)<=200 or not matches_topic(title, self.topic):
            raise ParseError('PDF 首页未找到明确的主题标题')
        evidence = [{'record_key':'notice','field':'body','evidence_location':f'page={pages[i]}',
                     'quote_or_normalized_fact':pages[i+1].strip(), 'extractor':'parser',
                     'evidence_type':'pdf'} for i in range(1,len(pages),2)]
        ocr_pages={p['page'] for p in extraction.evidence}
        for proof in evidence:
            if int(proof['evidence_location'].split('=')[1]) in ocr_pages:
                proof.update(extractor='ocr',evidence_type='ocr')
        evidence.extend({'record_key':'notice','field':'body',
            'evidence_location':f"page={p['page']};line={p['line']};box={','.join(map(str,p['box']))};confidence={p['confidence']}",
            'quote_or_normalized_fact':p['text'],'extractor':'ocr','evidence_type':'ocr'} for p in extraction.evidence)
        # A dated filename is a useful year anchor, never a claimed publication date.
        url_year = re.search(r'(20\d{2})\d{4}', raw.canonical_url)
        year = int(url_year.group(1)) if url_year else None
        publish_time = None
        for line in text.splitlines():
            date = DATE.fullmatch(line.strip())
            if date:
                publish_time = iso_date(*date.groups())
        if ocr_pages:publish_time=None
        if publish_time:
            year = int(publish_time[:4])
        # OCR dates remain uncertain until a person checks the image; never infer a window.
        start, finish = (None,None) if ocr_pages else registration_dates(clean(text), year)
        values = {'title':title,'body':text,'attachments':[],'material_quotes':[]}
        if ocr_pages:values['body']='[OCR 自动识别，需对照官方原图核对]\n'+text
        for field,value in (('open_at',start),('deadline_at',finish)):
            if value:
                values[field] = value
                for proof in evidence:
                    if re.search(r'报名|申请|申报', proof['quote_or_normalized_fact']):
                        evidence.append({**proof, 'field':field})
                        break
        return ParsedDocument(records=[values], evidence=evidence,
                              metadata={'canonical_url':raw.canonical_url,'publish_time':publish_time})

    def normalize(self, parsed: ParsedDocument):
        return parsed.records

    def extract_rules(self, parsed: ParsedDocument):
        values = parsed.records[0]
        return [{"record_key": "notice", "field": field, "operator": "text_match",
                 "expected": values[field], "extractor": "parser", "confidence": 1.0,
                 "review_status": "pending"}
                for field in ("degree", "gpa", "ranking", "language") if values.get(field)]

    def validate(self, record) -> ValidationResult:
        return ValidationResult(valid=bool(record.get("title")))


class PublicNoticeAdapter(UniversityNoticeAdapter):
    """Public text and dates across topics, without deriving eligibility rules."""
    def __init__(self, topic='employment', article_selector=None, title_selector=None, title_context='', date_timezone=None):
        super().__init__(topic, article_selector, title_selector, title_context, date_timezone)

    def extract_rules(self, parsed: ParsedDocument):
        return []

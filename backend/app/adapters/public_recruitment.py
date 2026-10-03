"""Deterministic adapters for public-institution notices and public job tables."""
import re
from typing import Any
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from ..parsers import MAX_BYTES, ParseError
from .base import ParsedDocument, RawArtifact, SourceAdapter, ValidationResult

POSITION_ALIASES = {
    "position_code": ("岗位代码", "职位代码", "岗位编号", "职位编号"),
    "department": ("主管部门", "部门名称", "部门"),
    "organization": ("招聘单位", "用人单位", "单位名称", "机构名称"),
    "title": ("岗位名称", "职位名称", "招聘岗位"),
    "headcount": ("招聘人数", "招录人数", "计划人数"),
    "education": ("学历要求", "学历"),
    "degree": ("学位要求", "学位"),
    "majors": ("专业要求", "专业"),
    "age": ("年龄要求", "年龄"),
    "qualification": ("资格条件", "其他资格", "资格要求"),
    "political_status": ("政治面貌",),
    "fresh_graduate": ("应届生要求", "应届要求"),
    "work_region": ("工作地点", "工作地区", "地区"),
    "exam_subjects": ("考试科目", "笔试科目"),
    "remarks": ("备注", "说明", "其他条件"),
}
NOTICE_ALIASES = {
    "open_at": ("报名开始", "报名开始时间"),
    "deadline_at": ("报名截止", "报名截止时间", "截止时间"),
    "exam_at": ("笔试时间", "考试时间"),
    "interview_at": ("面试时间",),
}
REQUIRED = {"position_code", "organization", "title"}
RULE_FIELDS = ("education", "degree", "majors", "age", "qualification", "political_status",
               "fresh_graduate", "exam_subjects")


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def reject_login_page(soup: BeautifulSoup):
    text = soup.get_text(" ", strip=True).lower()
    if soup.select_one('input[type="password"]') or "验证码" in text or "captcha" in text:
        raise ParseError("检测到登录或验证码页面，不得作为后台采集来源")


class InstitutionRecruitmentAdapter(SourceAdapter):
    source_code = "CM-PI-001"

    def parse(self, raw: RawArtifact) -> ParsedDocument:
        if not raw.content or len(raw.content) > MAX_BYTES:
            raise ParseError("HTML 文件为空或超过限制")
        soup = BeautifulSoup(raw.content, "html.parser")
        reject_login_page(soup)
        title_node = soup.select_one("h1") or soup.select_one("title")
        if not title_node:
            raise ParseError("未找到招聘公告标题")
        notice = {"title": clean(title_node.get_text(" ", strip=True))}
        records, evidence = [], []
        for table_index, table in enumerate(soup.select("table"), start=1):
            rows = table.select("tr")
            if not rows:
                continue
            headers = [clean(cell.get_text(" ", strip=True)) for cell in rows[0].select("th, td")]
            columns = {}
            for field, aliases in POSITION_ALIASES.items():
                for index, header in enumerate(headers):
                    if header in aliases:
                        columns[field] = index
                        break
            if REQUIRED.issubset(columns):
                self._parse_positions(table_index, rows, columns, records, evidence)
                continue
            for row_index, row in enumerate(rows, start=1):
                cells = row.select("th, td")
                if len(cells) < 2:
                    continue
                label = clean(cells[0].get_text(" ", strip=True)).rstrip("：:")
                value = clean(cells[1].get_text(" ", strip=True))
                for field, aliases in NOTICE_ALIASES.items():
                    if label in aliases and value:
                        notice[field] = value
                        evidence.append({"record_key": "notice", "field": field,
                                         "evidence_location": f"dom=table:nth-of-type({table_index}) tr:nth-of-type({row_index})",
                                         "quote_or_normalized_fact": f"{label}={value}", "extractor": "parser"})
                        break
        if not records:
            raise ParseError("未找到含岗位代码、招聘单位和岗位名称的公开岗位表")
        attachments = []
        for link in soup.select('a[href]'):
            label = clean(link.get_text(" ", strip=True))
            href = clean(link.get("href"))
            if href and (re.search(r"\.(xlsx?|pdf|docx?)(?:$|\?)", href, re.IGNORECASE) or "附件" in label):
                attachments.append({"label": label or href.rsplit("/", 1)[-1],
                                    "url": urljoin(raw.canonical_url, href)})
        notice["attachments"] = attachments
        return ParsedDocument(records=[{"_kind": "notice", **notice}, *records], evidence=evidence,
                              metadata={"canonical_url": raw.canonical_url})

    def _parse_positions(self, table_index, rows, columns, records, evidence):
        for row_index, row in enumerate(rows[1:], start=2):
            cells = row.select("th, td")
            values = {}
            evidence_start = len(evidence)
            provisional = f"table-{table_index}-row-{row_index}"
            for field, column in columns.items():
                if column >= len(cells):
                    continue
                value = clean(cells[column].get_text(" ", strip=True))
                if field == "headcount" and value:
                    try:
                        value = int(value)
                    except ValueError as exc:
                        raise ParseError(f"岗位表第 {row_index} 行招聘人数不是整数") from exc
                values[field] = value
                if value not in ("", None):
                    evidence.append({"record_key": provisional, "field": field,
                                     "evidence_location": f"dom=table:nth-of-type({table_index}) tr:nth-of-type({row_index}) {cells[column].name}:nth-of-type({column + 1})",
                                     "quote_or_normalized_fact": f"{field}={value}", "extractor": "parser"})
            check = self.validate(values)
            if not any(values.values()):
                del evidence[evidence_start:]
                continue
            if not check.valid:
                raise ParseError("；".join(check.errors))
            key = values["position_code"]
            for item in evidence[evidence_start:]:
                item["record_key"] = key
            records.append({"_kind": "position", "_record_key": key, **values})

    def normalize(self, parsed: ParsedDocument):
        return [{key: value for key, value in row.items() if not key.startswith("_")}
                for row in parsed.records]

    def extract_rules(self, parsed: ParsedDocument):
        rules = []
        evidence = {(item["record_key"], item["field"]): item for item in parsed.evidence}
        for row in parsed.records:
            if row.get("_kind") != "position":
                continue
            for field in RULE_FIELDS:
                value = row.get(field)
                if value:
                    rules.append({"record_key": row["_record_key"], "field": field,
                                  "operator": "text_match", "expected": str(value),
                                  "description": f"{field}: {value}", "confidence": 1.0,
                                  "review_status": "pending", "extractor": "parser",
                                  "evidence": evidence[(row["_record_key"], field)]})
            if row.get("remarks"):
                rules.append({"record_key": row["_record_key"], "field": "remarks",
                              "operator": "candidate", "expected": row["remarks"],
                              "description": "备注中的复杂条件待人工确认", "confidence": 0.0,
                              "review_status": "pending", "extractor": "agent_candidate",
                              "evidence": evidence[(row["_record_key"], "remarks")]})
        return rules

    def validate(self, record) -> ValidationResult:
        missing = [field for field in REQUIRED if not record.get(field)]
        return ValidationResult(valid=not missing,
                                errors=["岗位记录缺少字段：" + ",".join(sorted(missing))] if missing else [])


class MohrssPublicJobAdapter(InstitutionRecruitmentAdapter):
    source_code = "CM-JOB-002"


class RegionalRecruitmentDirectoryAdapter(SourceAdapter):
    source_code = "CM-PI-001"

    def parse(self, raw: RawArtifact) -> ParsedDocument:
        if not raw.content or len(raw.content) > MAX_BYTES:
            raise ParseError("HTML 文件为空或超过限制")
        soup = BeautifulSoup(raw.content, "html.parser")
        reject_login_page(soup)
        records, evidence = [], []
        container = soup.select_one("[data-regional-directory], .regional-platforms")
        if not container:
            raise ParseError("未找到地方事业单位招聘平台目录")
        for index, link in enumerate(container.select('a[href]'), start=1):
            parent = link.parent
            region_code = clean(link.get("data-region-code") or
                                (parent.get("data-region-code") if parent else ""))
            name, href = clean(link.get_text(" ", strip=True)), clean(link.get("href"))
            if not region_code or not re.fullmatch(r"[0-9]{6}", region_code) or not name or not href:
                continue
            url = urljoin(raw.canonical_url, href)
            parts = urlsplit(url)
            if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
                    or parts.port not in (None, 443) or parts.fragment):
                continue
            key = f"{region_code}:{url}"
            records.append({"region_code": region_code, "name": name, "base_url": url,
                            "source_code": f"CM-PI-002-{region_code[:2]}"})
            evidence.append({"record_key": key, "field": "base_url",
                             "evidence_location": f"dom=[data-regional-directory] a:nth-of-type({index})",
                             "quote_or_normalized_fact": f"{region_code}|{name}|{url}", "extractor": "parser"})
        if not records:
            raise ParseError("地方平台目录没有带有效行政区划代码的公开链接")
        return ParsedDocument(records=records, evidence=evidence,
                              metadata={"canonical_url": raw.canonical_url})

    def normalize(self, parsed: ParsedDocument):
        return parsed.records

    def extract_rules(self, parsed: ParsedDocument):
        return []

    def validate(self, record) -> ValidationResult:
        return ValidationResult(valid=bool(record.get("region_code") and record.get("base_url")))

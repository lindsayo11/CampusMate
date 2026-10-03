"""Deterministic M5 adapters with a hard registry/application-layer boundary."""
import re
from typing import Any

from bs4 import BeautifulSoup

from ..parsers import MAX_BYTES, ParseError
from .base import ParsedDocument, RawArtifact, SourceAdapter, ValidationResult
from .education import clean, reject_login_page, selector_for

REGISTRY_HEADERS = {
    "institution_name": ("institution", "institution name", "院校名称", "学校名称"),
    "institution_official_id": ("registry id", "provider id", "official id", "注册编号"),
    "country_code": ("country code", "国家代码"),
    "country_name": ("country", "国家"),
    "region_name": ("region", "地区"),
    "public_status": ("status", "registry status", "公共状态", "注册状态"),
    "website_url": ("website", "official website", "学校官网"),
    "program_name": ("program", "course", "项目名称"),
    "program_code": ("program id", "course id", "项目编号"),
    "degree_level": ("degree", "level", "学位层次"),
}

APPLICATION_LABELS = {
    "cycle_year": ("entry year", "cycle year", "入学年度", "申请年度"),
    "deadline_at": ("application deadline", "deadline", "申请截止"),
    "open_at": ("applications open", "open date", "申请开放"),
    "degree": ("degree requirement", "degree-level qualifications", "学历要求"),
    "gpa": ("minimum gpa", "gpa", "gpa要求"),
    "language": ("english language", "language requirement", "语言要求"),
    "gre_gmat": ("gre/gmat", "gre or gmat", "gre/gmat要求"),
    "materials": ("supporting documents", "materials", "申请材料"),
    "application_fee": ("application fee", "申请费"),
}

FORBIDDEN_REGISTRY_FIELDS = {"deadline_at", "open_at", "degree", "gpa", "language",
                             "materials", "application_fee", "gre_gmat"}


def _normalized(value: Any) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", clean(value).lower()).strip()


def _column_map(headers, aliases):
    result = {}
    for field, candidates in aliases.items():
        normalized = {_normalized(item) for item in candidates}
        for index, header in enumerate(headers):
            if _normalized(header) in normalized:
                result[field] = index
                break
    return result


class OverseasRegistryAdapter(SourceAdapter):
    """Imports entity identity/public status only; never application requirements."""
    source_code = "CM-OS-REGISTRY"

    def parse(self, raw: RawArtifact) -> ParsedDocument:
        if not raw.content or len(raw.content) > MAX_BYTES:
            raise ParseError("Registry HTML 为空或超过限制")
        soup = BeautifulSoup(raw.content, "html.parser")
        reject_login_page(soup)
        records, evidence = [], []
        for table_index, table in enumerate(soup.select("table"), start=1):
            rows = table.select("tr")
            if len(rows) < 2:
                continue
            headers = [clean(cell.get_text(" ", strip=True)) for cell in rows[0].select("th,td")]
            application_columns = _column_map(headers, APPLICATION_LABELS)
            if application_columns:
                raise ParseError("Registry 端点不得提供或推导年度申请要求")
            columns = _column_map(headers, REGISTRY_HEADERS)
            if not {"institution_name", "country_code", "public_status"}.issubset(columns):
                continue
            for row_index, row in enumerate(rows[1:], start=2):
                cells, values = row.select("th,td"), {}
                key = f"registry-{table_index}-{row_index}"
                for field, column in columns.items():
                    if column >= len(cells):
                        continue
                    cell = cells[column]
                    link = cell.select_one("a[href]")
                    value = link.get("href") if field == "website_url" and link else cell.get_text(" ", strip=True)
                    value = clean(value)
                    if value:
                        values[field] = value
                        evidence.append({"record_key": key, "field": field,
                            "evidence_location": f"dom=table:nth-of-type({table_index}) tr:nth-of-type({row_index}) {cell.name}:nth-of-type({column + 1})",
                            "quote_or_normalized_fact": f"{field}={value}", "extractor": "parser",
                            "evidence_type": "table"})
                if values.get("institution_name") and values.get("country_code"):
                    records.append({**values, "_record_key": key})
        if not records:
            raise ParseError("未找到匿名可访问的官方 Registry 实体表")
        return ParsedDocument(records=records, evidence=evidence,
                              metadata={"scope": "entity_public_status_only"})

    def normalize(self, parsed: ParsedDocument):
        return [{key: value for key, value in row.items() if not key.startswith("_")}
                for row in parsed.records]

    def extract_rules(self, parsed: ParsedDocument):
        return []

    def validate(self, record) -> ValidationResult:
        forbidden = FORBIDDEN_REGISTRY_FIELDS.intersection(record)
        return ValidationResult(valid=not forbidden,
                                errors=["Registry 记录包含申请要求：" + ",".join(sorted(forbidden))]
                                if forbidden else [])


class OverseasUniversityProgramAdapter(SourceAdapter):
    """Parses one first-party program page into an annual application record."""
    source_code = "CM-OS-UNIVERSITY"

    def parse(self, raw: RawArtifact) -> ParsedDocument:
        if not raw.content or len(raw.content) > MAX_BYTES:
            raise ParseError("大学项目页面为空或超过限制")
        soup = BeautifulSoup(raw.content, "html.parser")
        reject_login_page(soup)
        title = soup.select_one("h1")
        if not title:
            raise ParseError("未找到大学第一方项目标题")
        values = {"title": clean(title.get_text(" ", strip=True))}
        evidence = []
        for row in soup.select("table tr"):
            cells = row.select("th,td")
            if len(cells) < 2:
                continue
            label, value = clean(cells[0].get_text(" ", strip=True)), clean(cells[1].get_text(" ", strip=True))
            normalized = _normalized(label)
            for field, aliases in APPLICATION_LABELS.items():
                if normalized in {_normalized(alias) for alias in aliases} and value:
                    values[field] = value
                    evidence.append({"record_key": "application", "field": field,
                        "evidence_location": "dom=" + selector_for(cells[1]),
                        "quote_or_normalized_fact": f"{label}={value}", "extractor": "parser",
                        "evidence_type": "table"})
                    break
        required = {"cycle_year", "deadline_at", "degree", "language", "materials"}
        if not required.issubset(values):
            raise ParseError("大学第一方页面缺少可确定性定位的年度、截止、学历、语言或材料字段")
        return ParsedDocument(records=[values], evidence=evidence,
                              metadata={"scope": "university_first_party_application"})

    def normalize(self, parsed: ParsedDocument):
        return parsed.records

    def extract_rules(self, parsed: ParsedDocument):
        values = parsed.records[0]
        return [{"record_key": "application", "field": field, "operator": "text_match",
                 "expected": values[field], "description": f"{field}: {values[field]}",
                 "extractor": "parser", "confidence": 1.0, "review_status": "pending"}
                for field in ("deadline_at", "degree", "gpa", "language", "gre_gmat",
                              "materials", "application_fee") if values.get(field)]

    def validate(self, record) -> ValidationResult:
        missing = [field for field in ("cycle_year", "deadline_at", "degree", "language", "materials")
                   if not record.get(field)]
        return ValidationResult(valid=not missing,
                                errors=["缺少字段：" + ",".join(missing)] if missing else [])

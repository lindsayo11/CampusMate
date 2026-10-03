"""Deterministic M6 adapters for public policy facts and governed open-data metadata."""
import re

from bs4 import BeautifulSoup

from ..parsers import MAX_BYTES, ParseError
from .base import ParsedDocument, RawArtifact, SourceAdapter, ValidationResult
from .education import clean, reject_login_page, selector_for

META_LABELS = {
    "policy_code": {"文号", "政策文号", "policy code"},
    "publisher": {"发布机关", "发布单位", "publisher"},
    "published_at": {"发布日期", "published"},
    "effective_at": {"施行日期", "生效日期", "effective"},
    "expires_at": {"失效日期", "有效期至", "expires"},
    "application_url": {"办理入口", "申请入口", "application url"},
}
RULE_FIELDS = {"毕业年限": "graduation_years", "户籍": "domicile", "创业地点": "startup_region",
               "贷款额度": "loan_amount", "贷款期限": "loan_duration", "补贴比例": "subsidy_ratio",
               "申请材料": "materials", "在校生": "student_status", "股权比例": "equity_ratio"}


class GovernmentPolicyAdapter(SourceAdapter):
    source_code = "CM-ENT"

    def parse(self, raw: RawArtifact) -> ParsedDocument:
        if not raw.content or len(raw.content) > MAX_BYTES:
            raise ParseError("政策 HTML 为空或超过限制")
        soup = BeautifulSoup(raw.content, "html.parser")
        reject_login_page(soup)
        title_node = soup.select_one("h1")
        if not title_node:
            raise ParseError("未找到政策标题")
        values = {"title": clean(title_node.get_text(" ", strip=True))}
        evidence = [{"record_key": "policy", "field": "title",
                     "evidence_location": "dom=" + selector_for(title_node),
                     "quote_or_normalized_fact": values["title"], "extractor": "parser",
                     "evidence_type": "dom"}]
        rules = []
        for table_index, table in enumerate(soup.select("table"), start=1):
            for row_index, row in enumerate(table.select("tr"), start=1):
                cells = row.select("th,td")
                if len(cells) < 2:
                    continue
                label, value = clean(cells[0].get_text(" ", strip=True)), clean(cells[1].get_text(" ", strip=True))
                normalized = label.casefold()
                field = next((key for key, names in META_LABELS.items() if normalized in {n.casefold() for n in names}), None)
                if field and value:
                    link = cells[1].select_one("a[href]")
                    values[field] = clean(link.get("href")) if field == "application_url" and link else value
                    evidence.append({"record_key": "policy", "field": field,
                        "evidence_location": f"dom=table:nth-of-type({table_index}) tr:nth-of-type({row_index}) td:nth-of-type(1)",
                        "quote_or_normalized_fact": f"{label}={values[field]}", "extractor": "parser", "evidence_type": "table"})
                elif label in RULE_FIELDS and value:
                    rule_field = RULE_FIELDS[label]
                    rules.append({"field": rule_field, "operator": "text_match", "expected": value,
                                  "description": f"{label}: {value}", "extractor": "parser",
                                  "confidence": 1.0, "review_status": "pending"})
                    evidence.append({"record_key": "policy", "field": rule_field,
                        "evidence_location": f"dom=table:nth-of-type({table_index}) tr:nth-of-type({row_index}) td:nth-of-type(1)",
                        "quote_or_normalized_fact": f"{label}={value}", "extractor": "parser", "evidence_type": "table"})
        if not values.get("policy_code") or not values.get("publisher"):
            raise ParseError("政策页缺少可确定性定位的文号或发布机关")
        values["rules"] = rules
        return ParsedDocument(records=[values], evidence=evidence,
                              metadata={"scope": "public_policy", "fixture_or_snapshot": True})

    def normalize(self, parsed: ParsedDocument):
        return parsed.records

    def extract_rules(self, parsed: ParsedDocument):
        return parsed.records[0].get("rules", [])

    def validate(self, record) -> ValidationResult:
        missing = [key for key in ("title", "policy_code", "publisher") if not record.get(key)]
        return ValidationResult(valid=not missing, errors=["缺少字段：" + ",".join(missing)] if missing else [])


class OpenDataPlatformAdapter(SourceAdapter):
    """Never imports protected payloads; it only validates public metadata fixtures."""
    source_code = "CM-ENT-OPEN-DATA"

    def parse(self, raw: RawArtifact) -> ParsedDocument:
        text = raw.content.decode("utf-8-sig", errors="strict")
        if re.search(r"userKey|api[_-]?key|access[_-]?token|登录|验证码", text, re.IGNORECASE):
            raise ParseError("开放数据资源需要认证或用户操作，仅登记许可证与 Blocker")
        raise ParseError("开放数据 Adapter 仅登记资源元数据，不直接导入政策事实")

    def normalize(self, parsed: ParsedDocument):
        return parsed.records

    def extract_rules(self, parsed: ParsedDocument):
        return []

    def validate(self, record) -> ValidationResult:
        return ValidationResult(valid=False, errors=["metadata_only"])

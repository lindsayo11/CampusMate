"""Guard: every parser_type declared in the registry must have an implementation.

Why this test exists
--------------------
`source_registry.yaml` declares a `parser_type` per endpoint, and
`source_scheduler` dispatches on that string. But the dispatch chain ends in a
bare `else:` that falls back to `_parse_generic`. So a `parser_type` with no
implementation does NOT fail loudly - it silently produces a DocumentVersion
containing only page chrome, with zero records and zero evidence.

Measured on a real page (moe.gov.cn 2027 研考管理规定, 77955 bytes):

    MoEPolicyAdapter  -> 1 record,  219 evidence, real title
    _parse_generic    -> 0 records,   0 evidence, 20992 chars of nav chrome

That is the same failure class as pointing an adapter at a site homepage: the
run reports success while carrying no usable data. Because nothing validated
the registry against the code, five endpoints shipped referencing adapters that
do not exist anywhere in the codebase.

This test pins the current gap so it cannot silently grow. When someone
implements one of the missing adapters, remove it from KNOWN_MISSING and the
test keeps guarding the rest.
"""
from pathlib import Path

import yaml

from app.adapters import civil_service, education, entrepreneurship, overseas, public_recruitment

# Adapters referenced by source_registry.yaml that have no implementation yet.
# Missing implementations are refused by the scheduler before fetching.
# This list is a debt register, not an approval.
KNOWN_MISSING = {
    "OccupationAdapter",          # CM-BASE-OCCUPATION (职业分类大典, pdf)
    "PublicJobDiscoveryAdapter",  # CM-JOB-001 (国家大学生就业服务平台)
    "RegionAdapter",              # CM-BASE-REGION (国家地名信息库)
    "StatisticsAdapter",          # CM-BASE-NBS (国家统计局, xlsx)
    "UniversityListAdapter",      # CM-BASE-UNIVERSITIES (全国高等学校名单, xlsx)
}

REGISTRY = Path(__file__).resolve().parents[1] / "app" / "source_registry.yaml"


def declared_parser_types() -> set[str]:
    body = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    declared = set()
    for source in body["sources"]:
        for endpoint in source.get("endpoints", []):
            value = (endpoint.get("parser_type") or "").strip()
            if value:
                declared.add(value)
    return declared


def implemented_adapters() -> set[str]:
    names = set()
    for module in (civil_service, education, entrepreneurship, overseas, public_recruitment):
        for attr in dir(module):
            obj = getattr(module, attr)
            if isinstance(obj, type) and attr.endswith("Adapter"):
                names.add(attr)
    return names


def test_declared_parser_types_are_implemented_or_known_missing():
    """A new endpoint must not reference an adapter that does not exist."""
    declared = declared_parser_types()
    implemented = implemented_adapters()
    missing = declared - implemented
    assert missing == KNOWN_MISSING, (
        "registry 声明的 parser_type 与实现不匹配。\n"
        f"  新出现的缺失（需要实现适配器）: {sorted(missing - KNOWN_MISSING)}\n"
        f"  已修复可移出 KNOWN_MISSING 的: {sorted(KNOWN_MISSING - missing)}\n"
        "注意：缺失的 parser_type 不会报错，而是静默走 _parse_generic 产出空记录。"
    )


def test_known_missing_list_stays_documented():
    """Every known gap must stay listed, so the debt is visible rather than forgotten."""
    declared = declared_parser_types()
    implemented = implemented_adapters()
    for name in KNOWN_MISSING:
        assert name in declared, f"{name} 已不在注册表中，请从 KNOWN_MISSING 移除"
        assert name not in implemented, f"{name} 已实现，请从 KNOWN_MISSING 移除"


def test_unknown_parser_type_degrades_silently_and_that_is_the_risk():
    """Documents the actual behaviour so the risk is not merely assumed.

    If this ever starts raising instead of returning text, the fallback was
    made fail-closed - update this test and the module docstring.
    """
    from app.source_scheduler import _parse_generic

    # A realistic-length page: the short-input guard does NOT catch this.
    page = ("<html><body>" + "<p>导航栏内容</p>" * 40 + "</body></html>").encode()
    text = _parse_generic(page, "html")
    assert isinstance(text, str) and len(text) > 20, "预期：静默返回纯文本，不报错"

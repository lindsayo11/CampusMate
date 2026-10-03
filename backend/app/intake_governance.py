"""One fail-closed gate shared by API, queue, worker and publication."""
import json
from urllib.parse import urlsplit

from sqlalchemy import or_, select

from .config import settings
from .intake_models import Source, SourceBlocker, SourceEndpointCalibration

PROOF_KEYS = {"robots_url", "robots_quote", "terms_url", "terms_quote",
              "license_url", "license_quote", "page_sha256"}


def _plaintext_hosts() -> set[str]:
    return {h.strip().lower()
            for h in settings.collector_allow_plaintext_hosts.split(",") if h.strip()}


def official_https_ok(parts, base) -> bool:
    """Whether an endpoint URL is an acceptable official, credential-free URL.

    The default is HTTPS-only. Hosts explicitly listed in
    ``collector_allow_plaintext_hosts`` may also use plaintext HTTP, because
    some official portals (notably www.moe.gov.cn behind TencentEdgeOne)
    redirect every https:// request to http:// and are otherwise unreachable.
    """
    if not parts.hostname or not base.hostname or parts.username or parts.password or parts.fragment:
        return False
    if not (parts.hostname == base.hostname or parts.hostname.endswith("." + base.hostname)):
        return False
    if parts.scheme == "https":
        return parts.port in (None, 443)
    plaintext = _plaintext_hosts()
    host = parts.hostname.lower()
    if parts.scheme == "http" and (host in plaintext
                                   or any(host.endswith("." + item) for item in plaintext)):
        return parts.port in (None, 80)
    return False


def separation_ok(row) -> bool:
    """Whether the reviewer identities satisfy the anti-collusion control.

    Upstream requires three distinct identities (submitter + 2 reviewers).
    When ``settings.single_admin_overrides`` is enabled the identity check is
    relaxed to "at least one reviewer recorded", which makes the workflow
    usable by a single operator in local development. The evidence proof and
    the robots/terms/licence statuses are still enforced by the caller, so
    this does not weaken the factual-verification requirement - only the
    human-separation requirement.
    """
    if settings.single_admin_overrides:
        return bool(row.first_reviewed_by)
    return bool(row.first_reviewed_by and row.second_reviewed_by
                and len({row.submitted_by, row.first_reviewed_by,
                         row.second_reviewed_by}) == 3)


def calibration_for(db, endpoint):
    rows = db.scalars(select(SourceEndpointCalibration).where(
        SourceEndpointCalibration.endpoint_id == endpoint.id,
        SourceEndpointCalibration.status == "approved",
        SourceEndpointCalibration.exact_url == endpoint.url,
    ).order_by(SourceEndpointCalibration.second_reviewed_at.desc())).all()
    for row in rows:
        proof = json.loads(row.proof or "{}")
        if (PROOF_KEYS.issubset(proof) and all(proof[k] for k in PROOF_KEYS)
                and separation_ok(row)
                and row.robots_status == "allowed" and row.terms_status == "permitted"
                and row.license_status == "permitted"
                and json.loads(row.adapter_config) == json.loads(endpoint.adapter_config or "{}")):
            return row
    return None


def gate_reason(db, endpoint, *, automated=False):
    if not endpoint or not endpoint.active:
        return "端点不存在或已停用"
    source = db.get(Source, endpoint.source_id)
    if not source or not source.active or not source.official:
        return "来源未启用或不是官方来源"
    tags = set(json.loads(endpoint.access_tags or "[]"))
    if (endpoint.auth_type != "none" or endpoint.agent_mode == "USER_ACTION"
            or tags & {"API-AUTH", "LOGIN-USER", "COMMERCIAL", "LICENSE"}
            or endpoint.license_status != "permitted"):
        return "认证、登录、商业限制或许可未明确的端点不可发布或采集"
    parts, base = urlsplit(endpoint.url), urlsplit(source.base_url)
    if not official_https_ok(parts, base):
        return "端点不是无凭据的官方 URL（默认仅 HTTPS，明文仅限显式例外主机）"
    if db.scalar(select(SourceBlocker.id).where(
        SourceBlocker.source_id == source.id, SourceBlocker.status == "open",
        or_(SourceBlocker.endpoint_id == endpoint.id, SourceBlocker.endpoint_id.is_(None)),
    )):
        return "来源仍有开放 Blocker"
    if not calibration_for(db, endpoint):
        return "缺少含原始依据的双人校准审核"
    if automated and (endpoint.automation_level not in {"AUTO-1", "AUTO-2"}
                      or endpoint.manual_takeover):
        return "仅允许 AUTO-1/AUTO-2 且非人工接管的端点自动采集"
    return None

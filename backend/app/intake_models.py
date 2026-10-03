"""Normalized, versioned data-source intake models.

The existing opportunity tables remain the public product surface.  These
tables form the auditable intake layer required before a record is published.
"""
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    publisher: Mapped[str] = mapped_column(String(160))
    authority_level: Mapped[str] = mapped_column(String(4), index=True)
    source_class: Mapped[str] = mapped_column(String(30), index=True)
    official: Mapped[bool] = mapped_column(Boolean, default=True)
    jurisdiction_level: Mapped[str] = mapped_column(String(30), index=True)
    region_code: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    school_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    supported_paths: Mapped[str] = mapped_column(Text, default="[]")
    supported_item_types: Mapped[str] = mapped_column(Text, default="[]")
    base_url: Mapped[str] = mapped_column(String(500))
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SourceEndpoint(Base):
    __tablename__ = "source_endpoints"
    __table_args__ = (UniqueConstraint("source_id", "name", name="uq_source_endpoint_name"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(120), default="default")
    endpoint_type: Mapped[str] = mapped_column(String(20), index=True)
    url: Mapped[str] = mapped_column(String(500))
    access_tags: Mapped[str] = mapped_column(Text, default="[]")
    auth_type: Mapped[str] = mapped_column(String(20), default="none")
    secret_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    format: Mapped[str] = mapped_column(String(20), default="html")
    parser_type: Mapped[str] = mapped_column(String(80), default="")
    rate_limit: Mapped[str] = mapped_column(String(80), default="")
    cors_status: Mapped[str] = mapped_column(String(20), default="unknown")
    robots_status: Mapped[str] = mapped_column(String(20), default="unknown")
    fetch_interval: Mapped[str] = mapped_column(String(80), default="7d")
    automation_level: Mapped[str] = mapped_column(String(10), index=True)
    agent_mode: Mapped[str] = mapped_column(String(20))
    license_note: Mapped[str] = mapped_column(Text, default="")
    license_status: Mapped[str] = mapped_column(String(20), default="unknown", index=True)
    adapter_config: Mapped[str] = mapped_column(Text, default="{}")
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    max_failures: Mapped[int] = mapped_column(Integer, default=3)
    scheduled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    manual_takeover: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    paused_reason: Mapped[str] = mapped_column(Text, default="")
    last_error: Mapped[str] = mapped_column(String(500), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class NoticeResource(Base):
    """Durable listing/detail frontier, independent of the qualification-rule collector."""
    __tablename__ = "notice_resources"
    __table_args__ = (UniqueConstraint("endpoint_id", "url", name="uq_notice_resource_url"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    endpoint_id: Mapped[str] = mapped_column(String(36), index=True)
    url: Mapped[str] = mapped_column(String(500))
    title: Mapped[str] = mapped_column(String(240), default="")
    kind: Mapped[str] = mapped_column(String(20))
    parent_url: Mapped[str] = mapped_column(String(500), default="")
    depth: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(30), default="queued")
    etag: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_modified: Mapped[str | None] = mapped_column(String(200), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    document_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_check_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(String(500), default="")


class SourceEndpointRun(Base):
    __tablename__ = "source_endpoint_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    endpoint_id: Mapped[str] = mapped_column(String(36), index=True)
    source_item_id: Mapped[str] = mapped_column(String(160), default="default")
    status: Mapped[str] = mapped_column(String(20), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    ready_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    document_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SourceChangeReview(Base):
    __tablename__ = "source_change_reviews"
    __table_args__ = (UniqueConstraint("document_version_id", name="uq_source_change_document"),)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    endpoint_id: Mapped[str] = mapped_column(String(36), index=True)
    document_version_id: Mapped[str] = mapped_column(String(36), index=True)
    risk_level: Mapped[str] = mapped_column(String(20), default="high", index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    changed_fields: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SourceRegistryCandidate(Base):
    __tablename__ = "source_registry_candidates"
    __table_args__ = (UniqueConstraint("document_version_id", "base_url",
                                      name="uq_source_candidate_document_url"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    discovery_source_id: Mapped[str] = mapped_column(String(36), index=True)
    document_version_id: Mapped[str] = mapped_column(String(36), index=True)
    source_code: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(160))
    region_code: Mapped[str] = mapped_column(String(20), index=True)
    base_url: Mapped[str] = mapped_column(String(500))
    authority_level: Mapped[str] = mapped_column(String(4), default="A+")
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    evidence_id: Mapped[str] = mapped_column(String(36), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    import_mode: Mapped[str] = mapped_column(String(20), default="manual", server_default="manual")
    test_batch: Mapped[str | None] = mapped_column(String(80), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("source_endpoint_id", "source_item_id", "version_no",
                                      name="uq_document_version_number"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_endpoint_id: Mapped[str] = mapped_column(String(36), index=True)
    canonical_url: Mapped[str] = mapped_column(String(500), index=True)
    source_item_id: Mapped[str] = mapped_column(String(160), default="default")
    publish_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_modified: Mapped[str | None] = mapped_column(String(160), nullable=True)
    etag: Mapped[str | None] = mapped_column(String(300), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    attachment_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    version_no: Mapped[int] = mapped_column(Integer)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    raw_storage_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, default="")
    previous_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_version_id: Mapped[str] = mapped_column(String(36), index=True)
    source_id: Mapped[str] = mapped_column(String(36), index=True)
    evidence_location: Mapped[str] = mapped_column(String(300))
    quote_or_normalized_fact: Mapped[str] = mapped_column(Text)
    extractor: Mapped[str] = mapped_column(String(20), index=True)
    evidence_type: Mapped[str] = mapped_column(String(20), default="dom", index=True)
    review_status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    verified_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Institution(Base):
    __tablename__ = "institutions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    institution_type: Mapped[str] = mapped_column(String(40), default="unknown")
    country_code: Mapped[str] = mapped_column(String(8), default="CN")
    region_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    official_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    official_name: Mapped[str] = mapped_column(String(200), default="")
    website_url: Mapped[str] = mapped_column(String(500), default="")
    public_status: Mapped[str] = mapped_column(String(40), default="unknown", index=True)
    review_status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    source_document_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class Program(Base):
    __tablename__ = "programs"
    __table_args__ = (UniqueConstraint("institution_id", "program_code", name="uq_program_code"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    institution_id: Mapped[str] = mapped_column(String(64), index=True)
    program_code: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(200), index=True)
    degree_level: Mapped[str] = mapped_column(String(40), default="")
    study_mode: Mapped[str] = mapped_column(String(40), default="")
    official_url: Mapped[str] = mapped_column(String(500), default="")
    public_status: Mapped[str] = mapped_column(String(40), default="unknown", index=True)
    review_status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    source_document_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)


class ApplicationCycle(Base):
    __tablename__ = "application_cycles"
    __table_args__ = (UniqueConstraint("program_id", "path_id", "cycle_year", name="uq_application_cycle"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    program_id: Mapped[str] = mapped_column(String(64), index=True)
    path_id: Mapped[int] = mapped_column(Integer, index=True)
    cycle_year: Mapped[int] = mapped_column(Integer, index=True)
    open_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exam_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    interview_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    application_url: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    source_document_id: Mapped[str] = mapped_column(String(36), index=True)
    requirements_source_type: Mapped[str] = mapped_column(String(30), default="university_first_party", index=True)
    review_status: Mapped[str] = mapped_column(String(20), default="pending", index=True)


class GeographicEntity(Base):
    __tablename__ = "geographic_entities"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    entity_type: Mapped[str] = mapped_column(String(20), index=True)
    canonical_name: Mapped[str] = mapped_column(String(160), index=True)
    parent_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)


class EntityAlias(Base):
    __tablename__ = "entity_aliases"
    __table_args__ = (UniqueConstraint("entity_type", "normalized_alias", name="uq_entity_alias"),)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(20), index=True)
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    alias: Mapped[str] = mapped_column(String(240))
    normalized_alias: Mapped[str] = mapped_column(String(240), index=True)
    locale: Mapped[str] = mapped_column(String(20), default="und")
    source_document_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class RegistryAssertion(Base):
    __tablename__ = "registry_assertions"
    __table_args__ = (UniqueConstraint("source_id", "entity_type", "entity_id", "registry_id",
                                      name="uq_registry_assertion"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(36), index=True)
    entity_type: Mapped[str] = mapped_column(String(20), index=True)
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    registry_id: Mapped[str] = mapped_column(String(160), default="")
    assertion_type: Mapped[str] = mapped_column(String(40), index=True)
    assertion_value: Mapped[str] = mapped_column(String(240))
    evidence_id: Mapped[str] = mapped_column(String(36), index=True)
    review_status: Mapped[str] = mapped_column(String(20), default="pending", index=True)


class SourceBlocker(Base):
    __tablename__ = "source_blockers"
    __table_args__ = (UniqueConstraint("source_id", "endpoint_id", "blocker_type",
                                      name="uq_source_blocker"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(36), index=True)
    endpoint_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    blocker_type: Mapped[str] = mapped_column(String(30), index=True)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    detail: Mapped[str] = mapped_column(Text)
    required_action: Mapped[str] = mapped_column(Text, default="")
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SourceEndpointCalibration(Base):
    """Human calibration evidence required before a blocked endpoint may run."""
    __tablename__ = "source_endpoint_calibrations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    endpoint_id: Mapped[str] = mapped_column(String(36), index=True)
    exact_url: Mapped[str] = mapped_column(String(500))
    robots_status: Mapped[str] = mapped_column(String(20), index=True)
    terms_status: Mapped[str] = mapped_column(String(20), index=True)
    license_status: Mapped[str] = mapped_column(String(20), index=True)
    field_mapping: Mapped[str] = mapped_column(Text, default="{}")
    adapter_config: Mapped[str] = mapped_column(Text, default="{}")
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    submitted_by: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    first_reviewed_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    first_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    second_reviewed_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    second_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    proof: Mapped[str] = mapped_column(Text, default="{}")


class DocumentArchive(Base):
    __tablename__ = "document_archives"
    document_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    content: Mapped[bytes] = mapped_column(LargeBinary)
    content_type: Mapped[str] = mapped_column(String(160))
    is_fixture: Mapped[bool] = mapped_column(Boolean, default=False)


class DataPublication(Base):
    __tablename__ = "data_publications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(36), unique=True)
    status: Mapped[str] = mapped_column(String(20), index=True, default="pending")
    snapshot: Mapped[str] = mapped_column(Text)
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    submitted_by: Mapped[str] = mapped_column(String(80))
    first_reviewed_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    second_reviewed_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DataSubscription(Base):
    __tablename__ = "data_subscriptions"
    __table_args__ = (UniqueConstraint("user_id", "item_id", name="uq_data_subscription_user_item"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(80), index=True)
    item_id: Mapped[str] = mapped_column(String(64))
    publication_id: Mapped[str] = mapped_column(String(36))
    plan_id: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    remind_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    alerted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    message: Mapped[str] = mapped_column(Text, default="")


class RecruitmentCycle(Base):
    __tablename__ = "recruitment_cycles"
    __table_args__ = (UniqueConstraint("source_id", "cycle_code", name="uq_recruitment_cycle"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(36), index=True)
    cycle_code: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    cycle_year: Mapped[int] = mapped_column(Integer, index=True)
    open_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    source_document_id: Mapped[str] = mapped_column(String(36), index=True)


class ExamCycle(Base):
    __tablename__ = "exam_cycles"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    path_id: Mapped[int] = mapped_column(Integer, index=True)
    cycle_year: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(200))
    registration_open_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    registration_deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exam_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_document_id: Mapped[str] = mapped_column(String(36), index=True)


class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("recruitment_cycle_id", "position_code", name="uq_position_cycle_code"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    recruitment_cycle_id: Mapped[str] = mapped_column(String(64), index=True)
    position_code: Mapped[str] = mapped_column(String(100), index=True)
    department: Mapped[str] = mapped_column(String(200), default="")
    organization: Mapped[str] = mapped_column(String(200), default="")
    title: Mapped[str] = mapped_column(String(200), index=True)
    headcount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    education: Mapped[str] = mapped_column(String(120), default="")
    degree: Mapped[str] = mapped_column(String(120), default="")
    majors: Mapped[str] = mapped_column(Text, default="")
    political_status: Mapped[str] = mapped_column(String(120), default="")
    grassroots_years: Mapped[str] = mapped_column(String(120), default="")
    fresh_graduate: Mapped[str] = mapped_column(String(120), default="")
    work_region: Mapped[str] = mapped_column(String(120), default="")
    remarks: Mapped[str] = mapped_column(Text, default="")
    source_document_id: Mapped[str] = mapped_column(String(36), index=True)


class DevelopmentItem(Base):
    __tablename__ = "development_items"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    item_type: Mapped[str] = mapped_column(String(40), index=True)
    organization_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cycle_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    cycle_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    location: Mapped[str] = mapped_column(String(160), default="")
    materials: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    source_document_id: Mapped[str] = mapped_column(String(36), index=True)


class DevelopmentItemPath(Base):
    __tablename__ = "development_item_paths"
    __table_args__ = (UniqueConstraint("development_item_id", "path_id", name="uq_development_item_path"),)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    development_item_id: Mapped[str] = mapped_column(String(64), index=True)
    path_id: Mapped[int] = mapped_column(Integer, index=True)


class PolicyRecord(Base):
    __tablename__ = "policy_records"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    policy_code: Mapped[str] = mapped_column(String(120), default="", index=True)
    title: Mapped[str] = mapped_column(String(300), index=True)
    publisher: Mapped[str] = mapped_column(String(200), default="")
    policy_type: Mapped[str] = mapped_column(String(40), default="entrepreneurship")
    jurisdiction_level: Mapped[str] = mapped_column(String(30), index=True)
    region_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    jurisdiction_path: Mapped[str] = mapped_column(Text, default="[]")
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    application_url: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(20), default="candidate", index=True)
    review_status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    source_document_id: Mapped[str] = mapped_column(String(36), index=True)


class PolicyRelation(Base):
    __tablename__ = "policy_relations"
    __table_args__ = (UniqueConstraint("from_policy_id", "to_policy_id", "relation_type",
                                      name="uq_policy_relation"),)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    from_policy_id: Mapped[str] = mapped_column(String(64), index=True)
    to_policy_id: Mapped[str] = mapped_column(String(64), index=True)
    relation_type: Mapped[str] = mapped_column(String(20), index=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    review_status: Mapped[str] = mapped_column(String(20), default="pending")
    evidence_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)


class OpenDataResource(Base):
    __tablename__ = "open_data_resources"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(36), index=True)
    endpoint_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(240))
    resource_url: Mapped[str] = mapped_column(String(500))
    access_mode: Mapped[str] = mapped_column(String(30), index=True)
    license_status: Mapped[str] = mapped_column(String(20), index=True)
    import_status: Mapped[str] = mapped_column(String(20), default="metadata_only", index=True)
    blocker_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

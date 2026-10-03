"""Add versioned source registry, evidence and normalized intake entities."""
import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def ix(table, *columns):
    for column in columns:
        op.create_index(f"ix_{table}_{column}", table, [column])


def upgrade():
    with op.batch_alter_table("development_paths") as batch:
        batch.add_column(sa.Column("code", sa.String(80), nullable=True))
        batch.add_column(sa.Column("parent_id", sa.Integer(), nullable=True))
        batch.create_unique_constraint("uq_development_paths_code", ["code"])
        batch.create_index("ix_development_paths_parent_id", ["parent_id"])

    with op.batch_alter_table("eligibility_rules") as batch:
        batch.alter_column("opportunity_id", existing_type=sa.String(40), nullable=True)
        batch.add_column(sa.Column("target_type", sa.String(30), nullable=False, server_default="opportunity"))
        batch.add_column(sa.Column("target_id", sa.String(64), nullable=True))
        batch.add_column(sa.Column("evidence_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("logic_group", sa.String(40), nullable=False, server_default="all"))
        batch.add_column(sa.Column("confidence", sa.Float(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("review_status", sa.String(20), nullable=False, server_default="pending"))
        batch.add_column(sa.Column("extractor", sa.String(20), nullable=False, server_default="parser"))
        batch.create_index("ix_eligibility_rules_target_id", ["target_id"])
        batch.create_index("ix_eligibility_rules_evidence_id", ["evidence_id"])
        batch.create_index("ix_eligibility_rules_review_status", ["review_status"])

    op.create_table("sources",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("source_code", sa.String(40), nullable=False, unique=True),
        sa.Column("name", sa.String(160), nullable=False), sa.Column("publisher", sa.String(160), nullable=False),
        sa.Column("authority_level", sa.String(4), nullable=False), sa.Column("source_class", sa.String(30), nullable=False),
        sa.Column("official", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("jurisdiction_level", sa.String(30), nullable=False), sa.Column("region_code", sa.String(20)),
        sa.Column("school_id", sa.String(64)), sa.Column("supported_paths", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("supported_item_types", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("base_url", sa.String(500), nullable=False), sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False))
    ix("sources", "name", "authority_level", "source_class", "jurisdiction_level", "region_code", "school_id", "active")

    op.create_table("source_endpoints",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(120), nullable=False, server_default="default"),
        sa.Column("endpoint_type", sa.String(20), nullable=False), sa.Column("url", sa.String(500), nullable=False),
        sa.Column("access_tags", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("auth_type", sa.String(20), nullable=False, server_default="none"), sa.Column("secret_ref", sa.String(200)),
        sa.Column("format", sa.String(20), nullable=False, server_default="html"),
        sa.Column("parser_type", sa.String(80), nullable=False, server_default=""),
        sa.Column("rate_limit", sa.String(80), nullable=False, server_default=""),
        sa.Column("cors_status", sa.String(20), nullable=False, server_default="unknown"),
        sa.Column("robots_status", sa.String(20), nullable=False, server_default="unknown"),
        sa.Column("fetch_interval", sa.String(80), nullable=False, server_default="7d"),
        sa.Column("automation_level", sa.String(10), nullable=False), sa.Column("agent_mode", sa.String(20), nullable=False),
        sa.Column("license_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("source_id", "name", name="uq_source_endpoint_name"))
    ix("source_endpoints", "source_id", "endpoint_type", "automation_level", "active")

    op.create_table("document_versions",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("source_endpoint_id", sa.String(36), nullable=False),
        sa.Column("canonical_url", sa.String(500), nullable=False), sa.Column("source_item_id", sa.String(160), nullable=False, server_default="default"),
        sa.Column("publish_time", sa.DateTime(timezone=True)), sa.Column("last_modified", sa.String(160)), sa.Column("etag", sa.String(300)),
        sa.Column("content_hash", sa.String(64), nullable=False), sa.Column("attachment_hash", sa.String(64)),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False), sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_changed_at", sa.DateTime(timezone=True), nullable=False), sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False), sa.Column("raw_storage_uri", sa.String(500)),
        sa.Column("raw_text", sa.Text(), nullable=False, server_default=""), sa.Column("previous_id", sa.String(36)),
        sa.UniqueConstraint("source_endpoint_id", "source_item_id", "version_no", name="uq_document_version_number"))
    ix("document_versions", "source_endpoint_id", "canonical_url", "content_hash")

    op.create_table("evidence",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("document_version_id", sa.String(36), nullable=False),
        sa.Column("source_id", sa.String(36), nullable=False), sa.Column("evidence_location", sa.String(300), nullable=False),
        sa.Column("quote_or_normalized_fact", sa.Text(), nullable=False), sa.Column("extractor", sa.String(20), nullable=False),
        sa.Column("verified_by", sa.String(80)), sa.Column("verified_at", sa.DateTime(timezone=True)))
    ix("evidence", "document_version_id", "source_id", "extractor")

    op.create_table("institutions",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("name", sa.String(200), nullable=False),
        sa.Column("institution_type", sa.String(40), nullable=False, server_default="unknown"),
        sa.Column("country_code", sa.String(8), nullable=False, server_default="CN"), sa.Column("region_code", sa.String(20)),
        sa.Column("official_id", sa.String(120)), sa.Column("source_document_id", sa.String(36)))
    ix("institutions", "name")
    op.create_table("programs",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("institution_id", sa.String(64), nullable=False),
        sa.Column("program_code", sa.String(80), nullable=False), sa.Column("name", sa.String(200), nullable=False),
        sa.Column("degree_level", sa.String(40), nullable=False, server_default=""),
        sa.Column("study_mode", sa.String(40), nullable=False, server_default=""),
        sa.UniqueConstraint("institution_id", "program_code", name="uq_program_code"))
    ix("programs", "institution_id", "name")
    op.create_table("application_cycles",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("program_id", sa.String(64), nullable=False),
        sa.Column("path_id", sa.Integer(), nullable=False), sa.Column("cycle_year", sa.Integer(), nullable=False),
        sa.Column("open_at", sa.DateTime(timezone=True)), sa.Column("deadline_at", sa.DateTime(timezone=True)),
        sa.Column("exam_at", sa.DateTime(timezone=True)), sa.Column("interview_at", sa.DateTime(timezone=True)),
        sa.Column("result_at", sa.DateTime(timezone=True)), sa.Column("application_url", sa.String(500), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"), sa.Column("source_document_id", sa.String(36), nullable=False),
        sa.UniqueConstraint("program_id", "path_id", "cycle_year", name="uq_application_cycle"))
    ix("application_cycles", "program_id", "path_id", "cycle_year", "status", "source_document_id")
    op.create_table("recruitment_cycles",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("cycle_code", sa.String(100), nullable=False), sa.Column("name", sa.String(200), nullable=False),
        sa.Column("cycle_year", sa.Integer(), nullable=False), sa.Column("open_at", sa.DateTime(timezone=True)),
        sa.Column("deadline_at", sa.DateTime(timezone=True)), sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("source_document_id", sa.String(36), nullable=False),
        sa.UniqueConstraint("source_id", "cycle_code", name="uq_recruitment_cycle"))
    ix("recruitment_cycles", "source_id", "cycle_year", "status", "source_document_id")
    op.create_table("exam_cycles",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("path_id", sa.Integer(), nullable=False),
        sa.Column("cycle_year", sa.Integer(), nullable=False), sa.Column("name", sa.String(200), nullable=False),
        sa.Column("registration_open_at", sa.DateTime(timezone=True)), sa.Column("registration_deadline_at", sa.DateTime(timezone=True)),
        sa.Column("exam_at", sa.DateTime(timezone=True)), sa.Column("source_document_id", sa.String(36), nullable=False))
    ix("exam_cycles", "path_id", "cycle_year", "source_document_id")
    op.create_table("positions",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("recruitment_cycle_id", sa.String(64), nullable=False),
        sa.Column("position_code", sa.String(100), nullable=False), sa.Column("department", sa.String(200), nullable=False, server_default=""),
        sa.Column("organization", sa.String(200), nullable=False, server_default=""), sa.Column("title", sa.String(200), nullable=False),
        sa.Column("headcount", sa.Integer()), sa.Column("education", sa.String(120), nullable=False, server_default=""),
        sa.Column("degree", sa.String(120), nullable=False, server_default=""), sa.Column("majors", sa.Text(), nullable=False, server_default=""),
        sa.Column("political_status", sa.String(120), nullable=False, server_default=""),
        sa.Column("grassroots_years", sa.String(120), nullable=False, server_default=""),
        sa.Column("fresh_graduate", sa.String(120), nullable=False, server_default=""),
        sa.Column("work_region", sa.String(120), nullable=False, server_default=""), sa.Column("remarks", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_document_id", sa.String(36), nullable=False),
        sa.UniqueConstraint("recruitment_cycle_id", "position_code", name="uq_position_cycle_code"))
    ix("positions", "recruitment_cycle_id", "position_code", "title", "source_document_id")
    op.create_table("development_items",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("title", sa.String(200), nullable=False),
        sa.Column("item_type", sa.String(40), nullable=False), sa.Column("organization_id", sa.String(64)),
        sa.Column("cycle_type", sa.String(30)), sa.Column("cycle_id", sa.String(64)),
        sa.Column("description", sa.Text(), nullable=False, server_default=""), sa.Column("start_time", sa.DateTime(timezone=True)),
        sa.Column("deadline", sa.DateTime(timezone=True)), sa.Column("location", sa.String(160), nullable=False, server_default=""),
        sa.Column("materials", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"), sa.Column("source_document_id", sa.String(36), nullable=False))
    ix("development_items", "title", "item_type", "cycle_id", "status", "source_document_id")
    op.create_table("development_item_paths",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("development_item_id", sa.String(64), nullable=False),
        sa.Column("path_id", sa.Integer(), nullable=False),
        sa.UniqueConstraint("development_item_id", "path_id", name="uq_development_item_path"))
    ix("development_item_paths", "development_item_id", "path_id")
    op.create_table("policy_records",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("title", sa.String(300), nullable=False),
        sa.Column("jurisdiction_level", sa.String(30), nullable=False), sa.Column("region_code", sa.String(20)),
        sa.Column("effective_at", sa.DateTime(timezone=True)), sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(20), nullable=False, server_default="candidate"), sa.Column("source_document_id", sa.String(36), nullable=False))
    ix("policy_records", "title", "jurisdiction_level", "status", "source_document_id")
    op.create_table("policy_relations",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("from_policy_id", sa.String(64), nullable=False),
        sa.Column("to_policy_id", sa.String(64), nullable=False), sa.Column("relation_type", sa.String(20), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1"),
        sa.Column("review_status", sa.String(20), nullable=False, server_default="pending"),
        sa.UniqueConstraint("from_policy_id", "to_policy_id", "relation_type", name="uq_policy_relation"))
    ix("policy_relations", "from_policy_id", "to_policy_id", "relation_type")


def downgrade():
    for table in ("policy_relations", "policy_records", "development_item_paths", "development_items", "positions",
                  "exam_cycles", "recruitment_cycles", "application_cycles", "programs", "institutions", "evidence",
                  "document_versions", "source_endpoints", "sources"):
        op.drop_table(table)
    with op.batch_alter_table("eligibility_rules") as batch:
        batch.drop_index("ix_eligibility_rules_review_status")
        batch.drop_index("ix_eligibility_rules_evidence_id")
        batch.drop_index("ix_eligibility_rules_target_id")
        for name in ("extractor", "review_status", "confidence", "logic_group", "evidence_id", "target_id", "target_type"):
            batch.drop_column(name)
        batch.alter_column("opportunity_id", existing_type=sa.String(40), nullable=False)
    with op.batch_alter_table("development_paths") as batch:
        batch.drop_index("ix_development_paths_parent_id")
        batch.drop_constraint("uq_development_paths_code", type_="unique")
        batch.drop_column("parent_id")
        batch.drop_column("code")

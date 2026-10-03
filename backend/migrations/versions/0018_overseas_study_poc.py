"""Add M5 overseas institution, registry, alias and application review fields."""
import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("source_endpoints") as batch:
        batch.add_column(sa.Column("license_status", sa.String(20), nullable=False,
                                   server_default="unknown"))
        batch.create_index("ix_source_endpoints_license_status", ["license_status"])
    with op.batch_alter_table("evidence") as batch:
        batch.add_column(sa.Column("evidence_type", sa.String(20), nullable=False,
                                   server_default="dom"))
        batch.add_column(sa.Column("review_status", sa.String(20), nullable=False,
                                   server_default="pending"))
        batch.create_index("ix_evidence_evidence_type", ["evidence_type"])
        batch.create_index("ix_evidence_review_status", ["review_status"])
    with op.batch_alter_table("institutions") as batch:
        batch.add_column(sa.Column("official_name", sa.String(200), nullable=False,
                                   server_default=""))
        batch.add_column(sa.Column("website_url", sa.String(500), nullable=False,
                                   server_default=""))
        batch.add_column(sa.Column("public_status", sa.String(40), nullable=False,
                                   server_default="unknown"))
        batch.add_column(sa.Column("review_status", sa.String(20), nullable=False,
                                   server_default="pending"))
        batch.create_index("ix_institutions_public_status", ["public_status"])
        batch.create_index("ix_institutions_review_status", ["review_status"])
    with op.batch_alter_table("programs") as batch:
        batch.add_column(sa.Column("official_url", sa.String(500), nullable=False,
                                   server_default=""))
        batch.add_column(sa.Column("public_status", sa.String(40), nullable=False,
                                   server_default="unknown"))
        batch.add_column(sa.Column("review_status", sa.String(20), nullable=False,
                                   server_default="pending"))
        batch.add_column(sa.Column("source_document_id", sa.String(36), nullable=True))
        batch.create_index("ix_programs_public_status", ["public_status"])
        batch.create_index("ix_programs_review_status", ["review_status"])
        batch.create_index("ix_programs_source_document_id", ["source_document_id"])
    with op.batch_alter_table("application_cycles") as batch:
        batch.add_column(sa.Column("requirements_source_type", sa.String(30), nullable=False,
                                   server_default="university_first_party"))
        batch.add_column(sa.Column("review_status", sa.String(20), nullable=False,
                                   server_default="pending"))
        batch.create_index("ix_application_cycles_requirements_source_type",
                           ["requirements_source_type"])
        batch.create_index("ix_application_cycles_review_status", ["review_status"])

    op.create_table("geographic_entities",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("canonical_name", sa.String(160), nullable=False),
        sa.Column("parent_id", sa.String(64), nullable=True))
    for column in ("entity_type", "canonical_name", "parent_id"):
        op.create_index(f"ix_geographic_entities_{column}", "geographic_entities", [column])
    op.create_table("entity_aliases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("alias", sa.String(240), nullable=False),
        sa.Column("normalized_alias", sa.String(240), nullable=False),
        sa.Column("locale", sa.String(20), nullable=False, server_default="und"),
        sa.Column("source_document_id", sa.String(36), nullable=True),
        sa.UniqueConstraint("entity_type", "normalized_alias", name="uq_entity_alias"))
    for column in ("entity_type", "entity_id", "normalized_alias"):
        op.create_index(f"ix_entity_aliases_{column}", "entity_aliases", [column])
    op.create_table("registry_assertions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("registry_id", sa.String(160), nullable=False, server_default=""),
        sa.Column("assertion_type", sa.String(40), nullable=False),
        sa.Column("assertion_value", sa.String(240), nullable=False),
        sa.Column("evidence_id", sa.String(36), nullable=False),
        sa.Column("review_status", sa.String(20), nullable=False, server_default="pending"),
        sa.UniqueConstraint("source_id", "entity_type", "entity_id", "registry_id",
                            name="uq_registry_assertion"))
    for column in ("source_id", "entity_type", "entity_id", "assertion_type", "evidence_id",
                   "review_status"):
        op.create_index(f"ix_registry_assertions_{column}", "registry_assertions", [column])
    op.create_table("source_blockers",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("endpoint_id", sa.String(36), nullable=True),
        sa.Column("blocker_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("required_action", sa.Text(), nullable=False, server_default=""),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("source_id", "endpoint_id", "blocker_type", name="uq_source_blocker"))
    for column in ("source_id", "endpoint_id", "blocker_type", "status"):
        op.create_index(f"ix_source_blockers_{column}", "source_blockers", [column])


def downgrade():
    for table in ("source_blockers", "registry_assertions", "entity_aliases",
                  "geographic_entities"):
        op.drop_table(table)
    with op.batch_alter_table("application_cycles") as batch:
        batch.drop_index("ix_application_cycles_review_status")
        batch.drop_index("ix_application_cycles_requirements_source_type")
        batch.drop_column("review_status")
        batch.drop_column("requirements_source_type")
    with op.batch_alter_table("programs") as batch:
        batch.drop_index("ix_programs_source_document_id")
        batch.drop_index("ix_programs_review_status")
        batch.drop_index("ix_programs_public_status")
        batch.drop_column("source_document_id")
        batch.drop_column("public_status")
        batch.drop_column("review_status")
        batch.drop_column("official_url")
    with op.batch_alter_table("institutions") as batch:
        batch.drop_index("ix_institutions_review_status")
        batch.drop_index("ix_institutions_public_status")
        batch.drop_column("review_status")
        batch.drop_column("public_status")
        batch.drop_column("website_url")
        batch.drop_column("official_name")
    with op.batch_alter_table("evidence") as batch:
        batch.drop_index("ix_evidence_review_status")
        batch.drop_index("ix_evidence_evidence_type")
        batch.drop_column("review_status")
        batch.drop_column("evidence_type")
    with op.batch_alter_table("source_endpoints") as batch:
        batch.drop_index("ix_source_endpoints_license_status")
        batch.drop_column("license_status")

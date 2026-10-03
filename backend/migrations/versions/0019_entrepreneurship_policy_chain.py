"""Extend policy records and register governed open-data resources for M6."""
import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("policy_records") as batch:
        batch.add_column(sa.Column("policy_code", sa.String(120), nullable=False, server_default=""))
        batch.add_column(sa.Column("publisher", sa.String(200), nullable=False, server_default=""))
        batch.add_column(sa.Column("policy_type", sa.String(40), nullable=False, server_default="entrepreneurship"))
        batch.add_column(sa.Column("jurisdiction_path", sa.Text(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("application_url", sa.String(500), nullable=False, server_default=""))
        batch.add_column(sa.Column("review_status", sa.String(20), nullable=False, server_default="pending"))
        batch.create_index("ix_policy_records_policy_code", ["policy_code"])
        batch.create_index("ix_policy_records_review_status", ["review_status"])
    with op.batch_alter_table("policy_relations") as batch:
        batch.add_column(sa.Column("evidence_id", sa.String(36), nullable=True))
        batch.create_index("ix_policy_relations_evidence_id", ["evidence_id"])
    op.create_table("open_data_resources",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("endpoint_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(240), nullable=False),
        sa.Column("resource_url", sa.String(500), nullable=False),
        sa.Column("access_mode", sa.String(30), nullable=False),
        sa.Column("license_status", sa.String(20), nullable=False),
        sa.Column("import_status", sa.String(20), nullable=False, server_default="metadata_only"),
        sa.Column("blocker_id", sa.String(64), nullable=True))
    for column in ("source_id", "endpoint_id", "access_mode", "license_status", "import_status"):
        op.create_index(f"ix_open_data_resources_{column}", "open_data_resources", [column])


def downgrade():
    op.drop_table("open_data_resources")
    with op.batch_alter_table("policy_relations") as batch:
        batch.drop_index("ix_policy_relations_evidence_id")
        batch.drop_column("evidence_id")
    with op.batch_alter_table("policy_records") as batch:
        batch.drop_index("ix_policy_records_review_status")
        batch.drop_index("ix_policy_records_policy_code")
        for column in ("review_status", "application_url", "jurisdiction_path", "policy_type", "publisher", "policy_code"):
            batch.drop_column(column)

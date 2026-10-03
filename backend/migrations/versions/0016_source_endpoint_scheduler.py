"""Add governed SourceEndpoint scheduling, leases and source-change reviews."""
import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("source_endpoints") as batch:
        batch.add_column(sa.Column("adapter_config", sa.Text(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("max_failures", sa.Integer(), nullable=False, server_default="3"))
        batch.add_column(sa.Column("scheduled", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("manual_takeover", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("paused_reason", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("last_error", sa.String(500), nullable=False, server_default=""))
        batch.create_index("ix_source_endpoints_next_run_at", ["next_run_at"])
        batch.create_index("ix_source_endpoints_scheduled", ["scheduled"])
        batch.create_index("ix_source_endpoints_manual_takeover", ["manual_takeover"])

    op.create_table(
        "source_endpoint_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("endpoint_id", sa.String(36), nullable=False),
        sa.Column("source_item_id", sa.String(160), nullable=False, server_default="default"),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_token", sa.String(36), nullable=True),
        sa.Column("document_version_id", sa.String(36), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("error", sa.String(500), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    for column in ("endpoint_id", "status", "ready_at", "document_version_id"):
        op.create_index(f"ix_source_endpoint_runs_{column}", "source_endpoint_runs", [column])

    op.create_table(
        "source_change_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("endpoint_id", sa.String(36), nullable=False),
        sa.Column("document_version_id", sa.String(36), nullable=False),
        sa.Column("risk_level", sa.String(20), nullable=False, server_default="high"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("changed_fields", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_by", sa.String(80), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("document_version_id", name="uq_source_change_document"),
    )
    for column in ("endpoint_id", "document_version_id", "risk_level", "status"):
        op.create_index(f"ix_source_change_reviews_{column}", "source_change_reviews", [column])


def downgrade():
    op.drop_table("source_change_reviews")
    op.drop_table("source_endpoint_runs")
    with op.batch_alter_table("source_endpoints") as batch:
        batch.drop_index("ix_source_endpoints_manual_takeover")
        batch.drop_index("ix_source_endpoints_scheduled")
        batch.drop_index("ix_source_endpoints_next_run_at")
        for column in ("last_error", "paused_reason", "manual_takeover", "scheduled", "max_failures",
                       "next_run_at", "last_attempt_at", "adapter_config"):
            batch.drop_column(column)

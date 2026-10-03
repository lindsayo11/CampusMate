"""Durable allowlisted collection sources and runs."""
import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("collection_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("url", sa.String(500), nullable=False, unique=True),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("format", sa.String(10), nullable=False),
        sa.Column("interval_minutes", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("permission_note", sa.String(500), nullable=False))
    op.create_table("collection_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(36), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_token", sa.String(36), nullable=True),
        sa.Column("document_id", sa.String(36), nullable=True),
        sa.Column("byte_hash", sa.String(64), nullable=True),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_collection_runs_source_id", "collection_runs", ["source_id"])
    op.create_index("ix_collection_runs_status", "collection_runs", ["status"])


def downgrade():
    op.drop_index("ix_collection_runs_status", table_name="collection_runs")
    op.drop_index("ix_collection_runs_source_id", table_name="collection_runs")
    op.drop_table("collection_runs")
    op.drop_table("collection_sources")

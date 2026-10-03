"""Add reviewable SourceRegistry candidates discovered from official directories."""
import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "source_registry_candidates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("discovery_source_id", sa.String(36), nullable=False),
        sa.Column("document_version_id", sa.String(36), nullable=False),
        sa.Column("source_code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("region_code", sa.String(20), nullable=False),
        sa.Column("base_url", sa.String(500), nullable=False),
        sa.Column("authority_level", sa.String(4), nullable=False, server_default="A+"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("evidence_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_by", sa.String(80), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("document_version_id", "base_url", name="uq_source_candidate_document_url"),
    )
    for column in ("discovery_source_id", "document_version_id", "source_code", "region_code",
                   "status", "evidence_id"):
        op.create_index(f"ix_source_registry_candidates_{column}",
                        "source_registry_candidates", [column])


def downgrade():
    op.drop_table("source_registry_candidates")

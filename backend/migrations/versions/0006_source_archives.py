"""Immutable source snapshots and rule evidence."""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("eligibility_rules", sa.Column("evidence", sa.Text(), nullable=False, server_default=""))
    op.create_table("source_heads", sa.Column("url_hash", sa.String(64), primary_key=True),
                    sa.Column("source_url", sa.String(500), nullable=False), sa.Column("document_id", sa.String(36), nullable=True))
    op.create_table("source_documents", sa.Column("id", sa.String(36), primary_key=True),
                    sa.Column("source_url", sa.String(500), nullable=False),
                    sa.Column("content_hash", sa.String(64), nullable=False),
                    sa.Column("raw_text", sa.Text(), nullable=False),
                    sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
                    sa.Column("archived_at", sa.DateTime(timezone=True), nullable=False),
                    sa.Column("previous_id", sa.String(36), nullable=True))
    op.create_index("ix_source_documents_source_url", "source_documents", ["source_url"])
    op.create_table("source_extractions", sa.Column("id", sa.String(64), primary_key=True),
                    sa.Column("document_id", sa.String(36), nullable=False),
                    sa.Column("review_id", sa.Integer(), nullable=False), sa.UniqueConstraint("review_id"))
    op.create_index("ix_source_extractions_document_id", "source_extractions", ["document_id"])


def downgrade():
    op.drop_table("source_extractions")
    op.drop_table("source_documents")
    op.drop_table("source_heads")
    with op.batch_alter_table("eligibility_rules") as batch:
        batch.drop_column("evidence")

"""Store source-version-bound AI summaries."""

import sqlalchemy as sa
from alembic import op

 = "0039"
 = "0038"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "document_insights",
        sa.Column("document_id", sa.String(length=36), primary_key=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("keywords", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("model", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("error", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_document_insights_status", "document_insights", ["status"])


def downgrade():
    op.drop_index("ix_document_insights_status", table_name="document_insights")
    op.drop_table("document_insights")

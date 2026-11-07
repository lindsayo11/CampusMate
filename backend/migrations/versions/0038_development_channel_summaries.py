"""Persist AI summaries aggregated by development channel."""

import sqlalchemy as sa
from alembic import op

 = "0038"
 = "0037"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "development_channel_summaries",
        sa.Column("path_code", sa.String(length=80), primary_key=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("fingerprint", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("payload", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("model", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("error", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_development_channel_summaries_status", "development_channel_summaries", ["status"])
    op.create_index("ix_development_channel_summaries_fingerprint", "development_channel_summaries", ["fingerprint"])


def downgrade():
    op.drop_index("ix_development_channel_summaries_fingerprint", table_name="development_channel_summaries")
    op.drop_index("ix_development_channel_summaries_status", table_name="development_channel_summaries")
    op.drop_table("development_channel_summaries")

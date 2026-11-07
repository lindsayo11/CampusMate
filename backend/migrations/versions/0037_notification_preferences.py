"""Persist notification display preferences per authenticated user."""

import sqlalchemy as sa
from alembic import op

 = "0037"
 = "0036"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "notification_preferences",
        sa.Column("user_id", sa.String(length=80), primary_key=True),
        sa.Column("source_updates", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("notification_preferences")

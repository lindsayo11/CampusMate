"""Add activity-linked teams and captain-approved join requests; keep old teams."""
from alembic import op
import sqlalchemy as sa

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("activity_teams",
        sa.Column("team_id", sa.String(36), primary_key=True),
        sa.Column("publication_id", sa.String(36), nullable=False),
        sa.Column("item_id", sa.String(64), nullable=False),
        sa.Column("recruiting", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_activity_teams_publication_id", "activity_teams", ["publication_id"])
    op.create_index("ix_activity_teams_item_id", "activity_teams", ["item_id"])
    op.create_table("team_join_requests",
        sa.Column("team_id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(80), primary_key=True),
        sa.Column("id", sa.String(36), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("message", sa.String(300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))


def downgrade():
    op.drop_table("team_join_requests")
    op.drop_index("ix_activity_teams_item_id", table_name="activity_teams")
    op.drop_index("ix_activity_teams_publication_id", table_name="activity_teams")
    op.drop_table("activity_teams")

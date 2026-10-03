"""Team task assignments and optimistic edit versions."""
import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("team_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("team_id", sa.String(36), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("assignee", sa.String(80), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(80), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_team_tasks_team_id", "team_tasks", ["team_id"])


def downgrade():
    op.drop_index("ix_team_tasks_team_id", table_name="team_tasks")
    op.drop_table("team_tasks")

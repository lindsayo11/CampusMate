"""Idempotent deadline alerts for team tasks."""
import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("task_alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dedup_key", sa.String(64), nullable=False, unique=True),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(80), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_task_alerts_task_id", "task_alerts", ["task_id"])
    op.create_index("ix_task_alerts_user_id", "task_alerts", ["user_id"])


def downgrade():
    op.drop_index("ix_task_alerts_user_id", table_name="task_alerts")
    op.drop_index("ix_task_alerts_task_id", table_name="task_alerts")
    op.drop_table("task_alerts")

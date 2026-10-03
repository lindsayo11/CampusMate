"""Per-member monotonic read cursors."""
import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("room_reads",
        sa.Column("room_id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(80), primary_key=True),
        sa.Column("last_message_id", sa.Integer(), nullable=False))


def downgrade():
    op.drop_table("room_reads")

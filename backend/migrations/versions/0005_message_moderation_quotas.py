"""Message moderation and cross-room account quotas."""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("room_messages", sa.Column("hidden", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("message_reports", sa.Column("status", sa.String(20), nullable=False, server_default="pending"))
    op.add_column("message_reports", sa.Column("decision_note", sa.Text(), nullable=True))
    op.add_column("message_reports", sa.Column("resolved_by", sa.String(80), nullable=True))
    op.add_column("message_reports", sa.Column("resolved_at", sa.String(40), nullable=True))
    op.create_table("social_quotas", sa.Column("key", sa.String(180), primary_key=True),
                    sa.Column("window", sa.Integer(), nullable=False), sa.Column("count", sa.Integer(), nullable=False))


def downgrade():
    op.drop_table("social_quotas")
    with op.batch_alter_table("message_reports") as batch:
        for name in ["status", "decision_note", "resolved_by", "resolved_at"]:
            batch.drop_column(name)
    with op.batch_alter_table("room_messages") as batch:
        batch.drop_column("hidden")

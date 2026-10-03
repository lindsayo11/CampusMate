"""Worker liveness persisted independently of request traffic."""
from alembic import op
import sqlalchemy as sa
revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("worker_heartbeats", sa.Column("name", sa.String(40), primary_key=True),
                    sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
                    sa.Column("state", sa.String(20), nullable=False))


def downgrade():
    op.drop_table("worker_heartbeats")

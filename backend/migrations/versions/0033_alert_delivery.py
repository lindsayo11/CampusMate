"""Durable, deduplicated external alert delivery."""
import sqlalchemy as sa
from alembic import op
revision='0033'
down_revision = '0032'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('collection_alert_deliveries',
        sa.Column('key',sa.String(64),primary_key=True),sa.Column('alert_key',sa.String(160),nullable=False),
        sa.Column('status',sa.String(20),nullable=False),sa.Column('message',sa.String(500),nullable=False),
        sa.Column('state',sa.String(20),nullable=False),sa.Column('attempts',sa.Integer(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('next_attempt_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('delivered_at',sa.DateTime(timezone=True)),sa.Column('lease_until',sa.DateTime(timezone=True)),
        sa.Column('error',sa.String(160),nullable=False))
    for column in ('alert_key','state','next_attempt_at'):
        op.create_index('ix_collection_alert_deliveries_'+column,'collection_alert_deliveries',[column])


def downgrade():op.drop_table('collection_alert_deliveries')

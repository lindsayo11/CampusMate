"""Successful check times, private failed responses and durable collection alerts."""
import sqlalchemy as sa
from alembic import op
revision = '0031'
down_revision = '0028'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('notice_resources', sa.Column('last_success_at', sa.DateTime(timezone=True)))
    # Infer only unequivocally successful historic checks, not failed attempts.
    op.execute("UPDATE notice_resources SET last_success_at=checked_at WHERE error='' AND content_hash<>''")
    op.create_table('collection_attempts',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('resource_id',sa.String(36),nullable=False),
        sa.Column('endpoint_id',sa.String(36),nullable=False),
        sa.Column('observed_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('outcome',sa.String(30),nullable=False),
        sa.Column('error',sa.String(500),nullable=False),
        sa.Column('content_hash',sa.String(64),nullable=False),
        sa.Column('content_type',sa.String(160),nullable=False),
        sa.Column('content',sa.LargeBinary(),nullable=True))
    for key in ('resource_id','endpoint_id','observed_at'):
        op.create_index('ix_collection_attempts_'+key,'collection_attempts',[key])
    op.create_table('collection_alerts',
        sa.Column('key',sa.String(160),primary_key=True),
        sa.Column('endpoint_id',sa.String(36)),
        sa.Column('status',sa.String(20),nullable=False),
        sa.Column('message',sa.String(500),nullable=False),
        sa.Column('first_seen_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('last_seen_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('resolved_at',sa.DateTime(timezone=True)))
    op.create_index('ix_collection_alerts_status','collection_alerts',['status'])


def downgrade():
    op.drop_table('collection_alerts')
    op.drop_table('collection_attempts')
    op.drop_column('notice_resources','last_success_at')

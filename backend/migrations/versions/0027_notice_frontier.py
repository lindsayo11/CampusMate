"""Persistent public-notice discovery and conditional rechecks."""
import sqlalchemy as sa
from alembic import op
revision = '0027'
down_revision = '0026'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('notice_resources',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('endpoint_id',sa.String(36),nullable=False),
        sa.Column('url',sa.String(500),nullable=False),
        sa.Column('title',sa.String(240),nullable=False),
        sa.Column('kind',sa.String(20),nullable=False),
        sa.Column('parent_url',sa.String(500),nullable=False),
        sa.Column('depth',sa.Integer(),nullable=False),
        sa.Column('status',sa.String(30),nullable=False),
        sa.Column('etag',sa.String(500),nullable=True),
        sa.Column('last_modified',sa.String(200),nullable=True),
        sa.Column('content_hash',sa.String(64),nullable=False),
        sa.Column('document_id',sa.String(36),nullable=True),
        sa.Column('discovered_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('checked_at',sa.DateTime(timezone=True),nullable=True),
        sa.Column('changed_at',sa.DateTime(timezone=True),nullable=True),
        sa.Column('next_check_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('lease_until',sa.DateTime(timezone=True),nullable=True),
        sa.Column('lease_token',sa.String(36),nullable=True),
        sa.Column('failures',sa.Integer(),nullable=False),
        sa.Column('error',sa.String(500),nullable=False),
        sa.UniqueConstraint('endpoint_id','url',name='uq_notice_resource_url'))
    op.create_index('ix_notice_resources_endpoint_id','notice_resources',['endpoint_id'])
    op.create_index('ix_notice_resources_next_check_at','notice_resources',['next_check_at'])

def downgrade():
    op.drop_table('notice_resources')

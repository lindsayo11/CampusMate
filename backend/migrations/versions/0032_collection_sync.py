"""Public-original exchange state; no personal or review data is transferred."""
import sqlalchemy as sa
from alembic import op
revision='0032'
down_revision = '0031'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('collection_sync_states',
        sa.Column('name',sa.String(40),primary_key=True),
        sa.Column('last_checked_at',sa.DateTime(timezone=True)),
        sa.Column('last_success_at',sa.DateTime(timezone=True)),
        sa.Column('state',sa.String(20),nullable=False),
        sa.Column('pulled',sa.Integer(),nullable=False),sa.Column('pushed',sa.Integer(),nullable=False),
        sa.Column('pending',sa.Integer(),nullable=False),sa.Column('error',sa.String(500),nullable=False),
        sa.Column('lease_until',sa.DateTime(timezone=True)))
    op.create_table('collection_sync_records',
        sa.Column('key',sa.String(100),primary_key=True),
        sa.Column('document_id',sa.String(36)),sa.Column('content_hash',sa.String(64),nullable=False),
        sa.Column('state',sa.String(30),nullable=False),sa.Column('error',sa.String(500),nullable=False),
        sa.Column('observed_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_collection_sync_records_document_id','collection_sync_records',['document_id'])


def downgrade():
    op.drop_table('collection_sync_records')
    op.drop_table('collection_sync_states')

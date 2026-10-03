"""Private student feedback with an administrator resolution trail."""
import sqlalchemy as sa
from alembic import op
revision = '0026'
down_revision = '0025'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('data_corrections',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.String(80), nullable=False),
        sa.Column('publication_id', sa.String(36), nullable=False),
        sa.Column('category', sa.String(30), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('review_note', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_data_corrections_user_id','data_corrections',['user_id'])
    op.create_index('ix_data_corrections_publication_id','data_corrections',['publication_id'])


def downgrade():
    op.drop_table('data_corrections')

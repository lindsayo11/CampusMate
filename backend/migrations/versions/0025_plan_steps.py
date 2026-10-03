"""Persist a student's personal preparation checklist without altering existing plans."""
import sqlalchemy as sa
from alembic import op
revision = '0025'
down_revision = '0024'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('plan_steps',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('plan_id', sa.Integer(), sa.ForeignKey('user_plans.id'), nullable=False),
        sa.Column('title', sa.String(300), nullable=False),
        sa.Column('done', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('plan_id', 'title'))
    op.create_index('ix_plan_steps_plan_id', 'plan_steps', ['plan_id'])


def downgrade():
    op.drop_table('plan_steps')

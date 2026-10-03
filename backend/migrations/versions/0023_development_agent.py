"""Durable development-assistant conversation and personal plan reminders."""
import sqlalchemy as sa
from alembic import op
revision = '0023'
down_revision = '0022'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('agent_conversations', sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('user_id',sa.String(80),nullable=False), sa.Column('title',sa.String(160),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_agent_conversations_user_id','agent_conversations',['user_id'])
    op.create_table('agent_turns',sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('conversation_id',sa.String(36),nullable=False),sa.Column('query',sa.Text(),nullable=False),
        sa.Column('response',sa.Text(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_agent_turns_conversation_id','agent_turns',['conversation_id'])
    op.create_table('plan_reminders',sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('user_id',sa.String(80),nullable=False),sa.Column('plan_id',sa.Integer(),nullable=False),
        sa.Column('due_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('delivered_at',sa.DateTime(timezone=True),nullable=True),
        sa.Column('read_at',sa.DateTime(timezone=True),nullable=True),sa.Column('status',sa.String(20),nullable=False))
    op.create_index('ix_plan_reminders_user_id','plan_reminders',['user_id'])
    op.create_index('ix_plan_reminders_plan_id','plan_reminders',['plan_id'])


def downgrade():
    op.drop_table('plan_reminders')
    op.drop_table('agent_turns')
    op.drop_table('agent_conversations')

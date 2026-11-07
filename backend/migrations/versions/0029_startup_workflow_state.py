"""Persist the thirteen-step entrepreneurship workflow per project."""
import sqlalchemy as sa
from alembic import op

revision = '0029'
down_revision = '0028'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if 'workflow_json' not in {column['name'] for column in inspector.get_columns('startup_projects')}:
        op.add_column('startup_projects', sa.Column('workflow_json', sa.Text(), nullable=False, server_default='{}'))


def downgrade():
    op.drop_column('startup_projects', 'workflow_json')

"""Private startup workspace and document history."""
import sqlalchemy as sa
from alembic import op
revision = '0028'
down_revision = '0027'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('startup_projects',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('user_id',sa.String(80),nullable=False),
        sa.Column('name',sa.String(160),nullable=False),
        sa.Column('brief_json',sa.Text(),nullable=False),
        sa.Column('revision',sa.Integer(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_startup_projects_user_id','startup_projects',['user_id'])
    op.create_table('startup_artifacts',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('project_id',sa.String(36),sa.ForeignKey('startup_projects.id'),nullable=False),
        sa.Column('kind',sa.String(40),nullable=False),
        sa.Column('version',sa.Integer(),nullable=False),
        sa.Column('project_revision',sa.Integer(),nullable=False),
        sa.Column('title',sa.String(200),nullable=False),
        sa.Column('markdown',sa.Text(),nullable=False),
        sa.Column('sources_json',sa.Text(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('project_id','kind','version',name='uq_startup_artifact_version'))
    op.create_index('ix_startup_artifacts_project_id','startup_artifacts',['project_id'])


def downgrade():
    op.drop_table('startup_artifacts')
    op.drop_table('startup_projects')

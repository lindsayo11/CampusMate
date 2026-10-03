"""Align development path status index with the ORM model."""
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

def upgrade():
    op.create_index("ix_development_paths_status", "development_paths", ["status"])

def downgrade():
    op.drop_index("ix_development_paths_status", table_name="development_paths")

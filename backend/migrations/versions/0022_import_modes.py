"""Distinguish server ingestion, manual uploads and retained demo batches."""
import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('document_versions') as batch:
        batch.add_column(sa.Column('import_mode', sa.String(20), nullable=False, server_default='manual'))
        batch.add_column(sa.Column('test_batch', sa.String(80), nullable=True))
        batch.add_column(sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE document_versions SET import_mode='system' WHERE id IN "
               "(SELECT document_version_id FROM source_endpoint_runs WHERE status IN ('succeeded','unchanged'))")


def downgrade():
    with op.batch_alter_table('document_versions') as batch:
        batch.drop_column('deleted_at')
        batch.drop_column('test_batch')
        batch.drop_column('import_mode')

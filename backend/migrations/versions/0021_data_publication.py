"""Raw archives, calibration proof and immutable data publication snapshots."""
import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("source_endpoint_calibrations") as batch:
        batch.add_column(sa.Column("proof", sa.Text(), nullable=False, server_default="{}"))
    op.create_table("document_archives",
        sa.Column("document_id", sa.String(36), primary_key=True),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("content_type", sa.String(160), nullable=False),
        sa.Column("is_fixture", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table("data_publications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("document_id", sa.String(36), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("snapshot", sa.Text(), nullable=False),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("submitted_by", sa.String(80), nullable=False),
        sa.Column("first_reviewed_by", sa.String(80), nullable=True),
        sa.Column("second_reviewed_by", sa.String(80), nullable=True),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_data_publications_status", "data_publications", ["status"])
    op.create_table("data_subscriptions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(80), nullable=False),
        sa.Column("item_id", sa.String(64), nullable=False),
        sa.Column("publication_id", sa.String(36), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("remind_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("alerted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.UniqueConstraint("user_id", "item_id", name="uq_data_subscription_user_item"))
    op.create_index("ix_data_subscriptions_user_id", "data_subscriptions", ["user_id"])
    # Prior approvals did not retain supporting proof. They must be revalidated.
    op.execute("UPDATE source_endpoints SET scheduled = false, next_run_at = NULL")


def downgrade():
    op.drop_table("data_subscriptions")
    op.drop_table("data_publications")
    op.drop_table("document_archives")
    with op.batch_alter_table("source_endpoint_calibrations") as batch:
        batch.drop_column("proof")

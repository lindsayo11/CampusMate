"""Add two-person endpoint calibration gate."""
import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "source_endpoint_calibrations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("endpoint_id", sa.String(36), nullable=False),
        sa.Column("exact_url", sa.String(500), nullable=False),
        sa.Column("robots_status", sa.String(20), nullable=False),
        sa.Column("terms_status", sa.String(20), nullable=False),
        sa.Column("license_status", sa.String(20), nullable=False),
        sa.Column("field_mapping", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("adapter_config", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_by", sa.String(80), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("first_reviewed_by", sa.String(80), nullable=True),
        sa.Column("first_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("second_reviewed_by", sa.String(80), nullable=True),
        sa.Column("second_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("endpoint_id", "robots_status", "terms_status", "license_status", "status"):
        op.create_index(
            f"ix_source_endpoint_calibrations_{column}",
            "source_endpoint_calibrations",
            [column],
        )


def downgrade():
    op.drop_table("source_endpoint_calibrations")

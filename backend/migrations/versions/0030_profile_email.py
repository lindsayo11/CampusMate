"""Store the authenticated email for exact teammate lookup."""

import sqlalchemy as sa
from alembic import op


revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("profiles")}
    if "email" not in columns:
        op.add_column("profiles", sa.Column("email", sa.String(length=320), nullable=True))
    indexes = {index["name"] for index in inspector.get_indexes("profiles")}
    if "ix_profiles_email" not in indexes:
        op.create_index("ix_profiles_email", "profiles", ["email"], unique=False)


def downgrade():
    inspector = sa.inspect(op.get_bind())
    indexes = {index["name"] for index in inspector.get_indexes("profiles")}
    if "ix_profiles_email" in indexes:
        op.drop_index("ix_profiles_email", table_name="profiles")
    columns = {column["name"] for column in inspector.get_columns("profiles")}
    if "email" in columns:
        op.drop_column("profiles", "email")

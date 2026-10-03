"""Add graduation development paths, enhanced profiles and personal plans."""
import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("profiles", sa.Column("degree", sa.String(40), nullable=False, server_default="本科"))
    op.add_column("profiles", sa.Column("target_year", sa.Integer(), nullable=True))
    for name in ("target_path", "target_region", "language_score"):
        op.add_column("profiles", sa.Column(name, sa.String(80), nullable=False, server_default=""))
    for name in ("research_exp", "internship_exp", "competition_exp", "startup_exp"):
        op.add_column("profiles", sa.Column(name, sa.Text(), nullable=False, server_default=""))
    op.create_table("development_paths", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(60), nullable=False, unique=True), sa.Column("description", sa.Text(), nullable=False),
        sa.Column("target_group", sa.String(120), nullable=False, server_default="本科生"),
        sa.Column("duration", sa.String(80), nullable=False, server_default=""), sa.Column("status", sa.String(20), nullable=False, server_default="published"))
    op.create_table("timeline_nodes", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("path_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(120), nullable=False), sa.Column("month", sa.String(30), nullable=False, server_default=""),
        sa.Column("grade", sa.String(30), nullable=False, server_default=""), sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("importance", sa.String(20), nullable=False, server_default="normal"))
    op.create_index("ix_timeline_nodes_path_id", "timeline_nodes", ["path_id"])
    op.create_table("user_plans", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("user_id", sa.String(80), nullable=False),
        sa.Column("path_id", sa.Integer(), nullable=True), sa.Column("title", sa.String(160), nullable=False), sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="todo"), sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_user_plans_user_id", "user_plans", ["user_id"])

def downgrade():
    op.drop_index("ix_user_plans_user_id", table_name="user_plans"); op.drop_table("user_plans")
    op.drop_index("ix_timeline_nodes_path_id", table_name="timeline_nodes"); op.drop_table("timeline_nodes"); op.drop_table("development_paths")
    for name in ("startup_exp", "competition_exp", "internship_exp", "research_exp", "language_score", "target_region", "target_path", "target_year", "degree"):
        op.drop_column("profiles", name)

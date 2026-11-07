"""Allow official opportunity portals without a stated deadline."""

import sqlalchemy as sa
from alembic import op

 = "0036"
 = "0035"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("opportunities", recreate="always") as batch:
        batch.alter_column("deadline", existing_type=sa.DateTime(timezone=True), nullable=True)


def downgrade():
    with op.batch_alter_table("opportunities", recreate="always") as batch:
        batch.alter_column("deadline", existing_type=sa.DateTime(timezone=True), nullable=False)

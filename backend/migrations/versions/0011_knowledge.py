"""Traceable chunks, explicit public access, and links to approved opportunities."""
import json

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("document_chunks",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("document_id", sa.String(36), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False))
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
    op.create_table("knowledge_access",
        sa.Column("document_id", sa.String(36), primary_key=True),
        sa.Column("public", sa.Boolean(), nullable=False))
    op.create_table("knowledge_publications",
        sa.Column("opportunity_id", sa.String(40), primary_key=True),
        sa.Column("document_id", sa.String(36), nullable=False),
        sa.Column("review_id", sa.Integer(), nullable=False))
    op.create_index("ix_knowledge_publications_document_id", "knowledge_publications", ["document_id"])
    # Restore existing archive→review→opportunity links from the deterministic approval audit.
    # No existing raw source becomes public automatically. Chunks are built on explicit access grant.
    bind = op.get_bind()
    extractions = dict(bind.execute(sa.text("SELECT review_id, document_id FROM source_extractions")).all())
    opportunities = set(bind.execute(sa.text("SELECT id FROM opportunities")).scalars())
    seen = set()
    for resource, detail in bind.execute(sa.text("SELECT resource, detail FROM audit_events WHERE action='approve' ORDER BY id")):
        try:
            review_id = int(resource.removeprefix("review:"))
            oid = json.loads(detail)["opportunity_id"]
        except (ValueError, KeyError, TypeError):
            continue
        if review_id in extractions and oid in opportunities and oid not in seen:
            bind.execute(sa.text("INSERT INTO knowledge_publications (opportunity_id, document_id, review_id) VALUES (:oid,:doc,:rid)"),
                         {"oid": oid, "doc": extractions[review_id], "rid": review_id})
            seen.add(oid)


def downgrade():
    op.drop_index("ix_knowledge_publications_document_id", table_name="knowledge_publications")
    op.drop_table("knowledge_publications")
    op.drop_table("knowledge_access")
    op.drop_index("ix_document_chunks_document_id", table_name="document_chunks")
    op.drop_table("document_chunks")

"""System-ingested documents reach the knowledge base without human review.

Why the old shape blocked system ingestion
------------------------------------------
`knowledge_publications` used `opportunity_id` as its primary key, and
`visible_statement()` inner-joined both `ReviewItem` (status must be
'approved') and `Opportunity` (must be published with a future deadline).
A system-collected policy document has no opportunity card and no review
record, so it could never satisfy the predicate - it stayed invisible no
matter how the review policy was configured.

That also explains why the two collectors behaved differently:
`collector.py` archives into `source_documents` and goes through the
editorial review flow, while `source_scheduler.py` writes `document_versions`
and never touched the knowledge tables at all.

New shape
---------
`document_id` becomes the primary key (one publication state per document -
a document is either publicly searchable or not), and `source` records which
path produced it:

    editorial  human import -> still requires approved review + live opportunity
    system     governed auto-collection -> no human review, publish immediately

`title` / `item_type` are stored for the system path so a search result can
be rendered without inventing an opportunity card.
"""
import sqlalchemy as sa
from alembic import op

revision = '0024'
down_revision = '0023'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('knowledge_publications_new',
        sa.Column('document_id', sa.String(36), primary_key=True),
        sa.Column('source', sa.String(20), nullable=False, server_default='editorial'),
        sa.Column('opportunity_id', sa.String(40), nullable=True),
        sa.Column('review_id', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(160), nullable=False, server_default=''),
        sa.Column('item_type', sa.String(20), nullable=False, server_default=''))
    # A document could previously hold one row per opportunity; the new key allows
    # only one, so collapse to the earliest opportunity per document.
    op.execute(
        "INSERT INTO knowledge_publications_new "
        "(document_id, source, opportunity_id, review_id, title, item_type) "
        "SELECT document_id, 'editorial', MIN(opportunity_id), MIN(review_id), '', '' "
        "FROM knowledge_publications GROUP BY document_id")
    op.drop_table('knowledge_publications')
    op.rename_table('knowledge_publications_new', 'knowledge_publications')
    op.create_index('ix_knowledge_publications_source', 'knowledge_publications', ['source'])


def downgrade():
    op.create_table('knowledge_publications_old',
        sa.Column('opportunity_id', sa.String(40), primary_key=True),
        sa.Column('document_id', sa.String(36), nullable=False),
        sa.Column('review_id', sa.Integer(), nullable=False))
    op.execute(
        "INSERT INTO knowledge_publications_old (opportunity_id, document_id, review_id) "
        "SELECT opportunity_id, document_id, review_id FROM knowledge_publications "
        "WHERE source = 'editorial' AND opportunity_id IS NOT NULL AND review_id IS NOT NULL")
    op.drop_table('knowledge_publications')
    op.rename_table('knowledge_publications_old', 'knowledge_publications')
    op.create_index('ix_knowledge_publications_document_id', 'knowledge_publications', ['document_id'])

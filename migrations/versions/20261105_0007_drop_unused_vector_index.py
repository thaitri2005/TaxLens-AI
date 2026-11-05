"""drop the HNSW index on document embeddings

Revision ID: 20261105_0007
Revises: 20261105_0006
Create Date: 2026-11-05

Vector search scans every embedding so that it stays exact, and pg_stat_user_indexes showed
one scan of this index ever. It took 121 MB of a 605 MB database and slowed every embedding
insert.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261105_0007"
down_revision: str | Sequence[str] | None = "20261105_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_embeddings_cosine")


def downgrade() -> None:
    op.execute(
        "CREATE INDEX ix_document_embeddings_cosine "
        "ON document_embeddings USING hnsw (embedding vector_cosine_ops)"
    )

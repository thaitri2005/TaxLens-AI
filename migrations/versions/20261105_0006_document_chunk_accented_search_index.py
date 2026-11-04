"""index the accented search vector

Revision ID: 20261105_0006
Revises: 20261017_0005
Create Date: 2026-11-05

Keyword retrieval counts each query term's matches from the GIN indexes instead of reading
every chunk's stored vector, so the accented vector needs an index as the folded one has.
IF NOT EXISTS because the index may be built by hand on a live database first.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261105_0006"
down_revision: str | Sequence[str] | None = "20261017_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_document_chunks_search_vector "
        "ON document_chunks USING gin (search_vector)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_search_vector")

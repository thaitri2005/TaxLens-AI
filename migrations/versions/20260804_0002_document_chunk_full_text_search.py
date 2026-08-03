"""add document chunk full-text search index

Revision ID: 20260804_0002
Revises: 20260803_0001
Create Date: 2026-08-04
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260804_0002"
down_revision: str | Sequence[str] | None = "20260803_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX ix_document_chunks_full_text "
        "ON document_chunks USING gin "
        "(to_tsvector('simple'::regconfig, coalesce(heading, '') || ' ' || content))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_full_text")

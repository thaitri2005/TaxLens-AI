"""add document embeddings

Revision ID: 20260804_0003
Revises: 20260804_0002
Create Date: 2026-08-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260804_0003"
down_revision: str | Sequence[str] | None = "20260804_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_embeddings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "document_chunk_id",
            sa.Uuid(),
            sa.ForeignKey("document_chunks.id"),
            nullable=False,
        ),
        sa.Column("model_id", sa.String(length=255), nullable=False),
        sa.Column("model_revision", sa.String(length=64), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "document_chunk_id",
            "model_id",
            "model_revision",
            name="uq_document_embedding_model_revision",
        ),
    )
    op.execute(
        "ALTER TABLE document_embeddings ALTER COLUMN embedding "
        "TYPE vector(384) USING embedding::vector"
    )
    op.execute(
        "CREATE INDEX ix_document_embeddings_cosine "
        "ON document_embeddings USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.drop_index("ix_document_embeddings_cosine", table_name="document_embeddings")
    op.drop_table("document_embeddings")

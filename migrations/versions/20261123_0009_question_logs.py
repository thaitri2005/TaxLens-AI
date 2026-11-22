"""log questions asked on the site and the askers' ratings

Revision ID: 20261123_0009
Revises: 20261123_0008
Create Date: 2026-11-23

Real questions and thumbs-up or thumbs-down ratings become candidates for the gold set
(scripts/export_question_log.py).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261123_0009"
down_revision: str | Sequence[str] | None = "20261123_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "question_logs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("user_accounts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("intent", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("evidence_status", sa.String(length=40), nullable=True),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("cited_documents", sa.JSON(), nullable=False),
        sa.Column("seconds", sa.Float(), nullable=False),
        sa.Column("rating", sa.SmallInteger(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("rated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_question_logs_user_id", "question_logs", ["user_id"])
    op.create_index("ix_question_logs_created_at", "question_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_question_logs_created_at", table_name="question_logs")
    op.drop_index("ix_question_logs_user_id", table_name="question_logs")
    op.drop_table("question_logs")

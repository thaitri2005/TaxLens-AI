"""record when a document ends, and on what basis

Revision ID: 20261123_0008
Revises: 20261105_0007
Create Date: 2026-11-23

Search and answers leave out documents whose end is confirmed (an explicit repeal or the
Ministry of Finance's expiry date) and flag those whose end is only inferred. The columns
stay empty until scripts/apply_document_endings.py loads a repeal list.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261123_0008"
down_revision: str | Sequence[str] | None = "20261105_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("legal_documents", sa.Column("ended_on", sa.Date(), nullable=True))
    op.add_column("legal_documents", sa.Column("end_basis", sa.String(length=20), nullable=True))
    op.add_column("legal_documents", sa.Column("ended_by", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("legal_documents", "ended_by")
    op.drop_column("legal_documents", "end_basis")
    op.drop_column("legal_documents", "ended_on")

"""store document chunk full-text search vectors, with and without diacritics

Revision ID: 20261017_0005
Revises: 20260807_0004
Create Date: 2026-10-17

Keyword retrieval ranks every chunk that matches any query term, so the search vectors
are stored instead of being recomputed from chunk text per row. The folded vector strips
Vietnamese diacritics with translate() (no extension needed), so queries typed without
accents and OCR text that lost accents still match.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261017_0005"
down_revision: str | Sequence[str] | None = "20260807_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen copy of taxlens.retrieval.text.VIETNAMESE_ACCENTED / VIETNAMESE_UNACCENTED.
_ACCENTED = (
    "AàÀáÁãÃảẢạẠăĂằẰắẮẵẴẳẲặẶâÂầẦấẤẫẪẩẨậẬEèÈéÉẽẼẻẺẹẸêÊềỀếẾễỄểỂệỆIìÌíÍĩĨỉỈịỊOòÒóÓõÕỏỎọỌôÔồỒốỐỗỖổỔộỘ"
    "ơƠờỜớỚỡỠởỞợỢUùÙúÚũŨủỦụỤưƯừỪứỨữỮửỬựỰYỳỲýÝỹỸỷỶỵỴđĐ"
)
_UNACCENTED = (
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaeeeeeeeeeeeeeeeeeeeeeeeiiiiiiiiiiioooooooooooooooooooooo"
    "ooooooooooooouuuuuuuuuuuuuuuuuuuuuuuyyyyyyyyyyydd"
)
_SEARCHABLE_TEXT = "coalesce(heading, '') || ' ' || content"


def upgrade() -> None:
    op.execute(
        "ALTER TABLE document_chunks ADD COLUMN search_vector tsvector "
        f"GENERATED ALWAYS AS (to_tsvector('simple'::regconfig, {_SEARCHABLE_TEXT})) STORED"
    )
    op.execute(
        "ALTER TABLE document_chunks ADD COLUMN search_vector_folded tsvector "
        "GENERATED ALWAYS AS (to_tsvector('simple'::regconfig, "
        f"translate({_SEARCHABLE_TEXT}, '{_ACCENTED}', '{_UNACCENTED}'))) STORED"
    )
    op.execute(
        "CREATE INDEX ix_document_chunks_search_vector_folded "
        "ON document_chunks USING gin (search_vector_folded)"
    )
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_full_text")


def downgrade() -> None:
    op.execute(
        "CREATE INDEX ix_document_chunks_full_text "
        f"ON document_chunks USING gin (to_tsvector('simple'::regconfig, {_SEARCHABLE_TEXT}))"
    )
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_search_vector_folded")
    op.execute("ALTER TABLE document_chunks DROP COLUMN search_vector_folded")
    op.execute("ALTER TABLE document_chunks DROP COLUMN search_vector")

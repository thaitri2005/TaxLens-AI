"""Remove documents that do not belong in the tax corpus.

Before the discovery tax filter existed, the daily crawl ingested every document on the
government portal (education, construction, trade, ...). This removes documents whose
titles fail the same filter, plus the English sample seed documents, from the database:
versions, passages, embeddings, processing jobs, and relationships. Raw PDFs and
normalized text stay in object storage. Documents in the curated manifest are always kept.

    python scripts/prune_non_tax_documents.py            # dry run: list only
    python scripts/prune_non_tax_documents.py --apply    # delete
"""

import argparse
import json
from pathlib import Path

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from taxlens.db import SessionLocal
from taxlens.ingestion.connectors import is_tax_title
from taxlens.legal_data.document_numbers import issuer_code
from taxlens.legal_data.models import (
    DocumentChunk,
    DocumentEmbedding,
    DocumentVersion,
    LegalDocument,
    LegalRelationship,
    ProcessingJob,
    SourceRecord,
)

CURATED_MANIFEST = Path("data/corpus/tax_documents.json")
SEED_SOURCE_NAME = "seed-corpus"
# Finance, tax, and customs documents are kept even when their stored title has no tax
# keyword: some were filed under the number of the circular they amend, with a truncated
# summary, and may still concern fees or invoices.
PROTECTED_ISSUER_CODES = frozenset({"BTC", "TCT", "TCHQ"})


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove non-tax documents from the corpus")
    parser.add_argument("--apply", action="store_true", help="Delete instead of listing")
    arguments = parser.parse_args()

    curated = _curated_document_numbers()
    with SessionLocal() as session:
        candidates = _documents_to_remove(session, curated)
        mode = "APPLY" if arguments.apply else "dry run"
        print(f"{len(candidates)} document(s) to remove ({mode}):")
        for document, reason in candidates:
            print(f"  {document.document_number} | {reason} | {document.title[:100]}")
        if not arguments.apply:
            total = session.scalar(select(func.count(LegalDocument.id))) or 0
            # Printed last: job logs keep only the end of the output.
            print(f"Dry run: {len(candidates)} of {total} document(s) would be removed.")
            return
        for document, _ in candidates:
            _delete_document(session, document)
            session.commit()
        remaining = session.scalar(select(func.count(LegalDocument.id))) or 0
    print(f"Removed {len(candidates)} document(s); {remaining} remain.")


def _curated_document_numbers() -> set[str]:
    if not CURATED_MANIFEST.is_file():
        return set()
    return {entry["document_number"] for entry in json.loads(CURATED_MANIFEST.read_text("utf-8"))}


def _documents_to_remove(
    session: Session, curated: set[str]
) -> list[tuple[LegalDocument, str]]:
    seed_documents = set(
        session.scalars(
            select(DocumentVersion.document_id)
            .join(SourceRecord, DocumentVersion.source_record_id == SourceRecord.id)
            .where(SourceRecord.source_name == SEED_SOURCE_NAME)
        ).all()
    )
    candidates: list[tuple[LegalDocument, str]] = []
    for document in session.scalars(
        select(LegalDocument).order_by(LegalDocument.document_number)
    ).all():
        if (
            document.document_number in curated
            or issuer_code(document.document_number) in PROTECTED_ISSUER_CODES
        ):
            continue
        if document.id in seed_documents:
            candidates.append((document, "sample seed document"))
        elif not is_tax_title(document.title, document.document_number):
            candidates.append((document, "not tax-related"))
    return candidates


def _delete_document(session: Session, document: LegalDocument) -> None:
    version_ids = list(
        session.scalars(
            select(DocumentVersion.id).where(DocumentVersion.document_id == document.id)
        ).all()
    )
    source_record_ids = {
        source_id
        for source_id in session.scalars(
            select(DocumentVersion.source_record_id).where(
                DocumentVersion.document_id == document.id
            )
        ).all()
        if source_id is not None
    }
    chunk_ids = select(DocumentChunk.id).where(DocumentChunk.document_version_id.in_(version_ids))
    session.execute(delete(DocumentEmbedding).where(DocumentEmbedding.document_chunk_id.in_(chunk_ids)))
    session.execute(delete(DocumentChunk).where(DocumentChunk.document_version_id.in_(version_ids)))
    session.execute(delete(ProcessingJob).where(ProcessingJob.document_version_id.in_(version_ids)))
    session.execute(
        delete(LegalRelationship).where(
            or_(
                LegalRelationship.source_version_id.in_(version_ids),
                LegalRelationship.target_document_id == document.id,
            )
        )
    )
    session.execute(delete(DocumentVersion).where(DocumentVersion.id.in_(version_ids)))
    session.execute(delete(LegalDocument).where(LegalDocument.id == document.id))
    for source_record_id in source_record_ids:
        still_used = session.scalar(
            select(func.count(DocumentVersion.id)).where(
                DocumentVersion.source_record_id == source_record_id
            )
        )
        if not still_used:
            session.execute(delete(SourceRecord).where(SourceRecord.id == source_record_id))


if __name__ == "__main__":
    main()

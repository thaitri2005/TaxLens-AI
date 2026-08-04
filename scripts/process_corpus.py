import argparse

from sqlalchemy import select

from taxlens.config import get_settings
from taxlens.db import SessionLocal
from taxlens.document_processing.process import process_document_version
from taxlens.legal_data.models import DocumentVersion
from taxlens.storage.local import LocalObjectStorage


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize and chunk pending TaxLens documents")
    parser.add_argument("--all", action="store_true", help="Reprocess every document version")
    arguments = parser.parse_args()

    storage = LocalObjectStorage(get_settings().local_storage_path)
    with SessionLocal() as session:
        query = select(DocumentVersion).order_by(DocumentVersion.created_at)
        if not arguments.all:
            query = query.where(DocumentVersion.normalized_content_hash.is_(None))
        versions = session.scalars(query).all()
        results = [process_document_version(session, storage, version) for version in versions]

    processed = sum(result.status == "PROCESSED" for result in results)
    unchanged = sum(result.status == "UNCHANGED" for result in results)
    failed = sum(result.status == "FAILED" for result in results)
    chunk_count = sum(result.chunk_count for result in results)
    print(
        f"Processing complete: {processed} processed, {unchanged} unchanged, "
        f"{failed} failed, {chunk_count} chunks"
    )


if __name__ == "__main__":
    main()

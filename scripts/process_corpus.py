import argparse
import time

from sqlalchemy import exists, select

from taxlens.db import SessionLocal
from taxlens.document_processing.process import process_document_version
from taxlens.legal_data.models import DocumentVersion, LegalDocument, ProcessingJob
from taxlens.storage.factory import get_object_storage


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize and chunk pending TaxLens documents")
    parser.add_argument("--all", action="store_true", help="Reprocess every document version")
    parser.add_argument(
        "--limit",
        type=int,
        help="Process at most this many document versions in one bounded batch",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Include document versions whose latest processing job failed",
    )
    arguments = parser.parse_args()
    if arguments.limit is not None and arguments.limit < 1:
        parser.error("--limit must be at least 1")

    storage = get_object_storage()
    with SessionLocal() as session:
        query = select(DocumentVersion).join(LegalDocument).order_by(DocumentVersion.created_at)
        if not arguments.all:
            query = query.where(DocumentVersion.normalized_content_hash.is_(None))
        if not arguments.retry_failed:
            failed_job = select(ProcessingJob.id).where(
                ProcessingJob.document_version_id == DocumentVersion.id,
                ProcessingJob.status == "FAILED",
            )
            query = query.where(~exists(failed_job))
        if arguments.limit is not None:
            query = query.limit(arguments.limit)
        versions = session.scalars(query).all()
        total = len(versions)
        print(f"Processing {total} document version(s)...", flush=True)
        results = []
        for index, version in enumerate(versions, start=1):
            document = session.get(LegalDocument, version.document_id)
            document_number = document.document_number if document is not None else str(version.id)
            title = document.title if document is not None else "Unknown document"
            print(
                f"[{index}/{total}] START {document_number} | {title} | "
                f"{version.raw_artifact_key}",
                flush=True,
            )
            started_at = time.perf_counter()
            result = process_document_version(session, storage, version)
            results.append(result)
            elapsed = time.perf_counter() - started_at
            detail = result.error_code or result.extraction_method or "complete"
            print(
                f"[{index}/{total}] DONE {document_number} | {result.status} | "
                f"{result.chunk_count} chunks | {detail} | {elapsed:.1f}s",
                flush=True,
            )

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

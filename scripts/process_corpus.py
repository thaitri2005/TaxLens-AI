import argparse
import concurrent.futures
import json
import time
import uuid
from pathlib import Path

from sqlalchemy import Select, exists, func, select

from taxlens.db import SessionLocal
from taxlens.document_processing.legacy_text import has_legacy_text
from taxlens.document_processing.process import (
    CHUNKER_STAGE_SUFFIX,
    ProcessResult,
    mark_processing_failed,
    process_document_version,
)
from taxlens.legal_data.models import DocumentVersion, LegalDocument, ProcessingJob
from taxlens.storage.base import ObjectStorage
from taxlens.storage.factory import get_object_storage

WORD_PROCESSOR_SUFFIXES = (".doc", ".docx", ".rtf")


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize and chunk pending TaxLens documents")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Re-chunk every document version (reuses stored normalized text when available)",
    )
    parser.add_argument(
        "--rechunk-outdated",
        action="store_true",
        help="Re-chunk processed versions whose chunks predate the current chunker version",
    )
    parser.add_argument(
        "--reocr",
        action="store_true",
        help="Re-run extraction and OCR for scanned versions with the current OCR settings",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Process at most this many document versions in one bounded batch",
    )
    parser.add_argument(
        "--reextract-listed",
        type=Path,
        help="Re-run extraction and OCR for the document numbers listed in this JSON file",
    )
    parser.add_argument(
        "--reextract-legacy-text",
        action="store_true",
        help="Re-run extraction for Word and RTF documents whose stored text still holds TCVN3",
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
    candidates = (
        _legacy_text_query(storage)
        if arguments.reextract_legacy_text
        else _listed_query(arguments.reextract_listed)
        if arguments.reextract_listed is not None
        else _outdated_query()
        if arguments.rechunk_outdated
        else _scanned_query()
        if arguments.reocr
        else _candidate_query(reprocess_all=arguments.all, retry_failed=arguments.retry_failed)
    )
    force = arguments.all or arguments.rechunk_outdated
    results: list[ProcessResult] = []
    with SessionLocal() as session:
        pending = session.scalar(select(func.count()).select_from(candidates.subquery())) or 0
        total = min(pending, arguments.limit) if arguments.limit is not None else pending
        print(f"Processing {total} document version(s)...", flush=True)
        attempted: set[uuid.UUID] = set()
        while len(results) < total:
            query = candidates
            if attempted:
                query = query.where(DocumentVersion.id.not_in(attempted))
            # SKIP LOCKED lets overlapping runs (for example, an Airflow retry while an
            # earlier request is still running OCR) claim different versions.
            version = session.scalars(
                query.limit(1).with_for_update(of=DocumentVersion, skip_locked=True)
            ).first()
            if version is None:
                break
            version_id = version.id
            attempted.add(version_id)
            index = len(results) + 1
            document = session.get(LegalDocument, version.document_id)
            document_number = document.document_number if document is not None else str(version_id)
            title = document.title if document is not None else "Unknown document"
            print(
                f"[{index}/{total}] START {document_number} | {title} | {version.raw_artifact_key}",
                flush=True,
            )
            started_at = time.perf_counter()
            try:
                result = process_document_version(
                    session,
                    storage,
                    version,
                    force=force,
                    reextract=arguments.reocr
                    or arguments.reextract_listed is not None
                    or arguments.reextract_legacy_text,
                )
            except Exception as error:
                # One broken document must not stop the batch or block later runs.
                print(f"[{index}/{total}] ERROR {document_number} | {error!r}", flush=True)
                result = mark_processing_failed(session, version_id, error)
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


def _listed_query(path: Path) -> Select[tuple[DocumentVersion]]:
    numbers = json.loads(path.read_text(encoding="utf-8"))["documents"]
    return (
        select(DocumentVersion)
        .join(LegalDocument)
        .where(LegalDocument.document_number.in_(numbers))
        .order_by(DocumentVersion.created_at)
    )


def _legacy_text_query(storage: ObjectStorage) -> Select[tuple[DocumentVersion]]:
    """Versions to extract again, found by reading every stored text.

    They are extracted from the raw file because stored text can mix converted and unconverted
    lines. PDFs are left out: conversion could make a garbled text layer look like Vietnamese.
    """

    with SessionLocal() as session:
        rows = session.execute(
            select(
                DocumentVersion.id,
                DocumentVersion.normalized_artifact_key,
                DocumentVersion.raw_artifact_key,
            ).where(DocumentVersion.normalized_artifact_key.is_not(None))
        ).all()

    def holds_legacy_text(key: str) -> bool:
        if not storage.exists(key):
            return False
        return has_legacy_text(storage.get_bytes(key).decode("utf-8", errors="replace"))

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        flags = list(pool.map(holds_legacy_text, [row[1] for row in rows]))
    flagged = [row for row, flag in zip(rows, flags, strict=True) if flag]
    selected = [row[0] for row in flagged if _is_word_processor_file(row[2])]
    print(
        f"Stored texts checked: {len(rows)}; holding TCVN3: {len(flagged)}; "
        f"PDF or other, left alone: {len(flagged) - len(selected)}",
        flush=True,
    )
    return (
        select(DocumentVersion)
        .where(DocumentVersion.id.in_(selected))
        .order_by(DocumentVersion.created_at)
    )


def _is_word_processor_file(key: str | None) -> bool:
    return key is not None and key.lower().endswith(WORD_PROCESSOR_SUFFIXES)


def _outdated_query() -> Select[tuple[DocumentVersion]]:
    current_job = select(ProcessingJob.id).where(
        ProcessingJob.document_version_id == DocumentVersion.id,
        ProcessingJob.stage.endswith(CHUNKER_STAGE_SUFFIX),
    )
    return (
        select(DocumentVersion)
        .join(LegalDocument)
        .where(DocumentVersion.normalized_artifact_key.is_not(None), ~exists(current_job))
        .order_by(DocumentVersion.created_at)
    )


def _scanned_query() -> Select[tuple[DocumentVersion]]:
    """Versions whose text came from OCR, or whose OCR failed and may now succeed."""

    ocr_job = select(ProcessingJob.id).where(
        ProcessingJob.document_version_id == DocumentVersion.id,
        (ProcessingJob.stage.startswith("OCR_")) | (ProcessingJob.error_code == "OCR_REQUIRED"),
    )
    return (
        select(DocumentVersion)
        .join(LegalDocument)
        .where(exists(ocr_job))
        .order_by(DocumentVersion.created_at)
    )


def _candidate_query(reprocess_all: bool, retry_failed: bool) -> Select[tuple[DocumentVersion]]:
    query = select(DocumentVersion).join(LegalDocument).order_by(DocumentVersion.created_at)
    if not reprocess_all:
        query = query.where(DocumentVersion.normalized_content_hash.is_(None))
    if not retry_failed:
        failed_job = select(ProcessingJob.id).where(
            ProcessingJob.document_version_id == DocumentVersion.id,
            ProcessingJob.status == "FAILED",
        )
        query = query.where(~exists(failed_job))
    return query


if __name__ == "__main__":
    main()

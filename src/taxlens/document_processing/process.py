import hashlib
import re
from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from taxlens.legal_data.models import (
    DocumentChunk,
    DocumentEmbedding,
    DocumentVersion,
    ProcessingJob,
)
from taxlens.storage.local import LocalObjectStorage

ARTICLE_PATTERN = re.compile(r"(?mi)^(?:article|điều)\s+(\d+)\.\s*(.*)$")


@dataclass(frozen=True)
class ProcessResult:
    status: str
    version_id: str
    chunk_count: int
    error_code: str | None = None


def process_document_version(
    session: Session,
    storage: LocalObjectStorage,
    version: DocumentVersion,
) -> ProcessResult:
    existing_chunks = session.scalars(
        select(DocumentChunk).where(DocumentChunk.document_version_id == version.id)
    ).all()
    if version.normalized_content_hash is not None and any(
        chunk.content.strip() for chunk in existing_chunks
    ):
        return ProcessResult(
            status="UNCHANGED",
            version_id=str(version.id),
            chunk_count=len(existing_chunks),
        )

    raw_content = storage.get_bytes(version.raw_artifact_key)
    try:
        pages = extract_pages(raw_content, version.raw_artifact_key)
        if not any(page.strip() for page in pages):
            raise ValueError("No extractable text found; OCR is required")
    except Exception as error:
        _delete_chunks_and_embeddings(session, version.id, existing_chunks)
        version.normalized_content_hash = None
        version.normalized_artifact_key = None
        job = _latest_job(session, version)
        if job is not None:
            job.status = "FAILED"
            job.stage = "EXTRACTION"
            job.error_code = (
                "OCR_REQUIRED"
                if version.raw_artifact_key.casefold().endswith(".pdf")
                and raw_content.startswith(b"%PDF")
                else "DOCUMENT_EXTRACTION_FAILED"
            )
            job.error_detail = str(error)[:2000]
            job.attempt_count += 1
            session.commit()
        return ProcessResult(
            status="FAILED",
            version_id=str(version.id),
            chunk_count=0,
            error_code=job.error_code if job is not None else "DOCUMENT_EXTRACTION_FAILED",
        )

    normalized_pages = [normalize_text(page).strip() for page in pages]
    normalized_text = "\n\f\n".join(normalized_pages).strip() + "\n"
    normalized_content = normalized_text.encode("utf-8")
    normalized_hash = hashlib.sha256(normalized_content).hexdigest()
    normalized_key = f"normalized-text/{normalized_hash}.txt"
    if not storage.exists(normalized_key):
        storage.put_bytes(normalized_key, normalized_content, "text/plain; charset=utf-8")

    _delete_chunks_and_embeddings(session, version.id, existing_chunks)
    page_boundaries = _page_boundaries(normalized_pages)
    chunks = build_article_chunks(normalized_text, page_boundaries)
    for chunk in chunks:
        session.add(
            DocumentChunk(
                document_version_id=version.id,
                article_number=chunk.article_number,
                heading=chunk.heading,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                content=chunk.content,
                token_count=len(chunk.content.split()),
            )
        )

    version.normalized_content_hash = normalized_hash
    version.normalized_artifact_key = normalized_key
    job = _latest_job(session, version)
    if job is not None:
        job.status = "COMPLETED"
        job.stage = "CHUNKED"
    session.commit()
    return ProcessResult(status="PROCESSED", version_id=str(version.id), chunk_count=len(chunks))


@dataclass(frozen=True)
class ParsedChunk:
    article_number: str | None
    heading: str | None
    content: str
    page_start: int | None = None
    page_end: int | None = None


def normalize_text(raw_text: str) -> str:
    normalized_lines = [re.sub(r"[ \t]+", " ", line).strip() for line in raw_text.splitlines()]
    return "\n".join(normalized_lines).strip() + "\n"


def extract_pages(raw_content: bytes, artifact_key: str) -> list[str]:
    if artifact_key.casefold().endswith(".pdf"):
        reader = PdfReader(BytesIO(raw_content))
        return [page.extract_text() or "" for page in reader.pages]
    return [raw_content.decode("utf-8")]


def extract_text(raw_content: bytes, artifact_key: str) -> str:
    return "\n".join(extract_pages(raw_content, artifact_key))


def build_article_chunks(text: str, page_boundaries: list[int] | None = None) -> list[ParsedChunk]:
    if page_boundaries is None:
        page_boundaries = [0]
    matches = list(ARTICLE_PATTERN.finditer(text))
    if not matches:
        return [
            ParsedChunk(
                article_number=None,
                heading=None,
                content=text.strip(),
                page_start=_page_for_offset(page_boundaries, 0),
                page_end=_page_for_offset(page_boundaries, max(len(text) - 1, 0)),
            )
        ]

    chunks: list[ParsedChunk] = []
    for index, match in enumerate(matches):
        content_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        content = text[match.start() : content_end].strip()
        chunks.append(
            ParsedChunk(
                article_number=match.group(1),
                heading=match.group(2).strip() or None,
                content=content,
                page_start=_page_for_offset(page_boundaries, match.start()),
                page_end=_page_for_offset(page_boundaries, max(content_end - 1, match.start())),
            )
        )
    return chunks


def _page_boundaries(pages: list[str]) -> list[int]:
    boundaries: list[int] = []
    offset = 0
    for page in pages:
        boundaries.append(offset)
        offset += len(page) + 3
    return boundaries


def _page_for_offset(boundaries: list[int], offset: int) -> int:
    return bisect_right(boundaries, offset)


def _latest_job(session: Session, version: DocumentVersion) -> ProcessingJob | None:
    return session.scalar(
        select(ProcessingJob)
        .where(ProcessingJob.document_version_id == version.id)
        .order_by(ProcessingJob.created_at.desc())
    )


def _delete_chunks_and_embeddings(
    session: Session, version_id: object, chunks: Sequence[DocumentChunk]
) -> None:
    chunk_ids = [chunk.id for chunk in chunks]
    if chunk_ids:
        session.execute(
            delete(DocumentEmbedding).where(DocumentEmbedding.document_chunk_id.in_(chunk_ids))
        )
    session.execute(delete(DocumentChunk).where(DocumentChunk.document_version_id == version_id))

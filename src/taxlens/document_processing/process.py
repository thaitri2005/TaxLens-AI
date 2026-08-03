import hashlib
import re
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from taxlens.legal_data.models import DocumentChunk, DocumentVersion, ProcessingJob
from taxlens.storage.local import LocalObjectStorage

ARTICLE_PATTERN = re.compile(r"(?mi)^(?:article|điều)\s+(\d+)\.\s*(.*)$")


@dataclass(frozen=True)
class ProcessResult:
    status: str
    version_id: str
    chunk_count: int


def process_document_version(
    session: Session, storage: LocalObjectStorage, version: DocumentVersion
) -> ProcessResult:
    existing_chunks = session.scalars(
        select(DocumentChunk).where(DocumentChunk.document_version_id == version.id)
    ).all()
    if version.normalized_content_hash is not None and existing_chunks:
        return ProcessResult(
            status="UNCHANGED",
            version_id=str(version.id),
            chunk_count=len(existing_chunks),
        )

    raw_content = storage.get_bytes(version.raw_artifact_key)
    normalized_text = normalize_text(raw_content.decode("utf-8"))
    normalized_content = normalized_text.encode("utf-8")
    normalized_hash = hashlib.sha256(normalized_content).hexdigest()
    normalized_key = f"normalized-text/{normalized_hash}.txt"
    if not storage.exists(normalized_key):
        storage.put_bytes(normalized_key, normalized_content, "text/plain; charset=utf-8")

    session.execute(delete(DocumentChunk).where(DocumentChunk.document_version_id == version.id))
    chunks = build_article_chunks(normalized_text)
    for chunk in chunks:
        session.add(
            DocumentChunk(
                document_version_id=version.id,
                article_number=chunk.article_number,
                heading=chunk.heading,
                page_start=1,
                page_end=1,
                content=chunk.content,
                token_count=len(chunk.content.split()),
            )
        )

    version.normalized_content_hash = normalized_hash
    version.normalized_artifact_key = normalized_key
    job = session.scalar(
        select(ProcessingJob)
        .where(ProcessingJob.document_version_id == version.id)
        .order_by(ProcessingJob.created_at.desc())
    )
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


def normalize_text(raw_text: str) -> str:
    normalized_lines = [re.sub(r"[ \t]+", " ", line).strip() for line in raw_text.splitlines()]
    return "\n".join(normalized_lines).strip() + "\n"


def build_article_chunks(text: str) -> list[ParsedChunk]:
    matches = list(ARTICLE_PATTERN.finditer(text))
    if not matches:
        return [ParsedChunk(article_number=None, heading=None, content=text.strip())]

    chunks: list[ParsedChunk] = []
    for index, match in enumerate(matches):
        content_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        content = text[match.start() : content_end].strip()
        chunks.append(
            ParsedChunk(
                article_number=match.group(1),
                heading=match.group(2).strip() or None,
                content=content,
            )
        )
    return chunks

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from taxlens.ingestion.connectors import SourceDocument
from taxlens.legal_data.models import DocumentVersion, LegalDocument, ProcessingJob, SourceRecord
from taxlens.storage.base import ObjectStorage

IngestionStatus = Literal["NEW_DOCUMENT", "UNCHANGED"]


@dataclass(frozen=True)
class SeedDocument:
    source_name: str
    source_url: str
    source_document_id: str
    document_number: str
    title: str
    document_type: str
    issuing_agency: str | None
    issue_date: date | None
    effective_date: date | None
    legal_status: str
    content: bytes
    content_type: str = "text/plain; charset=utf-8"


@dataclass(frozen=True)
class IngestionResult:
    status: IngestionStatus
    document_id: str
    version_id: str
    raw_content_hash: str


def ingest_seed_document(
    session: Session, storage: ObjectStorage, document: SeedDocument
) -> IngestionResult:
    raw_content_hash = hashlib.sha256(document.content).hexdigest()
    existing_version = session.scalar(
        select(DocumentVersion).where(DocumentVersion.raw_content_hash == raw_content_hash)
    )
    if existing_version is not None:
        existing_document = session.get(LegalDocument, existing_version.document_id)
        if existing_document is not None:
            _refresh_document_metadata(session, existing_document, document)
            session.commit()
        return IngestionResult(
            status="UNCHANGED",
            document_id=str(existing_version.document_id),
            version_id=str(existing_version.id),
            raw_content_hash=raw_content_hash,
        )

    source_record = session.scalar(
        select(SourceRecord).where(SourceRecord.source_url == document.source_url)
    )
    now = datetime.now(UTC)
    if source_record is None:
        source_record = SourceRecord(
            source_name=document.source_name,
            source_url=document.source_url,
            source_document_id=document.source_document_id,
            last_seen_at=now,
        )
        session.add(source_record)
        session.flush()
    else:
        source_record.last_seen_at = now

    legal_document = session.scalar(
        select(LegalDocument).where(LegalDocument.document_number == document.document_number)
    )
    if legal_document is None:
        legal_document = LegalDocument(
            document_number=document.document_number,
            title=document.title,
            document_type=document.document_type,
            issuing_agency=document.issuing_agency,
        )
        session.add(legal_document)
        session.flush()
    else:
        _refresh_document_metadata(session, legal_document, document)

    artifact_key = _artifact_key(document, raw_content_hash)
    if not storage.exists(artifact_key):
        storage.put_bytes(artifact_key, document.content, document.content_type)

    version = DocumentVersion(
        document_id=legal_document.id,
        source_record_id=source_record.id,
        issue_date=document.issue_date,
        effective_date=document.effective_date,
        legal_status=document.legal_status,
        raw_content_hash=raw_content_hash,
        raw_artifact_key=artifact_key,
    )
    session.add(version)
    session.flush()
    session.add(
        ProcessingJob(
            document_version_id=version.id,
            status="PENDING",
            stage="DOWNLOADED",
        )
    )
    session.commit()

    return IngestionResult(
        status="NEW_DOCUMENT",
        document_id=str(legal_document.id),
        version_id=str(version.id),
        raw_content_hash=raw_content_hash,
    )


def ingest_source_document(
    session: Session,
    storage: ObjectStorage,
    document: SourceDocument,
    content: bytes,
) -> IngestionResult:
    """Persist a downloaded official document using the existing idempotent path."""
    return ingest_seed_document(
        session,
        storage,
        SeedDocument(
            source_name=document.source_name,
            source_url=document.source_url,
            source_document_id=document.source_document_id,
            document_number=document.document_number,
            title=document.title,
            document_type=document.document_type,
            issuing_agency=document.issuing_agency,
            issue_date=document.issue_date,
            effective_date=document.effective_date,
            legal_status=document.legal_status,
            content=content,
            content_type=document.content_type,
        ),
    )


def load_seed_manifest(manifest_path: Path) -> list[SeedDocument]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, list):
        raise ValueError("Seed manifest must contain a JSON list")

    documents: list[SeedDocument] = []
    for item in manifest:
        if not isinstance(item, dict):
            raise ValueError("Each seed manifest item must be a JSON object")
        content_path = manifest_path.parent / _required_string(item, "content_file")
        documents.append(
            SeedDocument(
                source_name=_required_string(item, "source_name"),
                source_url=_required_string(item, "source_url"),
                source_document_id=_required_string(item, "source_document_id"),
                document_number=_required_string(item, "document_number"),
                title=_required_string(item, "title"),
                document_type=_required_string(item, "document_type"),
                issuing_agency=_optional_string(item, "issuing_agency"),
                issue_date=_optional_date(item, "issue_date"),
                effective_date=_optional_date(item, "effective_date"),
                legal_status=_required_string(item, "legal_status"),
                content=content_path.read_bytes(),
            )
        )
    return documents


def _artifact_key(document: SeedDocument, content_hash: str) -> str:
    document_slug = re.sub(r"[^a-z0-9]+", "-", document.document_number.lower()).strip("-")
    issue_year = str(document.issue_date.year) if document.issue_date is not None else "unknown"
    return (
        f"raw-documents/source={document.source_name}/year={issue_year}/"
        f"document={document_slug}/{content_hash}{_artifact_suffix(document.content_type)}"
    )


_SUFFIXES_BY_CONTENT_TYPE = {
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/rtf": ".rtf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}
# Statuses that say nothing about validity; a known status from a source replaces them.
_UNRESOLVED_STATUSES = frozenset({"DISCOVERED", "UNKNOWN"})


def is_already_ingested(session: Session, source_name: str, source_document_id: str) -> bool:
    """Whether this source file was ingested before, so it need not be downloaded again."""

    return (
        session.scalar(
            select(DocumentVersion.id)
            .join(SourceRecord, DocumentVersion.source_record_id == SourceRecord.id)
            .where(
                SourceRecord.source_name == source_name,
                SourceRecord.source_document_id == source_document_id,
            )
            .limit(1)
        )
        is not None
    )


def _refresh_document_metadata(
    session: Session, legal_document: LegalDocument, document: SeedDocument
) -> None:
    """Fill gaps from a better-described source without overwriting curated values."""

    if _is_weak_title(legal_document.title, legal_document.document_number) and not (
        _is_weak_title(document.title, document.document_number)
    ):
        legal_document.title = document.title
    if legal_document.issuing_agency is None and document.issuing_agency:
        legal_document.issuing_agency = document.issuing_agency
    if document.legal_status in _UNRESOLVED_STATUSES:
        return
    for version in session.scalars(
        select(DocumentVersion).where(DocumentVersion.document_id == legal_document.id)
    ).all():
        # Status belongs to the document number, and the source's current status is newer
        # than what was recorded at an earlier ingestion.
        version.legal_status = document.legal_status
        if version.effective_date is None and document.effective_date is not None:
            version.effective_date = document.effective_date


def _is_weak_title(title: str, document_number: str) -> bool:
    # Listing pages sometimes yield only "388/2026/NĐ-CP 13/10/2026" as the title.
    remainder = title.casefold().replace(document_number.casefold(), " ")
    return len(re.findall(r"[^\W\d_]{2,}", remainder)) < 3


def _artifact_suffix(content_type: str) -> str:
    return _SUFFIXES_BY_CONTENT_TYPE.get(content_type.casefold().split(";", 1)[0], ".txt")


def _required_string(item: dict[str, object], field: str) -> str:
    value = item.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Seed manifest field '{field}' must be a non-empty string")
    return value


def _optional_string(item: dict[str, object], field: str) -> str | None:
    value = item.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Seed manifest field '{field}' must be a string or null")
    return value


def _optional_date(item: dict[str, object], field: str) -> date | None:
    value = item.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Seed manifest field '{field}' must be an ISO date string or null")
    return date.fromisoformat(value)

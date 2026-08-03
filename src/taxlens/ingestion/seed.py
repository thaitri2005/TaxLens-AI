import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from taxlens.legal_data.models import DocumentVersion, LegalDocument, ProcessingJob, SourceRecord
from taxlens.storage.local import LocalObjectStorage

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
    session: Session, storage: LocalObjectStorage, document: SeedDocument
) -> IngestionResult:
    raw_content_hash = hashlib.sha256(document.content).hexdigest()
    existing_version = session.scalar(
        select(DocumentVersion).where(DocumentVersion.raw_content_hash == raw_content_hash)
    )
    if existing_version is not None:
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
        f"document={document_slug}/{content_hash}.txt"
    )


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

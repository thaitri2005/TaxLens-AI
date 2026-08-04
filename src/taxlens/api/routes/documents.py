import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from taxlens.db import get_db_session
from taxlens.legal_data.models import (
    DocumentChunk,
    DocumentVersion,
    LegalDocument,
    ProcessingJob,
    SourceRecord,
)

router = APIRouter(prefix="/documents", tags=["documents"])


class DocumentSummary(BaseModel):
    id: uuid.UUID
    document_number: str
    title: str
    document_type: str
    issuing_agency: str | None
    source_name: str | None


class VersionSummary(BaseModel):
    id: uuid.UUID
    issue_date: date | None
    effective_date: date | None
    legal_status: str
    raw_artifact_key: str
    processing_status: str | None
    processing_error_code: str | None
    chunk_count: int


class DocumentDetail(DocumentSummary):
    versions: list[VersionSummary]


class ChunkSummary(BaseModel):
    id: uuid.UUID
    version_id: uuid.UUID
    article_number: str | None
    clause_number: str | None
    heading: str | None
    page_start: int | None
    page_end: int | None
    content: str


@router.get("", response_model=list[DocumentSummary])
def list_documents(
    limit: int = Query(default=50, ge=1, le=100),
    source_name: str | None = Query(default=None, max_length=120),
    document_type: str | None = Query(default=None, max_length=50),
    issuing_agency: str | None = Query(default=None, max_length=255),
    session: Session = Depends(get_db_session),
) -> list[DocumentSummary]:
    statement = (
        select(LegalDocument)
        .outerjoin(DocumentVersion, DocumentVersion.document_id == LegalDocument.id)
        .outerjoin(SourceRecord, DocumentVersion.source_record_id == SourceRecord.id)
        .distinct()
        .order_by(LegalDocument.document_number)
    )
    if source_name is not None:
        statement = statement.where(SourceRecord.source_name == source_name)
    if document_type is not None:
        statement = statement.where(LegalDocument.document_type == document_type)
    if issuing_agency is not None:
        statement = statement.where(LegalDocument.issuing_agency.ilike(f"%{issuing_agency}%"))
    documents = session.scalars(statement.limit(limit)).all()
    source_names = _source_names_by_document(session, [document.id for document in documents])
    return [_document_summary(document, source_names.get(document.id)) for document in documents]


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(
    document_id: uuid.UUID,
    session: Session = Depends(get_db_session),
) -> DocumentDetail:
    document = session.get(LegalDocument, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    versions = session.scalars(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document.id)
        .order_by(DocumentVersion.issue_date.desc(), DocumentVersion.created_at.desc())
    ).all()
    version_ids = [version.id for version in versions]
    processing = _processing_by_version(session, version_ids)
    chunk_counts = _chunk_counts_by_version(session, version_ids)
    source_name = _source_names_by_document(session, [document.id]).get(document.id)
    return DocumentDetail(
        **_document_summary(document, source_name).model_dump(),
        versions=[
            VersionSummary(
                id=version.id,
                issue_date=version.issue_date,
                effective_date=version.effective_date,
                legal_status=version.legal_status,
                raw_artifact_key=version.raw_artifact_key,
                processing_status=processing.get(version.id, (None, None))[0],
                processing_error_code=processing.get(version.id, (None, None))[1],
                chunk_count=chunk_counts.get(version.id, 0),
            )
            for version in versions
        ],
    )


@router.get("/{document_id}/chunks", response_model=list[ChunkSummary])
def list_document_chunks(
    document_id: uuid.UUID,
    session: Session = Depends(get_db_session),
) -> list[ChunkSummary]:
    document = session.get(LegalDocument, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    chunks = session.scalars(
        select(DocumentChunk)
        .join(DocumentVersion, DocumentChunk.document_version_id == DocumentVersion.id)
        .where(DocumentVersion.document_id == document.id)
        .order_by(DocumentVersion.issue_date.desc(), DocumentChunk.article_number)
    ).all()
    return [
        ChunkSummary(
            id=chunk.id,
            version_id=chunk.document_version_id,
            article_number=chunk.article_number,
            clause_number=chunk.clause_number,
            heading=chunk.heading,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            content=chunk.content,
        )
        for chunk in chunks
    ]


def _document_summary(document: LegalDocument, source_name: str | None = None) -> DocumentSummary:
    return DocumentSummary(
        id=document.id,
        document_number=document.document_number,
        title=document.title,
        document_type=document.document_type,
        issuing_agency=document.issuing_agency,
        source_name=source_name,
    )


def _source_names_by_document(
    session: Session, document_ids: list[uuid.UUID]
) -> dict[uuid.UUID, str]:
    if not document_ids:
        return {}
    rows = session.execute(
        select(DocumentVersion.document_id, SourceRecord.source_name)
        .join(SourceRecord, DocumentVersion.source_record_id == SourceRecord.id)
        .where(DocumentVersion.document_id.in_(document_ids))
        .order_by(DocumentVersion.created_at.desc())
    ).all()
    source_names: dict[uuid.UUID, str] = {}
    for document_id, source_name in rows:
        if document_id not in source_names:
            source_names[document_id] = source_name
    return source_names


def _processing_by_version(
    session: Session, version_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[str, str | None]]:
    if not version_ids:
        return {}
    rows = session.scalars(
        select(ProcessingJob)
        .where(ProcessingJob.document_version_id.in_(version_ids))
        .order_by(ProcessingJob.updated_at.desc(), ProcessingJob.created_at.desc())
    ).all()
    statuses: dict[uuid.UUID, tuple[str, str | None]] = {}
    for job in rows:
        if job.document_version_id not in statuses:
            statuses[job.document_version_id] = (job.status, job.error_code)
    return statuses


def _chunk_counts_by_version(
    session: Session, version_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    if not version_ids:
        return {}
    rows = session.execute(
        select(DocumentChunk.document_version_id, func.count(DocumentChunk.id))
        .where(DocumentChunk.document_version_id.in_(version_ids))
        .group_by(DocumentChunk.document_version_id)
    ).all()
    return {version_id: int(count) for version_id, count in rows}

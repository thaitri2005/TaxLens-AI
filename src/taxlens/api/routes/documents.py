import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from taxlens.db import get_db_session
from taxlens.legal_data.models import DocumentChunk, DocumentVersion, LegalDocument

router = APIRouter(prefix="/documents", tags=["documents"])


class DocumentSummary(BaseModel):
    id: uuid.UUID
    document_number: str
    title: str
    document_type: str
    issuing_agency: str | None


class VersionSummary(BaseModel):
    id: uuid.UUID
    issue_date: date | None
    effective_date: date | None
    legal_status: str
    raw_artifact_key: str


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
    session: Session = Depends(get_db_session),
) -> list[DocumentSummary]:
    documents = session.scalars(
        select(LegalDocument).order_by(LegalDocument.document_number).limit(limit)
    ).all()
    return [_document_summary(document) for document in documents]


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
    return DocumentDetail(
        **_document_summary(document).model_dump(),
        versions=[
            VersionSummary(
                id=version.id,
                issue_date=version.issue_date,
                effective_date=version.effective_date,
                legal_status=version.legal_status,
                raw_artifact_key=version.raw_artifact_key,
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


def _document_summary(document: LegalDocument) -> DocumentSummary:
    return DocumentSummary(
        id=document.id,
        document_number=document.document_number,
        title=document.title,
        document_type=document.document_type,
        issuing_agency=document.issuing_agency,
    )

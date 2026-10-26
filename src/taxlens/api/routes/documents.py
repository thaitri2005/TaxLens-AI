import csv
import io
import uuid
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from taxlens.api.auth import require_admin, require_authenticated_user
from taxlens.db import get_db_session
from taxlens.legal_data.document_kinds import document_kind
from taxlens.legal_data.models import (
    DocumentChunk,
    DocumentEmbedding,
    DocumentVersion,
    LegalDocument,
    ProcessingJob,
    SourceRecord,
)

router = APIRouter(
    prefix="/documents", tags=["documents"], dependencies=[Depends(require_authenticated_user)]
)
admin_export_router = APIRouter(
    prefix="/admin/documents", tags=["administration"], dependencies=[Depends(require_admin)]
)

EXPORT_COLUMNS = (
    "document_number",
    "title",
    "kind",
    "document_type",
    "issuing_agency",
    "source",
    "source_document_id",
    "source_url",
    "issue_date",
    "effective_date",
    "legal_status",
    "processing_status",
    "processing_error",
    "passages",
    "embedded_passages",
    "collected_at",
)


class DocumentSummary(BaseModel):
    id: uuid.UUID
    document_number: str
    title: str
    document_type: str
    kind: str
    issuing_agency: str | None
    source_name: str | None


class DocumentListItem(DocumentSummary):
    legal_status: str | None
    issue_date: date | None


class DocumentPage(BaseModel):
    total: int
    items: list[DocumentListItem]


class VersionSummary(BaseModel):
    id: uuid.UUID
    issue_date: date | None
    effective_date: date | None
    legal_status: str
    raw_artifact_key: str
    source_url: str | None
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


class CountByValue(BaseModel):
    value: str
    count: int


class DocumentOverview(BaseModel):
    total_documents: int
    searchable_documents: int
    passages: int
    embedded_passages: int
    failed_versions: int
    by_status: list[CountByValue]
    by_source: list[CountByValue]
    by_kind: list[CountByValue]


@router.get("", response_model=DocumentPage)
def list_documents(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None, max_length=200),
    source_name: str | None = Query(default=None, max_length=120),
    document_type: str | None = Query(default=None, max_length=50),
    kind: str | None = Query(default=None, max_length=30),
    legal_status: str | None = Query(default=None, max_length=50),
    issuing_agency: str | None = Query(default=None, max_length=255),
    session: Session = Depends(get_db_session),
) -> DocumentPage:
    """One page of documents, newest issue first, and how many match in total.

    The library is browsed a page at a time; nothing here grows with the corpus except
    the count.
    """

    document_types: list[str] | None = None
    if kind is not None:
        recorded = session.scalars(select(LegalDocument.document_type).distinct()).all()
        document_types = [value for value in recorded if document_kind(value) == kind]
    if document_type is not None:
        document_types = [
            value for value in (document_types or [document_type]) if value == document_type
        ]
    matching = _matching_document_ids(
        q=q,
        source_name=source_name,
        document_types=document_types,
        legal_status=legal_status,
        issuing_agency=issuing_agency,
    )
    total = session.scalar(select(func.count()).select_from(matching.subquery())) or 0
    latest_issue = (
        select(
            DocumentVersion.document_id,
            func.max(DocumentVersion.issue_date).label("issue_date"),
        )
        .group_by(DocumentVersion.document_id)
        .subquery()
    )
    documents = session.scalars(
        select(LegalDocument)
        .outerjoin(latest_issue, latest_issue.c.document_id == LegalDocument.id)
        .where(LegalDocument.id.in_(matching))
        .order_by(latest_issue.c.issue_date.desc().nulls_last(), LegalDocument.document_number)
        .offset(offset)
        .limit(limit)
    ).all()
    document_ids = [document.id for document in documents]
    source_names = _source_names_by_document(session, document_ids)
    latest_versions = _latest_versions_by_document(session, document_ids)
    items = []
    for document in documents:
        version = latest_versions.get(document.id)
        items.append(
            DocumentListItem(
                **_document_summary(document, source_names.get(document.id)).model_dump(),
                legal_status=version.legal_status if version is not None else None,
                issue_date=version.issue_date if version is not None else None,
            )
        )
    return DocumentPage(total=int(total), items=items)


@router.get("/overview", response_model=DocumentOverview)
def document_overview(session: Session = Depends(get_db_session)) -> DocumentOverview:
    """Corpus statistics and the values the library can be filtered by.

    A handful of aggregate queries, so the Documents tab can show its summary at once
    and load the list separately.
    """

    searchable = session.scalar(
        select(func.count(func.distinct(DocumentVersion.document_id))).join(
            DocumentChunk, DocumentChunk.document_version_id == DocumentVersion.id
        )
    )
    latest_job = (
        select(
            ProcessingJob.status,
            func.row_number()
            .over(
                partition_by=ProcessingJob.document_version_id,
                order_by=(ProcessingJob.updated_at.desc(), ProcessingJob.created_at.desc()),
            )
            .label("position"),
        )
    ).subquery()
    failed = session.scalar(
        select(func.count())
        .select_from(latest_job)
        .where(latest_job.c.position == 1, latest_job.c.status == "FAILED")
    )
    documents_per = func.count(func.distinct(DocumentVersion.document_id))
    by_status = select(DocumentVersion.legal_status, documents_per).group_by(
        DocumentVersion.legal_status
    )
    by_source = (
        select(SourceRecord.source_name, documents_per)
        .join(DocumentVersion, DocumentVersion.source_record_id == SourceRecord.id)
        .group_by(SourceRecord.source_name)
    )
    by_type = select(LegalDocument.document_type, func.count(LegalDocument.id)).group_by(
        LegalDocument.document_type
    )
    return DocumentOverview(
        total_documents=session.scalar(select(func.count(LegalDocument.id))) or 0,
        searchable_documents=searchable or 0,
        passages=session.scalar(select(func.count(DocumentChunk.id))) or 0,
        embedded_passages=session.scalar(
            select(func.count(func.distinct(DocumentEmbedding.document_chunk_id)))
        )
        or 0,
        failed_versions=failed or 0,
        by_status=_counts(session.execute(by_status).all()),
        by_source=_counts(session.execute(by_source).all()),
        by_kind=_counts(session.execute(by_type).all(), group=document_kind),
    )


def _counts(rows: Iterable[Any], group: Callable[[str], str] = str) -> list[CountByValue]:
    """(value, count) rows as counts, largest first; ``group`` merges values."""

    totals: dict[str, int] = {}
    for value, count in rows:
        key = group(str(value))
        totals[key] = totals.get(key, 0) + int(count)
    counts = [CountByValue(value=value, count=count) for value, count in totals.items()]
    return sorted(counts, key=lambda item: (-item.count, item.value))


def _matching_document_ids(
    *,
    q: str | None,
    source_name: str | None,
    document_types: list[str] | None,
    legal_status: str | None,
    issuing_agency: str | None,
) -> Select[Any]:  # typed Select[tuple[UUID]] in SQLAlchemy 2.0, Select[UUID] in 2.1
    statement = (
        select(LegalDocument.id)
        .outerjoin(DocumentVersion, DocumentVersion.document_id == LegalDocument.id)
        .outerjoin(SourceRecord, DocumentVersion.source_record_id == SourceRecord.id)
        .distinct()
    )
    if q and q.strip():
        text = q.strip()
        statement = statement.where(
            or_(
                LegalDocument.document_number.icontains(text, autoescape=True),
                LegalDocument.title.icontains(text, autoescape=True),
            )
        )
    if source_name is not None:
        statement = statement.where(SourceRecord.source_name == source_name)
    if document_types is not None:
        statement = statement.where(LegalDocument.document_type.in_(document_types))
    if legal_status is not None:
        statement = statement.where(DocumentVersion.legal_status == legal_status)
    if issuing_agency is not None:
        statement = statement.where(
            LegalDocument.issuing_agency.icontains(issuing_agency, autoescape=True)
        )
    return statement


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
    source_urls = _source_urls_by_version(session, version_ids)
    return DocumentDetail(
        **_document_summary(document, source_name).model_dump(),
        versions=[
            VersionSummary(
                id=version.id,
                issue_date=version.issue_date,
                effective_date=version.effective_date,
                legal_status=version.legal_status,
                raw_artifact_key=version.raw_artifact_key,
                source_url=source_urls.get(version.id),
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
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db_session),
) -> list[ChunkSummary]:
    document = session.get(LegalDocument, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    chunks = session.scalars(
        select(DocumentChunk)
        .join(DocumentVersion, DocumentChunk.document_version_id == DocumentVersion.id)
        .where(DocumentVersion.document_id == document.id)
        .order_by(
            DocumentVersion.issue_date.desc(),
            DocumentChunk.article_number,
            DocumentChunk.id,
        )
        .offset(offset)
        .limit(limit)
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
        kind=document_kind(document.document_type),
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


def _latest_versions_by_document(
    session: Session, document_ids: list[uuid.UUID]
) -> dict[uuid.UUID, DocumentVersion]:
    if not document_ids:
        return {}
    versions = session.scalars(
        select(DocumentVersion)
        .where(DocumentVersion.document_id.in_(document_ids))
        .order_by(DocumentVersion.issue_date.desc().nulls_last(), DocumentVersion.created_at.desc())
    ).all()
    latest: dict[uuid.UUID, DocumentVersion] = {}
    for version in versions:
        latest.setdefault(version.document_id, version)
    return latest


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


def _source_urls_by_version(session: Session, version_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not version_ids:
        return {}
    rows = session.execute(
        select(DocumentVersion.id, SourceRecord.source_url)
        .join(SourceRecord, DocumentVersion.source_record_id == SourceRecord.id)
        .where(DocumentVersion.id.in_(version_ids))
    ).all()
    return {version_id: source_url for version_id, source_url in rows}


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


@admin_export_router.get("/export")
def export_document_list(session: Session = Depends(get_db_session)) -> Response:
    """A spreadsheet (CSV) of every collected file: metadata only, no document text.

    One row per document version, so a document collected from two sources appears
    twice. A handful of whole-table queries, so the cost does not grow per document.
    """

    versions = session.execute(
        select(
            DocumentVersion.id,
            LegalDocument.document_number,
            LegalDocument.title,
            LegalDocument.document_type,
            LegalDocument.issuing_agency,
            SourceRecord.source_name,
            SourceRecord.source_document_id,
            SourceRecord.source_url,
            DocumentVersion.issue_date,
            DocumentVersion.effective_date,
            DocumentVersion.legal_status,
            DocumentVersion.created_at,
        )
        .join(LegalDocument, DocumentVersion.document_id == LegalDocument.id)
        .outerjoin(SourceRecord, DocumentVersion.source_record_id == SourceRecord.id)
        .order_by(LegalDocument.document_number, DocumentVersion.created_at)
    ).all()

    processing: dict[uuid.UUID, tuple[str, str | None]] = {}
    for version_id, job_status, error_code in session.execute(
        select(ProcessingJob.document_version_id, ProcessingJob.status, ProcessingJob.error_code)
        .order_by(ProcessingJob.updated_at.desc(), ProcessingJob.created_at.desc())
    ).all():
        processing.setdefault(version_id, (job_status, error_code))
    passages = dict(
        session.execute(
            select(DocumentChunk.document_version_id, func.count(DocumentChunk.id)).group_by(
                DocumentChunk.document_version_id
            )
        ).all()
    )
    embedded = dict(
        session.execute(
            select(DocumentChunk.document_version_id, func.count(func.distinct(DocumentChunk.id)))
            .join(DocumentEmbedding, DocumentEmbedding.document_chunk_id == DocumentChunk.id)
            .group_by(DocumentChunk.document_version_id)
        ).all()
    )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(EXPORT_COLUMNS)
    for row in versions:
        job_status, error_code = processing.get(row.id, ("NOT_PROCESSED", None))
        writer.writerow(
            [
                _spreadsheet_safe(value)
                for value in (
                    row.document_number,
                    row.title,
                    document_kind(row.document_type),
                    row.document_type,
                    row.issuing_agency,
                    row.source_name,
                    row.source_document_id,
                    row.source_url,
                    row.issue_date,
                    row.effective_date,
                    row.legal_status,
                    job_status,
                    error_code,
                    int(passages.get(row.id, 0)),
                    int(embedded.get(row.id, 0)),
                    row.created_at.date() if row.created_at else None,
                )
            ]
        )
    filename = f"taxlens-documents-{datetime.now(UTC):%Y-%m-%d}.csv"
    # The byte-order mark makes Excel read the file as UTF-8, so Vietnamese shows correctly.
    return Response(
        content="\ufeff" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _spreadsheet_safe(value: object) -> object:
    """Keep spreadsheet programs from running a cell that starts like a formula."""

    if value is None:
        return ""
    if isinstance(value, str) and value[:1] in ("=", "+", "@", "\t", "\r"):
        return "'" + value
    return value

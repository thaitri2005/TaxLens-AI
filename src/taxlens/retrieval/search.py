from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import Select, func, literal_column, select
from sqlalchemy.orm import Session

from taxlens.legal_data.models import DocumentChunk, DocumentVersion, LegalDocument


@dataclass(frozen=True)
class SearchFilters:
    document_number: str | None = None
    document_type: str | None = None
    legal_status: str | None = None
    issuing_agency: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None


@dataclass(frozen=True)
class SearchResult:
    chunk: DocumentChunk
    version: DocumentVersion
    document: LegalDocument
    score: float


def search_chunks(
    session: Session,
    query: str,
    filters: SearchFilters | None = None,
    limit: int = 20,
) -> list[SearchResult]:
    normalized_query = query.strip()
    if not normalized_query:
        return []
    active_filters = filters or SearchFilters()

    if session.get_bind().dialect.name == "postgresql":
        statement = _postgresql_search_statement(normalized_query, active_filters, limit)
    else:
        statement = _fallback_search_statement(normalized_query, active_filters, limit)

    rows = session.execute(statement).all()
    return [
        SearchResult(chunk=chunk, version=version, document=document, score=float(score))
        for chunk, version, document, score in rows
    ]


def _postgresql_search_statement(query: str, filters: SearchFilters, limit: int) -> Select[Any]:
    search_config: Any = literal_column("'simple'::regconfig")
    searchable_content = func.coalesce(DocumentChunk.heading, "") + " " + DocumentChunk.content
    search_vector = func.to_tsvector(search_config, searchable_content)
    search_query = func.websearch_to_tsquery(search_config, query)
    score: Any = func.ts_rank_cd(search_vector, search_query).label("score")

    statement = _base_statement(score)
    statement = statement.where(search_vector.op("@@")(search_query))
    statement = _apply_filters(statement, filters)
    return statement.order_by(score.desc(), DocumentChunk.id).limit(limit)


def _fallback_search_statement(query: str, filters: SearchFilters, limit: int) -> Select[Any]:
    score: Any = literal_column("1.0").label("score")
    normalized_query = f"%{query.lower()}%"
    statement = _base_statement(score)
    statement = statement.where(
        func.lower(DocumentChunk.content).like(normalized_query)
        | func.lower(func.coalesce(DocumentChunk.heading, "")).like(normalized_query)
        | func.lower(LegalDocument.title).like(normalized_query)
        | func.lower(LegalDocument.document_number).like(normalized_query)
    )
    statement = _apply_filters(statement, filters)
    return statement.order_by(DocumentChunk.id).limit(limit)


def _base_statement(score: Any) -> Select[Any]:
    return (
        select(DocumentChunk, DocumentVersion, LegalDocument, score)
        .join(DocumentVersion, DocumentChunk.document_version_id == DocumentVersion.id)
        .join(LegalDocument, DocumentVersion.document_id == LegalDocument.id)
    )


def _apply_filters(statement: Select[Any], filters: SearchFilters) -> Select[Any]:
    if filters.document_number is not None:
        statement = statement.where(
            LegalDocument.document_number.ilike(f"%{filters.document_number}%")
        )
    if filters.document_type is not None:
        statement = statement.where(LegalDocument.document_type == filters.document_type)
    if filters.legal_status is not None:
        statement = statement.where(DocumentVersion.legal_status == filters.legal_status)
    if filters.issuing_agency is not None:
        statement = statement.where(
            LegalDocument.issuing_agency.ilike(f"%{filters.issuing_agency}%")
        )
    if filters.effective_from is not None:
        statement = statement.where(DocumentVersion.effective_date >= filters.effective_from)
    if filters.effective_to is not None:
        statement = statement.where(DocumentVersion.effective_date <= filters.effective_to)
    return statement

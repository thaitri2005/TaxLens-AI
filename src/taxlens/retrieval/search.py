from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from sqlalchemy import Select, func, literal_column, select
from sqlalchemy.orm import Session

from taxlens.legal_data.models import (
    DocumentChunk,
    DocumentEmbedding,
    DocumentVersion,
    LegalDocument,
    SourceRecord,
)
from taxlens.retrieval.embeddings import EmbeddingProvider
from taxlens.retrieval.reranking import NoOpReranker, Reranker

SearchMode = Literal["keyword", "semantic", "hybrid"]
RRF_K = 60


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
    source_url: str | None = None
    keyword_score: float | None = None
    vector_score: float | None = None
    fused_score: float = 0.0

    @property
    def score(self) -> float:
        return self.fused_score


def search_chunks(
    session: Session,
    query: str,
    filters: SearchFilters | None = None,
    limit: int = 20,
) -> list[SearchResult]:
    return keyword_search_chunks(session, query, filters, limit)


def keyword_search_chunks(
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
        statement = _postgresql_keyword_statement(normalized_query, active_filters, limit)
    else:
        statement = _fallback_keyword_statement(normalized_query, active_filters, limit)
    return _to_keyword_results(session.execute(statement).all())


def semantic_search_chunks(
    session: Session,
    query_vector: list[float],
    provider: EmbeddingProvider,
    filters: SearchFilters | None = None,
    limit: int = 20,
) -> list[SearchResult]:
    if session.get_bind().dialect.name != "postgresql":
        return []
    active_filters = filters or SearchFilters()
    distance = DocumentEmbedding.embedding.cosine_distance(query_vector)
    score: Any = (1 - distance).label("score")
    statement = (
        _base_statement(score)
        .join(DocumentEmbedding, DocumentEmbedding.document_chunk_id == DocumentChunk.id)
        .where(
            DocumentEmbedding.model_id == provider.model_id,
            DocumentEmbedding.model_revision == provider.model_revision,
            DocumentEmbedding.dimensions == provider.dimensions,
        )
    )
    statement = _apply_filters(statement, active_filters)
    rows = session.execute(statement.order_by(distance, DocumentChunk.id).limit(limit)).all()
    return [
        SearchResult(
            chunk=chunk,
            version=version,
            document=document,
            source_url=source_url,
            vector_score=float(score_value),
            fused_score=float(score_value),
        )
        for chunk, version, document, source_url, score_value in rows
    ]


def hybrid_search_chunks(
    session: Session,
    query: str,
    provider: EmbeddingProvider | None,
    filters: SearchFilters | None = None,
    limit: int = 20,
    candidate_limit: int = 50,
    reranker: Reranker | None = None,
) -> list[SearchResult]:
    keyword_results = keyword_search_chunks(session, query, filters, candidate_limit)
    if provider is None or session.get_bind().dialect.name != "postgresql":
        return (reranker or NoOpReranker()).rerank(query, keyword_results, limit).results

    query_embedding = provider.embed_query(query)
    semantic_results = semantic_search_chunks(
        session,
        query_embedding.vectors[0],
        provider,
        filters,
        candidate_limit,
    )
    fused_results = fuse_ranked_results(keyword_results, semantic_results, candidate_limit)
    return (reranker or NoOpReranker()).rerank(query, fused_results, limit).results


def fuse_ranked_results(
    keyword_results: list[SearchResult],
    semantic_results: list[SearchResult],
    limit: int,
) -> list[SearchResult]:
    fused: dict[str, SearchResult] = {}
    scores: dict[str, float] = {}

    for rank, result in enumerate(keyword_results, start=1):
        key = str(result.chunk.id)
        fused[key] = result
        scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + rank)

    for rank, result in enumerate(semantic_results, start=1):
        key = str(result.chunk.id)
        existing = fused.get(key)
        if existing is None:
            fused[key] = result
        else:
            fused[key] = SearchResult(
                chunk=existing.chunk,
                version=existing.version,
                document=existing.document,
                source_url=existing.source_url,
                keyword_score=existing.keyword_score,
                vector_score=result.vector_score,
            )
        scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + rank)

    return sorted(
        [
            SearchResult(
                chunk=result.chunk,
                version=result.version,
                document=result.document,
                source_url=result.source_url,
                keyword_score=result.keyword_score,
                vector_score=result.vector_score,
                fused_score=scores[key],
            )
            for key, result in fused.items()
        ],
        key=lambda result: (-result.fused_score, str(result.chunk.id)),
    )[:limit]


def _postgresql_keyword_statement(query: str, filters: SearchFilters, limit: int) -> Select[Any]:
    search_config: Any = literal_column("'simple'::regconfig")
    searchable_content = func.coalesce(DocumentChunk.heading, "") + " " + DocumentChunk.content
    search_vector = func.to_tsvector(search_config, searchable_content)
    search_query = func.websearch_to_tsquery(search_config, query)
    score: Any = func.ts_rank_cd(search_vector, search_query).label("score")
    statement = _base_statement(score).where(search_vector.op("@@")(search_query))
    statement = _apply_filters(statement, filters)
    return statement.order_by(score.desc(), DocumentChunk.id).limit(limit)


def _fallback_keyword_statement(query: str, filters: SearchFilters, limit: int) -> Select[Any]:
    score: Any = literal_column("1.0").label("score")
    normalized_query = f"%{query.lower()}%"
    statement = _base_statement(score).where(
        func.lower(DocumentChunk.content).like(normalized_query)
        | func.lower(func.coalesce(DocumentChunk.heading, "")).like(normalized_query)
        | func.lower(LegalDocument.title).like(normalized_query)
        | func.lower(LegalDocument.document_number).like(normalized_query)
    )
    statement = _apply_filters(statement, filters)
    return statement.order_by(DocumentChunk.id).limit(limit)


def _base_statement(score: Any) -> Select[Any]:
    return (
        select(DocumentChunk, DocumentVersion, LegalDocument, SourceRecord, score)
        .join(DocumentVersion, DocumentChunk.document_version_id == DocumentVersion.id)
        .join(LegalDocument, DocumentVersion.document_id == LegalDocument.id)
        .outerjoin(SourceRecord, DocumentVersion.source_record_id == SourceRecord.id)
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


def _to_keyword_results(rows: Sequence[Any]) -> list[SearchResult]:
    return [
        SearchResult(
            chunk=chunk,
            version=version,
            document=document,
            source_url=source_url.source_url if source_url is not None else None,
            keyword_score=float(score),
            fused_score=float(score),
        )
        for chunk, version, document, source_url, score in rows
    ]

import operator
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from functools import reduce
from typing import Any, Literal

from sqlalchemy import Select, case, func, literal_column, select
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
from taxlens.retrieval.text import fold_vietnamese

SearchMode = Literal["keyword", "semantic", "hybrid"]
RRF_K = 60
MAX_KEYWORD_TERMS = 12
EXACT_MATCH_WEIGHT = 0.5
_TERM_EDGE_CHARACTERS = "\"'“”‘’.,;:!?()[]{}<>…"
# Question words and function words that appear in almost every passage. Words that
# change legal meaning (for example "không" in "không chịu thuế") are deliberately kept.
_KEYWORD_STOPWORDS = frozenset(
    {
        "là", "của", "và", "các", "những", "được", "cho", "trong", "với", "về", "theo",
        "thì", "này", "đó", "nào", "gì", "bao", "nhiêu", "như", "thế", "có", "một", "để",
        "từ", "tại", "khi", "nếu", "hay", "hoặc", "ạ", "nhé", "vậy", "sao",
        "a", "an", "the", "of", "to", "in", "on", "for", "and", "or", "is", "are", "be",
        "what", "which", "how", "when", "does", "do", "with", "by", "about",
    }
)
_FOLDED_KEYWORD_STOPWORDS = frozenset(fold_vietnamese(word) for word in _KEYWORD_STOPWORDS)


@dataclass(frozen=True)
class SearchFilters:
    document_number: str | None = None
    document_type: str | None = None
    source_name: str | None = None
    legal_status: str | None = None
    issuing_agency: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    # Any of these recorded types (a document kind); an empty tuple matches nothing.
    document_types: tuple[str, ...] | None = None


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
    normalized_query = unicodedata.normalize("NFC", query).strip()
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
    return _to_semantic_results(rows)


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
        return (reranker or NoOpReranker()).rerank(
            query, deduplicate_passages(keyword_results), limit
        ).results

    query_embedding = provider.embed_query(query)
    semantic_results = semantic_search_chunks(
        session,
        query_embedding.vectors[0],
        provider,
        filters,
        candidate_limit,
    )
    fused_results = fuse_ranked_results(keyword_results, semantic_results, candidate_limit)
    return (reranker or NoOpReranker()).rerank(
        query, deduplicate_passages(fused_results), limit
    ).results


def deduplicate_passages(results: list[SearchResult]) -> list[SearchResult]:
    """Keep the best-ranked copy of a passage that exists in several versions.

    One document can be held twice (an OCR'd PDF and a Word file of the same text, or a
    re-published attachment); the same article and clause would otherwise fill several of
    the few slots given to the model.
    """

    versions_by_location: dict[tuple[object, ...], object] = {}
    unique: list[SearchResult] = []
    for result in results:
        chunk = result.chunk
        if chunk.article_number is None and chunk.heading is None:
            unique.append(result)
            continue
        location = (result.document.id, chunk.article_number, chunk.clause_number, chunk.heading)
        kept_version = versions_by_location.setdefault(location, result.version.id)
        # Parts of one long clause share a location within a version and are all kept; the
        # same location in another version of the document is a duplicate.
        if kept_version == result.version.id:
            unique.append(result)
    return unique


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


def keyword_terms(query: str) -> list[str]:
    """Split a natural-language query into distinct, meaningful search terms."""

    terms: list[str] = []
    seen: set[str] = set()
    for raw_term in unicodedata.normalize("NFC", query).split():
        term = raw_term.strip(_TERM_EDGE_CHARACTERS).lstrip("-")
        lowered = term.casefold()
        if (
            not term
            or lowered in seen
            or _is_stopword(lowered)
            or not any(character.isalnum() for character in term)
        ):
            continue
        seen.add(lowered)
        terms.append(term)
    return terms[:MAX_KEYWORD_TERMS]


def _is_stopword(term: str) -> bool:
    # An accented term is compared as typed; an unaccented one is compared with the folded
    # stopwords, so "la bao nhieu" is handled like "là bao nhiêu" without dropping
    # "cơ" (in "cơ quan") because it folds to the same "co" as "có".
    if fold_vietnamese(term) != term:
        return term in _KEYWORD_STOPWORDS
    return term in _FOLDED_KEYWORD_STOPWORDS


def _postgresql_keyword_statement(query: str, filters: SearchFilters, limit: int) -> Select[Any]:
    """Rank chunks by how many query terms they contain, ignoring diacritics.

    Matching any term (instead of websearch_to_tsquery's implicit AND) keeps natural
    questions searchable; counting matched terms still ranks chunks containing all of them
    first. Matching runs on the accent-folded vector, so unaccented queries and OCR text
    that lost diacritics match; an exact accented match earns a bonus, which keeps "thuế"
    (tax) ahead of "thuê" (rent) although both fold to "thue".
    """

    terms = keyword_terms(query) or [query]
    folded_terms = list(dict.fromkeys(fold_vietnamese(term).casefold() for term in terms))
    accented_terms = [term for term in terms if fold_vietnamese(term) != term]
    config: Any = literal_column("'simple'::regconfig")
    folded_vector: Any = literal_column("document_chunks.search_vector_folded")
    accented_vector: Any = literal_column("document_chunks.search_vector")
    any_term_query = func.websearch_to_tsquery(config, " or ".join(folded_terms))
    folded_matches = _matched_term_count(folded_vector, config, folded_terms)
    score_parts = [folded_matches, func.ts_rank_cd(folded_vector, any_term_query, 32)]
    if accented_terms:
        score_parts.append(
            EXACT_MATCH_WEIGHT * _matched_term_count(accented_vector, config, accented_terms)
        )
    score: Any = reduce(operator.add, score_parts).label("score")
    statement = _base_statement(score).where(folded_vector.op("@@")(any_term_query))
    statement = _apply_filters(statement, filters)
    return statement.order_by(score.desc(), DocumentChunk.id).limit(limit)


def _matched_term_count(vector: Any, config: Any, terms: list[str]) -> Any:
    return reduce(
        operator.add,
        [
            case((vector.op("@@")(func.websearch_to_tsquery(config, term)), 1), else_=0)
            for term in terms
        ],
    )


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
    if filters.document_types is not None:
        statement = statement.where(LegalDocument.document_type.in_(filters.document_types))
    if filters.source_name is not None:
        statement = statement.where(SourceRecord.source_name == filters.source_name)
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


def _to_semantic_results(rows: Sequence[Any]) -> list[SearchResult]:
    return [
        SearchResult(
            chunk=chunk,
            version=version,
            document=document,
            source_url=source_url.source_url if source_url is not None else None,
            vector_score=float(score_value),
            fused_score=float(score_value),
        )
        for chunk, version, document, source_url, score_value in rows
    ]


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

import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from taxlens.api.auth import require_authenticated_user
from taxlens.db import get_db_session
from taxlens.legal_data.document_kinds import document_types_of_kind
from taxlens.retrieval.citations import Citation, build_citation
from taxlens.retrieval.embeddings import get_available_embedding_provider
from taxlens.retrieval.search import (
    SearchFilters,
    hybrid_search_chunks,
    keyword_search_chunks,
    semantic_search_chunks,
)
from taxlens.retrieval.snippets import build_excerpt

router = APIRouter(
    prefix="/search", tags=["search"], dependencies=[Depends(require_authenticated_user)]
)


class SearchCitation(BaseModel):
    document_id: uuid.UUID
    version_id: uuid.UUID
    document_number: str
    title: str
    heading: str | None
    version_label: str | None
    legal_status: str
    effective_date: date | None
    article_number: str | None
    clause_number: str | None
    page_start: int | None
    page_end: int | None
    source_artifact_key: str
    source_url: str | None
    excerpt: str | None = None


class SearchHit(BaseModel):
    chunk_id: uuid.UUID
    keyword_score: float | None
    vector_score: float | None
    fused_score: float
    snippet: str
    content: str
    citation: SearchCitation


@router.get("", response_model=list[SearchHit])
def search(
    q: str = Query(min_length=1, max_length=500),
    document_number: str | None = Query(default=None, max_length=100),
    document_type: str | None = Query(default=None, max_length=50),
    kind: str | None = Query(default=None, max_length=30),
    source_name: str | None = Query(default=None, max_length=120),
    legal_status: str | None = Query(default=None, max_length=50),
    issuing_agency: str | None = Query(default=None, max_length=255),
    effective_from: date | None = None,
    effective_to: date | None = None,
    mode: Literal["keyword", "semantic", "hybrid"] = "hybrid",
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=200),
    session: Session = Depends(get_db_session),
) -> list[SearchHit]:
    """Ranked passages; ``offset`` pages through them (``limit`` per page).

    Ranking is computed for the first ``offset + limit`` passages and the page is sliced
    from that list, so pages stay consistent with each other.
    """

    window = offset + limit
    filters = SearchFilters(
        document_number=document_number,
        document_type=document_type,
        source_name=source_name,
        legal_status=legal_status,
        issuing_agency=issuing_agency,
        effective_from=effective_from,
        effective_to=effective_to,
        document_types=(
            tuple(document_types_of_kind(session, kind)) if kind is not None else None
        ),
    )
    if mode == "keyword":
        results = keyword_search_chunks(session, q, filters, window)
    else:
        provider = (
            get_available_embedding_provider()
            if session.get_bind().dialect.name == "postgresql"
            else None
        )
        if mode == "semantic" and provider is not None:
            query_embedding = provider.embed_query(q)
            results = semantic_search_chunks(
                session,
                query_embedding.vectors[0],
                provider,
                filters,
                window,
            )
        elif mode == "semantic":
            results = []
        else:
            results = hybrid_search_chunks(
                session, q, provider, filters, window, candidate_limit=max(50, window)
            )
    return [
        SearchHit(
            chunk_id=result.chunk.id,
            keyword_score=result.keyword_score,
            vector_score=result.vector_score,
            fused_score=result.fused_score,
            snippet=build_excerpt(result.chunk.content, q, maximum_length=260),
            content=result.chunk.content,
            citation=to_search_citation(build_citation(result)),
        )
        for result in results[offset:window]
    ]


def to_search_citation(citation: Citation) -> SearchCitation:
    return SearchCitation(
        document_id=citation.document_id,
        version_id=citation.version_id,
        document_number=citation.document_number,
        title=citation.title,
        heading=citation.heading,
        version_label=citation.version_label,
        legal_status=citation.legal_status,
        effective_date=citation.effective_date,
        article_number=citation.article_number,
        clause_number=citation.clause_number,
        page_start=citation.page_start,
        page_end=citation.page_end,
        source_artifact_key=citation.source_artifact_key,
        source_url=citation.source_url,
        excerpt=citation.excerpt,
    )

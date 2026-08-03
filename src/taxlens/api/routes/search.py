import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from taxlens.db import get_db_session
from taxlens.retrieval.search import SearchFilters, search_chunks

router = APIRouter(prefix="/search", tags=["search"])


class SearchCitation(BaseModel):
    document_id: uuid.UUID
    version_id: uuid.UUID
    document_number: str
    title: str
    legal_status: str
    article_number: str | None
    clause_number: str | None
    page_start: int | None
    page_end: int | None
    source_artifact_key: str


class SearchHit(BaseModel):
    chunk_id: uuid.UUID
    score: float
    content: str
    citation: SearchCitation


@router.get("", response_model=list[SearchHit])
def search(
    q: str = Query(min_length=1, max_length=500),
    document_number: str | None = Query(default=None, max_length=100),
    document_type: str | None = Query(default=None, max_length=50),
    legal_status: str | None = Query(default=None, max_length=50),
    issuing_agency: str | None = Query(default=None, max_length=255),
    effective_from: date | None = None,
    effective_to: date | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db_session),
) -> list[SearchHit]:
    filters = SearchFilters(
        document_number=document_number,
        document_type=document_type,
        legal_status=legal_status,
        issuing_agency=issuing_agency,
        effective_from=effective_from,
        effective_to=effective_to,
    )
    results = search_chunks(session, q, filters, limit)
    return [
        SearchHit(
            chunk_id=result.chunk.id,
            score=result.score,
            content=result.chunk.content,
            citation=SearchCitation(
                document_id=result.document.id,
                version_id=result.version.id,
                document_number=result.document.document_number,
                title=result.document.title,
                legal_status=result.version.legal_status,
                article_number=result.chunk.article_number,
                clause_number=result.chunk.clause_number,
                page_start=result.chunk.page_start,
                page_end=result.chunk.page_end,
                source_artifact_key=result.version.raw_artifact_key,
            ),
        )
        for result in results
    ]


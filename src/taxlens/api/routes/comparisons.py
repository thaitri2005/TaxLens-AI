from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from taxlens.api.routes.search import SearchCitation
from taxlens.db import get_db_session
from taxlens.intelligence.chat import get_chat_provider
from taxlens.intelligence.comparison import (
    ComparisonError,
    ComparisonSummary,
    DocumentComparison,
    compare_documents,
    summarize_comparison,
)
from taxlens.retrieval.citations import Citation

router = APIRouter(prefix="/comparisons", tags=["comparisons"])


class ComparisonRequest(BaseModel):
    before_document_number: str = Field(min_length=1, max_length=100)
    after_document_number: str = Field(min_length=1, max_length=100)


class ArticleChangeResponse(BaseModel):
    key: str
    change_type: Literal["ADDED", "REMOVED", "MODIFIED", "UNCHANGED"]
    before_content: str | None
    after_content: str | None
    before_citation: SearchCitation | None
    after_citation: SearchCitation | None


class ComparisonResponse(BaseModel):
    before_document_number: str
    after_document_number: str
    before_version_id: str
    after_version_id: str
    changes: list[ArticleChangeResponse]


class ComparisonSummaryResponse(BaseModel):
    comparison: ComparisonResponse
    summary: str
    practical_impact: str
    uncertainties: list[str]
    referenced_change_keys: list[str]
    disclaimer: str


@router.post("", response_model=ComparisonResponse)
def compare(
    request: ComparisonRequest,
    session: Session = Depends(get_db_session),
) -> ComparisonResponse:
    try:
        result = compare_documents(
            session,
            request.before_document_number,
            request.after_document_number,
        )
    except ComparisonError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return _to_response(result)


@router.post("/summary", response_model=ComparisonSummaryResponse)
def summarize(
    request: ComparisonRequest,
    session: Session = Depends(get_db_session),
) -> ComparisonSummaryResponse:
    try:
        comparison = compare_documents(
            session,
            request.before_document_number,
            request.after_document_number,
        )
        result = summarize_comparison(comparison, get_chat_provider())
    except ComparisonError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
    return _summary_response(result)


def _to_response(result: DocumentComparison) -> ComparisonResponse:
    return ComparisonResponse(
        before_document_number=result.before_document_number,
        after_document_number=result.after_document_number,
        before_version_id=result.before_version_id,
        after_version_id=result.after_version_id,
        changes=[
            ArticleChangeResponse(
                key=change.key,
                change_type=change.change_type,
                before_content=change.before_content,
                after_content=change.after_content,
                before_citation=_citation_response(change.before_citation),
                after_citation=_citation_response(change.after_citation),
            )
            for change in result.changes
        ],
    )


def _summary_response(result: ComparisonSummary) -> ComparisonSummaryResponse:
    return ComparisonSummaryResponse(
        comparison=_to_response(result.comparison),
        summary=result.summary,
        practical_impact=result.practical_impact,
        uncertainties=result.uncertainties,
        referenced_change_keys=list(result.referenced_change_keys),
        disclaimer="This summary explains source differences and is not legal or tax advice.",
    )


def _citation_response(citation: Citation | None) -> SearchCitation | None:
    if citation is None:
        return None
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
    )

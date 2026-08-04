from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from taxlens.api.routes.search import SearchCitation
from taxlens.db import get_db_session
from taxlens.intelligence.chat import get_chat_provider
from taxlens.intelligence.qa import QuestionAnswer, answer_question
from taxlens.retrieval.embeddings import get_embedding_provider

router = APIRouter(prefix="/questions", tags=["questions"])


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


class ClaimResponse(BaseModel):
    text: str
    citation_numbers: list[int]


class QuestionResponse(BaseModel):
    status: Literal[
        "ANSWERED",
        "UNSUPPORTED",
        "INSUFFICIENT_EVIDENCE",
        "PROVIDER_UNAVAILABLE",
        "INVALID_MODEL_OUTPUT",
    ]
    intent: str
    evidence_status: str | None
    answer: str | None
    confirmed_facts: list[ClaimResponse]
    interpretation: str | None
    uncertainties: list[str]
    citations: list[SearchCitation]
    review_actions: list[str]
    disclaimer: str


@router.post("", response_model=QuestionResponse)
def ask_question(
    request: QuestionRequest,
    session: Session = Depends(get_db_session),
) -> QuestionResponse:
    embedding_provider = (
        get_embedding_provider() if session.get_bind().dialect.name == "postgresql" else None
    )
    result = answer_question(
        session,
        request.question,
        get_chat_provider(),
        embedding_provider,
    )
    return _to_response(result)


def _to_response(result: QuestionAnswer) -> QuestionResponse:
    return QuestionResponse(
        status=result.status.value,
        intent=result.query_plan.intent.value,
        evidence_status=result.evidence.status.value if result.evidence else None,
        answer=result.answer,
        confirmed_facts=[
            ClaimResponse(text=claim.text, citation_numbers=list(claim.citation_numbers))
            for claim in result.confirmed_facts
        ],
        interpretation=result.interpretation,
        uncertainties=result.uncertainties,
        citations=[
            SearchCitation(
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
            for citation in result.citations
        ],
        review_actions=result.review_actions,
        disclaimer=result.disclaimer,
    )

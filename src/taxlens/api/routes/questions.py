from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from taxlens.api.auth import AuthenticatedUser, ask_rate_limiter, require_authenticated_user
from taxlens.api.routes.search import SearchCitation, to_search_citation
from taxlens.db import get_db_session
from taxlens.intelligence.chat import get_chat_provider
from taxlens.intelligence.qa import QuestionAnswer, answer_question
from taxlens.retrieval.embeddings import get_available_embedding_provider

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
    practical_advice: list[str]
    disclaimer: str


@router.post("", response_model=QuestionResponse)
def ask_question(
    request: QuestionRequest,
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: Session = Depends(get_db_session),
) -> QuestionResponse:
    ask_rate_limiter.check(str(user.id))
    embedding_provider = (
        get_available_embedding_provider()
        if session.get_bind().dialect.name == "postgresql"
        else None
    )
    result = answer_question(
        session,
        request.question,
        get_chat_provider(),
        embedding_provider,
        retrieval_limit=5,
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
        citations=[to_search_citation(citation) for citation in result.citations],
        review_actions=result.review_actions,
        practical_advice=result.practical_advice,
        disclaimer=result.disclaimer,
    )

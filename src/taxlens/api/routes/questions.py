import logging
import uuid
from datetime import UTC, datetime
from time import perf_counter
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from taxlens.api.auth import AuthenticatedUser, ask_rate_limiter, require_authenticated_user
from taxlens.api.routes.search import SearchCitation, to_search_citation
from taxlens.db import get_db_session
from taxlens.intelligence.chat import get_chat_provider
from taxlens.intelligence.qa import QuestionAnswer, answer_question
from taxlens.legal_data.models import QuestionLog
from taxlens.retrieval.embeddings import get_available_embedding_provider

logger = logging.getLogger(__name__)
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
    # The question's entry in the log, for its feedback; None if the log could not be written.
    question_id: uuid.UUID | None = None


class FeedbackRequest(BaseModel):
    rating: Literal["up", "down"]
    comment: str | None = Field(default=None, max_length=1000)


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
    started = perf_counter()
    result = answer_question(
        session,
        request.question,
        get_chat_provider(),
        embedding_provider,
        retrieval_limit=5,
    )
    response = _to_response(result)
    response.question_id = _log_question(
        session, user, request.question, result, perf_counter() - started
    )
    return response


@router.post("/{question_id}/feedback", status_code=status.HTTP_204_NO_CONTENT)
def give_feedback(
    question_id: uuid.UUID,
    feedback: FeedbackRequest,
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: Session = Depends(get_db_session),
) -> None:
    """Rate an answer; only the person who asked may rate it, and a new rating replaces one."""

    entry = session.get(QuestionLog, question_id)
    if entry is None or entry.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    entry.rating = 1 if feedback.rating == "up" else -1
    entry.comment = (feedback.comment or "").strip() or None
    entry.rated_at = datetime.now(UTC)
    session.commit()
    logger.info("question_rated id=%s rating=%s", question_id, feedback.rating)


def _log_question(
    session: Session,
    user: AuthenticatedUser,
    question: str,
    result: QuestionAnswer,
    seconds: float,
) -> uuid.UUID | None:
    """Record the question and its outcome; a failure here never costs the asker the answer."""

    entry = QuestionLog(
        user_id=user.id,
        question=question,
        intent=result.query_plan.intent.value,
        status=result.status.value,
        evidence_status=result.evidence.status.value if result.evidence else None,
        answer=result.answer,
        cited_documents=[citation.document_number for citation in result.citations],
        seconds=round(seconds, 2),
    )
    try:
        session.add(entry)
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        logger.exception("question_log_failed")
        return None
    logger.info(
        "question_logged id=%s status=%s seconds=%.2f", entry.id, entry.status, entry.seconds
    )
    return entry.id


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

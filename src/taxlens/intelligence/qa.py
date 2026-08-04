import json
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy.orm import Session

from taxlens.intelligence.chat import ChatMessage, ChatProvider, ChatProviderError, ChatRequest
from taxlens.intelligence.evidence import EvidenceAssessment, assess_evidence
from taxlens.intelligence.planning import QueryIntent, QueryPlan, plan_query
from taxlens.retrieval.citations import Citation, build_citation
from taxlens.retrieval.embeddings import EmbeddingProvider
from taxlens.retrieval.search import SearchResult, hybrid_search_chunks


class AnswerStatus(StrEnum):
    ANSWERED = "ANSWERED"
    UNSUPPORTED = "UNSUPPORTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    INVALID_MODEL_OUTPUT = "INVALID_MODEL_OUTPUT"


@dataclass(frozen=True)
class CitedClaim:
    text: str
    citation_numbers: tuple[int, ...]


@dataclass(frozen=True)
class GeneratedAnswer:
    answer: str
    confirmed_facts: list[CitedClaim]
    interpretation: str | None
    uncertainties: list[str]
    review_actions: list[str]


@dataclass(frozen=True)
class QuestionAnswer:
    status: AnswerStatus
    query_plan: QueryPlan
    evidence: EvidenceAssessment | None
    answer: str | None
    confirmed_facts: list[CitedClaim]
    interpretation: str | None
    uncertainties: list[str]
    citations: list[Citation]
    review_actions: list[str]
    disclaimer: str


def answer_question(
    session: Session,
    question: str,
    chat_provider: ChatProvider,
    embedding_provider: EmbeddingProvider | None = None,
    retrieval_limit: int = 5,
) -> QuestionAnswer:
    query_plan = plan_query(question)
    if query_plan.intent is QueryIntent.UNSUPPORTED:
        return _safe_answer(
            AnswerStatus.UNSUPPORTED,
            query_plan,
            None,
            "The request is outside the supported regulatory-question scope.",
            [],
        )

    results = hybrid_search_chunks(
        session,
        query_plan.original_query,
        embedding_provider,
        query_plan.filters,
        limit=retrieval_limit,
    )
    evidence = assess_evidence(results)
    citations = [build_citation(result) for result in results]
    if not evidence.is_sufficient:
        return _safe_answer(
            AnswerStatus.INSUFFICIENT_EVIDENCE,
            query_plan,
            evidence,
            evidence.reason,
            citations,
        )

    try:
        completion = chat_provider.complete(
            ChatRequest(messages=_build_messages(query_plan, results, citations))
        )
    except ChatProviderError:
        return _safe_answer(
            AnswerStatus.PROVIDER_UNAVAILABLE,
            query_plan,
            evidence,
            "The configured language model is unavailable; review the cited evidence directly.",
            citations,
        )

    try:
        generated = parse_generated_answer(completion.content, len(citations))
    except ValueError:
        return _safe_answer(
            AnswerStatus.INVALID_MODEL_OUTPUT,
            query_plan,
            evidence,
            "The model response did not meet the required evidence-linked format.",
            citations,
        )

    return QuestionAnswer(
        status=AnswerStatus.ANSWERED,
        query_plan=query_plan,
        evidence=evidence,
        answer=generated.answer,
        confirmed_facts=generated.confirmed_facts,
        interpretation=generated.interpretation,
        uncertainties=generated.uncertainties,
        citations=citations,
        review_actions=generated.review_actions,
        disclaimer=_disclaimer(),
    )


def parse_generated_answer(content: str, citation_count: int) -> GeneratedAnswer:
    content = _unwrap_json_content(content)
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as error:
        raise ValueError("Model response is not JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("Model response must be a JSON object")

    answer = _required_text(payload, "answer")
    confirmed_facts = _parse_claims(payload.get("confirmed_facts"), citation_count)
    interpretation = _optional_text(payload.get("interpretation"))
    uncertainties = _text_list(payload.get("uncertainties"), "uncertainties")
    review_actions = _text_list(payload.get("review_actions"), "review_actions")
    return GeneratedAnswer(
        answer=answer,
        confirmed_facts=confirmed_facts,
        interpretation=interpretation,
        uncertainties=uncertainties,
        review_actions=review_actions,
    )


def _build_messages(
    query_plan: QueryPlan,
    results: Sequence[SearchResult],
    citations: Sequence[Citation],
) -> list[ChatMessage]:
    evidence_blocks = "\n\n".join(
        (
            f"[{index}] {citation.document_number} | {citation.legal_status} | "
            f"Article {citation.article_number or 'n/a'} | "
            f"Clause {citation.clause_number or 'n/a'} | "
            f"Pages {citation.page_start or 'n/a'}-{citation.page_end or 'n/a'}\n"
            f"{result.chunk.content[:2500]}"
        )
        for index, (result, citation) in enumerate(zip(results, citations, strict=True), start=1)
    )
    system_prompt = (
        "You are a Vietnamese tax-regulation research assistant. Use only the provided evidence. "
        "Do not invent legal facts, give definitive professional advice, or cite sources outside "
        "the list. Return valid JSON only with: answer (string), confirmed_facts (array of objects "
        "with text and citation_numbers), interpretation (string or null), uncertainties (array "
        "of strings), and review_actions (array of strings). Every confirmed fact needs one or "
        "more valid citation numbers."
    )
    user_prompt = (
        f"Intent: {query_plan.intent}\nQuestion: {query_plan.original_query}\n\n"
        f"Evidence:\n{evidence_blocks}"
    )
    return [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=user_prompt),
    ]


def _safe_answer(
    status: AnswerStatus,
    query_plan: QueryPlan,
    evidence: EvidenceAssessment | None,
    uncertainty: str,
    citations: list[Citation],
) -> QuestionAnswer:
    return QuestionAnswer(
        status=status,
        query_plan=query_plan,
        evidence=evidence,
        answer=None,
        confirmed_facts=[],
        interpretation=None,
        uncertainties=[uncertainty],
        citations=citations,
        review_actions=["Review the cited source material or refine the question and filters."],
        disclaimer=_disclaimer(),
    )


def _required_text(payload: dict[object, object], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Optional text must be a string or null")
    return value.strip() or None


def _text_list(value: object, name: str) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ValueError(f"{name} must be an array of non-empty strings")
    return [item.strip() for item in value]


def _parse_claims(value: object, citation_count: int) -> list[CitedClaim]:
    if not isinstance(value, list):
        raise ValueError("confirmed_facts must be an array")
    if all(isinstance(item, str) and item.strip() for item in value):
        if citation_count == 0:
            raise ValueError("Confirmed facts require citations")
        return [
            CitedClaim(text=item.strip(), citation_numbers=tuple(range(1, citation_count + 1)))
            for item in value
        ]
    claims: list[CitedClaim] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("Each confirmed fact must be an object")
        text = _required_text(item, "text")
        citation_numbers = item.get("citation_numbers")
        normalized_numbers = _normalize_citation_numbers(citation_numbers, citation_count)
        if not normalized_numbers:
            raise ValueError("Each confirmed fact needs valid citation numbers")
        claims.append(CitedClaim(text=text, citation_numbers=tuple(normalized_numbers)))
    return claims


def _normalize_citation_numbers(value: object, citation_count: int) -> list[int]:
    if not isinstance(value, list):
        return []
    normalized: list[int] = []
    for number in value:
        if isinstance(number, int) and not isinstance(number, bool):
            normalized_number = number
        elif isinstance(number, str) and number.isdigit():
            normalized_number = int(number)
        else:
            return []
        if not 1 <= normalized_number <= citation_count:
            return []
        normalized.append(normalized_number)
    return normalized


def _unwrap_json_content(content: str) -> str:
    normalized = content.strip()
    if normalized.startswith("```") and normalized.endswith("```"):
        lines = normalized.splitlines()
        return "\n".join(lines[1:-1]).strip()
    return normalized


def _disclaimer() -> str:
    return "This is evidence-grounded research assistance, not legal or tax advice."

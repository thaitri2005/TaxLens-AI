import json
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from functools import lru_cache
from typing import Any, TypedDict

from langchain_core.prompts import PromptTemplate
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.orm import Session

from taxlens.config import get_settings
from taxlens.intelligence.chat import ChatMessage, ChatProvider, ChatProviderError, ChatRequest
from taxlens.intelligence.evidence import EvidenceAssessment, assess_evidence
from taxlens.intelligence.planning import QueryIntent, QueryPlan, plan_query
from taxlens.retrieval.citations import Citation, build_citation
from taxlens.retrieval.embeddings import EmbeddingProvider
from taxlens.retrieval.search import SearchResult, hybrid_search_chunks
from taxlens.retrieval.snippets import lexical_support

logger = logging.getLogger(__name__)
EVIDENCE_CLAIM_MAX_LENGTH = 240
MAX_PRACTICAL_ADVICE = 4


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
    omitted_fact_count: int = 0
    answerable: bool = True
    practical_advice: list[str] = field(default_factory=list)


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
    practical_advice: list[str] = field(default_factory=list)


def answer_question(
    session: Session,
    question: str,
    chat_provider: ChatProvider,
    embedding_provider: EmbeddingProvider | None = None,
    retrieval_limit: int = 5,
) -> QuestionAnswer:
    graph = _build_question_graph()
    state = graph.invoke(
        {
            "session": session,
            "question": question,
            "chat_provider": chat_provider,
            "embedding_provider": embedding_provider,
            "retrieval_limit": retrieval_limit,
        }
    )
    result = state.get("result")
    if not isinstance(result, QuestionAnswer):
        raise RuntimeError("Question graph did not produce a QuestionAnswer")
    return result


class QuestionGraphState(TypedDict, total=False):
    session: Session
    question: str
    chat_provider: ChatProvider
    embedding_provider: EmbeddingProvider | None
    retrieval_limit: int
    query_plan: QueryPlan
    results: list[SearchResult]
    evidence: EvidenceAssessment
    citations: list[Citation]
    result: QuestionAnswer


@lru_cache(maxsize=1)
def _build_question_graph() -> CompiledStateGraph[Any, Any, Any, Any]:
    graph = StateGraph(QuestionGraphState)
    graph.add_node("plan_query", _plan_query_node)
    graph.add_node("retrieve_evidence", _retrieve_evidence_node)
    graph.add_node("assess_evidence", _assess_evidence_node)
    graph.add_node("generate_answer", _generate_answer_node)
    graph.add_node("finalize_insufficient", _finalize_insufficient_node)
    graph.add_edge(START, "plan_query")
    graph.add_edge("plan_query", "retrieve_evidence")
    graph.add_conditional_edges(
        "retrieve_evidence",
        _route_supported_query,
        {"assess": "assess_evidence", "unsupported": "finalize_insufficient"},
    )
    graph.add_conditional_edges(
        "assess_evidence",
        _route_evidence,
        {"generate": "generate_answer", "insufficient": "finalize_insufficient"},
    )
    graph.add_edge("generate_answer", END)
    graph.add_edge("finalize_insufficient", END)
    return graph.compile()


def _plan_query_node(state: QuestionGraphState) -> dict[str, object]:
    return {"query_plan": plan_query(state["question"])}


def _retrieve_evidence_node(state: QuestionGraphState) -> dict[str, object]:
    query_plan = state["query_plan"]
    if query_plan.intent is QueryIntent.UNSUPPORTED:
        return {"results": []}
    results = hybrid_search_chunks(
        state["session"],
        query_plan.original_query,
        state.get("embedding_provider"),
        query_plan.filters,
        limit=state.get("retrieval_limit", 5),
    )
    return {"results": results}


def _assess_evidence_node(state: QuestionGraphState) -> dict[str, object]:
    results = state.get("results", [])
    evidence = assess_evidence(results, get_settings().qa_min_semantic_score)
    # Generation only sees the selected evidence, so citation numbers must follow it too.
    cited_results = list(evidence.results) if evidence.is_sufficient else results
    question = state["query_plan"].original_query
    return {
        "evidence": evidence,
        "citations": [build_citation(result, question) for result in cited_results],
    }


def _route_supported_query(state: QuestionGraphState) -> str:
    return "unsupported" if state["query_plan"].intent is QueryIntent.UNSUPPORTED else "assess"


def _route_evidence(state: QuestionGraphState) -> str:
    return "generate" if state["evidence"].is_sufficient else "insufficient"


def _finalize_insufficient_node(state: QuestionGraphState) -> dict[str, object]:
    query_plan = state["query_plan"]
    evidence = state.get("evidence")
    citations = state.get("citations", [])
    if query_plan.intent is QueryIntent.UNSUPPORTED:
        result = _safe_answer(
            AnswerStatus.UNSUPPORTED,
            query_plan,
            None,
            "The request is outside the supported regulatory-question scope.",
            citations,
        )
    else:
        result = _safe_answer(
            AnswerStatus.INSUFFICIENT_EVIDENCE,
            query_plan,
            evidence,
            evidence.reason if evidence else "No relevant evidence was retrieved.",
            citations,
        )
    return {"result": result}


def _generate_answer_node(state: QuestionGraphState) -> dict[str, object]:
    query_plan = state["query_plan"]
    evidence = state["evidence"]
    results = list(evidence.results)
    citations = state.get("citations", [])
    try:
        completion = state["chat_provider"].complete(
            ChatRequest(messages=_build_messages(query_plan, results, citations))
        )
    except ChatProviderError:
        result = _safe_answer(
            AnswerStatus.PROVIDER_UNAVAILABLE,
            query_plan,
            evidence,
            "The configured language model is unavailable; review the cited evidence directly.",
            citations,
        )
        return {"result": result}

    try:
        generated = parse_generated_answer(completion.content, len(citations))
    except ValueError as error:
        recovered_answer = _recover_answer_text(completion.content)
        if recovered_answer:
            result = _recovered_answer(
                query_plan, evidence, results, citations, recovered_answer
            )
        else:
            logger.warning("Unable to parse model answer: %s", error)
            result = _evidence_fallback_answer(query_plan, evidence, results, citations)
        return {"result": result}

    if not generated.answerable:
        return {
            "result": _safe_answer(
                AnswerStatus.INSUFFICIENT_EVIDENCE,
                query_plan,
                evidence,
                "The retrieved passages do not answer this question.",
                citations,
                extra_uncertainties=generated.uncertainties,
            )
        }

    supported_facts = [fact for fact in generated.confirmed_facts if _is_supported(fact, results)]
    omitted = generated.omitted_fact_count + len(generated.confirmed_facts) - len(supported_facts)
    uncertainties = [*generated.uncertainties, *evidence.notes]
    if omitted:
        uncertainties.append(
            f"{omitted} statement(s) from the model were omitted because the cited passages "
            "do not contain them."
        )
    return {
        "result": QuestionAnswer(
            status=AnswerStatus.ANSWERED,
            query_plan=query_plan,
            evidence=evidence,
            answer=generated.answer,
            confirmed_facts=supported_facts,
            interpretation=generated.interpretation,
            uncertainties=uncertainties,
            citations=citations,
            review_actions=generated.review_actions,
            disclaimer=_disclaimer(),
            practical_advice=generated.practical_advice,
        )
    }


def parse_generated_answer(content: str, citation_count: int) -> GeneratedAnswer:
    """Parse model JSON, keeping only claims whose citations can be validated.

    Only a missing answer makes the response unusable; malformed optional fields and
    claims without valid citations are dropped rather than discarding the whole answer.
    """

    content = _extract_json_content(content)
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as error:
        raise ValueError("Model response is not JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("Model response must be a JSON object")

    answerable = payload.get("answerable") is not False
    # An answer is only required when the model says the evidence answers the question.
    answer = _required_text(payload, "answer") if answerable else ""
    confirmed_facts, omitted_fact_count = _parse_claims(
        payload.get("confirmed_facts"), citation_count
    )
    return GeneratedAnswer(
        answer=answer,
        confirmed_facts=confirmed_facts,
        interpretation=_optional_text(payload.get("interpretation")),
        uncertainties=_text_list(payload.get("uncertainties")),
        review_actions=_text_list(payload.get("review_actions")),
        omitted_fact_count=omitted_fact_count,
        answerable=answerable,
        practical_advice=_text_list(payload.get("practical_advice"))[:MAX_PRACTICAL_ADVICE],
    )


def _is_supported(fact: CitedClaim, results: Sequence[SearchResult]) -> bool:
    """Whether the cited passages contain most of the fact's words (diacritics ignored).

    Range checks alone let a model attach any citation number to any statement; this
    rejects statements that the cited text does not actually contain.
    """

    cited_text = " ".join(
        f"{results[number - 1].chunk.heading or ''} {results[number - 1].chunk.content[:2500]}"
        for number in fact.citation_numbers
        if 1 <= number <= len(results)
    )
    return lexical_support(fact.text, cited_text) >= get_settings().qa_min_fact_support


def _build_messages(
    query_plan: QueryPlan,
    results: Sequence[SearchResult],
    citations: Sequence[Citation],
) -> list[ChatMessage]:
    evidence_blocks = "\n\n".join(
        _evidence_block(index, result, citation)
        for index, (result, citation) in enumerate(zip(results, citations, strict=True), start=1)
    )
    system_prompt = (
        "You are a Vietnamese tax-regulation assistant for accountants and tax advisers. "
        "Base every legal rule, rate, deadline, and condition on the numbered evidence "
        "passages; they are OCR text of official documents and may contain recognition "
        "errors. Answer in the language of the question (a Vietnamese question gets a "
        "Vietnamese answer). If the passages do not answer the question, set answerable to "
        "false and explain what is missing in uncertainties instead of guessing.\n\n"
        "Write a helpful answer of up to about 250 words: state the rule and the document "
        "and article it comes from, then explain in plain language what it means for the "
        "situation asked about, including the conditions, exceptions, rates, and deadlines "
        "the passages give. Give up to 5 confirmed facts; each must restate what its cited "
        "passage says, reusing the passage wording, and cite only passages that contain it.\n\n"
        "In practical_advice, give 1 to 4 short, concrete next steps a practitioner could "
        "take under these rules, such as documents or invoices to prepare, conditions to "
        "check, deadlines to note, or when to confirm with the tax authority. Advice must "
        "follow from the passages: do not introduce rules, rates, or deadlines they do not "
        "contain, and say when the right step depends on facts the question does not give.\n\n"
        "Return valid JSON only with: answerable (boolean), answer (string), "
        "confirmed_facts (array of objects with text and citation_numbers), interpretation "
        "(string or null), uncertainties (array of strings), practical_advice (array of "
        "strings), and review_actions (array of strings)."
    )
    user_prompt = PromptTemplate.from_template(
        "Intent: {intent}\nQuestion: {question}\n\nEvidence:\n{evidence}"
    ).format(
        intent=query_plan.intent,
        question=query_plan.original_query,
        evidence=evidence_blocks,
    )
    return [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=user_prompt),
    ]


def _evidence_block(index: int, result: SearchResult, citation: Citation) -> str:
    header = (
        f"[{index}] {citation.document_number} | {citation.legal_status} | "
        f"Article {citation.article_number or 'n/a'} | "
        f"Clause {citation.clause_number or 'n/a'} | "
        f"Pages {citation.page_start or 'n/a'}-{citation.page_end or 'n/a'}"
    )
    # Clause-level chunks do not repeat the article title, so pass it explicitly.
    heading = f"\nHeading: {citation.heading}" if citation.heading else ""
    return f"{header}{heading}\n{result.chunk.content[:2500]}"


def _safe_answer(
    status: AnswerStatus,
    query_plan: QueryPlan,
    evidence: EvidenceAssessment | None,
    uncertainty: str,
    citations: list[Citation],
    extra_uncertainties: Sequence[str] = (),
) -> QuestionAnswer:
    return QuestionAnswer(
        status=status,
        query_plan=query_plan,
        evidence=evidence,
        answer=None,
        confirmed_facts=[],
        interpretation=None,
        uncertainties=[
            uncertainty,
            *extra_uncertainties,
            *(evidence.notes if evidence else ()),
        ],
        citations=citations,
        review_actions=["Review the cited source material or refine the question and filters."],
        disclaimer=_disclaimer(),
    )


def _evidence_fallback_answer(
    query_plan: QueryPlan,
    evidence: EvidenceAssessment,
    results: Sequence[SearchResult],
    citations: list[Citation],
) -> QuestionAnswer:
    # The model produced nothing usable, so report that instead of presenting an answer;
    # the evidence excerpts remain available for direct review.
    return QuestionAnswer(
        status=AnswerStatus.INVALID_MODEL_OUTPUT,
        query_plan=query_plan,
        evidence=evidence,
        answer=None,
        confirmed_facts=_evidence_claims(results),
        interpretation=None,
        uncertainties=[
            "The language model response could not be used; the relevant evidence passages "
            "are listed instead.",
            *evidence.notes,
        ],
        citations=citations,
        review_actions=["Review the cited source material for the complete rule and context."],
        disclaimer=_disclaimer(),
    )


def _recovered_answer(
    query_plan: QueryPlan,
    evidence: EvidenceAssessment,
    results: Sequence[SearchResult],
    citations: list[Citation],
    answer: str,
) -> QuestionAnswer:
    return QuestionAnswer(
        status=AnswerStatus.ANSWERED,
        query_plan=query_plan,
        evidence=evidence,
        answer=answer,
        confirmed_facts=_evidence_claims(results),
        interpretation=None,
        uncertainties=[
            "The model response was malformed, so its statements could not be checked against "
            "citations; the listed facts are the retrieved evidence passages.",
            *evidence.notes,
        ],
        citations=citations,
        review_actions=["Review the cited source material for the complete rule and context."],
        disclaimer=_disclaimer(),
    )


def _evidence_claims(results: Sequence[SearchResult]) -> list[CitedClaim]:
    claims: list[CitedClaim] = []
    for index, result in enumerate(results, start=1):
        text = " ".join((result.chunk.heading or result.chunk.content).split())
        if not text:
            continue
        if len(text) > EVIDENCE_CLAIM_MAX_LENGTH:
            text = text[: EVIDENCE_CLAIM_MAX_LENGTH - 1].rsplit(" ", 1)[0] + "…"
        claims.append(CitedClaim(text=text, citation_numbers=(index,)))
    return claims


def _recover_answer_text(content: str) -> str | None:
    match = re.search(r'"answer"\s*:\s*"((?:\\.|[^"\\])*)', content)
    if not match:
        return None
    try:
        value = json.loads(f'"{match.group(1)}"')
    except json.JSONDecodeError:
        return None
    return value.strip() if isinstance(value, str) and value.strip() else None


def _required_text(payload: dict[object, object], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _text_list(value: object) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _parse_claims(value: object, citation_count: int) -> tuple[list[CitedClaim], int]:
    """Return claims with valid citations and the number of claims that were dropped."""

    if not isinstance(value, list):
        return [], 0
    claims: list[CitedClaim] = []
    omitted = 0
    for item in value:
        # A bare string has no citation the model committed to, so it cannot be presented
        # as a confirmed fact.
        if not isinstance(item, dict):
            omitted += 1
            continue
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            omitted += 1
            continue
        normalized_numbers = _normalize_citation_numbers(
            item.get("citation_numbers"), citation_count
        )
        if not normalized_numbers:
            omitted += 1
            continue
        claims.append(CitedClaim(text=text.strip(), citation_numbers=tuple(normalized_numbers)))
    return claims, omitted


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


def _extract_json_content(content: str) -> str:
    normalized = content.strip()
    if not normalized:
        return normalized

    without_reasoning = normalized
    while "<think>" in without_reasoning.lower():
        start = without_reasoning.lower().find("<think>")
        end = without_reasoning.lower().find("</think>", start + len("<think>"))
        if end < 0:
            without_reasoning = without_reasoning[:start]
            break
        without_reasoning = without_reasoning[:start] + without_reasoning[end + len("</think>") :]
    normalized = without_reasoning.strip()

    if normalized.startswith("```"):
        lines = normalized.splitlines()
        if len(lines) >= 3 and lines[-1].strip().startswith("```"):
            normalized = "\n".join(lines[1:-1]).strip()

    try:
        json.loads(normalized)
        return normalized
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for index, character in enumerate(normalized):
        if character != "{":
            continue
        try:
            payload, end = decoder.raw_decode(normalized[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return normalized[index : index + end]
    return normalized


def _disclaimer() -> str:
    return "This is evidence-grounded research assistance, not legal or tax advice."

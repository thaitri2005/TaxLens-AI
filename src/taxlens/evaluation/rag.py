import re
from collections.abc import Sequence
from dataclasses import dataclass

from taxlens.intelligence.qa import CitedClaim


@dataclass(frozen=True)
class RagEvaluationMetrics:
    faithfulness: float
    answer_relevancy: float
    context_precision: float
    citation_completeness: float


def evaluate_rag_answer(
    question: str,
    answer: str | None,
    claims: Sequence[CitedClaim],
    contexts: Sequence[str],
    citation_count: int,
) -> RagEvaluationMetrics:
    """Calculate cheap, deterministic RAGAS-style metrics without a judge model."""

    faithfulness = citation_completeness(claims, citation_count)
    answer_tokens = _tokens(answer or "")
    question_tokens = _tokens(question)
    answer_relevancy = _overlap(answer_tokens, question_tokens)
    context_precision = _context_precision(question_tokens, contexts)
    return RagEvaluationMetrics(
        faithfulness=faithfulness,
        answer_relevancy=answer_relevancy,
        context_precision=context_precision,
        citation_completeness=faithfulness,
    )


def citation_completeness(claims: Sequence[CitedClaim], citation_count: int) -> float:
    if not claims:
        return 1.0
    complete_claims = sum(
        bool(claim.citation_numbers)
        and all(1 <= number <= citation_count for number in claim.citation_numbers)
        for claim in claims
    )
    return complete_claims / len(claims)


def _context_precision(question_tokens: set[str], contexts: Sequence[str]) -> float:
    if not contexts:
        return 0.0
    relevant = sum(bool(_tokens(context) & question_tokens) for context in contexts)
    return relevant / len(contexts)


def _overlap(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(right)


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"\w+", value.casefold()) if len(token) > 1}

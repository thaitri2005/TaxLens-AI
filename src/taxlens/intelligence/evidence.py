from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from taxlens.retrieval.search import SearchResult

# Statuses that mean a provision no longer states the current rule.
INACTIVE_LEGAL_STATUSES = frozenset({"SUPERSEDED", "EXPIRED", "REPEALED", "INACTIVE"})
# Statuses that say nothing about validity (for example, freshly crawled documents).
UNRESOLVED_LEGAL_STATUSES = frozenset({"DISCOVERED", "UNKNOWN"})


class EvidenceStatus(StrEnum):
    SUFFICIENT = "SUFFICIENT"
    NO_EVIDENCE = "NO_EVIDENCE"
    CONFLICTING_VERSIONS = "CONFLICTING_VERSIONS"
    INSUFFICIENT_STRUCTURAL_SUPPORT = "INSUFFICIENT_STRUCTURAL_SUPPORT"
    INACTIVE_ONLY = "INACTIVE_ONLY"
    LOW_RELEVANCE = "LOW_RELEVANCE"


@dataclass(frozen=True)
class EvidenceAssessment:
    status: EvidenceStatus
    reason: str
    results: tuple[SearchResult, ...] = ()
    """Evidence selected for generation and citation, in retrieval order."""
    notes: tuple[str, ...] = ()
    """Caveats about evidence that was retrieved but excluded."""

    @property
    def is_sufficient(self) -> bool:
        return self.status is EvidenceStatus.SUFFICIENT


def assess_evidence(
    results: Sequence[SearchResult], min_semantic_score: float | None = None
) -> EvidenceAssessment:
    if not results:
        return EvidenceAssessment(
            status=EvidenceStatus.NO_EVIDENCE,
            reason="No legal evidence matched the query and selected filters.",
        )

    semantic_scores = [r.vector_score for r in results if r.vector_score is not None]
    if (
        min_semantic_score is not None
        and semantic_scores
        and max(semantic_scores) < min_semantic_score
    ):
        # A cost guard for clearly unrelated questions; borderline relevance is left to the
        # model's answerability verdict.
        return EvidenceAssessment(
            status=EvidenceStatus.LOW_RELEVANCE,
            reason="No indexed passage is close enough to the question to answer it.",
        )

    notes: list[str] = []
    located = [result for result in results if _has_structural_locator(result)]
    if not located:
        return EvidenceAssessment(
            status=EvidenceStatus.INSUFFICIENT_STRUCTURAL_SUPPORT,
            reason="No retrieved result has an article, clause, or page locator.",
        )
    if len(located) < len(results):
        notes.append(
            f"{len(results) - len(located)} retrieved passage(s) without an article or page "
            "locator were not used."
        )

    current = [
        result for result in located if result.version.legal_status not in INACTIVE_LEGAL_STATUSES
    ]
    if not current:
        return EvidenceAssessment(
            status=EvidenceStatus.INACTIVE_ONLY,
            reason="Only superseded or expired provisions matched the question.",
            results=tuple(located),
            notes=tuple(notes),
        )
    if len(current) < len(located):
        notes.append(
            f"{len(located) - len(current)} superseded or expired passage(s) were excluded in "
            "favour of current provisions."
        )

    known_statuses_by_document: dict[object, set[str]] = defaultdict(set)
    for result in current:
        if result.version.legal_status not in UNRESOLVED_LEGAL_STATUSES:
            known_statuses_by_document[result.document.id].add(result.version.legal_status)
    if any(len(statuses) > 1 for statuses in known_statuses_by_document.values()):
        return EvidenceAssessment(
            status=EvidenceStatus.CONFLICTING_VERSIONS,
            reason=(
                "Versions of the same document with different legal statuses were retrieved "
                "and require version selection."
            ),
            results=tuple(current),
            notes=tuple(notes),
        )

    if any(result.version.legal_status in UNRESOLVED_LEGAL_STATUSES for result in current):
        notes.append(
            "The legal status of at least one cited document has not been verified; confirm "
            "it is still in force."
        )
    return EvidenceAssessment(
        status=EvidenceStatus.SUFFICIENT,
        reason="Retrieved evidence has a consistent legal status and structural locators.",
        results=tuple(current),
        notes=tuple(notes),
    )


def _has_structural_locator(result: SearchResult) -> bool:
    return any(
        value is not None
        for value in (
            result.chunk.article_number,
            result.chunk.clause_number,
            result.chunk.page_start,
            result.chunk.page_end,
        )
    )

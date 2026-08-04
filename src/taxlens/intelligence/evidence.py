from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from taxlens.retrieval.search import SearchResult


class EvidenceStatus(StrEnum):
    SUFFICIENT = "SUFFICIENT"
    NO_EVIDENCE = "NO_EVIDENCE"
    CONFLICTING_VERSIONS = "CONFLICTING_VERSIONS"
    INSUFFICIENT_STRUCTURAL_SUPPORT = "INSUFFICIENT_STRUCTURAL_SUPPORT"


@dataclass(frozen=True)
class EvidenceAssessment:
    status: EvidenceStatus
    reason: str

    @property
    def is_sufficient(self) -> bool:
        return self.status is EvidenceStatus.SUFFICIENT


def assess_evidence(results: Sequence[SearchResult]) -> EvidenceAssessment:
    if not results:
        return EvidenceAssessment(
            status=EvidenceStatus.NO_EVIDENCE,
            reason="No legal evidence matched the query and selected filters.",
        )

    statuses_by_document: dict[object, set[str]] = defaultdict(set)
    for result in results:
        statuses_by_document[result.document.id].add(result.version.legal_status)
    all_statuses = {status for statuses in statuses_by_document.values() for status in statuses}
    has_document_conflict = any(
        len(statuses) > 1 for statuses in statuses_by_document.values()
    )
    if len(all_statuses) > 1 or has_document_conflict:
        return EvidenceAssessment(
            status=EvidenceStatus.CONFLICTING_VERSIONS,
            reason=(
                "Retrieved evidence contains multiple legal statuses and requires "
                "version selection."
            ),
        )

    if any(not _has_structural_locator(result) for result in results):
        return EvidenceAssessment(
            status=EvidenceStatus.INSUFFICIENT_STRUCTURAL_SUPPORT,
            reason="At least one retrieved result has no article, clause, or page locator.",
        )

    return EvidenceAssessment(
        status=EvidenceStatus.SUFFICIENT,
        reason="Retrieved evidence has a consistent legal status and structural locators.",
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

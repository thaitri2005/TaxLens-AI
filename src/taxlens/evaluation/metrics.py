import math
from collections.abc import Sequence
from dataclasses import dataclass

from taxlens.intelligence.qa import CitedClaim


@dataclass(frozen=True)
class RetrievalMetrics:
    hit_at_k: bool
    precision_at_k: float
    recall_at_k: float
    reciprocal_rank: float
    ndcg_at_k: float


def evaluate_retrieval(
    ranked_chunk_ids: Sequence[str],
    relevant_chunk_ids: set[str],
    k: int,
) -> RetrievalMetrics:
    if k < 1:
        raise ValueError("k must be at least 1")
    if not relevant_chunk_ids:
        return RetrievalMetrics(
            hit_at_k=False,
            precision_at_k=0.0,
            recall_at_k=0.0,
            reciprocal_rank=0.0,
            ndcg_at_k=0.0,
        )

    ranked_at_k = list(ranked_chunk_ids[:k])
    relevant_found = set(ranked_at_k) & relevant_chunk_ids
    first_rank = next(
        (
            rank
            for rank, chunk_id in enumerate(ranked_at_k, start=1)
            if chunk_id in relevant_chunk_ids
        ),
        None,
    )
    dcg = sum(
        1 / math.log2(rank + 1)
        for rank, chunk_id in enumerate(ranked_at_k, start=1)
        if chunk_id in relevant_chunk_ids
    )
    ideal_relevant_count = min(len(relevant_chunk_ids), k)
    ideal_dcg = sum(
        1 / math.log2(rank + 1) for rank in range(1, ideal_relevant_count + 1)
    )
    return RetrievalMetrics(
        hit_at_k=bool(relevant_found),
        precision_at_k=len(relevant_found) / k,
        recall_at_k=len(relevant_found) / len(relevant_chunk_ids),
        reciprocal_rank=1 / first_rank if first_rank is not None else 0.0,
        ndcg_at_k=dcg / ideal_dcg if ideal_dcg else 0.0,
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

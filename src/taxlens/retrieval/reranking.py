from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from time import perf_counter
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from taxlens.retrieval.search import SearchResult


@dataclass(frozen=True)
class RerankOutcome:
    results: list[SearchResult]
    provider_name: str
    latency_ms: float


class Reranker(Protocol):
    provider_name: str

    def rerank(
        self,
        query: str,
        candidates: Sequence[SearchResult],
        limit: int,
    ) -> RerankOutcome: ...


class NoOpReranker:
    provider_name = "none"

    def rerank(
        self,
        query: str,
        candidates: Sequence[SearchResult],
        limit: int,
    ) -> RerankOutcome:
        del query
        started_at = perf_counter()
        return RerankOutcome(
            results=list(candidates[:limit]),
            provider_name=self.provider_name,
            latency_ms=(perf_counter() - started_at) * 1000,
        )

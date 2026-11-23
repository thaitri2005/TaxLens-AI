from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from time import perf_counter
from typing import TYPE_CHECKING, Any, Protocol

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


# Same constant as the keyword/vector fusion in retrieval/search.py.
RRF_K = 60
# Characters of a passage given to a cross-encoder; its 512-token window holds about this much
# Vietnamese text, and the start of a clause carries its rule.
CROSS_ENCODER_PASSAGE_CHARS = 1500


class CrossEncoderReranker:
    """Orders candidates by a cross-encoder's score for (question, passage).

    Reads the question and each passage together, unlike the bi-encoder used for vector
    search, so it can rank a clause above a passage that only shares its words. Runs on CPU;
    the model loads on first use.
    """

    def __init__(
        self,
        model_name: str,
        batch_size: int = 16,
        max_length: int = 512,
        fuse: bool = False,
        score_cache: dict[str, float] | None = None,
    ) -> None:
        """``fuse`` combines the cross-encoder's order with the incoming order by reciprocal
        rank instead of replacing it. ``score_cache`` (keyed by model, question, and passage
        id) lets one scoring serve several runs."""

        self.model_name = model_name
        self.provider_name = f"cross-encoder:{model_name}" + (":fused" if fuse else "")
        self._batch_size = batch_size
        self._max_length = max_length
        self._fuse = fuse
        self.score_cache = score_cache if score_cache is not None else {}
        self._model: Any = None

    def rerank(
        self,
        query: str,
        candidates: Sequence[SearchResult],
        limit: int,
    ) -> RerankOutcome:
        started_at = perf_counter()
        if not candidates:
            return RerankOutcome([], self.provider_name, 0.0)
        scores = self._scores(query, candidates)
        order = sorted(range(len(candidates)), key=lambda index: -scores[index])
        if self._fuse:
            fused = {index: 1.0 / (RRF_K + index + 1) for index in range(len(candidates))}
            for rank, index in enumerate(order, start=1):
                fused[index] += 1.0 / (RRF_K + rank)
            order = sorted(fused, key=lambda index: (-fused[index], index))
        return RerankOutcome(
            results=[candidates[index] for index in order[:limit]],
            provider_name=self.provider_name,
            latency_ms=(perf_counter() - started_at) * 1000,
        )

    def _scores(self, query: str, candidates: Sequence[SearchResult]) -> list[float]:
        keys = [f"{self.model_name}|{query}|{result.chunk.id}" for result in candidates]
        missing = [index for index, key in enumerate(keys) if key not in self.score_cache]
        if missing:
            pairs = [(query, _passage_text(candidates[index])) for index in missing]
            predicted = self._load().predict(
                pairs, batch_size=self._batch_size, show_progress_bar=False
            )
            for index, score in zip(missing, predicted, strict=True):
                self.score_cache[keys[index]] = float(score)
        return [self.score_cache[key] for key in keys]

    def _load(self) -> Any:
        if self._model is None:
            import os

            os.environ.setdefault("USE_TF", "0")
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name, device="cpu", max_length=self._max_length)
        return self._model


def _passage_text(result: SearchResult) -> str:
    heading = result.chunk.heading or ""
    return f"{heading}\n{result.chunk.content[:CROSS_ENCODER_PASSAGE_CHARS]}".strip()

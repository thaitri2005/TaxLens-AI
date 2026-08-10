import logging

import pytest

from taxlens.evaluation.metrics import citation_completeness, evaluate_retrieval
from taxlens.intelligence.qa import CitedClaim
from taxlens.intelligence.telemetry import ModelCallTelemetry, record_model_call


def test_retrieval_metrics_calculate_hit_recall_and_reciprocal_rank() -> None:
    metrics = evaluate_retrieval(["a", "b", "c"], {"b", "c"}, k=2)

    assert metrics.hit_at_k is True
    assert metrics.precision_at_k == 0.5
    assert metrics.recall_at_k == 0.5
    assert metrics.reciprocal_rank == 0.5
    assert metrics.ndcg_at_k > 0.0


def test_retrieval_metrics_handle_empty_relevance_and_invalid_k() -> None:
    metrics = evaluate_retrieval(["a"], set(), k=1)

    assert metrics.recall_at_k == 0.0
    with pytest.raises(ValueError, match="at least 1"):
        evaluate_retrieval(["a"], {"a"}, k=0)


def test_citation_completeness_checks_claim_references() -> None:
    claims = [
        CitedClaim(text="Fact one", citation_numbers=(1,)),
        CitedClaim(text="Fact two", citation_numbers=(3,)),
    ]

    assert citation_completeness(claims, citation_count=2) == 0.5
    assert citation_completeness([], citation_count=0) == 1.0


def test_model_telemetry_is_structured_in_logs(caplog) -> None:
    caplog.set_level(logging.INFO, logger="taxlens.intelligence.telemetry")

    record_model_call(
        ModelCallTelemetry(
            model="test-model",
            provider="test-provider",
            latency_ms=12.345,
            input_tokens=10,
            output_tokens=5,
            outcome="success",
        )
    )

    record = caplog.records[-1]
    assert record.message == "model_call"
    assert record.taxlens_model == "test-model"
    assert record.taxlens_latency_ms == 12.35
    assert record.taxlens_output_tokens == 5

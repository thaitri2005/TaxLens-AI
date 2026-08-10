from scripts.evaluate_tax_retrieval import (
    _evaluation_status,
    _metrics_summary,
)


def test_evaluation_status_separates_missing_and_partial_coverage() -> None:
    assert _evaluation_status(
        {"expected_document_count": 3, "embedded_document_count": 0}
    ) == "not_evaluable"
    assert _evaluation_status(
        {"expected_document_count": 3, "embedded_document_count": 2}
    ) == "partial_coverage"
    assert _evaluation_status(
        {"expected_document_count": 3, "embedded_document_count": 3}
    ) == "ready"


def test_metrics_summary_aggregates_a_selected_k() -> None:
    reports = [
        {
            "metrics_by_k": {
                "5": {
                    "hit_at_k": True,
                    "precision_at_k": 0.2,
                    "recall_at_k": 1.0,
                    "reciprocal_rank": 1.0,
                    "ndcg_at_k": 1.0,
                }
            }
        },
        {
            "metrics_by_k": {
                "5": {
                    "hit_at_k": False,
                    "precision_at_k": 0.0,
                    "recall_at_k": 0.0,
                    "reciprocal_rank": 0.0,
                    "ndcg_at_k": 0.0,
                }
            }
        },
    ]

    summary = _metrics_summary(reports, 5)

    assert summary == {
        "case_count": 2,
        "mean_hit_at_k": 0.5,
        "mean_precision_at_k": 0.1,
        "mean_recall_at_k": 0.5,
        "mean_reciprocal_rank": 0.5,
        "mean_ndcg_at_k": 0.5,
    }

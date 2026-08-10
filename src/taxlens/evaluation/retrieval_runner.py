from typing import Any


def metrics_summary(reports: list[dict[str, Any]], k: int) -> dict[str, Any]:
    if not reports:
        return {
            "case_count": 0,
            "mean_hit_at_k": None,
            "mean_precision_at_k": None,
            "mean_recall_at_k": None,
            "mean_reciprocal_rank": None,
            "mean_ndcg_at_k": None,
        }
    metrics = [report["metrics_by_k"][str(k)] for report in reports]
    return {
        "case_count": len(metrics),
        "mean_hit_at_k": sum(bool(item["hit_at_k"]) for item in metrics) / len(metrics),
        "mean_precision_at_k": sum(
            float(item["precision_at_k"]) for item in metrics
        )
        / len(metrics),
        "mean_recall_at_k": sum(float(item["recall_at_k"]) for item in metrics)
        / len(metrics),
        "mean_reciprocal_rank": sum(
            float(item["reciprocal_rank"]) for item in metrics
        )
        / len(metrics),
        "mean_ndcg_at_k": sum(float(item["ndcg_at_k"]) for item in metrics)
        / len(metrics),
    }


def evaluation_status(corpus_coverage: dict[str, Any]) -> str:
    expected_count = int(corpus_coverage["expected_document_count"])
    embedded_count = int(corpus_coverage["embedded_document_count"])
    if embedded_count == 0:
        return "not_evaluable"
    if embedded_count < expected_count:
        return "partial_coverage"
    return "ready"


def evaluation_status_reason(status: str) -> str:
    if status == "not_evaluable":
        return "None of the expected evaluation documents are embedded"
    if status == "partial_coverage":
        return "Only some expected evaluation documents are embedded"
    return "All expected evaluation documents are embedded"

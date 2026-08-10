import argparse
import json
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from taxlens.config import get_settings
from taxlens.db import SessionLocal
from taxlens.evaluation.metrics import evaluate_retrieval
from taxlens.evaluation.reports import persist_retrieval_report
from taxlens.evaluation.tracking import get_experiment_tracker
from taxlens.legal_data.models import (
    DocumentChunk,
    DocumentEmbedding,
    DocumentVersion,
    LegalDocument,
)
from taxlens.retrieval.embeddings import get_embedding_provider
from taxlens.retrieval.search import SearchFilters, SearchResult, hybrid_search_chunks


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate retrieval against labeled tax queries")
    parser.add_argument(
        "--dataset", type=Path, default=Path("data/evaluation/tax_retrieval.json")
    )
    parser.add_argument("--k", type=int, default=5)
    arguments = parser.parse_args()
    if arguments.k < 1:
        parser.error("--k must be at least 1")

    raw_dataset = json.loads(arguments.dataset.read_text(encoding="utf-8"))
    if not isinstance(raw_dataset, list) or not raw_dataset:
        parser.error("Evaluation dataset must contain at least one case")
    dataset: list[dict[str, Any]] = []
    for index, case in enumerate(raw_dataset, start=1):
        if not isinstance(case, dict):
            parser.error(f"Evaluation case {index} must be a JSON object")
        query = case.get("query")
        relevant_documents = case.get("relevant_document_numbers")
        if not isinstance(query, str) or not query.strip():
            parser.error(f"Evaluation case {index} must contain a non-empty query")
        if not isinstance(relevant_documents, list) or not relevant_documents:
            parser.error(
                f"Evaluation case {index} must contain relevant_document_numbers"
            )
        if not all(isinstance(document_number, str) for document_number in relevant_documents):
            parser.error(
                f"Evaluation case {index} has an invalid relevant document number"
            )
        dataset.append(
            {
                "query": query,
                "relevant_document_numbers": relevant_documents,
            }
        )
    provider = get_embedding_provider()
    reports: list[dict[str, object]] = []
    with SessionLocal() as session:
        expected_document_numbers = {
            document_number
            for case in dataset
            for document_number in case["relevant_document_numbers"]
        }
        corpus_coverage = _corpus_coverage(session, expected_document_numbers)
        embedded_document_numbers = {
            str(item["document_number"])
            for item in corpus_coverage["documents"]
            if item["embedding_count"]
        }
        for case in dataset:
            relevant_documents = set(case["relevant_document_numbers"])
            covered_documents = relevant_documents & embedded_document_numbers
            missing_documents = relevant_documents - embedded_document_numbers
            coverage_status = (
                "fully_covered"
                if not missing_documents
                else "partially_covered"
                if covered_documents
                else "not_covered"
            )
            results = hybrid_search_chunks(
                session,
                case["query"],
                provider,
                SearchFilters(),
                limit=arguments.k,
            )
            ranked_documents = _unique_document_numbers(results)
            metrics = evaluate_retrieval(
                ranked_documents,
                relevant_documents,
                arguments.k,
            )
            reports.append(
                {
                    "query": case["query"],
                    "ranked_documents": ranked_documents,
                    "relevant_document_numbers": case["relevant_document_numbers"],
                    "hit_at_k": metrics.hit_at_k,
                    "precision_at_k": metrics.precision_at_k,
                    "recall_at_k": metrics.recall_at_k,
                    "reciprocal_rank": metrics.reciprocal_rank,
                    "ndcg_at_k": metrics.ndcg_at_k,
                    "coverage_status": coverage_status,
                    "covered_relevant_document_numbers": sorted(covered_documents),
                    "missing_relevant_document_numbers": sorted(missing_documents),
                }
            )

    count = len(reports)
    fully_covered_reports = [
        report for report in reports if report["coverage_status"] == "fully_covered"
    ]
    settings = get_settings()
    output: dict[str, Any] = {
        "model": settings.embedding_model_id,
        "dataset": str(arguments.dataset),
        "k": arguments.k,
        "case_count": count,
        "corpus_coverage": corpus_coverage,
        "mean_hit_at_k": sum(bool(report["hit_at_k"]) for report in reports) / count,
        "mean_precision_at_k": _mean_metric(reports, "precision_at_k"),
        "mean_recall_at_k": sum(float(report["recall_at_k"]) for report in reports) / count,
        "mean_reciprocal_rank": sum(float(report["reciprocal_rank"]) for report in reports)
        / count,
        "mean_ndcg_at_k": _mean_metric(reports, "ndcg_at_k"),
        "fully_covered_case_count": len(fully_covered_reports),
        "fully_covered_mean_hit_at_k": (
            _mean_metric(fully_covered_reports, "hit_at_k")
            if fully_covered_reports
            else None
        ),
        "fully_covered_mean_precision_at_k": (
            _mean_metric(fully_covered_reports, "precision_at_k")
            if fully_covered_reports
            else None
        ),
        "fully_covered_mean_recall_at_k": (
            _mean_metric(fully_covered_reports, "recall_at_k")
            if fully_covered_reports
            else None
        ),
        "fully_covered_mean_reciprocal_rank": (
            _mean_metric(fully_covered_reports, "reciprocal_rank")
            if fully_covered_reports
            else None
        ),
        "fully_covered_mean_ndcg_at_k": (
            _mean_metric(fully_covered_reports, "ndcg_at_k")
            if fully_covered_reports
            else None
        ),
        "coverage_summary": _coverage_summary(reports, corpus_coverage),
        "cases": reports,
    }
    persisted = persist_retrieval_report(output)
    tracker = get_experiment_tracker(settings)
    with tracker.start_run("retrieval-evaluation"):
        tracker.log_params(
            {
                "dataset": str(arguments.dataset),
                "embedding_model": settings.embedding_model_id,
                "k": arguments.k,
                "case_count": count,
            }
        )
        tracking_metrics = {
            "mean_hit_at_k": float(persisted["mean_hit_at_k"]),
            "mean_precision_at_k": float(persisted["mean_precision_at_k"]),
            "mean_recall_at_k": float(persisted["mean_recall_at_k"]),
            "mean_reciprocal_rank": float(persisted["mean_reciprocal_rank"]),
            "mean_ndcg_at_k": float(persisted["mean_ndcg_at_k"]),
            "corpus_present_document_count": float(
                corpus_coverage["present_document_count"]
            ),
            "corpus_chunked_document_count": float(
                corpus_coverage["chunked_document_count"]
            ),
            "corpus_embedded_document_count": float(
                corpus_coverage["embedded_document_count"]
            ),
            "document_coverage_rate": float(
                _coverage_summary(reports, corpus_coverage)["document_coverage_rate"]
            ),
            "fully_covered_case_count": float(len(fully_covered_reports)),
        }
        if fully_covered_reports:
            tracking_metrics.update(
                {
                    "fully_covered_mean_hit_at_k": float(
                        persisted["fully_covered_mean_hit_at_k"]
                    ),
                    "fully_covered_mean_precision_at_k": float(
                        persisted["fully_covered_mean_precision_at_k"]
                    ),
                    "fully_covered_mean_recall_at_k": float(
                        persisted["fully_covered_mean_recall_at_k"]
                    ),
                    "fully_covered_mean_reciprocal_rank": float(
                        persisted["fully_covered_mean_reciprocal_rank"]
                    ),
                    "fully_covered_mean_ndcg_at_k": float(
                        persisted["fully_covered_mean_ndcg_at_k"]
                    ),
                }
            )
        tracker.log_metrics(tracking_metrics)
    print(json.dumps(persisted, ensure_ascii=False, indent=2))


def _mean_metric(reports: list[dict[str, object]], key: str) -> float:
    return sum(float(report[key]) for report in reports) / len(reports)


def _coverage_summary(
    reports: list[dict[str, object]], corpus_coverage: dict[str, object]
) -> dict[str, object]:
    expected_count = int(corpus_coverage["expected_document_count"])
    embedded_count = int(corpus_coverage["embedded_document_count"])
    return {
        "expected_document_count": expected_count,
        "embedded_document_count": embedded_count,
        "document_coverage_rate": (
            embedded_count / expected_count if expected_count else 0.0
        ),
        "fully_covered_case_count": sum(
            report["coverage_status"] == "fully_covered" for report in reports
        ),
        "partially_covered_case_count": sum(
            report["coverage_status"] == "partially_covered" for report in reports
        ),
        "not_covered_case_count": sum(
            report["coverage_status"] == "not_covered" for report in reports
        ),
    }


def _corpus_coverage(session, expected_document_numbers: set[str]) -> dict[str, object]:
    statuses: list[dict[str, object]] = []
    for document_number in sorted(expected_document_numbers):
        document = session.scalar(
            select(LegalDocument).where(LegalDocument.document_number == document_number)
        )
        if document is None:
            statuses.append(
                {
                    "document_number": document_number,
                    "present": False,
                    "version_count": 0,
                    "chunk_count": 0,
                    "embedding_count": 0,
                }
            )
            continue

        version_count = session.scalar(
            select(func.count(DocumentVersion.id)).where(
                DocumentVersion.document_id == document.id
            )
        ) or 0
        chunk_count = session.scalar(
            select(func.count(DocumentChunk.id))
            .join(DocumentVersion, DocumentChunk.document_version_id == DocumentVersion.id)
            .where(DocumentVersion.document_id == document.id)
        ) or 0
        embedding_count = session.scalar(
            select(func.count(DocumentEmbedding.id))
            .join(DocumentChunk, DocumentEmbedding.document_chunk_id == DocumentChunk.id)
            .join(DocumentVersion, DocumentChunk.document_version_id == DocumentVersion.id)
            .where(DocumentVersion.document_id == document.id)
        ) or 0
        statuses.append(
            {
                "document_number": document_number,
                "present": True,
                "version_count": int(version_count),
                "chunk_count": int(chunk_count),
                "embedding_count": int(embedding_count),
            }
        )

    return {
        "expected_document_count": len(statuses),
        "present_document_count": sum(bool(item["present"]) for item in statuses),
        "chunked_document_count": sum(bool(item["chunk_count"]) for item in statuses),
        "embedded_document_count": sum(bool(item["embedding_count"]) for item in statuses),
        "documents": statuses,
    }


def _unique_document_numbers(results: list[SearchResult]) -> list[str]:
    ranked_documents: list[str] = []
    seen: set[str] = set()
    for result in results:
        document_number = result.document.document_number
        if document_number not in seen:
            seen.add(document_number)
            ranked_documents.append(document_number)
    return ranked_documents


if __name__ == "__main__":
    main()

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from taxlens.config import get_settings
from taxlens.db import SessionLocal
from taxlens.evaluation.metrics import evaluate_retrieval
from taxlens.evaluation.reports import persist_retrieval_report
from taxlens.evaluation.retrieval_runner import (
    evaluation_status,
    evaluation_status_reason,
    metrics_summary,
)
from taxlens.evaluation.tracking import get_experiment_tracker
from taxlens.legal_data.models import (
    DocumentChunk,
    DocumentEmbedding,
    DocumentVersion,
    LegalDocument,
)
from taxlens.retrieval.embeddings import get_embedding_provider
from taxlens.retrieval.search import (
    SearchFilters,
    SearchMode,
    SearchResult,
    hybrid_search_chunks,
    keyword_search_chunks,
    semantic_search_chunks,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate retrieval against labeled tax queries")
    parser.add_argument(
        "--dataset", type=Path, default=Path("data/evaluation/tax_retrieval.json")
    )
    parser.add_argument(
        "--k",
        type=int,
        default=None,
        help="Evaluate only this K; retained for backwards compatibility",
    )
    parser.add_argument(
        "--ks",
        nargs="+",
        type=int,
        default=[1, 3, 5, 10],
        help="Evaluate one or more K values (default: 1 3 5 10)",
    )
    parser.add_argument(
        "--mode",
        choices=["keyword", "semantic", "hybrid"],
        default="hybrid",
        help="Retrieval baseline to evaluate (default: hybrid)",
    )
    arguments = parser.parse_args()
    ks = [arguments.k] if arguments.k is not None else sorted(set(arguments.ks))
    if any(k < 1 for k in ks):
        parser.error("all K values must be at least 1")

    dataset_bytes = arguments.dataset.read_bytes()
    dataset_hash = hashlib.sha256(dataset_bytes).hexdigest()
    raw_dataset = json.loads(dataset_bytes.decode("utf-8"))
    if not isinstance(raw_dataset, list) or not raw_dataset:
        parser.error("Evaluation dataset must contain at least one case")
    dataset: list[dict[str, Any]] = []
    seen_case_ids: set[str] = set()
    for index, case in enumerate(raw_dataset, start=1):
        if not isinstance(case, dict):
            parser.error(f"Evaluation case {index} must be a JSON object")
        query = case.get("query")
        relevant_documents = case.get("relevant_document_numbers")
        case_id = case.get("case_id", f"case-{index:03d}")
        if not isinstance(case_id, str) or not case_id.strip():
            parser.error(f"Evaluation case {index} must contain a valid case_id")
        if case_id in seen_case_ids:
            parser.error(f"Evaluation dataset contains duplicate case_id: {case_id}")
        seen_case_ids.add(case_id)
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
                "case_id": case_id,
                "query": query,
                "relevant_document_numbers": relevant_documents,
            }
        )
    mode: SearchMode = arguments.mode
    provider = get_embedding_provider() if mode != "keyword" else None
    reports: list[dict[str, Any]] = []
    primary_k = 5 if 5 in ks else max(ks)
    with SessionLocal() as session:
        expected_document_numbers = {
            document_number
            for case in dataset
            for document_number in case["relevant_document_numbers"]
        }
        corpus_coverage = _corpus_coverage(session, expected_document_numbers)
        corpus_snapshot = _corpus_snapshot(session)
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
            results = _search(
                session,
                case["query"],
                provider,
                mode,
                max(ks),
            )
            ranked_documents = _unique_document_numbers(results)
            metrics_by_k: dict[str, dict[str, Any]] = {}
            for k in ks:
                metrics = evaluate_retrieval(ranked_documents, relevant_documents, k)
                metrics_by_k[str(k)] = {
                    "hit_at_k": metrics.hit_at_k,
                    "precision_at_k": metrics.precision_at_k,
                    "recall_at_k": metrics.recall_at_k,
                    "reciprocal_rank": metrics.reciprocal_rank,
                    "ndcg_at_k": metrics.ndcg_at_k,
                }
            primary_metrics = metrics_by_k[str(primary_k)]
            reports.append(
                {
                    "case_id": case["case_id"],
                    "query": case["query"],
                    "ranked_documents": ranked_documents,
                    "relevant_document_numbers": case["relevant_document_numbers"],
                    **primary_metrics,
                    "metrics_by_k": metrics_by_k,
                    "coverage_status": coverage_status,
                    "covered_relevant_document_numbers": sorted(covered_documents),
                    "missing_relevant_document_numbers": sorted(missing_documents),
                }
            )

    count = len(reports)
    fully_covered_reports = [
        report for report in reports if report["coverage_status"] == "fully_covered"
    ]
    coverage_summary = _coverage_summary(reports, corpus_coverage)
    status = evaluation_status(corpus_coverage)
    metrics_by_k = {str(k): metrics_summary(reports, k) for k in ks}
    fully_covered_metrics_by_k = {
        str(k): metrics_summary(fully_covered_reports, k) for k in ks
    }
    primary_metrics = metrics_by_k[str(primary_k)]
    primary_covered_metrics = fully_covered_metrics_by_k[str(primary_k)]
    settings = get_settings()
    output: dict[str, Any] = {
        "model": settings.embedding_model_id,
        "retrieval_mode": mode,
        "dataset": str(arguments.dataset),
        "dataset_hash": dataset_hash,
        "ks": ks,
        "k": primary_k,
        "case_count": count,
        "evaluation_status": status,
        "quality_gate": {
            "status": status,
            "ranking_metrics_usable": bool(fully_covered_reports),
            "reason": evaluation_status_reason(status),
        },
        "corpus_coverage": corpus_coverage,
        "corpus_snapshot": corpus_snapshot,
        "metrics_by_k": metrics_by_k,
        "fully_covered_metrics_by_k": fully_covered_metrics_by_k,
        "mean_hit_at_k": primary_metrics["mean_hit_at_k"],
        "mean_precision_at_k": primary_metrics["mean_precision_at_k"],
        "mean_recall_at_k": primary_metrics["mean_recall_at_k"],
        "mean_reciprocal_rank": primary_metrics["mean_reciprocal_rank"],
        "mean_ndcg_at_k": primary_metrics["mean_ndcg_at_k"],
        "fully_covered_case_count": len(fully_covered_reports),
        "fully_covered_mean_hit_at_k": primary_covered_metrics["mean_hit_at_k"],
        "fully_covered_mean_precision_at_k": primary_covered_metrics[
            "mean_precision_at_k"
        ],
        "fully_covered_mean_recall_at_k": primary_covered_metrics["mean_recall_at_k"],
        "fully_covered_mean_reciprocal_rank": primary_covered_metrics[
            "mean_reciprocal_rank"
        ],
        "fully_covered_mean_ndcg_at_k": primary_covered_metrics["mean_ndcg_at_k"],
        "coverage_summary": coverage_summary,
        "cases": reports,
    }
    persisted = persist_retrieval_report(output)
    tracker = get_experiment_tracker(settings)
    with tracker.start_run("retrieval-evaluation"):
        tracker.log_params(
            {
                "dataset": str(arguments.dataset),
                "embedding_model": settings.embedding_model_id,
                "retrieval_mode": mode,
                "k": primary_k,
                "ks": ",".join(str(k) for k in ks),
                "case_count": count,
                "dataset_hash": dataset_hash,
                "corpus_fingerprint": corpus_snapshot["fingerprint"],
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
            "corpus_total_document_count": float(
                corpus_snapshot["document_count"]
            ),
            "corpus_total_chunk_count": float(corpus_snapshot["chunk_count"]),
            "corpus_total_embedding_count": float(
                corpus_snapshot["embedding_count"]
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


def _coverage_summary(
    reports: list[dict[str, Any]], corpus_coverage: dict[str, object]
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


def _corpus_snapshot(session) -> dict[str, object]:
    document_numbers = list(
        session.scalars(
            select(LegalDocument.document_number).order_by(LegalDocument.document_number)
        )
    )
    version_rows = session.execute(
        select(LegalDocument.document_number, DocumentVersion.raw_content_hash)
        .join(DocumentVersion, DocumentVersion.document_id == LegalDocument.id)
        .order_by(LegalDocument.document_number, DocumentVersion.raw_content_hash)
    ).all()
    fingerprint_payload = [
        {
            "document_number": document_number,
            "raw_content_hash": raw_content_hash,
        }
        for document_number, raw_content_hash in version_rows
    ]
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    version_count = session.scalar(select(func.count(DocumentVersion.id))) or 0
    chunk_count = session.scalar(select(func.count(DocumentChunk.id))) or 0
    embedding_count = session.scalar(select(func.count(DocumentEmbedding.id))) or 0
    return {
        "document_count": len(document_numbers),
        "version_count": int(version_count),
        "chunk_count": int(chunk_count),
        "embedding_count": int(embedding_count),
        "fingerprint": fingerprint,
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


def _search(
    session,
    query: str,
    provider,
    mode: SearchMode,
    limit: int,
) -> list[SearchResult]:
    filters = SearchFilters()
    if mode == "keyword":
        return keyword_search_chunks(session, query, filters, limit)
    if provider is None:
        raise RuntimeError(f"Retrieval mode {mode} requires an embedding provider")
    if mode == "semantic":
        query_vector = provider.embed_query(query).vectors[0]
        return semantic_search_chunks(session, query_vector, provider, filters, limit)
    return hybrid_search_chunks(session, query, provider, filters, limit)


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

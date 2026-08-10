import argparse
import json
from pathlib import Path

from sqlalchemy import func, select

from taxlens.config import get_settings
from taxlens.db import SessionLocal
from taxlens.evaluation.metrics import evaluate_retrieval
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

    dataset = json.loads(arguments.dataset.read_text(encoding="utf-8"))
    provider = get_embedding_provider()
    reports: list[dict[str, object]] = []
    with SessionLocal() as session:
        expected_document_numbers = {
            document_number
            for case in dataset
            for document_number in case["relevant_document_numbers"]
        }
        corpus_coverage = _corpus_coverage(session, expected_document_numbers)
        for case in dataset:
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
                set(case["relevant_document_numbers"]),
                arguments.k,
            )
            reports.append(
                {
                    "query": case["query"],
                    "ranked_documents": ranked_documents,
                    "relevant_document_numbers": case["relevant_document_numbers"],
                    "hit_at_k": metrics.hit_at_k,
                    "recall_at_k": metrics.recall_at_k,
                    "reciprocal_rank": metrics.reciprocal_rank,
                }
            )

    count = len(reports)
    output = {
        "model": get_settings().embedding_model_id,
        "k": arguments.k,
        "case_count": count,
        "corpus_coverage": corpus_coverage,
        "mean_hit_at_k": sum(bool(report["hit_at_k"]) for report in reports) / count,
        "mean_recall_at_k": sum(float(report["recall_at_k"]) for report in reports) / count,
        "mean_reciprocal_rank": sum(float(report["reciprocal_rank"]) for report in reports)
        / count,
        "cases": reports,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


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

import argparse
import json
from pathlib import Path

from taxlens.config import get_settings
from taxlens.db import SessionLocal
from taxlens.evaluation.metrics import evaluate_retrieval
from taxlens.retrieval.embeddings import get_embedding_provider
from taxlens.retrieval.search import SearchFilters, hybrid_search_chunks


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
        for case in dataset:
            results = hybrid_search_chunks(
                session,
                case["query"],
                provider,
                SearchFilters(),
                limit=arguments.k,
            )
            ranked_documents = [result.document.document_number for result in results]
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
        "mean_hit_at_k": sum(bool(report["hit_at_k"]) for report in reports) / count,
        "mean_recall_at_k": sum(float(report["recall_at_k"]) for report in reports) / count,
        "mean_reciprocal_rank": sum(float(report["reciprocal_rank"]) for report in reports)
        / count,
        "cases": reports,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

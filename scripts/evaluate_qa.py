import argparse
import json
from pathlib import Path

from taxlens.config import get_settings
from taxlens.db import SessionLocal
from taxlens.evaluation.rag import evaluate_rag_answer
from taxlens.evaluation.tracking import get_experiment_tracker
from taxlens.intelligence.chat import get_chat_provider
from taxlens.intelligence.qa import answer_question
from taxlens.retrieval.embeddings import EmbeddingProvider, get_embedding_provider


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate grounded Q&A with RAGAS-style metrics")
    parser.add_argument("--dataset", type=Path, default=Path("data/evaluation/qa.json"))
    parser.add_argument(
        "--keyword-only",
        action="store_true",
        help="skip local embeddings and evaluate using keyword retrieval",
    )
    arguments = parser.parse_args()
    dataset = json.loads(arguments.dataset.read_text(encoding="utf-8"))
    tracker = get_experiment_tracker()
    settings = get_settings()
    reports: list[dict[str, object]] = []
    embedding_provider: EmbeddingProvider | None = None
    if not arguments.keyword_only:
        try:
            embedding_provider = get_embedding_provider()
        except (OSError, ValueError) as error:
            print(
                "Embedding model is unavailable in this environment; "
                "continuing with keyword retrieval. Use --keyword-only to silence this fallback. "
                f"Details: {error}"
            )

    with tracker.start_run("qa-evaluation"):
        tracker.log_params(
            {
                "chat_model": settings.hf_chat_model,
                "embedding_model": settings.embedding_model_id,
                "case_count": len(dataset),
            }
        )
        with SessionLocal() as session:
            for case in dataset:
                result = answer_question(
                    session,
                    case["question"],
                    get_chat_provider(),
                    embedding_provider,
                    retrieval_limit=3,
                )
                metrics = evaluate_rag_answer(
                    case["question"],
                    result.answer,
                    result.confirmed_facts,
                    [citation.heading or citation.title or "" for citation in result.citations],
                    len(result.citations),
                )
                reports.append(
                    {
                        "question": case["question"],
                        "status": result.status.value,
                        "faithfulness": metrics.faithfulness,
                        "answer_relevancy": metrics.answer_relevancy,
                        "context_precision": metrics.context_precision,
                        "citation_completeness": metrics.citation_completeness,
                    }
                )

        metric_names = (
            "faithfulness",
            "answer_relevancy",
            "context_precision",
            "citation_completeness",
        )
        tracker.log_metrics(
            {
                name: sum(float(report[name]) for report in reports) / len(reports)
                for name in metric_names
            }
        )

    print(json.dumps({"case_count": len(reports), "cases": reports}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

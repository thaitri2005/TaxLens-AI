import argparse
import json

from taxlens.config import get_settings
from taxlens.db import SessionLocal
from taxlens.retrieval.citations import build_citation
from taxlens.retrieval.embeddings import get_embedding_provider
from taxlens.retrieval.search import SearchFilters, hybrid_search_chunks


def main() -> None:
    parser = argparse.ArgumentParser(description="Run retrieval smoke checks")
    parser.add_argument(
        "--query",
        action="append",
        dest="queries",
        help="Vietnamese or English query; repeat for multiple checks",
    )
    parser.add_argument("--limit", type=int, default=5)
    arguments = parser.parse_args()
    if arguments.limit < 1:
        parser.error("--limit must be at least 1")

    queries = arguments.queries or [
        "thuế suất giá trị gia tăng",
        "đối tượng chịu thuế",
        "thời điểm lập hóa đơn",
    ]
    provider = get_embedding_provider()
    reports: list[dict[str, object]] = []
    with SessionLocal() as session:
        for query in queries:
            results = hybrid_search_chunks(
                session,
                query,
                provider,
                SearchFilters(),
                limit=arguments.limit,
            )
            reports.append(
                {
                    "query": query,
                    "result_count": len(results),
                    "results": [
                        {
                            "document_number": build_citation(result).document_number,
                            "article_number": build_citation(result).article_number,
                            "page_start": build_citation(result).page_start,
                            "page_end": build_citation(result).page_end,
                            "source_url": build_citation(result).source_url,
                            "fused_score": result.fused_score,
                        }
                        for result in results
                    ],
                }
            )
    output = {"model": get_settings().embedding_model_id, "queries": reports}
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

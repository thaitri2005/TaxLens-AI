"""Phase 1 of plan.md: essential recall of the answers' 5 passages, without and with expansion.

    python data/evaluation/article-expansion/phase1.py --window 2500 --output REPORT.json

Evidence is chosen as answers choose it (qa.py): hybrid top 20, located passages, documents that
may have ended last, first 5. Expansion fills each passage's window with its article's other
passages, nearest first, each whole or not at all. No model calls.
"""

import argparse
import importlib.util
import json
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from taxlens.db import SessionLocal
from taxlens.evaluation.metrics import provision_ranks
from taxlens.intelligence.evidence import has_structural_locator
from taxlens.intelligence.qa import LOCATED_CANDIDATE_FACTOR, prefer_not_ended
from taxlens.legal_data.models import DocumentChunk
from taxlens.retrieval.embeddings import get_embedding_provider
from taxlens.retrieval.repeals import ended_documents
from taxlens.retrieval.search import SearchFilters, SearchResult, hybrid_search_chunks

EVIDENCE = 5
LIVE_RULES = ("explicit", "ministry")


def _evaluation() -> Any:
    path = Path("scripts/evaluate_tax_retrieval.py")
    spec = importlib.util.spec_from_file_location("evaluate_tax_retrieval", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _article(session: Any, chunk: DocumentChunk) -> list[DocumentChunk]:
    """The passages of a chunk's article in reading order (as the document view orders them)."""

    return list(
        session.scalars(
            select(DocumentChunk)
            .where(
                DocumentChunk.document_version_id == chunk.document_version_id,
                DocumentChunk.article_number == chunk.article_number,
            )
            .order_by(
                DocumentChunk.page_start.asc().nulls_last(),
                DocumentChunk.clause_number.is_not(None),
                func.length(DocumentChunk.clause_number),
                DocumentChunk.clause_number,
                DocumentChunk.id,
            )
        )
    )


def expand(session: Any, result: SearchResult, window: int) -> list[SearchResult]:
    """Passages added to ``result``'s window: next, previous, then outward, each whole."""

    if result.chunk.article_number is None:
        return []
    passages = _article(session, result.chunk)
    position = next(i for i, chunk in enumerate(passages) if chunk.id == result.chunk.id)
    order = []
    for step in range(1, len(passages)):
        order += [position + step, position - step]
    used = len(result.chunk.content)
    added = []
    for index in order:
        if 0 <= index < len(passages):
            size = len(passages[index].content)
            if used + size <= window:
                used += size
                added.append(SearchResult(passages[index], result.version, result.document))
    return added


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--window", type=int, default=2500)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--repeals", type=Path, default=Path("data/evaluation/repeals/corpus-v2.1-ministry.json")
    )
    arguments = parser.parse_args()

    evaluation = _evaluation()
    repeals = json.loads(arguments.repeals.read_text(encoding="utf-8"))["repeals"]
    cases = [
        case
        for case in evaluation._gold_set_cases(Path("data/evaluation/gold_set_v1.csv"), True)
        if case["essential_provisions"]
    ]
    provider = get_embedding_provider()
    part_counts: dict[Any, int] = {}
    rows = []
    with SessionLocal() as session:
        for case in cases:
            day = date.fromisoformat(case["search_date"])
            filters = SearchFilters(
                as_of=day, excluded_document_numbers=ended_documents(repeals, day, LIVE_RULES)
            )
            candidates = hybrid_search_chunks(
                session, case["query"], provider, filters, EVIDENCE * LOCATED_CANDIDATE_FACTOR
            )
            located = [result for result in candidates if has_structural_locator(result)]
            chosen = prefer_not_ended(located or candidates, day)[:EVIDENCE]
            added = [extra for result in chosen for extra in expand(session, result, arguments.window)]
            provisions = case["essential_provisions"]
            before = provision_ranks(evaluation._passage_locators(session, chosen, part_counts), provisions)
            after = provision_ranks(
                evaluation._passage_locators(session, chosen + added, part_counts), provisions
            )
            row = {
                "case_id": case["case_id"],
                "found_before": [rank is not None for rank in before],
                "found_after": [rank is not None for rank in after],
                "evidence_characters": sum(len(r.chunk.content[: arguments.window]) for r in chosen),
                "added_characters": sum(len(r.chunk.content) for r in added),
            }
            rows.append(row)
            print(case["case_id"], row["found_before"], "->", row["found_after"], flush=True)

    def recall(key: str) -> float:
        values = [sum(row[key]) / len(row[key]) for row in rows]
        return round(sum(values) / len(values), 3)

    up = sum(sum(r["found_after"]) > sum(r["found_before"]) for r in rows)
    down = sum(sum(r["found_after"]) < sum(r["found_before"]) for r in rows)
    summary = {
        "window": arguments.window,
        "cases": len(rows),
        "recall_without": recall("found_before"),
        "recall_with": recall("found_after"),
        "cases_up": up,
        "cases_down": down,
        "mean_evidence_characters": round(sum(r["evidence_characters"] for r in rows) / len(rows)),
        "mean_added_characters": round(sum(r["added_characters"] for r in rows) / len(rows)),
    }
    arguments.output.write_text(
        json.dumps({"summary": summary, "cases": rows}, indent=1), encoding="utf-8"
    )
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()

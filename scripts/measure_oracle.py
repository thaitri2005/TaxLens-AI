"""Oracle issue experiment: can hand-named legal issues recover the provisions search misses?

    python scripts/measure_oracle.py --output data/evaluation/runs/oracle-NAME.json

Plan, cases, query rules, and decision rule: data/evaluation/oracle/plan.md. Runs the live hybrid
search with each case's date and the live ending rules, so it is comparable with the baseline
report. Reports, for the 30 provisions the baseline misses in its top 20:

- leakage: each oracle query's longest run of words copied from its case's essential provisions,
  after the allowed names (tax and law names) are removed; the plan allows at most 3;
- M1: each missed provision's best rank over its case's oracle queries searched alone;
- M2: essential recall at K over all scored cases when the question's ranking and its oracle
  rankings are fused by reciprocal rank, compared case by case with the baseline.

No model calls; a few minutes from a laptop.
"""

import argparse
import importlib.util
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import select

from taxlens.db import SessionLocal
from taxlens.evaluation.metrics import provision_ranks
from taxlens.legal_data.models import DocumentChunk, DocumentVersion, LegalDocument
from taxlens.retrieval.embeddings import get_embedding_provider
from taxlens.retrieval.repeals import ended_documents
from taxlens.retrieval.search import RRF_K, SearchFilters, SearchResult, hybrid_search_chunks
from taxlens.retrieval.text import fold_vietnamese

ORACLE = Path("data/evaluation/oracle")
KS = (5, 10, 20)
# Depth of each ranking fused in M2.
FUSION_DEPTH = 50
LIVE_RULES = ("explicit", "ministry")


def _evaluation_module() -> Any:
    path = Path(__file__).with_name("evaluate_tax_retrieval.py")
    spec = importlib.util.spec_from_file_location("evaluate_tax_retrieval", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--queries", type=Path, default=ORACLE / "oracle-queries.json")
    parser.add_argument("--dataset", type=Path, default=Path("data/evaluation/gold_set_v1.csv"))
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path("data/evaluation/runs/hybrid-asof-ministry-v2.1-gold34.json"),
    )
    parser.add_argument(
        "--repeals", type=Path, default=Path("data/evaluation/repeals/corpus-v2.1-ministry.json")
    )
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()

    evaluation = _evaluation_module()
    oracle = json.loads(arguments.queries.read_text(encoding="utf-8"))
    baseline = {
        case["case_id"]: case
        for case in json.loads(arguments.baseline.read_text(encoding="utf-8"))["cases"]
    }
    repeals = json.loads(arguments.repeals.read_text(encoding="utf-8"))["repeals"]
    cases = [
        case
        for case in evaluation._gold_set_cases(arguments.dataset, True)
        if case["essential_provisions"]
    ]
    provider = get_embedding_provider()
    part_counts: dict[tuple[Any, str], int] = {}
    report_cases = []
    with SessionLocal() as session:
        for case in cases:
            case_id = case["case_id"]
            case_date = date.fromisoformat(case["search_date"]) if case["search_date"] else None
            filters = SearchFilters(
                as_of=case_date,
                excluded_document_numbers=(
                    ended_documents(repeals, case_date, LIVE_RULES) if case_date else ()
                ),
            )
            provisions = case["essential_provisions"]

            def ranks(
                results: list[SearchResult], provisions: list[Any] = provisions
            ) -> list[int | None]:
                locators = evaluation._passage_locators(session, results, part_counts)
                return provision_ranks(locators, provisions)

            question = hybrid_search_chunks(session, case["query"], provider, filters, FUSION_DEPTH)
            question_ranks = ranks(question[:20])
            base_ranks = [item["rank"] for item in baseline[case_id]["essential_provision_ranks"]]
            if question_ranks != base_ranks:
                print(f"{case_id}: question ranks {question_ranks}, baseline {base_ranks}")
            issues = oracle["cases"].get(case_id, {}).get("issues", [])
            entry: dict[str, Any] = {
                "case_id": case_id,
                "provisions": provisions,
                "baseline_ranks": base_ranks,
            }
            if issues:
                texts = _provision_texts(session, provisions)
                lists = []
                entry["queries"] = []
                for issue in issues:
                    results = hybrid_search_chunks(
                        session, issue["query"], provider, filters, FUSION_DEPTH
                    )
                    lists.append(results)
                    entry["queries"].append(
                        {
                            "query": issue["query"],
                            "targets": issue.get("targets"),
                            "ranks": ranks(results[:20]),
                            "copied_run": _longest_copied_run(
                                issue["query"], texts, oracle["allowed_names"]
                            ),
                        }
                    )
                entry["oracle_best_ranks"] = [
                    min((r for r in column if r is not None), default=None)
                    for column in zip(*(query["ranks"] for query in entry["queries"]), strict=True)
                ]
                entry["merged_ranks"] = ranks(_fuse([question, *lists])[:20])
            else:
                entry["merged_ranks"] = question_ranks
            report_cases.append(entry)
            print(case_id, "done", flush=True)

    summary = _summary(report_cases)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(
            {
                "queries": str(arguments.queries),
                "queries_status": oracle.get("status"),
                "baseline": str(arguments.baseline),
                "summary": summary,
                "cases": report_cases,
            },
            ensure_ascii=False,
            indent=2,
            default=list,
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))


def _fuse(rankings: list[list[SearchResult]]) -> list[SearchResult]:
    """Reciprocal-rank fusion of several rankings, equal weight, by passage."""

    scores: dict[object, float] = {}
    passages: dict[object, SearchResult] = {}
    for ranking in rankings:
        for rank, result in enumerate(ranking, start=1):
            passages.setdefault(result.chunk.id, result)
            scores[result.chunk.id] = scores.get(result.chunk.id, 0.0) + 1.0 / (RRF_K + rank)
    order = sorted(scores, key=lambda key: (-scores[key], str(key)))
    return [passages[key] for key in order]


def _provision_texts(session: Any, provisions: list[Any]) -> list[str]:
    """Text of every passage in the articles that hold the case's essential provisions."""

    texts = []
    for places in provisions:
        for document, article, _clause in places:
            texts.extend(
                session.scalars(
                    select(DocumentChunk.content)
                    .join(DocumentVersion, DocumentVersion.id == DocumentChunk.document_version_id)
                    .join(LegalDocument, LegalDocument.id == DocumentVersion.document_id)
                    .where(
                        LegalDocument.document_number == document,
                        DocumentChunk.article_number == article,
                    )
                )
            )
    return texts


def _words(text: str, allowed: list[str], mark: str) -> list[str]:
    folded = " ".join(re.findall(r"\w+", fold_vietnamese(text).lower()))
    # An allowed name becomes a token found only on its own side, so it breaks any run.
    for number, name in enumerate(allowed):
        name = " ".join(re.findall(r"\w+", fold_vietnamese(name).lower()))
        folded = re.sub(rf"\b{re.escape(name)}\b", f"{mark}{number}", folded)
    return folded.split()


def _longest_copied_run(query: str, texts: list[str], allowed: list[str]) -> list[str]:
    """The longest run of the query's words found in a row in any of the texts."""

    words = _words(query, allowed, "qname")
    best: list[str] = []
    for text in texts:
        source = _words(text, allowed, "pname")
        previous = [0] * (len(source) + 1)
        for position, word in enumerate(words):
            current = [0] * (len(source) + 1)
            for index, other in enumerate(source, start=1):
                if word == other:
                    current[index] = previous[index - 1] + 1
                    if current[index] > len(best):
                        best = words[position - current[index] + 1 : position + 1]
            previous = current
    return best


def _summary(cases: list[dict[str, Any]]) -> dict[str, Any]:
    missed = [
        (case["case_id"], index, best)
        for case in cases
        if "oracle_best_ranks" in case
        for index, (base, best) in enumerate(
            zip(case["baseline_ranks"], case["oracle_best_ranks"], strict=True)
        )
        if base is None or base > 20
    ]
    queries = [query for case in cases for query in case.get("queries", [])]

    def recall(rank_key: str, k: int) -> float:
        values: list[float] = [
            sum(r is not None and r <= k for r in case[rank_key]) / len(case[rank_key])
            for case in cases
        ]
        return round(sum(values) / len(values), 3)

    def compare(k: int) -> dict[str, int]:
        outcome = {"up": 0, "down": 0, "same": 0}
        for case in cases:
            base = sum(r is not None and r <= k for r in case["baseline_ranks"])
            merged = sum(r is not None and r <= k for r in case["merged_ranks"])
            outcome["up" if merged > base else "down" if merged < base else "same"] += 1
        return outcome

    return {
        "missed_provisions": len(missed),
        "queries": len(queries),
        "queries_over_copy_limit": [
            f"{query['query']} [{' '.join(query['copied_run'])}]"
            for query in queries
            if len(query["copied_run"]) > 3
        ],
        "m1_recovered": {
            str(k): round(sum(b is not None and b <= k for *_, b in missed) / len(missed), 3)
            for k in KS
        },
        "m1_unrecovered_at_20": [f"{c}#{i}" for c, i, b in missed if b is None],
        "scored_cases": len(cases),
        "baseline_recall": {str(k): recall("baseline_ranks", k) for k in KS},
        "m2_merged_recall": {str(k): recall("merged_ranks", k) for k in KS},
        "m2_cases_against_baseline": {str(k): compare(k) for k in KS},
    }


if __name__ == "__main__":
    main()

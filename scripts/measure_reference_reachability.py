"""Upper limit of following one legal reference from the retrieved passages.

    python scripts/measure_reference_reachability.py data/evaluation/runs/hybrid-asof.json --k 10

For each essential provision the run missed at K, asks whether a top-K passage explicitly
refers to it. Nothing is re-ranked, so this bounds what one hop could recover; it does not
measure a method. Levels, best first:
- ``clause``: names its document and article, and the clause matches or is not given.
- ``article``: names its document and article, but a different clause.
- ``document``: mentions only its document.
- ``none``: no reference reaches it.
``candidates`` is how many distinct articles one hop would have to consider for the case:
the cost of the upper limit. A law named without a number resolves to the latest law
issued by the case date whose title contains that name.
"""

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import select

from taxlens.db import SessionLocal
from taxlens.legal_data.models import DocumentVersion, LegalDocument
from taxlens.retrieval.embeddings import get_embedding_provider
from taxlens.retrieval.issues import Issue, issue_guided_search
from taxlens.retrieval.references import LegalReference, find_references
from taxlens.retrieval.search import SearchFilters, hybrid_search_chunks
from taxlens.retrieval.text import fold_vietnamese

LEVELS = ("clause", "article", "document", "none")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("report", type=Path)
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument(
        "--issues", type=Path, default=Path("data/evaluation/issues/gold_set_v1.json")
    )
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()

    report = json.loads(arguments.report.read_text(encoding="utf-8"))
    guided = report["retrieval_mode"] == "issue-guided"
    stored = json.loads(arguments.issues.read_text(encoding="utf-8"))["cases"] if guided else {}
    as_of = report.get("as_of_filter") == "case"
    provider = get_embedding_provider()
    rows: list[dict[str, Any]] = []
    cases: list[dict[str, Any]] = []
    with SessionLocal() as session:
        numbers, laws = _document_index(session)
        for case in report["cases"]:
            missed = [
                item
                for item in case.get("essential_provision_ranks", [])
                if item["in_corpus"] and (item["rank"] is None or item["rank"] > arguments.k)
            ]
            if not case.get("essential_provision_ranks"):
                continue
            text = case.get("search_date") or case.get("as_of_date")
            case_date = date.fromisoformat(text) if text else None
            filters = SearchFilters(as_of=case_date if as_of else None)
            if guided:
                issues = [
                    Issue(issue=item["issue"], query=item["query"])
                    for item in stored[case["case_id"]]["issues"]
                ]
                results = issue_guided_search(
                    session, case["query"], issues, provider, filters, arguments.k
                )
            else:
                results = hybrid_search_chunks(
                    session, case["query"], provider, filters, arguments.k
                )
            targets: set[tuple[str, str | None, str | None]] = set()
            sources: dict[tuple[str, str | None, str | None], str] = {}
            for result in results:
                for reference in find_references(result.chunk.content):
                    document = _resolve(
                        reference, result.document.document_number, numbers, laws, case_date
                    )
                    if document:
                        target = (document, reference.article, reference.clause)
                        targets.add(target)
                        sources.setdefault(
                            target,
                            f"{result.document.document_number} Art {result.chunk.article_number}",
                        )
            for item in missed:
                level, via = _reach(item["provision"], targets, sources)
                rows.append(
                    {
                        "case_id": case["case_id"],
                        "provision": item["provision"],
                        "level": level,
                        "via": via,
                    }
                )
            cases.append(
                {
                    "case_id": case["case_id"],
                    "missed": len(missed),
                    "candidates": len({(d, a) for d, a, _ in targets if a}),
                }
            )
    counts = {level: sum(row["level"] == level for row in rows) for level in LEVELS}
    output = json.dumps(
        {
            "report": str(arguments.report),
            "retrieval_mode": report["retrieval_mode"],
            "k": arguments.k,
            "missed_in_corpus": len(rows),
            "reach": counts,
            "cases": cases,
            "provisions": rows,
        },
        ensure_ascii=False,
        indent=2,
    )
    if arguments.output:
        arguments.output.write_text(output + "\n", encoding="utf-8")
    print(output)


def _document_index(session) -> tuple[dict[str, str], list[tuple[str, str, date | None]]]:
    """Folded number → number, and ``(folded title, number, issue date)`` of each law."""

    rows = session.execute(
        select(LegalDocument.document_number, LegalDocument.title, DocumentVersion.issue_date).join(
            DocumentVersion, DocumentVersion.document_id == LegalDocument.id
        )
    ).all()
    numbers = {fold_vietnamese(number).lower(): number for number, _, _ in rows}
    laws = [
        (fold_vietnamese(title or "").lower(), number, issued)
        for number, title, issued in rows
        if "/QH" in number
    ]
    return numbers, laws


def _resolve(
    reference: LegalReference,
    own_document: str,
    numbers: dict[str, str],
    laws: list[tuple[str, str, date | None]],
    case_date: date | None,
) -> str | None:
    if reference.same_document:
        return own_document
    if reference.document_number:
        return numbers.get(reference.document_number)
    if reference.law_name:
        matches = [
            (issued or date.min, number)
            for title, number, issued in laws
            if reference.law_name in title
            and (case_date is None or issued is None or issued <= case_date)
        ]
        return max(matches)[1] if matches else None
    return None


def _reach(places, targets, sources) -> tuple[str, str | None]:
    found: dict[str, str | None] = {}
    for document, article, clause in places:
        base = clause.rstrip("abcdefghijklmnopqrstuvwxyz") if clause else None
        for target in targets:
            target_document, target_article, target_clause = target
            if target_document != document:
                continue
            if target_article is None:
                level = "document"
            elif target_article != article:
                continue
            elif target_clause is None or clause is None or target_clause in (clause, base):
                level = "clause"
            else:
                level = "article"
            found.setdefault(level, sources[target])
    for level in LEVELS[:-1]:
        if level in found:
            return level, found[level]
    return "none", None


if __name__ == "__main__":
    main()

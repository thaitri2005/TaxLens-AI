"""Give each essential provision a saved run missed one cause (docs/issue-guided-retrieval.md).

    python scripts/diagnose_retrieval_misses.py data/evaluation/runs/hybrid-asof.json --k 10

Causes, first that applies:
- ``not_in_corpus``: the document is not embedded.
- ``no_passage``: the document is there but no passage carries that article and clause,
  usually because the article heading or clause numbers were lost in OCR.
- ``excluded_by_date``: the case date filter left the document out, so its recorded date
  is wrong for this case.
- ``ranked_below_k``: a passage holding it ranks within the top --depth for the question
  (hybrid search, same filter); the rank is given.
- ``not_retrieved``: no passage holding it ranks within --depth.
``truncated`` is noted separately: every passage holding it is longer than the embedding
model's input, so only its beginning is searched semantically.
"""

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from taxlens.config import get_settings
from taxlens.db import SessionLocal
from taxlens.document_processing.process import CLAUSE_PATTERN
from taxlens.evaluation.metrics import provision_ranks
from taxlens.legal_data.models import DocumentChunk, DocumentVersion, LegalDocument
from taxlens.retrieval.embeddings import get_embedding_provider
from taxlens.retrieval.search import SearchFilters, hybrid_search_chunks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("report", type=Path, help="A report saved with --output")
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--depth", type=int, default=200, help="How deep to look for a rank")
    arguments = parser.parse_args()

    report = json.loads(arguments.report.read_text(encoding="utf-8"))
    as_of = report.get("as_of_filter") == "case"
    max_tokens = get_settings().embedding_max_tokens
    provider = get_embedding_provider()
    rows = []
    with SessionLocal() as session:
        for case in report["cases"]:
            missed = [
                item
                for item in case.get("essential_provision_ranks", [])
                if item["rank"] is None or item["rank"] > arguments.k
            ]
            if not missed:
                continue
            case_date_text = case.get("search_date") or case.get("as_of_date")
            case_date = date.fromisoformat(case_date_text) if case_date_text else None
            filters = SearchFilters(as_of=case_date if as_of else None)
            deep = None
            for item in missed:
                places = item["provision"]
                row: dict[str, Any] = {"case_id": case["case_id"], "provision": places}
                if not item["in_corpus"]:
                    rows.append({**row, "cause": "not_in_corpus"})
                    continue
                holding = _holding_passages(session, places)
                if not holding:
                    rows.append({**row, "cause": "no_passage"})
                    continue
                row["truncated"] = all(tokens > max_tokens for _, tokens, _ in holding)
                if as_of and case_date and all(
                    start is not None and start > case_date for _, _, start in holding
                ):
                    rows.append({**row, "cause": "excluded_by_date"})
                    continue
                if deep is None:
                    deep = [
                        result.chunk.id
                        for result in hybrid_search_chunks(
                            session,
                            case["query"],
                            provider,
                            filters,
                            arguments.depth,
                            candidate_limit=arguments.depth,
                        )
                    ]
                ids = {chunk_id for chunk_id, _, _ in holding}
                rank = next((n for n, chunk_id in enumerate(deep, 1) if chunk_id in ids), None)
                rows.append(
                    {
                        **row,
                        "cause": "ranked_below_k" if rank else "not_retrieved",
                        "rank": rank,
                    }
                )
    causes: dict[str, int] = {}
    for row in rows:
        causes[row["cause"]] = causes.get(row["cause"], 0) + 1
    print(
        json.dumps(
            {
                "report": str(arguments.report),
                "retrieval_mode": report.get("retrieval_mode"),
                "k": arguments.k,
                "missed": len(rows),
                "causes": causes,
                "truncated": sum(bool(row.get("truncated")) for row in rows),
                "provisions": rows,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _holding_passages(session, places: list[list[str | None]]) -> list[tuple[Any, int, Any]]:
    """``(chunk id, tokens, known start date)`` of every passage holding one of the places."""

    held = []
    for document, article, _ in places:
        chunks = session.execute(
            select(
                DocumentChunk.id,
                DocumentChunk.clause_number,
                DocumentChunk.content,
                DocumentChunk.token_count,
                func.coalesce(DocumentVersion.effective_date, DocumentVersion.issue_date),
            )
            .join(DocumentVersion, DocumentChunk.document_version_id == DocumentVersion.id)
            .join(LegalDocument, DocumentVersion.document_id == LegalDocument.id)
            .where(
                LegalDocument.document_number == document,
                DocumentChunk.article_number == article,
            )
        ).all()
        whole = len(chunks) == 1
        for chunk_id, clause, content, tokens, start in chunks:
            clauses: Any = clause
            if clause is None and not whole:
                clauses = frozenset(m.group(1) for m in CLAUSE_PATTERN.finditer(content))
            if provision_ranks([(document, article, clauses)], [places])[0] is not None:
                held.append((chunk_id, tokens, start))
    return held


if __name__ == "__main__":
    main()

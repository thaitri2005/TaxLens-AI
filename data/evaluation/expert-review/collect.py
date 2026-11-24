"""Collect the expert review packet's content into packet-data.json (no model calls).

    python data/evaluation/expert-review/collect.py

1. Documents flagged "may have ended" (inferred rules) that reach the top 20 of a scored gold case.
2. Old documents with no recorded ending that fill the top 10 of the reviewed oracle queries whose
   provision is not found.
3. The essential provisions of the 17 hard cases (and L4), with their text in the corpus.
4. The 15 graded answers (answers-gold-v1-2026-11-23c) with the judge's verdicts.
"""

import csv
import importlib.util
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import select

from taxlens.db import SessionLocal
from taxlens.legal_data.models import DocumentChunk, DocumentVersion, LegalDocument
from taxlens.retrieval.embeddings import get_embedding_provider
from taxlens.retrieval.repeals import CONFIRMED_RULES, INFERRED_RULES, ended_documents
from taxlens.retrieval.search import SearchFilters, hybrid_search_chunks

HERE = Path(__file__).parent
EVALUATION = Path("data/evaluation")
OLD_BEFORE = 2017
EXCERPT = 1800


def _evaluation() -> Any:
    path = Path("scripts/evaluate_tax_retrieval.py")
    spec = importlib.util.spec_from_file_location("evaluate_tax_retrieval", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _year(issued: date | None) -> int:
    return issued.year if issued else 0


def _provision_text(session: Any, document: str, article: str, clause: str | None) -> str:
    rows = session.execute(
        select(DocumentChunk.clause_number, DocumentChunk.content)
        .join(DocumentVersion, DocumentVersion.id == DocumentChunk.document_version_id)
        .join(LegalDocument, LegalDocument.id == DocumentVersion.document_id)
        .where(LegalDocument.document_number == document, DocumentChunk.article_number == article)
        .order_by(DocumentChunk.page_start.asc().nulls_last(), DocumentChunk.clause_number)
    ).all()
    chosen = [text for number, text in rows if clause is None or number in (clause, None)]
    text = " ".join(" ".join(chosen or [text for _, text in rows]).split())
    return text[:EXCERPT] + ("…" if len(text) > EXCERPT else "")


def main() -> None:
    evaluation = _evaluation()
    repeals = json.loads(
        (EVALUATION / "repeals/corpus-v2.1-ministry.json").read_text(encoding="utf-8")
    )["repeals"]
    gold = {
        row["case_id"]: row
        for row in csv.DictReader((EVALUATION / "gold_set_v1.csv").open(encoding="utf-8-sig"))
    }
    cases = {
        case["case_id"]: case
        for case in evaluation._gold_set_cases(EVALUATION / "gold_set_v1.csv", True)
        if case["essential_provisions"]
    }
    oracle = json.loads(
        (EVALUATION / "oracle/oracle-queries-reviewed.json").read_text(encoding="utf-8")
    )
    counted = json.loads((EVALUATION / "runs/oracle-reviewed.json").read_text(encoding="utf-8"))
    baseline = {
        case["case_id"]: case
        for case in json.loads(
            (EVALUATION / "runs/hybrid-asof-ministry-v2.1-gold34-item19.json").read_text(
                encoding="utf-8"
            )
        )["cases"]
    }
    provider = get_embedding_provider()
    flagged: dict[str, dict[str, Any]] = {}
    old_counts: Counter[str] = Counter()
    old_cases: dict[str, set[str]] = defaultdict(set)
    titles: dict[str, tuple[str, date | None]] = {}
    with SessionLocal() as session:
        for case_id, case in cases.items():
            day = date.fromisoformat(case["search_date"])
            filters = SearchFilters(
                as_of=day,
                excluded_document_numbers=ended_documents(repeals, day, CONFIRMED_RULES),
            )
            results = hybrid_search_chunks(session, case["query"], provider, filters, 20)
            for rank, result in enumerate(results, start=1):
                number = result.document.document_number
                titles[number] = (result.document.title or "", result.version.issue_date)
                repeal = repeals.get(number)
                if (
                    repeal
                    and repeal["rule"] in INFERRED_RULES
                    and date.fromisoformat(repeal["ended_on"]) <= day
                ):
                    entry = flagged.setdefault(number, {**repeal, "cases": {}})
                    entry["cases"][case_id] = min(rank, entry["cases"].get(case_id, rank))
            print(case_id, "flagged so far", len(flagged), flush=True)

        unrecovered = {
            case["case_id"]
            for case in counted["cases"]
            if any(
                (base is None or base > 20) and best is None
                for base, best in zip(
                    case["baseline_ranks"], case.get("oracle_best_ranks", []), strict=False
                )
            )
        }
        for case_id in sorted(unrecovered):
            day = date.fromisoformat(cases[case_id]["search_date"])
            filters = SearchFilters(
                as_of=day,
                excluded_document_numbers=ended_documents(repeals, day, CONFIRMED_RULES),
            )
            for issue in oracle["cases"][case_id]["issues"]:
                seen = set()
                for result in hybrid_search_chunks(session, issue["query"], provider, filters, 10):
                    number = result.document.document_number
                    issued = result.version.issue_date
                    titles[number] = (result.document.title or "", issued)
                    if number in seen or number in repeals or _year(issued) >= OLD_BEFORE:
                        continue
                    seen.add(number)
                    old_counts[number] += 1
                    old_cases[number].add(case_id)

        hard = sorted({case["case_id"] for case in counted["cases"] if "oracle_best_ranks" in case})
        provisions = []
        for case_id in sorted(set(hard) | {"L4"}, key=lambda c: (c[0], int(c[1:]))):
            row = gold[case_id]
            ranks = [item["rank"] for item in baseline[case_id]["essential_provision_ranks"]]
            texts = []
            for places, rank in zip(cases[case_id]["essential_provisions"], ranks, strict=True):
                document, article, clause = places[0]
                label = f"{document} Art {article}" + (f"({clause})" if clause else "")
                texts.append(
                    {
                        "provision": label,
                        "rank_in_search": rank,
                        "text": _provision_text(session, document, article, clause),
                    }
                )
            provisions.append(
                {
                    "case_id": case_id,
                    "question": row["question"],
                    "as_of_date": row["as_of_date"],
                    "gold_answer": row["gold_answer"],
                    "gold_provisions": row["gold_provisions"],
                    "essential": texts,
                }
            )

    answers = json.loads(
        (EVALUATION / "runs/answers-gold-v1-2026-11-23c.json").read_text(encoding="utf-8")
    )["cases"]
    packet = {
        "flagged_endings": [
            {
                "document": number,
                "title": titles[number][0],
                "rule": entry["rule"],
                "parent": entry["by"],
                "inferred_end": entry["ended_on"],
                "cases": entry["cases"],
            }
            for number, entry in sorted(flagged.items(), key=lambda kv: -len(kv[1]["cases"]))
        ],
        "unrecorded_old": [
            {
                "document": number,
                "title": titles[number][0],
                "issued": str(titles[number][1]) if titles[number][1] else None,
                "times_in_top10": count,
                "cases": sorted(old_cases[number]),
            }
            for number, count in old_counts.most_common()
        ],
        "provisions": provisions,
        "answers": [
            {
                key: case.get(key)
                for key in (
                    "case_id",
                    "question",
                    "gold_answer",
                    "status",
                    "answer",
                    "verdict",
                    "reason",
                    "uncertain",
                )
            }
            for case in answers
        ],
    }
    (HERE / "packet-data.json").write_text(
        json.dumps(packet, ensure_ascii=False, indent=1, default=str), encoding="utf-8"
    )
    print({key: len(value) for key, value in packet.items()})


if __name__ == "__main__":
    main()

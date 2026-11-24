"""List the documents the corpus itself says have ended (taxlens/retrieval/repeals.py).

    python scripts/extract_repeals.py --output data/evaluation/repeals/corpus-v1.json

An ended document's date is its repealer's recorded effective date, then the date stated
in its last article that gives one, then its issue date; never before the issue date. A
document said to continue in force until a date ends the day after it instead. The file is
an input to frozen runs: make it once and commit it, as with issue decompositions.
"""

import argparse
import json
from datetime import date
from pathlib import Path

from sqlalchemy import select

from taxlens.db import SessionLocal
from taxlens.legal_data.models import DocumentChunk, DocumentVersion, LegalDocument
from taxlens.retrieval.repeals import (
    amending_law_targets,
    amends_only,
    effective_date_in,
    explicit_targets,
    infer_repeals,
    list_continuation_targets,
    normalize,
    opens_list,
    sunset_targets,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()

    found: list[tuple[str, str]] = []
    # Amending laws named with a law that ends as amended, with that law's name and the
    # ending document; kept if they amend that law alone.
    amending: list[tuple[str, str, str]] = []
    sunsets: list[tuple[str, str, date]] = []
    # A list split by size continues in other passages of its clause, in no stored order.
    list_opened: set[tuple[object, str | None, str | None]] = set()
    continued: dict[tuple[object, str | None, str | None], set[tuple[str, str]]] = {}
    stated: dict[str, tuple[int, date]] = {}
    recorded: dict[str, date | None] = {}
    issued_on: dict[str, date | None] = {}
    with SessionLocal() as session:
        titles = dict(
            session.execute(select(LegalDocument.document_number, LegalDocument.title)).all()
        )
        statement = (
            select(
                LegalDocument.document_number,
                DocumentVersion.effective_date,
                DocumentVersion.issue_date,
                DocumentChunk.document_version_id,
                DocumentChunk.article_number,
                DocumentChunk.clause_number,
                DocumentChunk.content,
            )
            .join(DocumentVersion, DocumentChunk.document_version_id == DocumentVersion.id)
            .join(LegalDocument, DocumentVersion.document_id == LegalDocument.id)
        )
        for number, effective, issued, version, article, clause, content in session.execute(
            statement.execution_options(yield_per=2000)
        ):
            recorded[number] = effective
            issued_on[number] = issued
            found.extend((target, number) for target in explicit_targets(content))
            amending.extend(
                (target, law, number) for target, law in amending_law_targets(content).items()
            )
            sunsets.extend((target, number, day) for target, day in sunset_targets(content).items())
            part = (version, article, clause)
            if opens_list(content):
                list_opened.add(part)
            elif items := list_continuation_targets(content):
                continued.setdefault(part, set()).update((item, number) for item in items)
            own = effective_date_in(content)
            position = int(article) if article and article.isdigit() else -1
            if own and position >= stated.get(number, (-2,))[0]:
                stated[number] = (position, own)

    def ended_on(by: str) -> date | None:
        issued = issued_on.get(by)
        own = stated.get(by)
        chosen = recorded.get(by) or (own[1] if own else None) or issued
        return max(chosen, issued) if chosen and issued else chosen

    by_folded = {normalize(number): number for number in titles}
    found.extend(
        (target, by)
        for target, law, by in amending
        if amends_only(titles.get(by_folded.get(target, "")) or "", law)
    )
    for part, pairs in continued.items():
        if part in list_opened:
            found.extend(pairs)
    explicit = [(target, by, day) for target, by in found if (day := ended_on(by))]
    explicit += sunsets
    repeals = infer_repeals(explicit, {number: title or "" for number, title in titles.items()})
    repeals = {number: repeal for number, repeal in repeals.items() if number in titles}
    rules: dict[str, int] = {}
    for repeal in repeals.values():
        rules[repeal.rule] = rules.get(repeal.rule, 0) + 1
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(
            {
                "document_count": len(titles),
                "ended_count": len(repeals),
                "rules": rules,
                "repeals": {
                    number: {
                        "ended_on": repeal.ended_on.isoformat(),
                        "rule": repeal.rule,
                        "by": repeal.by,
                    }
                    for number, repeal in sorted(repeals.items())
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(len(titles), len(repeals), rules)


if __name__ == "__main__":
    main()

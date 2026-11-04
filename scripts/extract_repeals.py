"""List the documents the corpus itself says have ended (taxlens/retrieval/repeals.py).

    python scripts/extract_repeals.py --output data/evaluation/repeals/corpus-v1.json

An ended document's date is its repealer's recorded effective date, then the date stated
in its last article that gives one, then its issue date; never before the issue date. The
file is an input to frozen runs: make it once and commit it, as with issue decompositions.
"""

import argparse
import json
from datetime import date
from pathlib import Path

from sqlalchemy import select

from taxlens.db import SessionLocal
from taxlens.legal_data.models import DocumentChunk, DocumentVersion, LegalDocument
from taxlens.retrieval.repeals import effective_date_in, explicit_targets, infer_repeals


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()

    found: list[tuple[str, str]] = []
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
                DocumentChunk.article_number,
                DocumentChunk.content,
            )
            .join(DocumentVersion, DocumentChunk.document_version_id == DocumentVersion.id)
            .join(LegalDocument, DocumentVersion.document_id == LegalDocument.id)
        )
        for number, effective, issued, article, content in session.execute(
            statement.execution_options(yield_per=2000)
        ):
            recorded[number] = effective
            issued_on[number] = issued
            found.extend((target, number) for target in explicit_targets(content))
            own = effective_date_in(content)
            position = int(article) if article and article.isdigit() else -1
            if own and position >= stated.get(number, (-2,))[0]:
                stated[number] = (position, own)

    def ended_on(by: str) -> date | None:
        issued = issued_on.get(by)
        own = stated.get(by)
        chosen = recorded.get(by) or (own[1] if own else None) or issued
        return max(chosen, issued) if chosen and issued else chosen

    explicit = [(target, by, day) for target, by in found if (day := ended_on(by))]
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

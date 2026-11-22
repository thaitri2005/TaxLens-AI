"""Load a committed repeal list into the documents' ending columns.

    python scripts/apply_document_endings.py --repeals REPEAL_LIST [--apply]

with REPEAL_LIST the corpus's list with ministry dates, such as
data/evaluation/repeals/corpus-v2-ministry.json.

A dry run unless --apply: prints what would change. The list replaces what is stored, so a
document missing from it loses its ending. Search and answers read the columns directly, so
nothing needs a restart. Which rules end a document and which only flag it is decided in
taxlens.retrieval.repeals (CONFIRMED_RULES, INFERRED_RULES), not here.
"""

import argparse
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

from sqlalchemy import select

from taxlens.db import SessionLocal
from taxlens.legal_data.models import LegalDocument
from taxlens.retrieval.repeals import RULES, normalize

# add_ministry_expiry.py records the ministry's own status, with no ending document.
NO_DOCUMENT = "ministry status"

Ending = tuple[date | None, str | None, str | None]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repeals", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="Write the changes")
    arguments = parser.parse_args()

    stored = json.loads(arguments.repeals.read_text(encoding="utf-8"))["repeals"]
    with SessionLocal() as session:
        documents = session.scalars(select(LegalDocument)).all()
        by_number = {document.document_number: document for document in documents}
        by_folded = {normalize(number): number for number in by_number}

        wanted: dict[str, Ending] = {}
        unmatched: list[str] = []
        unresolved: set[str] = set()
        for number, repeal in stored.items():
            if repeal["rule"] not in RULES:
                raise SystemExit(f"{number}: unknown rule {repeal['rule']!r}")
            target = number if number in by_number else by_folded.get(normalize(number))
            if target is None:
                unmatched.append(number)
                continue
            ended_by = _document_number(repeal["by"], by_folded, unresolved)
            wanted[target] = (date.fromisoformat(repeal["ended_on"]), repeal["rule"], ended_by)

        changes: Counter[str] = Counter()
        for number, document in by_number.items():
            current: Ending = (document.ended_on, document.end_basis, document.ended_by)
            target_ending: Ending = wanted.get(number, (None, None, None))
            if current == target_ending:
                changes["unchanged"] += 1
                continue
            changes["cleared" if target_ending[0] is None else "set"] += 1
            if arguments.apply:
                document.ended_on, document.end_basis, document.ended_by = target_ending
        if arguments.apply:
            session.commit()

    rules = Counter(ending[1] for ending in wanted.values())
    print(f"list: {arguments.repeals} ({len(stored)} entries)")
    print(f"documents in database: {len(by_number)}; with an ending: {len(wanted)}")
    print("by rule:", dict(sorted(rules.items())))
    mode = "(applied)" if arguments.apply else "(dry run)"
    print("changes:", dict(sorted(changes.items())), mode)
    if unmatched:
        print(f"not in the database ({len(unmatched)}):", ", ".join(sorted(unmatched)))
    if unresolved:
        print(
            f"related documents not in the corpus ({len(unresolved)}):",
            ", ".join(sorted(unresolved)),
        )


def _document_number(by: str, by_folded: dict[str, str], unresolved: set[str]) -> str | None:
    """The corpus spelling of the related document, since repeal lists may hold it folded."""

    if by == NO_DOCUMENT:
        return None
    found = by_folded.get(normalize(by))
    if found is not None:
        return found
    unresolved.add(by)
    return _official_spelling(by) if by == by.lower() else by


# Parts of a document number that lose their accent or case when folded.
_SPELLING = {"QD": "QĐ", "ND": "NĐ", "TTG": "TTg"}


def _official_spelling(folded: str) -> str:
    """``106/2007/qd-btc`` → ``106/2007/QĐ-BTC``, for a number not in the corpus."""

    parts = re.split(r"([/-])", folded.upper())
    return "".join(_SPELLING.get(part, part) for part in parts)


if __name__ == "__main__":
    main()

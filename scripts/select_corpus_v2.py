"""Apply the inclusion rules to the candidate lists (docs/corpus-inclusion.md).

    python scripts/select_corpus_v2.py

Offline. "In force" for rule C4 is approximated: the latest law of each name, the laws
amending it that were issued in or after its year, minus laws listed as ended.
"""

import json
import re
from datetime import date
from pathlib import Path
from statistics import mean

from taxlens.retrieval.repeals import ended_documents, normalize

CANDIDATES = Path("data/evaluation/corpus/candidates-v2.json")
OUTPUT = Path("data/evaluation/corpus/selected-v2.json")
REPEALS = Path("data/evaluation/repeals/corpus-v1.json")
MANIFEST = Path("data/evaluation/corpus/corpus-v1.json")


def year_of(number: str) -> int:
    match = re.search(r"/(\d{4})/", number)
    return int(match[1]) if match else 0


def latest_laws(laws: dict[str, dict]) -> dict[str, dict]:
    """The latest law of each name, and amending laws no older than the oldest of those."""

    latest: dict[str, tuple[int, str]] = {}
    amending: list[str] = []
    for number, row in laws.items():
        title = normalize(row["title"])
        if "sua doi" in title:
            amending.append(number)
        elif year_of(number) >= latest.get(title, (0, ""))[0]:
            latest[title] = (year_of(number), number)
    kept = {number for _, number in latest.values()}
    latest_years = {normalize(laws[number]["title"]): year for year, number in latest.values()}
    for number in amending:
        title = normalize(laws[number]["title"])
        amended = [year for name, year in latest_years.items() if name in title]
        # An amendment of an older law of that name went with the law it amended.
        if not amended or year_of(number) >= min(amended):
            kept.add(number)
    return {number: laws[number] for number in kept}


def main() -> None:
    candidates = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    stored = json.loads(REPEALS.read_text(encoding="utf-8"))["repeals"]
    ended = {normalize(number) for number in ended_documents(stored, date.today())}
    versions = json.loads(MANIFEST.read_text(encoding="utf-8"))["versions"]
    held = {normalize(version["document_number"]): version for version in versions}

    selected: dict[str, dict] = {}
    for rule, rows in (
        ("C2", candidates["C2"]),
        ("C3", candidates["C3"]),
        ("C4", latest_laws(candidates["C4"])),
    ):
        for number, row in rows.items():
            folded = normalize(number)
            if folded in held or number in selected or (rule == "C4" and folded in ended):
                continue
            selected[number] = {"rule": rule, **row}

    sizes: dict[str, list[int]] = {"law": [], "decree": [], "circular": []}
    for folded, version in held.items():
        sizes[_kind(folded)].append(version["chunk_count"])
    counts = {kind: 0 for kind in sizes}
    rules: dict[str, int] = {}
    for number, row in selected.items():
        counts[_kind(normalize(number))] += 1
        rules[row["rule"]] = rules.get(row["rule"], 0) + 1
    passages = round(sum(count * mean(sizes[kind]) for kind, count in counts.items()))
    OUTPUT.write_text(
        json.dumps(
            {
                "document_count": len(selected),
                "rules": rules,
                "kinds": counts,
                "estimated_passages": passages,
                "documents": selected,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(len(selected), rules, counts, passages)


def _kind(folded_number: str) -> str:
    if "/qh" in folded_number:
        return "law"
    return "decree" if "nd-cp" in folded_number else "circular"


if __name__ == "__main__":
    main()

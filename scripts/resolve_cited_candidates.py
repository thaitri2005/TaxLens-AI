"""Look up the cited numbers the first portal pass did not find (rule C3).

    python scripts/resolve_cited_candidates.py

The first pass searched for ``ND-CP``, which the portal does not match to ``NĐ-CP``, so
decrees were recorded as missing. This repeats those searches with the right letter, then
looks in the ministry database, including expired documents and every field. About 15
minutes for the portal; the ministry listing has taken ten minutes or more.
"""

import json
import sys
import time
from dataclasses import asdict
from datetime import date
from pathlib import Path

import httpx

from taxlens.ingestion.connectors import ConnectorError, GovernmentPortalSearch
from taxlens.ingestion.mof import MofLegalDocumentConnector, MofSearchOptions
from taxlens.retrieval.repeals import normalize

CANDIDATES = Path("data/evaluation/corpus/candidates-v2.json")


def main() -> None:
    data = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    missing = list(data["cited_not_on_portal"])
    found = data["C3"]
    portal = GovernmentPortalSearch()
    still: list[str] = []

    def save() -> None:
        data["cited_not_on_portal"] = still + missing
        data["counts"] = {rule: len(data[rule]) for rule in ("C4", "C2", "C3")}
        CANDIDATES.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
        )

    started = time.monotonic()
    while missing:
        number = missing.pop(0)
        query = number.upper().replace("ND-CP", "NĐ-CP")
        rows = None
        for attempt in range(1, 4):
            try:
                rows = portal._post(category="0", year="0", issuer="0", keyword=query)[0]
                break
            except httpx.HTTPError:
                time.sleep(10 * attempt)
        match = next((row for row in rows or [] if normalize(row.document_number) == number), None)
        if match:
            found[match.document_number] = asdict(match)
        else:
            still.append(number)
        save()
    print("portal", round(time.monotonic() - started), "s; still missing", len(still), flush=True)

    started = time.monotonic()
    options = MofSearchOptions(issued_from=date(1990, 1, 1), include_expired=True, any_field=True)
    try:
        listing = MofLegalDocumentConnector().list_documents(options)
    except ConnectorError as error:
        print("ministry unavailable:", error)
        sys.exit(1)
    by_number = {normalize(document.document_number): document for document in listing}
    remaining = []
    for number in still:
        document = by_number.get(number)
        if document:
            found[document.document_number] = asdict(document)
        else:
            remaining.append(number)
    still[:] = remaining
    save()
    print(
        "ministry",
        round(time.monotonic() - started),
        "s;",
        len(listing),
        "records; still",
        len(still),
    )


if __name__ == "__main__":
    main()

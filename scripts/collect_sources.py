"""Collect tax documents from official sources, cheapest work first.

Sources, in order:
1. Ministry of Finance database (vbpq.mof.gov.vn): finance circulars, joint circulars,
   consolidated texts, with legal status and effective dates; many have Word files whose
   text needs no OCR.
2. Government portal search (vanban.chinhphu.vn, "Thuế - Lệ phí" category): laws, decrees,
   and Prime Minister decisions that the ministry database does not hold. Documents whose
   number is already in the corpus are skipped, so the ministry's richer record wins.

Listing is metadata only. Files are downloaded only for documents not ingested before, at
most ``--limit`` per run, so a large historical backfill spreads over several runs.

    python scripts/collect_sources.py --since-days 60 --limit 50       # daily
    python scripts/collect_sources.py --from-year 1990 --limit 300     # backfill
    python scripts/collect_sources.py --from-year 1990 --dry-run       # count only
"""

import argparse
from collections.abc import Callable
from datetime import date, timedelta

from sqlalchemy import select

from taxlens.db import SessionLocal
from taxlens.ingestion.connectors import ConnectorError, GovernmentPortalSearch, SourceDocument
from taxlens.ingestion.mof import MofLegalDocumentConnector, MofSearchOptions
from taxlens.ingestion.seed import ingest_source_document, is_already_ingested
from taxlens.legal_data.models import LegalDocument
from taxlens.storage.factory import get_object_storage


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect official tax documents")
    parser.add_argument("--source", choices=("mof", "government", "all"), default="all")
    window = parser.add_mutually_exclusive_group()
    window.add_argument("--since-days", type=int, help="Only documents issued recently")
    window.add_argument("--from-year", type=int, help="Backfill from this issue year")
    parser.add_argument("--include-expired", action="store_true")
    parser.add_argument("--limit", type=int, default=100, help="Maximum downloads per run")
    parser.add_argument("--dry-run", action="store_true", help="List and count only")
    arguments = parser.parse_args()
    if arguments.limit < 1:
        parser.error("--limit must be at least 1")

    today = date.today()
    issued_from = (
        today - timedelta(days=arguments.since_days)
        if arguments.since_days is not None
        else date(arguments.from_year, 1, 1)
        if arguments.from_year is not None
        else None
    )
    first_year = issued_from.year if issued_from is not None else 1988

    Fetch = Callable[[SourceDocument], bytes]
    candidates: list[tuple[SourceDocument, Fetch]] = []
    if arguments.source in ("mof", "all"):
        mof = MofLegalDocumentConnector()
        found = mof.list_documents(
            MofSearchOptions(issued_from=issued_from, include_expired=arguments.include_expired)
        )
        print(f"Ministry of Finance: {len(found)} tax document(s) listed", flush=True)
        candidates.extend((document, mof.fetch_document) for document in found)
    if arguments.source in ("government", "all"):
        government = GovernmentPortalSearch()
        found = government.tax_documents(range(today.year, first_year - 1, -1))
        print(f"Government portal: {len(found)} tax document(s) listed", flush=True)
        candidates.extend((document, government.fetch_document) for document in found)

    storage = get_object_storage()
    downloaded = skipped = failed = 0
    with SessionLocal() as session:
        known_numbers = set(session.scalars(select(LegalDocument.document_number)).all())
        pending: list[tuple[SourceDocument, Fetch]] = []
        for document, fetch in candidates:
            if is_already_ingested(session, document.source_name, document.source_document_id):
                skipped += 1
            elif document.source_name != "mof-vbpq" and document.document_number in known_numbers:
                # Already held from the ministry database, whose record is richer.
                skipped += 1
            else:
                pending.append((document, fetch))
                known_numbers.add(document.document_number)
        print(
            f"{len(pending)} new document(s) to collect; {skipped} already in the corpus",
            flush=True,
        )
        if arguments.dry_run:
            print(f"Dry run: would download {min(len(pending), arguments.limit)} now.")
            return
        for document, fetch in pending[: arguments.limit]:
            try:
                content = fetch(document)
                result = ingest_source_document(session, storage, document, content)
                downloaded += 1
                print(f"Collected {document.document_number}: {result.status}", flush=True)
            except (ConnectorError, OSError) as error:
                session.rollback()
                failed += 1
                print(f"Skipped {document.document_number}: {error}", flush=True)
    remaining = max(0, len(pending) - arguments.limit)
    print(
        f"Collection complete: {downloaded} collected, {failed} failed, "
        f"{remaining} remaining for later runs"
    )


if __name__ == "__main__":
    main()

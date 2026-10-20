"""Collect tax documents from official sources, cheapest work first.

Sources:
- ``government``: the government portal's tax category (vanban.chinhphu.vn): laws, decrees,
  Prime Minister decisions, and finance circulars. Reachable from Azure; used by Airflow.
- ``mof``: the Ministry of Finance database (vbpq.mof.gov.vn): circulars and consolidated
  texts with legal status, many as Word files. It only accepts Vietnamese IP addresses, so
  run it from a machine in Vietnam against the Azure database and storage
  (docs/operations.md), then run the ``process_and_embed`` maintenance action.

Listing is metadata only. Files are downloaded only for documents not collected before,
at most ``--limit`` per run. With ``--source all`` the ministry runs first, and portal
documents whose number is already in the corpus are skipped (the ministry record is richer).

    python scripts/collect_sources.py --source government --since-days 60     # daily
    python scripts/collect_sources.py --source mof --from-year 1990 --dry-run
    python scripts/collect_sources.py --source mof --from-year 1990 --limit 300
"""

import argparse
import json
import logging
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from taxlens.config import get_settings
from taxlens.db import SessionLocal, database_is_ready
from taxlens.ingestion.connectors import ConnectorError, GovernmentPortalSearch, SourceDocument
from taxlens.ingestion.mof import SOURCE_NAME as MOF_SOURCE
from taxlens.ingestion.mof import MofLegalDocumentConnector, MofSearchOptions
from taxlens.ingestion.seed import ingest_source_document
from taxlens.legal_data.models import DocumentVersion, LegalDocument, SourceRecord
from taxlens.storage.factory import get_object_storage

logger = logging.getLogger("collect_sources")
LISTING_CACHE_DIRECTORY = Path("data/local/cache")
Fetch = Callable[[SourceDocument], bytes]


@dataclass(frozen=True)
class Candidate:
    document: SourceDocument
    fetch: Fetch


def main() -> None:
    arguments = _parse_arguments()
    _configure_logging()
    issued_from = _issued_from(arguments)
    logger.info(
        "Collecting from %s, issued from %s, at most %d download(s)%s",
        arguments.source,
        issued_from or "the beginning",
        arguments.limit,
        " (dry run)" if arguments.dry_run else "",
    )

    # Check where results will be written before the slow listing, so a missing setting
    # fails in seconds instead of after ten minutes.
    _check_targets()
    candidates, unavailable = _list_sources(arguments.source, issued_from, arguments)
    if not candidates and unavailable:
        raise SystemExit(f"No source reachable: {', '.join(unavailable)}")

    with SessionLocal() as session:
        pending = _new_documents(session, candidates)
        if arguments.dry_run:
            logger.info("Dry run: would download %d now.", min(len(pending), arguments.limit))
            return
        collected, failed = _download(session, pending[: arguments.limit])

    logger.info(
        "Collection complete: %d collected, %d failed, %d remaining for later runs%s",
        collected,
        failed,
        max(0, len(pending) - arguments.limit),
        f"; unavailable: {', '.join(unavailable)}" if unavailable else "",
    )


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect official tax documents")
    parser.add_argument("--source", choices=("government", "mof", "all"), default="government")
    window = parser.add_mutually_exclusive_group()
    window.add_argument("--since-days", type=int, help="Only documents issued recently")
    window.add_argument("--from-year", type=int, help="Backfill from this issue year")
    parser.add_argument("--include-expired", action="store_true")
    parser.add_argument("--limit", type=int, default=100, help="Maximum downloads per run")
    parser.add_argument("--dry-run", action="store_true", help="List and count only")
    parser.add_argument(
        "--refresh-listing",
        action="store_true",
        help="Ignore the cached Ministry of Finance listing (kept for 24 hours)",
    )
    arguments = parser.parse_args()
    if arguments.limit < 1:
        parser.error("--limit must be at least 1")
    return arguments


def _configure_logging() -> None:
    # Timestamped, unbuffered lines: progress must be visible on a laptop console and in
    # the Airflow job log while the run is in progress.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
        force=True,
    )
    # Client libraries log every HTTP request at INFO; keep only their warnings.
    for noisy in ("httpx", "azure", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _issued_from(arguments: argparse.Namespace) -> date | None:
    if arguments.since_days is not None:
        return date.today() - timedelta(days=arguments.since_days)
    if arguments.from_year is not None:
        return date(arguments.from_year, 1, 1)
    return None


def _list_sources(
    source: str, issued_from: date | None, arguments: argparse.Namespace
) -> tuple[list[Candidate], list[str]]:
    """List every selected source; an unreachable source is reported, not fatal."""

    candidates: list[Candidate] = []
    unavailable: list[str] = []
    if source in ("mof", "all"):
        started = time.monotonic()
        mof = MofLegalDocumentConnector()
        options = MofSearchOptions(
            issued_from=issued_from, include_expired=arguments.include_expired
        )
        try:
            found = _cached_mof_listing(mof, options, arguments.refresh_listing)
        except ConnectorError as error:
            unavailable.append("Ministry of Finance")
            logger.warning("Ministry of Finance unavailable: %s", error)
        else:
            logger.info(
                "Ministry of Finance: %d tax document(s) listed in %s",
                len(found),
                _duration(time.monotonic() - started),
            )
            candidates.extend(Candidate(document, mof.fetch_document) for document in found)
    if source in ("government", "all"):
        started = time.monotonic()
        government = GovernmentPortalSearch()
        first_year = issued_from.year if issued_from is not None else 1988
        try:
            found = government.tax_documents(range(date.today().year, first_year - 1, -1))
        except (ConnectorError, httpx.HTTPError) as error:
            unavailable.append("government portal")
            logger.warning("Government portal unavailable: %s", error)
        else:
            logger.info(
                "Government portal: %d tax document(s) listed in %s",
                len(found),
                _duration(time.monotonic() - started),
            )
            candidates.extend(Candidate(document, government.fetch_document) for document in found)
    return candidates, unavailable


def _check_targets() -> None:
    settings = get_settings()
    logger.info(
        "Database: %s@%s/%s | storage: %s",
        settings.database_user,
        settings.database_host,
        settings.database_name,
        settings.object_storage_backend,
    )
    if not database_is_ready():
        raise SystemExit(
            f"Cannot reach the database at {settings.database_host}. For a laptop run, set "
            "DATABASE_HOST and the other settings in this same terminal window and allow "
            "your IP in the PostgreSQL firewall (docs/operations.md)."
        )
    try:
        get_object_storage().exists("evaluation/retrieval/latest.json")
    except Exception as error:
        raise SystemExit(
            f"Cannot use {settings.object_storage_backend} storage: {error}. For Azure, run "
            '`pip install -e ".[cloud]"` and set AZURE_STORAGE_CONNECTION_STRING '
            "(docs/operations.md)."
        ) from error
    if settings.database_host in ("localhost", "127.0.0.1") or (
        settings.object_storage_backend != "azure_blob"
    ):
        logger.warning(
            "Writing to a local database or local storage; documents will not reach Azure."
        )


def _cached_mof_listing(
    connector: MofLegalDocumentConnector, options: MofSearchOptions, refresh: bool
) -> list[SourceDocument]:
    """The ministry listing takes about ten minutes; reuse one from the last 24 hours."""

    cache = LISTING_CACHE_DIRECTORY / (
        f"mof-{options.issued_from or 'all'}-"
        f"{'with-expired' if options.include_expired else 'current'}.json"
    )
    if not refresh and cache.is_file() and time.time() - cache.stat().st_mtime < 86_400:
        documents = [
            SourceDocument(
                **{
                    **item,
                    "issue_date": _date_or_none(item["issue_date"]),
                    "effective_date": _date_or_none(item["effective_date"]),
                }
            )
            for item in json.loads(cache.read_text(encoding="utf-8"))
        ]
        logger.info(
            "Ministry of Finance: reusing listing from %s (%d documents; "
            "--refresh-listing to fetch again)",
            time.strftime("%H:%M", time.localtime(cache.stat().st_mtime)),
            len(documents),
        )
        return documents
    documents = connector.list_documents(options)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(
        json.dumps([asdict(document) for document in documents], default=str, ensure_ascii=False),
        encoding="utf-8",
    )
    return documents


def _date_or_none(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _new_documents(session: Session, candidates: list[Candidate]) -> list[Candidate]:
    collected_ids = set(
        session.execute(
            select(SourceRecord.source_name, SourceRecord.source_document_id).join(
                DocumentVersion, DocumentVersion.source_record_id == SourceRecord.id
            )
        ).all()
    )
    known_numbers = set(session.scalars(select(LegalDocument.document_number)).all())
    pending: list[Candidate] = []
    for candidate in candidates:
        document = candidate.document
        if (document.source_name, document.source_document_id) in collected_ids:
            continue
        if document.source_name != MOF_SOURCE and document.document_number in known_numbers:
            continue  # held from the ministry database, whose record is richer
        pending.append(candidate)
        known_numbers.add(document.document_number)
    logger.info(
        "%d new document(s) to collect; %d already in the corpus",
        len(pending),
        len(candidates) - len(pending),
    )
    return pending


def _download(session: Session, batch: list[Candidate]) -> tuple[int, int]:
    storage = get_object_storage()
    collected = failed = 0
    started = time.monotonic()
    for index, candidate in enumerate(batch, start=1):
        document = candidate.document
        try:
            content = candidate.fetch(document)
            result = ingest_source_document(session, storage, document, content)
        except (ConnectorError, OSError, DBAPIError) as error:
            # A dropped database connection or a failed download affects this document only:
            # the transaction is rolled back, the pool reconnects, and the next run retries it.
            session.rollback()
            failed += 1
            logger.warning(
                "[%d/%d] FAILED %s: %s",
                index,
                len(batch),
                document.document_number,
                str(error).strip().splitlines()[0][:200],
            )
            continue
        collected += 1
        elapsed = time.monotonic() - started
        logger.info(
            "[%d/%d] %s | %s | %s %s | %s left",
            index,
            len(batch),
            document.document_number,
            result.status,
            document.content_type.rsplit("/", 1)[-1][:12],
            _size(len(content)),
            _duration(elapsed / index * (len(batch) - index)),
        )
    return collected, failed


def _size(byte_count: int) -> str:
    if byte_count >= 1_000_000:
        return f"{byte_count / 1_000_000:.1f} MB"
    return f"{byte_count // 1000} KB"


def _duration(seconds: float) -> str:
    minutes, seconds = divmod(int(seconds), 60)
    return f"{minutes}m{seconds:02d}s" if minutes else f"{seconds}s"


if __name__ == "__main__":
    main()

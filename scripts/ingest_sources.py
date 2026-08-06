import argparse
import hashlib
from datetime import date

from taxlens.db import SessionLocal
from taxlens.ingestion.connectors import (
    ConnectorError,
    SourceDocument,
    create_official_connector,
)
from taxlens.ingestion.seed import ingest_source_document
from taxlens.storage.factory import get_object_storage


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover or ingest official legal PDFs")
    parser.add_argument("--source", choices=("mof", "government"), required=True)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument(
        "--url",
        help="Explicit official PDF URL; useful for portals with dynamic catalogs",
    )
    parser.add_argument("--document-number", help="Document number required with --url")
    parser.add_argument("--title", help="Document title; defaults to document number")
    parser.add_argument("--issue-date", help="Issue date in ISO format, when known")
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download and persist documents; without this flag, only discover",
    )
    arguments = parser.parse_args()
    if arguments.limit < 1:
        parser.error("--limit must be at least 1")
    if arguments.url and not arguments.document_number:
        parser.error("--document-number is required with --url")
    if arguments.issue_date and not arguments.url:
        parser.error("--issue-date can only be used with --url")

    connector = create_official_connector(arguments.source)
    if arguments.url:
        try:
            issue_date = date.fromisoformat(arguments.issue_date) if arguments.issue_date else None
        except ValueError as error:
            parser.error(f"--issue-date must be ISO formatted: {error}")
        documents = [
            SourceDocument(
                source_name=connector.source_name,
                source_document_id=hashlib.sha256(arguments.url.encode()).hexdigest()[:24],
                document_number=arguments.document_number,
                title=arguments.title or arguments.document_number,
                source_url=arguments.url,
                content_url=arguments.url,
                document_type=arguments.document_number.rsplit("/", 1)[-1],
                issuing_agency="Ministry of Finance" if arguments.source == "mof" else None,
                issue_date=issue_date,
            )
        ]
    else:
        try:
            documents = connector.list_documents()[: arguments.limit]
        except ConnectorError as error:
            parser.exit(1, f"Source discovery failed: {error}\n")
    if not arguments.download:
        for document in documents:
            print(f"{document.document_number}\t{document.title}\t{document.content_url}")
        print(f"Discovered {len(documents)} document(s); nothing downloaded")
        return

    storage = get_object_storage()
    results = []
    with SessionLocal() as session:
        for document in documents:
            try:
                content = connector.fetch_document(document)
                results.append(ingest_source_document(session, storage, document, content))
                print(f"Ingested {document.document_number}: {results[-1].status}")
            except ConnectorError as error:
                print(f"Skipped {document.document_number}: {error}")

    new_documents = sum(result.status == "NEW_DOCUMENT" for result in results)
    unchanged = sum(result.status == "UNCHANGED" for result in results)
    print(f"Source ingestion complete: {new_documents} new, {unchanged} unchanged")


if __name__ == "__main__":
    main()

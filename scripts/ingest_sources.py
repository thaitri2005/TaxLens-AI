import argparse

from taxlens.config import get_settings
from taxlens.db import SessionLocal
from taxlens.ingestion.connectors import ConnectorError, create_official_connector
from taxlens.ingestion.seed import ingest_source_document
from taxlens.storage.local import LocalObjectStorage


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover or ingest official legal PDFs")
    parser.add_argument("--source", choices=("mof", "government"), required=True)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download and persist documents; without this flag, only discover",
    )
    arguments = parser.parse_args()
    if arguments.limit < 1:
        parser.error("--limit must be at least 1")

    connector = create_official_connector(arguments.source)
    try:
        documents = connector.list_documents()[: arguments.limit]
    except ConnectorError as error:
        parser.exit(1, f"Source discovery failed: {error}\n")
    if not arguments.download:
        for document in documents:
            print(f"{document.document_number}\t{document.title}\t{document.content_url}")
        print(f"Discovered {len(documents)} document(s); nothing downloaded")
        return

    storage = LocalObjectStorage(get_settings().local_storage_path)
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

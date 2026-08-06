import argparse
import json
from datetime import date
from pathlib import Path

from taxlens.db import SessionLocal
from taxlens.ingestion.connectors import SourceDocument, create_official_connector
from taxlens.ingestion.seed import ingest_source_document
from taxlens.storage.factory import get_object_storage


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest a curated official document manifest")
    parser.add_argument("--manifest", type=Path, default=Path("data/corpus/tax_documents.json"))
    parser.add_argument("--download", action="store_true")
    arguments = parser.parse_args()
    entries = json.loads(arguments.manifest.read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        parser.error("Manifest must contain a JSON list")

    if not arguments.download:
        for entry in entries:
            print(f"{entry['document_number']}\t{entry['title']}\t{entry['content_url']}")
        print(f"Manifest contains {len(entries)} document(s); nothing downloaded")
        return

    storage = get_object_storage()
    results = []
    with SessionLocal() as session:
        for entry in entries:
            connector = create_official_connector(entry["source"])
            document = SourceDocument(
                source_name=connector.source_name,
                source_document_id=entry["document_number"],
                document_number=entry["document_number"],
                title=entry["title"],
                source_url=entry["source_url"],
                content_url=entry["content_url"],
                document_type=entry["document_number"].rsplit("/", 1)[-1],
                issuing_agency=(
                    "Ministry of Finance" if entry["source"] == "mof" else "Government of Vietnam"
                ),
                issue_date=date.fromisoformat(entry["issue_date"])
                if entry.get("issue_date")
                else None,
            )
            content = connector.fetch_document(document)
            result = ingest_source_document(session, storage, document, content)
            results.append(result)
            print(f"Ingested {document.document_number}: {result.status}")

    new_documents = sum(result.status == "NEW_DOCUMENT" for result in results)
    unchanged = sum(result.status == "UNCHANGED" for result in results)
    print(f"Manifest ingestion complete: {new_documents} new, {unchanged} unchanged")


if __name__ == "__main__":
    main()

import argparse
import json
from pathlib import Path

from sqlalchemy import select

from taxlens.db import SessionLocal
from taxlens.legal_data.models import DocumentVersion, LegalDocument, SourceRecord


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair metadata for curated official documents")
    parser.add_argument("--manifest", type=Path, default=Path("data/corpus/tax_documents.json"))
    arguments = parser.parse_args()
    entries = json.loads(arguments.manifest.read_text(encoding="utf-8"))

    updated = 0
    missing = 0
    with SessionLocal() as session:
        for entry in entries:
            document = session.scalar(
                select(LegalDocument).where(
                    LegalDocument.document_number == entry["document_number"]
                )
            )
            if document is None:
                missing += 1
                continue

            document.title = entry["title"]
            document.issuing_agency = "Ministry of Finance"
            versions = session.scalars(
                select(DocumentVersion).where(DocumentVersion.document_id == document.id)
            ).all()
            for version in versions:
                version.issue_date = entry.get("issue_date")
                source = session.get(SourceRecord, version.source_record_id)
                if source is not None:
                    source.source_url = entry["source_url"]
                    source.source_name = "government-portal"
            updated += 1

        session.commit()

    print(f"Metadata repair complete: {updated} updated, {missing} missing")


if __name__ == "__main__":
    main()

import argparse
import json
from datetime import date
from pathlib import Path

from sqlalchemy import select

from taxlens.db import SessionLocal
from taxlens.ingestion.connectors import OFFICIAL_SOURCE_CATALOGS
from taxlens.legal_data.document_numbers import issuing_agency_for
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

            source_config = OFFICIAL_SOURCE_CATALOGS[entry["source"]]
            document.title = entry["title"]
            # The issuer comes from the document number (NĐ-CP is a Government decree,
            # TT-BTC a Ministry of Finance circular), not from the portal it was found on.
            document.issuing_agency = issuing_agency_for(entry["document_number"]) or (
                "Ministry of Finance" if entry["source"] == "mof" else "Government of Vietnam"
            )
            issue_date = (
                date.fromisoformat(entry["issue_date"]) if entry.get("issue_date") else None
            )
            versions = session.scalars(
                select(DocumentVersion).where(DocumentVersion.document_id == document.id)
            ).all()
            for version in versions:
                version.issue_date = issue_date
                source = session.get(SourceRecord, version.source_record_id)
                if source is not None:
                    source.source_url = entry["source_url"]
                    source.source_name = source_config["source_name"]
            updated += 1

        session.commit()

    print(f"Metadata repair complete: {updated} updated, {missing} missing")


if __name__ == "__main__":
    main()

from datetime import date
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from taxlens.ingestion.seed import SeedDocument, ingest_seed_document
from taxlens.legal_data.models import DocumentVersion, LegalDocument, ProcessingJob, SourceRecord
from taxlens.storage.local import LocalObjectStorage


def test_seed_ingestion_is_idempotent(tmp_path: Path) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    LegalDocument.metadata.create_all(engine)
    storage = LocalObjectStorage(tmp_path / "storage")
    document = SeedDocument(
        source_name="seed-corpus",
        source_url="https://example.invalid/document",
        source_document_id="document-1",
        document_number="01/2025/TT-BTC",
        title="Sample document",
        document_type="CIRCULAR",
        issuing_agency="Ministry of Finance",
        issue_date=date(2025, 1, 1),
        effective_date=date(2025, 2, 1),
        legal_status="EFFECTIVE",
        content=b"Article 1. Sample legal content.",
    )

    with Session(engine) as session:
        first_result = ingest_seed_document(session, storage, document)
        second_result = ingest_seed_document(session, storage, document)

        assert first_result.status == "NEW_DOCUMENT"
        assert second_result.status == "UNCHANGED"
        assert session.scalar(select(func.count()).select_from(SourceRecord)) == 1
        assert session.scalar(select(func.count()).select_from(LegalDocument)) == 1
        assert session.scalar(select(func.count()).select_from(DocumentVersion)) == 1
        assert session.scalar(select(func.count()).select_from(ProcessingJob)) == 1
        assert storage.exists(
            "raw-documents/source=seed-corpus/year=2025/"
            f"document=01-2025-tt-btc/{first_result.raw_content_hash}.txt"
        )

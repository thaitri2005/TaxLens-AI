from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from taxlens.api.main import create_app
from taxlens.db import get_db_session
from taxlens.legal_data.models import (
    DocumentVersion,
    LegalDocument,
    ProcessingJob,
    SourceRecord,
)


def test_document_endpoints_return_persisted_documents() -> None:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    LegalDocument.metadata.create_all(engine)
    with Session(engine) as session:
        document = LegalDocument(
            document_number="01/2025/TT-BTC",
            title="Sample document",
            document_type="CIRCULAR",
            issuing_agency="Ministry of Finance",
        )
        session.add(document)
        session.flush()
        source_record = SourceRecord(
            source_name="government-portal",
            source_url="https://example.test/01-2025.pdf",
            source_document_id="01-2025",
        )
        session.add(source_record)
        session.flush()
        version = DocumentVersion(
            document_id=document.id,
            source_record_id=source_record.id,
            issue_date=date(2025, 1, 1),
            effective_date=date(2025, 2, 1),
            legal_status="EFFECTIVE",
            raw_content_hash="a" * 64,
            raw_artifact_key="raw/doc.txt",
        )
        session.add(version)
        session.flush()
        session.add(
            ProcessingJob(
                document_version_id=version.id,
                status="COMPLETED",
                stage="EMBEDDING",
                attempt_count=1,
            )
        )
        session.commit()
        document_id = document.id

    app = create_app()

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    client = TestClient(app)

    list_response = client.get("/documents")
    detail_response = client.get(f"/documents/{document_id}")

    assert list_response.status_code == 200
    assert list_response.json()[0]["document_number"] == "01/2025/TT-BTC"
    assert list_response.json()[0]["source_name"] == "government-portal"
    assert detail_response.status_code == 200
    assert detail_response.json()["versions"][0]["legal_status"] == "EFFECTIVE"
    assert detail_response.json()["source_name"] == "government-portal"
    assert detail_response.json()["versions"][0]["processing_status"] == "COMPLETED"
    assert detail_response.json()["versions"][0]["chunk_count"] == 0
    assert detail_response.json()["versions"][0]["source_url"] == "https://example.test/01-2025.pdf"

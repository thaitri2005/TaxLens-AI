from datetime import UTC, date, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from taxlens.api.auth import AuthenticatedUser, require_authenticated_user
from taxlens.api.main import create_app
from taxlens.db import get_db_session
from taxlens.legal_data.document_kinds import document_kind
from taxlens.legal_data.models import (
    DocumentChunk,
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
    app.dependency_overrides[require_authenticated_user] = lambda: AuthenticatedUser(
        id=uuid4(), username="test-user", role="user"
    )
    client = TestClient(app)

    list_response = client.get("/documents")
    detail_response = client.get(f"/documents/{document_id}")

    assert list_response.status_code == 200
    page = list_response.json()
    assert page["total"] == 1
    assert page["items"][0]["document_number"] == "01/2025/TT-BTC"
    assert page["items"][0]["source_name"] == "government-portal"
    assert page["items"][0]["legal_status"] == "EFFECTIVE"
    assert page["items"][0]["issue_date"] == "2025-01-01"
    assert detail_response.status_code == 200
    assert detail_response.json()["versions"][0]["legal_status"] == "EFFECTIVE"
    assert detail_response.json()["source_name"] == "government-portal"
    assert detail_response.json()["versions"][0]["processing_status"] == "COMPLETED"
    assert detail_response.json()["versions"][0]["chunk_count"] == 0
    assert detail_response.json()["versions"][0]["source_url"] == "https://example.test/01-2025.pdf"

    overview = client.get("/documents/overview").json()
    other_source = client.get("/documents", params={"source_name": "mof-vbpq"}).json()
    by_number = client.get("/documents", params={"q": "01/2025"}).json()
    by_title = client.get("/documents", params={"q": "sample", "legal_status": "EFFECTIVE"})
    no_match = client.get("/documents", params={"q": "100%"}).json()
    paged = client.get("/documents", params={"limit": 1, "offset": 1}).json()

    assert overview == {
        "total_documents": 1,
        "searchable_documents": 0,
        "passages": 0,
        "embedded_passages": 0,
        "failed_versions": 0,
        "by_status": [{"value": "EFFECTIVE", "count": 1}],
        "by_source": [{"value": "government-portal", "count": 1}],
        "by_kind": [{"value": "circular", "count": 1}],
    }
    assert client.get("/documents", params={"kind": "circular"}).json()["total"] == 1
    assert client.get("/documents", params={"kind": "decree"}).json()["total"] == 0
    assert page["items"][0]["kind"] == "circular"
    assert other_source == {"total": 0, "items": []}
    assert by_number["total"] == 1
    assert by_title.json()["total"] == 1
    assert no_match["total"] == 0
    assert paged == {"total": 1, "items": []}

    with Session(engine) as session:
        version_id = session.scalars(select(DocumentVersion.id)).one()
        session.add(
            ProcessingJob(
                document_version_id=version_id,
                status="FAILED",
                stage="EXTRACTION",
                attempt_count=2,
                updated_at=datetime(2030, 1, 1, tzinfo=UTC),
            )
        )
        session.add(
            DocumentChunk(
                document_version_id=version_id, content="Điều 1", token_count=2, article_number="1"
            )
        )
        session.commit()

    overview = client.get("/documents/overview").json()
    chunks = client.get(f"/documents/{document_id}/chunks", params={"limit": 1}).json()

    assert overview["failed_versions"] == 1
    assert overview["searchable_documents"] == 1
    assert overview["passages"] == 1
    assert [chunk["content"] for chunk in chunks] == ["Điều 1"]


def test_recorded_document_types_are_grouped_into_kinds() -> None:
    assert [
        document_kind(value)
        for value in (
            "TT-BTC",
            "Thông tư",
            "CIRCULAR",
            "TTLT-BTC-BKHĐT",
            "Thông tư liên tịch",
            "NĐ-CP",
            "Nghị định",
            "NQ-UBTVQH14",
            "QH14",
            "Luật",
            "QĐ-TTG",
            "VBHN-BTC",
            "Văn bản",
        )
    ] == [
        "circular",
        "circular",
        "circular",
        "joint_circular",
        "joint_circular",
        "decree",
        "decree",
        "resolution",
        "law",
        "law",
        "decision",
        "consolidated",
        "other",
    ]

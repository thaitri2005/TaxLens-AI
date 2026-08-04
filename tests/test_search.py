from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from taxlens.api.main import create_app
from taxlens.db import get_db_session
from taxlens.legal_data.models import (
    DocumentChunk,
    DocumentVersion,
    LegalDocument,
    SourceRecord,
)
from taxlens.retrieval.citations import build_citation
from taxlens.retrieval.reranking import NoOpReranker
from taxlens.retrieval.search import SearchFilters, search_chunks


def test_search_returns_matching_article_chunk_with_filters() -> None:
    engine = _create_engine_with_search_data()
    with Session(engine) as session:
        results = search_chunks(
            session,
            "VAT",
            SearchFilters(legal_status="EFFECTIVE", effective_from=date(2025, 1, 1)),
        )

    assert len(results) == 1
    assert results[0].document.document_number == "31/2025/TT-BTC"
    assert results[0].chunk.article_number == "1"
    assert results[0].score == 1.0


def test_search_api_returns_citation_ready_results() -> None:
    engine = _create_engine_with_search_data()
    app = create_app()

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    client = TestClient(app)

    response = client.get("/search", params={"q": "invoice", "legal_status": "EFFECTIVE"})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["citation"]["document_number"] == "31/2025/TT-BTC"
    assert payload[0]["citation"]["version_label"] == "2025"
    assert payload[0]["citation"]["effective_date"] == "2025-07-01"
    assert payload[0]["citation"]["article_number"] == "1"
    assert payload[0]["citation"]["heading"] == "Electronic invoices"
    assert payload[0]["citation"]["source_artifact_key"] == "raw/31-2025.txt"
    assert payload[0]["snippet"] == payload[0]["content"]


def test_search_api_filters_by_official_source() -> None:
    engine = _create_engine_with_search_data()
    app = create_app()

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    client = TestClient(app)

    response = client.get("/search", params={"q": "invoice", "source_name": "mof-vbpq"})

    assert response.status_code == 200
    assert response.json()[0]["citation"]["document_number"] == "31/2025/TT-BTC"


def test_citation_builder_uses_stored_provenance_and_noop_reranker_preserves_order() -> None:
    engine = _create_engine_with_search_data()
    with Session(engine) as session:
        results = search_chunks(session, "VAT", SearchFilters(legal_status="EFFECTIVE"))

    citation = build_citation(results[0])
    reranked = NoOpReranker().rerank("VAT", results, limit=1)

    assert citation.document_number == "31/2025/TT-BTC"
    assert citation.version_label == "2025"
    assert citation.legal_status == "EFFECTIVE"
    assert citation.article_number == "1"
    assert citation.page_start == 1
    assert citation.source_artifact_key == "raw/31-2025.txt"
    assert reranked.provider_name == "none"
    assert reranked.results == results[:1]


def _create_engine_with_search_data():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    LegalDocument.metadata.create_all(engine)
    with Session(engine) as session:
        effective_document = LegalDocument(
            document_number="31/2025/TT-BTC",
            title="Electronic invoice VAT guidance",
            document_type="CIRCULAR",
            issuing_agency="Ministry of Finance",
        )
        superseded_document = LegalDocument(
            document_number="02/2024/TT-BTC",
            title="Legacy VAT guidance",
            document_type="CIRCULAR",
            issuing_agency="Ministry of Finance",
        )
        session.add_all([effective_document, superseded_document])
        session.flush()
        source_record = SourceRecord(
            source_name="mof-vbpq",
            source_url="https://example.test/31-2025.pdf",
            source_document_id="31-2025",
        )
        session.add(source_record)
        session.flush()
        effective_version = DocumentVersion(
            document_id=effective_document.id,
            source_record_id=source_record.id,
            version_label="2025",
            issue_date=date(2025, 6, 1),
            effective_date=date(2025, 7, 1),
            legal_status="EFFECTIVE",
            raw_content_hash="a" * 64,
            raw_artifact_key="raw/31-2025.txt",
        )
        superseded_version = DocumentVersion(
            document_id=superseded_document.id,
            issue_date=date(2024, 1, 1),
            effective_date=date(2024, 2, 1),
            legal_status="SUPERSEDED",
            raw_content_hash="b" * 64,
            raw_artifact_key="raw/02-2024.txt",
        )
        session.add_all([effective_version, superseded_version])
        session.flush()
        session.add_all(
            [
                DocumentChunk(
                    document_version_id=effective_version.id,
                    article_number="1",
                    heading="Electronic invoices",
                    page_start=1,
                    page_end=1,
                    content="VAT invoice requirements for taxpayers.",
                    token_count=5,
                ),
                DocumentChunk(
                    document_version_id=superseded_version.id,
                    article_number="1",
                    heading="Legacy VAT",
                    page_start=1,
                    page_end=1,
                    content="Superseded VAT requirements.",
                    token_count=3,
                ),
            ]
        )
        session.commit()
    return engine

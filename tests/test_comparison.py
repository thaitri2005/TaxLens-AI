from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from taxlens.intelligence.chat import ChatRequest, ChatResponse
from taxlens.intelligence.comparison import ComparisonError, compare_documents
from taxlens.legal_data.models import DocumentChunk, DocumentVersion, LegalDocument


def test_compare_documents_classifies_article_changes() -> None:
    engine = _create_comparison_data()

    with Session(engine) as session:
        comparison = compare_documents(session, "02/2024/TT-BTC", "31/2025/TT-BTC")

    changes = {change.key: change for change in comparison.changes}
    assert {change.change_type for change in changes.values()} == {
        "ADDED",
        "REMOVED",
        "MODIFIED",
        "UNCHANGED",
    }
    assert changes["article:1|clause:unknown"].change_type == "MODIFIED"
    assert changes["article:2|clause:unknown"].change_type == "REMOVED"
    assert changes["article:3|clause:unknown"].change_type == "ADDED"
    assert changes["article:4|clause:unknown"].change_type == "UNCHANGED"
    assert changes["article:1|clause:unknown"].before_citation is not None
    assert changes["article:1|clause:unknown"].after_citation is not None


def test_compare_documents_rejects_missing_or_identical_documents() -> None:
    engine = _create_comparison_data()

    with Session(engine) as session:
        with pytest.raises(ComparisonError, match="two different"):
            compare_documents(session, "02/2024/TT-BTC", "02/2024/TT-BTC")
        with pytest.raises(ComparisonError, match="not found"):
            compare_documents(session, "missing", "31/2025/TT-BTC")


def test_summarize_comparison_validates_referenced_change_keys() -> None:
    from taxlens.intelligence.comparison import summarize_comparison

    engine = _create_comparison_data()
    provider = FakeSummaryProvider()
    with Session(engine) as session:
        comparison = compare_documents(session, "02/2024/TT-BTC", "31/2025/TT-BTC")
        summary = summarize_comparison(comparison, provider)

    assert summary.summary == "The scope changed."
    assert summary.practical_impact == "Review the new scope."
    assert summary.referenced_change_keys == ("article:1|clause:unknown",)
    assert provider.requests


class FakeSummaryProvider:
    requests: list[ChatRequest]

    def __init__(self) -> None:
        self.requests = []

    def complete(self, request: ChatRequest) -> ChatResponse:
        self.requests.append(request)
        return ChatResponse(
            content=(
                '{"summary":"The scope changed.",'
                '"practical_impact":"Review the new scope.",'
                '"uncertainties":[],'
                '"referenced_change_keys":["article:1|clause:unknown"]}'
            ),
            requested_model="test-model",
            provider_name="test-provider",
            input_tokens=10,
            output_tokens=10,
        )


def _create_comparison_data():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    LegalDocument.metadata.create_all(engine)
    with Session(engine) as session:
        before_document = LegalDocument(
            document_number="02/2024/TT-BTC",
            title="Before guidance",
            document_type="CIRCULAR",
        )
        after_document = LegalDocument(
            document_number="31/2025/TT-BTC",
            title="After guidance",
            document_type="CIRCULAR",
        )
        session.add_all([before_document, after_document])
        session.flush()
        before_version = DocumentVersion(
            document_id=before_document.id,
            effective_date=date(2024, 1, 1),
            legal_status="SUPERSEDED",
            raw_content_hash="a" * 64,
            raw_artifact_key="raw/before.txt",
        )
        after_version = DocumentVersion(
            document_id=after_document.id,
            effective_date=date(2025, 1, 1),
            legal_status="EFFECTIVE",
            raw_content_hash="b" * 64,
            raw_artifact_key="raw/after.txt",
        )
        session.add_all([before_version, after_version])
        session.flush()
        session.add_all(
            [
                _chunk(before_version, "1", "Old scope"),
                _chunk(before_version, "2", "Removed rule"),
                _chunk(before_version, "4", "Same rule"),
                _chunk(after_version, "1", "New scope"),
                _chunk(after_version, "3", "Added rule"),
                _chunk(after_version, "4", "Same rule"),
            ]
        )
        session.commit()
    return engine


def _chunk(version: DocumentVersion, article_number: str, content: str) -> DocumentChunk:
    return DocumentChunk(
        document_version_id=version.id,
        article_number=article_number,
        page_start=1,
        page_end=1,
        content=content,
        token_count=2,
    )

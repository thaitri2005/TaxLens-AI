import uuid

from taxlens.intelligence.evidence import EvidenceStatus, assess_evidence
from taxlens.intelligence.planning import QueryIntent, plan_query
from taxlens.legal_data.models import DocumentChunk, DocumentVersion, LegalDocument
from taxlens.retrieval.search import SearchResult


def test_query_planner_classifies_document_and_comparison_queries() -> None:
    document_plan = plan_query("Nội dung của 31/2025/TT-BTC là gì?")
    comparison_plan = plan_query("So sánh 31/2025/TT-BTC và 02/2024/TT-BTC")

    assert document_plan.intent is QueryIntent.DOCUMENT_LOOKUP
    assert document_plan.filters.document_number == "31/2025/TT-BTC"
    assert comparison_plan.intent is QueryIntent.DOCUMENT_COMPARISON
    assert comparison_plan.document_numbers == ("31/2025/TT-BTC", "02/2024/TT-BTC")


def test_query_planner_marks_greetings_as_unsupported() -> None:
    assert plan_query("chào bạn").intent is QueryIntent.UNSUPPORTED


def test_evidence_assessment_requires_evidence_consistent_status_and_locator() -> None:
    document_id = uuid.uuid4()
    effective_result = _result(
        legal_status="EFFECTIVE", article_number="1", document_id=document_id
    )
    superseded_result = _result(
        legal_status="SUPERSEDED", article_number="1", document_id=document_id
    )
    unlocated_result = _result(legal_status="EFFECTIVE", article_number=None)

    assert assess_evidence([]).status is EvidenceStatus.NO_EVIDENCE
    assert (
        assess_evidence([effective_result, superseded_result]).status
        is EvidenceStatus.CONFLICTING_VERSIONS
    )
    assert (
        assess_evidence([unlocated_result]).status is EvidenceStatus.INSUFFICIENT_STRUCTURAL_SUPPORT
    )
    assert assess_evidence([effective_result]).status is EvidenceStatus.SUFFICIENT


def _result(
    legal_status: str,
    article_number: str | None,
    document_id: uuid.UUID | None = None,
) -> SearchResult:
    document = LegalDocument(
        id=document_id or uuid.uuid4(),
        document_number="31/2025/TT-BTC",
        title="Invoice guidance",
        document_type="CIRCULAR",
        issuing_agency="Ministry of Finance",
    )
    version = DocumentVersion(
        id=uuid.uuid4(),
        document_id=document.id,
        legal_status=legal_status,
        raw_content_hash=str(uuid.uuid4()).replace("-", "") * 2,
        raw_artifact_key="raw/invoice.txt",
    )
    chunk = DocumentChunk(
        id=uuid.uuid4(),
        document_version_id=version.id,
        article_number=article_number,
        content="Invoice requirements.",
        token_count=2,
    )
    return SearchResult(chunk=chunk, version=version, document=document)

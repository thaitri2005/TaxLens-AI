import uuid

from taxlens.intelligence.evidence import EvidenceStatus, assess_evidence
from taxlens.intelligence.planning import QueryIntent, plan_query
from taxlens.legal_data.models import DocumentChunk, DocumentVersion, LegalDocument
from taxlens.retrieval.search import SearchResult


def test_query_planner_classifies_document_queries_and_filters_single_documents() -> None:
    document_plan = plan_query("Nội dung của 31/2025/TT-BTC là gì?")
    multi_document_plan = plan_query("31/2025/TT-BTC và 02/2024/TT-BTC quy định gì?")

    assert document_plan.intent is QueryIntent.DOCUMENT_LOOKUP
    assert document_plan.filters.document_number == "31/2025/TT-BTC"
    assert multi_document_plan.document_numbers == ("31/2025/TT-BTC", "02/2024/TT-BTC")
    assert multi_document_plan.filters.document_number is None


def test_query_planner_recognizes_laws_and_consolidated_documents() -> None:
    assert plan_query("Luật 48/2024/QH15 quy định gì?").document_numbers == ("48/2024/QH15",)
    assert plan_query("Văn bản 18/VBHN-BTC").document_numbers == ("18/VBHN-BTC",)
    assert plan_query("hạn nộp ngày 31/12/2025").document_numbers == ()


def test_query_planner_does_not_treat_corporate_income_tax_as_impact_analysis() -> None:
    plan = plan_query("Thuế suất thuế thu nhập doanh nghiệp là bao nhiêu?")

    assert plan.intent is QueryIntent.REGULATORY_QUESTION


def test_query_planner_marks_greetings_as_unsupported() -> None:
    assert plan_query("chào bạn").intent is QueryIntent.UNSUPPORTED


def test_evidence_assessment_requires_evidence_and_locator() -> None:
    unlocated_result = _result(legal_status="EFFECTIVE", article_number=None)
    effective_result = _result(legal_status="EFFECTIVE", article_number="1")

    assert assess_evidence([]).status is EvidenceStatus.NO_EVIDENCE
    assert (
        assess_evidence([unlocated_result]).status is EvidenceStatus.INSUFFICIENT_STRUCTURAL_SUPPORT
    )
    mixed = assess_evidence([unlocated_result, effective_result])
    assert mixed.status is EvidenceStatus.SUFFICIENT
    assert mixed.results == (effective_result,)
    assert mixed.notes


def test_evidence_assessment_prefers_current_provisions_over_superseded_ones() -> None:
    document_id = uuid.uuid4()
    effective = _result(legal_status="EFFECTIVE", article_number="1", document_id=document_id)
    superseded = _result(legal_status="SUPERSEDED", article_number="1", document_id=document_id)

    assessment = assess_evidence([superseded, effective])

    assert assessment.status is EvidenceStatus.SUFFICIENT
    assert assessment.results == (effective,)
    assert assess_evidence([superseded]).status is EvidenceStatus.INACTIVE_ONLY


def test_evidence_assessment_allows_unverified_statuses_across_documents() -> None:
    discovered = _result(legal_status="DISCOVERED", article_number="2")
    effective = _result(legal_status="EFFECTIVE", article_number="1")

    assessment = assess_evidence([discovered, effective])

    assert assessment.status is EvidenceStatus.SUFFICIENT
    assert len(assessment.results) == 2


def test_evidence_assessment_flags_conflicting_known_statuses_within_a_document() -> None:
    document_id = uuid.uuid4()
    effective = _result(legal_status="EFFECTIVE", article_number="1", document_id=document_id)
    pending = _result(legal_status="NOT_YET_EFFECTIVE", article_number="1", document_id=document_id)

    assert assess_evidence([effective, pending]).status is EvidenceStatus.CONFLICTING_VERSIONS


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

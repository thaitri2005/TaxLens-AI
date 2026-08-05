from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from taxlens.intelligence.chat import ChatRequest, ChatResponse
from taxlens.intelligence.qa import AnswerStatus, answer_question, parse_generated_answer
from taxlens.legal_data.models import DocumentChunk, DocumentVersion, LegalDocument


class FakeChatProvider:
    def __init__(self, content: str) -> None:
        self.content = content
        self.requests: list[ChatRequest] = []

    def complete(self, request: ChatRequest) -> ChatResponse:
        self.requests.append(request)
        return ChatResponse(
            content=self.content,
            requested_model="test-model",
            provider_name="test-provider",
            input_tokens=10,
            output_tokens=10,
        )


def test_answer_question_returns_validated_cited_answer() -> None:
    engine = _create_engine_with_evidence()
    provider = FakeChatProvider(
        '{"answer":"Hóa đơn phải đáp ứng yêu cầu được nêu.",'
        '"confirmed_facts":[{"text":"Hướng dẫn áp dụng cho hóa đơn VAT.",'
        '"citation_numbers":[1]}],"interpretation":null,'
        '"uncertainties":[],"review_actions":["Review Article 1."]}'
    )

    with Session(engine) as session:
        answer = answer_question(session, "VAT", provider)

    assert answer.status is AnswerStatus.ANSWERED
    assert answer.answer is not None
    assert answer.confirmed_facts[0].citation_numbers == (1,)
    assert len(answer.citations) == 1
    assert len(provider.requests) == 1


def test_answer_question_does_not_call_model_without_evidence() -> None:
    engine = _create_engine_with_evidence()
    provider = FakeChatProvider("{}")

    with Session(engine) as session:
        answer = answer_question(session, "Quy định về thuế tài sản số là gì?", provider)

    assert answer.status is AnswerStatus.INSUFFICIENT_EVIDENCE
    assert answer.citations == []
    assert provider.requests == []


def test_parse_generated_answer_rejects_claim_without_valid_citation() -> None:
    content = (
        '{"answer":"Kết luận", "confirmed_facts":['
        '{"text":"Sự kiện", "citation_numbers":[2]}],'
        '"interpretation":null,"uncertainties":[],"review_actions":[]}'
    )

    try:
        parse_generated_answer(content, citation_count=1)
    except ValueError as error:
        assert "citation" in str(error)
    else:
        raise AssertionError("Expected invalid citation numbers to be rejected")


def test_parse_generated_answer_links_plain_fact_strings_to_retrieved_citations() -> None:
    content = (
        '{"answer":"Kết luận", "confirmed_facts":["Sự kiện"],'
        '"interpretation":null,"uncertainties":[],"review_actions":[]}'
    )

    answer = parse_generated_answer(content, citation_count=2)

    assert answer.confirmed_facts[0].citation_numbers == (1, 2)


def test_parse_generated_answer_normalizes_numeric_citation_strings() -> None:
    content = (
        '{"answer":"Kết luận", "confirmed_facts":['
        '{"text":"Sự kiện", "citation_numbers":["2"]}],'
        '"interpretation":null,"uncertainties":[],"review_actions":[]}'
    )

    answer = parse_generated_answer(content, citation_count=2)

    assert answer.confirmed_facts[0].citation_numbers == (2,)


def test_parse_generated_answer_accepts_reasoning_and_markdown_wrappers() -> None:
    content = (
        "<think>Checking the evidence...</think>\n```json\n"
        '{"answer":"Kết luận", "confirmed_facts":[{"text":"Sự kiện",'
        '"citation_numbers":[1]}],"interpretation":null,"uncertainties":[],'
        '"review_actions":[]}\n```'
    )

    answer = parse_generated_answer(content, citation_count=1)

    assert answer.answer == "Kết luận"
    assert answer.confirmed_facts[0].citation_numbers == (1,)


def test_answer_question_returns_evidence_fallback_for_unparseable_model_output() -> None:
    engine = _create_engine_with_evidence()
    provider = FakeChatProvider("This is an unstructured response.")

    with Session(engine) as session:
        answer = answer_question(session, "VAT", provider)

    assert answer.status is AnswerStatus.ANSWERED
    assert answer.answer is not None
    assert answer.confirmed_facts[0].citation_numbers == (1,)
    assert answer.citations


def test_answer_question_recovers_complete_answer_from_truncated_json() -> None:
    engine = _create_engine_with_evidence()
    provider = FakeChatProvider('{"answer":"Có thông tin mới về hóa đơn điện tử.')

    with Session(engine) as session:
        answer = answer_question(session, "VAT", provider)

    assert answer.status is AnswerStatus.ANSWERED
    assert answer.answer == "Có thông tin mới về hóa đơn điện tử."
    assert answer.confirmed_facts[0].citation_numbers == (1,)


def test_parse_generated_answer_rejects_truncated_json() -> None:
    try:
        parse_generated_answer('{"answer":"Incomplete', citation_count=1)
    except ValueError as error:
        assert "JSON" in str(error)
    else:
        raise AssertionError("Expected truncated JSON to be rejected")


def _create_engine_with_evidence():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    LegalDocument.metadata.create_all(engine)
    with Session(engine) as session:
        document = LegalDocument(
            document_number="31/2025/TT-BTC",
            title="Electronic invoice VAT guidance",
            document_type="CIRCULAR",
            issuing_agency="Ministry of Finance",
        )
        session.add(document)
        session.flush()
        version = DocumentVersion(
            document_id=document.id,
            version_label="2025",
            issue_date=date(2025, 6, 1),
            effective_date=date(2025, 7, 1),
            legal_status="EFFECTIVE",
            raw_content_hash="c" * 64,
            raw_artifact_key="raw/31-2025.txt",
        )
        session.add(version)
        session.flush()
        session.add(
            DocumentChunk(
                document_version_id=version.id,
                article_number="1",
                page_start=1,
                page_end=1,
                heading="Electronic invoices",
                content="VAT invoice requirements for taxpayers.",
                token_count=5,
            )
        )
        session.commit()
    return engine

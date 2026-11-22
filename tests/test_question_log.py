import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from taxlens.api.auth import AuthenticatedUser, require_authenticated_user
from taxlens.api.main import create_app
from taxlens.api.routes import questions
from taxlens.db import get_db_session
from taxlens.intelligence.chat import ChatRequest, ChatResponse
from taxlens.legal_data.models import DocumentChunk, DocumentVersion, LegalDocument, QuestionLog

ANSWER = (
    '{"answerable":true,"answer":"Hóa đơn phải đáp ứng yêu cầu.","confirmed_facts":'
    '[{"text":"VAT invoice requirements apply to taxpayers.","citation_numbers":[1]}],'
    '"uncertainties":[],"review_actions":[]}'
)


class FakeChatProvider:
    def complete(self, request: ChatRequest) -> ChatResponse:
        return ChatResponse(
            content=ANSWER,
            requested_model="test-model",
            provider_name="test",
            input_tokens=1,
            output_tokens=1,
        )


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    LegalDocument.metadata.create_all(engine)
    with Session(engine) as session:
        document = LegalDocument(
            document_number="31/2025/TT-BTC", title="Invoices", document_type="CIRCULAR"
        )
        session.add(document)
        session.flush()
        version = DocumentVersion(
            document_id=document.id,
            issue_date=date(2025, 6, 1),
            legal_status="EFFECTIVE",
            raw_content_hash="d" * 64,
            raw_artifact_key="raw/31-2025.txt",
        )
        session.add(version)
        session.flush()
        session.add(
            DocumentChunk(
                document_version_id=version.id,
                article_number="1",
                content="VAT invoice requirements for taxpayers.",
                token_count=5,
            )
        )
        session.commit()
    return engine


def _client(engine, monkeypatch, user_id: uuid.UUID) -> TestClient:
    app = create_app()

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[require_authenticated_user] = lambda: AuthenticatedUser(
        id=user_id, username="asker", role="user"
    )
    monkeypatch.setattr(questions, "get_chat_provider", FakeChatProvider)
    return TestClient(app)


def test_a_question_is_logged_and_its_asker_can_rate_it(engine, monkeypatch) -> None:
    asker = uuid.uuid4()
    client = _client(engine, monkeypatch, asker)

    answered = client.post("/questions", json={"question": "VAT"}).json()
    rated = client.post(
        f"/questions/{answered['question_id']}/feedback",
        json={"rating": "down", "comment": " Missing the 2026 rate. "},
    )

    assert answered["status"] == "ANSWERED"
    assert rated.status_code == 204
    with Session(engine) as session:
        entry = session.scalars(select(QuestionLog)).one()
    assert (entry.user_id, entry.question, entry.status) == (asker, "VAT", "ANSWERED")
    assert entry.cited_documents == ["31/2025/TT-BTC"]
    assert (entry.rating, entry.comment) == (-1, "Missing the 2026 rate.")
    assert entry.rated_at is not None


def test_only_the_asker_can_rate_an_answer(engine, monkeypatch) -> None:
    answered = _client(engine, monkeypatch, uuid.uuid4()).post(
        "/questions", json={"question": "VAT"}
    )
    question_id = answered.json()["question_id"]

    other = _client(engine, monkeypatch, uuid.uuid4())
    response = other.post(f"/questions/{question_id}/feedback", json={"rating": "up"})

    assert response.status_code == 404
    with Session(engine) as session:
        assert session.scalars(select(QuestionLog.rating)).one() is None


def test_a_failed_log_still_returns_the_answer(engine, monkeypatch) -> None:
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE question_logs"))

    response = _client(engine, monkeypatch, uuid.uuid4()).post(
        "/questions", json={"question": "VAT"}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ANSWERED"
    assert response.json()["question_id"] is None


def test_spreadsheet_cells_never_start_like_a_formula() -> None:
    from taxlens.spreadsheets import spreadsheet_safe

    assert spreadsheet_safe('=HYPERLINK("http://x")') == '\'=HYPERLINK("http://x")'
    assert spreadsheet_safe("-1+2") == "'-1+2"
    assert spreadsheet_safe("@SUM(A1)") == "'@SUM(A1)"
    assert spreadsheet_safe("Thuế suất 10%") == "Thuế suất 10%"
    assert spreadsheet_safe(None) == ""
    assert spreadsheet_safe(3.5) == 3.5

import importlib.util
import re
import uuid
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy.dialects import postgresql

from taxlens.document_processing.process import (
    MAX_CHUNK_CHARACTERS,
    build_article_chunks,
    find_article_headings,
    header_document_number,
)
from taxlens.intelligence.evidence import EvidenceStatus, assess_evidence
from taxlens.legal_data.document_numbers import find_document_numbers, issuing_agency_for
from taxlens.legal_data.models import DocumentChunk, DocumentVersion, LegalDocument
from taxlens.retrieval.search import (
    SearchFilters,
    SearchResult,
    _postgresql_keyword_statement,
    asks_for_form,
    is_form_passage,
    keyword_terms,
    semantic_search_chunks,
)
from taxlens.retrieval.snippets import build_excerpt, lexical_support
from taxlens.retrieval.text import VIETNAMESE_ACCENTED, VIETNAMESE_UNACCENTED, fold_vietnamese

MIGRATION = (
    Path(__file__).parents[1] / "migrations/versions/20261017_0005_document_chunk_search_vector.py"
)


def test_fold_vietnamese_matches_the_migration_translate_map() -> None:
    spec = importlib.util.spec_from_file_location("search_vector_migration", MIGRATION)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration._ACCENTED == VIETNAMESE_ACCENTED
    assert migration._UNACCENTED == VIETNAMESE_UNACCENTED
    assert fold_vietnamese("Hóa đơn GTGT điện tử") == "Hoa don GTGT dien tu"


def test_keyword_terms_drop_question_words_with_or_without_accents() -> None:
    assert keyword_terms("Thuế suất là bao nhiêu?") == ["Thuế", "suất"]
    assert keyword_terms("thue suat la bao nhieu") == ["thue", "suat"]
    # "cơ" (in "cơ quan") folds like the stopword "có" but is kept when typed with accents.
    assert keyword_terms("cơ quan thuế") == ["cơ", "quan", "thuế"]


def test_postgres_keyword_query_matches_folded_terms_and_rewards_exact_accents() -> None:
    sql = str(
        _postgresql_keyword_statement("hóa đơn là gì", SearchFilters(), 5).compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )

    tsquery = "websearch_to_tsquery('simple'::regconfig, "
    assert f"search_vector_folded @@ {tsquery}'hoa')" in sql
    assert f"search_vector_folded @@ {tsquery}'don')" in sql
    assert f"document_chunks.search_vector @@ {tsquery}'hóa')" in sql
    assert f"ts_rank_cd(document_chunks.search_vector_folded, {tsquery}'hoa or don'), 32)" in sql
    assert "'là'" not in sql and "'gì'" not in sql


def test_postgres_keyword_query_reads_only_chunks_that_can_reach_the_limit() -> None:
    sql = str(
        _postgresql_keyword_statement("hóa đơn", SearchFilters(as_of=date(2024, 1, 1)), 5).compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )

    # Filters apply before the cutoff, or filtered-out chunks would raise it and lose results.
    assert sql.index("issue_date") < sql.index("OFFSET 4")
    assert "eligible.match_score > coalesce((SELECT eligible.match_score" in sql
    assert "- 1" in sql


def test_forms_are_told_apart_from_rules() -> None:
    assert is_form_passage("Tên: ...... Địa chỉ: ...... Mã số: ...... Ngày: ......")
    assert is_form_passage("Họ tên: ____________ Số: ______ Ngày: ______ Nơi cấp: ______")
    assert not is_form_passage("1. Mức thuế suất 10% áp dụng đối với hàng hóa, dịch vụ.")
    assert not is_form_passage("Mã hàng ...... thuế suất ...... (một bảng có ít ô trống)")


def test_a_question_about_a_form_keeps_forms() -> None:
    assert asks_for_form("Mẫu số 01/GTGT điền thế nào?")
    assert asks_for_form("to khai thue gtgt")
    assert not asks_for_form("Thuế suất thuế GTGT của nước ngọt là bao nhiêu?")


def test_vector_search_stays_an_exact_scan() -> None:
    statements = []

    class Rows:
        def all(self) -> list[object]:
            return []

    class Session:
        def get_bind(self) -> object:
            return SimpleNamespace(dialect=postgresql.dialect())

        def execute(self, statement: object) -> Rows:
            statements.append(statement)
            return Rows()

    provider = SimpleNamespace(model_id="m", model_revision="r", dimensions=3)
    semantic_search_chunks(Session(), [0.1, 0.2, 0.3], provider, limit=5)  # type: ignore[arg-type]

    sql = str(statements[0].compile(dialect=postgresql.dialect()))
    assert re.search(r"ORDER BY \(?document_embeddings\.embedding <=> \S+\)? \+ ", sql)


def test_article_headings_tolerate_ocr_noise_and_reject_references() -> None:
    text = "\n".join(
        [
            "| Điều 1. Phạm vi điều chỉnh",
            "Nội dung.",
            "-_.. Điêu 2. Đối tượng áp dụng",
            "Theo quy định tại khoản 1",
            "Điều 2.",
            "Điều 8, khoản 4 Điều 27 được thay thế.",
            "“Điều 7. Điều khoản được sửa đổi trong văn bản khác",
            "Điều 3, Hiệu lực thi hành",
            "Điều 1 của Nghị định này.",
        ]
    )

    headings = find_article_headings(text)

    assert [(heading.number, heading.title) for heading in headings] == [
        ("1", "Phạm vi điều chỉnh"),
        ("2", "Đối tượng áp dụng"),
        ("3", "Hiệu lực thi hành"),
    ]


def test_long_articles_are_split_into_bounded_clause_chunks_with_the_preamble_kept() -> None:
    clause = "Người bán phải lập hóa đơn khi bán hàng hóa, cung cấp dịch vụ. " * 20
    text = (
        "THÔNG TƯ Hướng dẫn về hóa đơn, chứng từ\nCăn cứ Luật Quản lý thuế;\n"
        f"Điều 1. Thời điểm lập hóa đơn\n1. {clause}\n2. {clause}\n3. {clause}\n"
        "Điều 2. Hiệu lực thi hành\nThông tư có hiệu lực từ ngày ký.\n"
    )

    chunks = build_article_chunks(text)

    assert chunks[0].article_number is None and "THÔNG TƯ" in chunks[0].content
    article_one = [chunk for chunk in chunks if chunk.article_number == "1"]
    assert [chunk.clause_number for chunk in article_one] == ["1", "2", "3"]
    assert all(chunk.heading == "Thời điểm lập hóa đơn" for chunk in article_one)
    assert article_one[0].content.startswith("Điều 1.")
    assert all(len(chunk.content) <= MAX_CHUNK_CHARACTERS for chunk in chunks)
    assert chunks[-1].article_number == "2" and chunks[-1].clause_number is None


def test_header_document_number_reads_the_document_own_number() -> None:
    assert header_document_number("CHÍNH PHỦ\nSố: 301/2026/NĐ-CP\nHà Nội") == "301/2026/NĐ-CP"
    assert header_document_number("Căn cứ Luật số 38/2019/QH14") is None


def test_document_numbers_cover_laws_consolidated_texts_and_issuers() -> None:
    assert find_document_numbers("Luật 48/2024/QH15 và 18/VBHN-BTC, ngày 31/12/2025") == (
        "48/2024/QH15",
        "18/VBHN-BTC",
    )
    assert issuing_agency_for("32/2025/TT-BTC") == "Ministry of Finance"
    assert issuing_agency_for("359/2025/NĐ-CP") == "Government of Vietnam"
    assert issuing_agency_for("48/2024/QH15") == "National Assembly"


def test_excerpt_quotes_the_passage_sentence_matching_the_question() -> None:
    content = (
        "Điều 9. Thời điểm lập hóa đơn. "
        + "Nội dung không liên quan đến câu hỏi. " * 10
        + "Thời điểm lập hóa đơn đối với cung cấp dịch vụ là thời điểm hoàn thành việc cung cấp "
        "dịch vụ. " + "Một đoạn khác. " * 10
    )

    excerpt = build_excerpt(content, "thoi diem lap hoa don cung cap dich vu", 140)

    assert "hoàn thành việc cung cấp dịch vụ" in excerpt
    assert excerpt.startswith("…")


def test_lexical_support_ignores_lost_diacritics() -> None:
    passage = "Người bán phải lập hóa don khi bán hàng hóa"  # OCR lost the accent on "đơn"
    assert lexical_support("Người bán phải lập hóa đơn", passage) == 1.0
    assert lexical_support("Thuế suất thuế thu nhập cá nhân", passage) < 0.5


def test_evidence_with_low_semantic_similarity_is_not_sent_to_the_model() -> None:
    document = LegalDocument(
        id=uuid.uuid4(), document_number="31/2025/TT-BTC", title="Invoices", document_type="TT"
    )
    version = DocumentVersion(
        id=uuid.uuid4(),
        document_id=document.id,
        legal_status="EFFECTIVE",
        raw_content_hash="e" * 64,
        raw_artifact_key="raw/invoice.txt",
    )
    chunk = DocumentChunk(
        id=uuid.uuid4(),
        document_version_id=version.id,
        article_number="1",
        content="Invoice requirements.",
        token_count=2,
    )
    weak = SearchResult(chunk=chunk, version=version, document=document, vector_score=0.71)

    assert assess_evidence([weak], min_semantic_score=0.8).status is EvidenceStatus.LOW_RELEVANCE
    assert assess_evidence([weak]).status is EvidenceStatus.SUFFICIENT


def test_keyword_terms_keep_legal_content_late_in_a_long_question() -> None:
    question = (
        "Tháng 2/2026, công ty tôi đã được hoàn thuế GTGT cho một lô hàng xuất khẩu, "
        "nhưng khách hàng nước ngoài trả lại lô hàng."
    )
    terms = keyword_terms(question)
    assert "trả" in terms and "lại" in terms


def test_keyword_terms_stay_bounded() -> None:
    assert len(keyword_terms(" ".join(f"term{i}" for i in range(200)))) == 64

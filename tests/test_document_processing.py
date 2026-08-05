from datetime import date
from io import BytesIO
from pathlib import Path
from uuid import UUID

from pypdf import PdfWriter
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from taxlens.document_processing.process import (
    build_article_chunks,
    extract_text,
    process_document_version,
)
from taxlens.ingestion.seed import SeedDocument, ingest_seed_document
from taxlens.legal_data.models import DocumentChunk, DocumentVersion, LegalDocument, ProcessingJob
from taxlens.storage.local import LocalObjectStorage


def test_article_parser_uses_structural_headings() -> None:
    chunks = build_article_chunks(
        "Article 1. Scope\nFirst content.\n\nArticle 2. Dates\nSecond content."
    )

    assert [chunk.article_number for chunk in chunks] == ["1", "2"]
    assert chunks[0].heading == "Scope"
    assert "Second content" in chunks[1].content


def test_article_parser_preserves_page_bounds() -> None:
    text = "Article 1. First\nContent\n\f\nArticle 2. Second\nMore content"
    chunks = build_article_chunks(text, [0, text.index("Article 2")])

    assert [(chunk.page_start, chunk.page_end) for chunk in chunks] == [(1, 1), (2, 2)]


def test_processing_creates_chunks_and_is_idempotent(tmp_path: Path) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    LegalDocument.metadata.create_all(engine)
    storage = LocalObjectStorage(tmp_path / "storage")
    seed_document = SeedDocument(
        source_name="seed-corpus",
        source_url="https://example.invalid/process-document",
        source_document_id="process-document",
        document_number="02/2025/TT-BTC",
        title="Process document",
        document_type="CIRCULAR",
        issuing_agency="Ministry of Finance",
        issue_date=date(2025, 2, 1),
        effective_date=date(2025, 3, 1),
        legal_status="EFFECTIVE",
        content=b"Article 1. Scope\nFirst content.\n\nArticle 2. Dates\nSecond content.",
    )

    with Session(engine) as session:
        ingestion = ingest_seed_document(session, storage, seed_document)
        version = session.get(DocumentVersion, UUID(ingestion.version_id))
        assert version is not None

        processed = process_document_version(session, storage, version)
        unchanged = process_document_version(session, storage, version)
        chunks = session.scalars(select(DocumentChunk).order_by(DocumentChunk.article_number)).all()

        assert processed.status == "PROCESSED"
        assert processed.chunk_count == 2
        assert unchanged.status == "UNCHANGED"
        assert len(chunks) == 2
        assert chunks[0].article_number == "1"
        assert version.normalized_artifact_key is not None
        assert storage.exists(version.normalized_artifact_key)


def test_extract_text_accepts_pdf_artifacts() -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    buffer = BytesIO()
    writer.write(buffer)

    assert extract_text(buffer.getvalue(), "raw/example.pdf") == ""


def test_processing_marks_image_only_pdf_as_ocr_required(
    tmp_path: Path, monkeypatch
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    LegalDocument.metadata.create_all(engine)
    storage = LocalObjectStorage(tmp_path / "storage")
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    pdf_buffer = BytesIO()
    writer.write(pdf_buffer)
    seed_document = SeedDocument(
        source_name="official-source",
        source_url="https://example.invalid/scanned",
        source_document_id="scanned",
        document_number="99/2025/TT-BTC",
        title="Scanned document",
        document_type="TT-BTC",
        issuing_agency="Ministry of Finance",
        issue_date=None,
        effective_date=None,
        legal_status="DISCOVERED",
        content=pdf_buffer.getvalue(),
        content_type="application/pdf",
    )

    with Session(engine) as session:
        monkeypatch.setattr(
            "taxlens.document_processing.process.ocr_pages",
            lambda raw_content, settings: [""],
        )
        ingestion = ingest_seed_document(session, storage, seed_document)
        version = session.get(DocumentVersion, UUID(ingestion.version_id))
        assert version is not None

        result = process_document_version(session, storage, version)
        job = session.scalar(select(ProcessingJob))

        assert result.status == "FAILED"
        assert result.error_code == "OCR_REQUIRED"
        assert job is not None
        assert job.error_code == "OCR_REQUIRED"


def test_processing_uses_ocr_when_native_pdf_text_is_unusable(
    tmp_path: Path, monkeypatch
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    LegalDocument.metadata.create_all(engine)
    storage = LocalObjectStorage(tmp_path / "storage")
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    pdf_buffer = BytesIO()
    writer.write(pdf_buffer)
    seed_document = SeedDocument(
        source_name="official-source",
        source_url="https://example.invalid/ocr",
        source_document_id="ocr",
        document_number="98/2025/TT-BTC",
        title="OCR document",
        document_type="TT-BTC",
        issuing_agency="Ministry of Finance",
        issue_date=None,
        effective_date=None,
        legal_status="DISCOVERED",
        content=pdf_buffer.getvalue(),
        content_type="application/pdf",
    )

    monkeypatch.setattr(
        "taxlens.document_processing.process.ocr_pages",
            lambda raw_content, settings: [
                "Article 1. OCR scope\nVietnamese tax content for the fallback test."
            ],
    )
    with Session(engine) as session:
        ingestion = ingest_seed_document(session, storage, seed_document)
        version = session.get(DocumentVersion, UUID(ingestion.version_id))
        assert version is not None

        result = process_document_version(session, storage, version)
        job = session.scalar(select(ProcessingJob))

        assert result.status == "PROCESSED"
        assert result.chunk_count == 1
        assert job is not None
        assert job.stage == "OCR_CHUNKED"

import importlib.util
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from taxlens.legal_data.models import (
    DocumentChunk,
    DocumentEmbedding,
    DocumentVersion,
    LegalDocument,
    SourceRecord,
)

SCRIPT = Path(__file__).parents[1] / "scripts/prune_non_tax_documents.py"


def _prune_module():
    spec = importlib.util.spec_from_file_location("prune_non_tax_documents", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_prune_removes_non_tax_and_seed_documents_but_keeps_tax_and_curated() -> None:
    prune = _prune_module()
    engine = create_engine("sqlite+pysqlite:///:memory:")
    LegalDocument.metadata.create_all(engine)
    with Session(engine) as session:
        _add(session, "152/2026/TT-BTC", "Quy định mức thu, nộp phí và lệ phí", "government-portal")
        _add(session, "86/2026/TT-BGDĐT", "Quy định chương trình giáo dục", "government-portal")
        _add(session, "31/2025/TT-BTC", "Sample electronic invoice guidance", "seed-corpus")
        _add(session, "99/2026/NĐ-CP", "Quy định về quản lý cụm công nghiệp", "government-portal")
        session.commit()

        candidates = prune._documents_to_remove(session, curated={"99/2026/NĐ-CP"})
        assert [(document.document_number, reason) for document, reason in candidates] == [
            ("31/2025/TT-BTC", "sample seed document"),
            ("86/2026/TT-BGDĐT", "not tax-related"),
        ]
        for document, _ in candidates:
            prune._delete_document(session, document)
        session.commit()

        remaining = session.scalars(select(LegalDocument.document_number)).all()
        assert sorted(remaining) == ["152/2026/TT-BTC", "99/2026/NĐ-CP"]
        assert session.scalar(select(func.count(DocumentChunk.id))) == 2
        assert session.scalar(select(func.count(DocumentEmbedding.id))) == 2
        assert session.scalar(select(func.count(SourceRecord.id))) == 2


def _add(session: Session, number: str, title: str, source: str) -> None:
    record = SourceRecord(source_name=source, source_url=f"https://example.invalid/{number}")
    document = LegalDocument(document_number=number, title=title, document_type="TT")
    session.add_all([record, document])
    session.flush()
    version = DocumentVersion(
        document_id=document.id,
        source_record_id=record.id,
        legal_status="DISCOVERED",
        raw_content_hash=number.ljust(64, "x")[:64],
        raw_artifact_key=f"raw/{number}.pdf",
    )
    session.add(version)
    session.flush()
    chunk = DocumentChunk(document_version_id=version.id, content="Nội dung.", token_count=2)
    session.add(chunk)
    session.flush()
    session.add(
        DocumentEmbedding(
            document_chunk_id=chunk.id,
            model_id="m",
            model_revision="r",
            dimensions=384,
            content_hash="h",
            embedding=[0.0] * 384,
        )
    )

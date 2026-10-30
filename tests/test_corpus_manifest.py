from datetime import date

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from taxlens.evaluation.corpus_manifest import build_corpus_manifest, compare_manifests
from taxlens.legal_data.models import (
    DocumentChunk,
    DocumentEmbedding,
    DocumentVersion,
    LegalDocument,
)

MODEL = ("intfloat/multilingual-e5-small", "rev-1")


def test_manifest_counts_versions_chunks_and_embeddings_of_the_model() -> None:
    engine = _engine_with_corpus()
    with Session(engine) as session:
        manifest = build_corpus_manifest(session, *MODEL, label="corpus-test")

    assert manifest["label"] == "corpus-test"
    assert (manifest["document_count"], manifest["version_count"]) == (1, 1)
    assert manifest["chunk_count"] == 2
    assert manifest["embedded_chunk_count"] == 1
    (version,) = manifest["versions"]
    assert version["effective_date"] == "2025-07-01"


def test_compare_manifests_reports_changed_passages_and_new_documents() -> None:
    engine = _engine_with_corpus()
    with Session(engine) as session:
        frozen = build_corpus_manifest(session, *MODEL)
        assert compare_manifests(frozen, build_corpus_manifest(session, *MODEL))["unchanged"]

        chunk = session.scalars(
            select(DocumentChunk).where(DocumentChunk.clause_number == "1")
        ).one()
        chunk.content = "Thuế suất 8%."
        _add_document(session, "02/2024/TT-BTC", "b" * 64)
        session.flush()
        difference = compare_manifests(frozen, build_corpus_manifest(session, *MODEL))

    assert not difference["unchanged"]
    assert difference["added"] == [
        {"document_number": "02/2024/TT-BTC", "raw_content_hash": "b" * 64}
    ]
    assert difference["changed"] == [
        {
            "document_number": "31/2025/TT-BTC",
            "raw_content_hash": "a" * 64,
            "fields": ["chunks_hash"],
        }
    ]


def test_compare_manifests_notices_a_different_embedding_model() -> None:
    engine = _engine_with_corpus()
    with Session(engine) as session:
        frozen = build_corpus_manifest(session, *MODEL)
        current = build_corpus_manifest(session, MODEL[0], "rev-2")

    difference = compare_manifests(frozen, current)
    assert not difference["unchanged"]
    assert difference["embedding_model_changed"]


def _engine_with_corpus():
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    LegalDocument.metadata.create_all(engine)
    with Session(engine) as session:
        version = _add_document(session, "31/2025/TT-BTC", "a" * 64)
        chunks = [
            DocumentChunk(
                document_version_id=version.id,
                article_number="9",
                clause_number=clause,
                content=f"Khoản {clause}.",
                token_count=3,
            )
            for clause in ("1", "2")
        ]
        session.add_all(chunks)
        session.flush()
        session.add(
            DocumentEmbedding(
                document_chunk_id=chunks[0].id,
                model_id=MODEL[0],
                model_revision=MODEL[1],
                dimensions=384,
                content_hash="c" * 64,
                embedding=[0.0] * 384,
            )
        )
        session.commit()
    return engine


def _add_document(session: Session, number: str, raw_hash: str) -> DocumentVersion:
    document = LegalDocument(document_number=number, title=number, document_type="CIRCULAR")
    session.add(document)
    session.flush()
    version = DocumentVersion(
        document_id=document.id,
        effective_date=date(2025, 7, 1),
        legal_status="EFFECTIVE",
        raw_content_hash=raw_hash,
        raw_artifact_key=f"raw/{number}.txt",
    )
    session.add(version)
    session.flush()
    return version

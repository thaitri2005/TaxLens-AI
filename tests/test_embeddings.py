from datetime import date

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from taxlens.legal_data.models import (
    DocumentChunk,
    DocumentEmbedding,
    DocumentVersion,
    LegalDocument,
)
from taxlens.retrieval import embeddings
from taxlens.retrieval.embeddings import EmbeddingBatch, embed_pending_chunks


class FakeEmbeddingProvider:
    model_id = "test-model"
    model_revision = "test-revision"
    dimensions = 384

    def embed_passages(self, texts: list[str]) -> EmbeddingBatch:
        return EmbeddingBatch(vectors=[[0.1] * self.dimensions for _ in texts], truncated_inputs=0)

    def embed_query(self, text: str) -> EmbeddingBatch:
        return EmbeddingBatch(vectors=[[0.1] * self.dimensions], truncated_inputs=0)


def test_embedding_backfill_is_idempotent() -> None:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    LegalDocument.metadata.create_all(engine)
    with Session(engine) as session:
        document = LegalDocument(
            document_number="03/2025/TT-BTC",
            title="Embedding test document",
            document_type="CIRCULAR",
            issuing_agency="Ministry of Finance",
        )
        session.add(document)
        session.flush()
        version = DocumentVersion(
            document_id=document.id,
            issue_date=date(2025, 3, 1),
            effective_date=date(2025, 4, 1),
            legal_status="EFFECTIVE",
            raw_content_hash="c" * 64,
            raw_artifact_key="raw/embedding-test.txt",
        )
        session.add(version)
        session.flush()
        session.add(
            DocumentChunk(
                document_version_id=version.id,
                article_number="1",
                heading="Scope",
                content="Embedding content.",
                token_count=2,
            )
        )
        session.commit()

        provider = FakeEmbeddingProvider()
        first = embed_pending_chunks(session, provider, batch_size=10)
        second = embed_pending_chunks(session, provider, batch_size=10)
        embeddings = session.scalars(select(DocumentEmbedding)).all()

    assert first.embedded == 1
    assert first.unchanged == 0
    assert second.embedded == 0
    assert second.unchanged == 1
    assert len(embeddings) == 1
    assert embeddings[0].dimensions == 384


def test_embedding_backfill_respects_the_batch_limit() -> None:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    LegalDocument.metadata.create_all(engine)
    with Session(engine) as session:
        document = LegalDocument(
            document_number="04/2025/TT-BTC", title="Limit", document_type="CIRCULAR"
        )
        session.add(document)
        session.flush()
        version = DocumentVersion(
            document_id=document.id,
            legal_status="EFFECTIVE",
            raw_content_hash="d" * 64,
            raw_artifact_key="raw/limit.txt",
        )
        session.add(version)
        session.flush()
        for index in range(3):
            session.add(
                DocumentChunk(
                    document_version_id=version.id,
                    article_number=str(index + 1),
                    content=f"Chunk {index}",
                    token_count=2,
                )
            )
        session.commit()

        first = embed_pending_chunks(session, FakeEmbeddingProvider(), batch_size=10, limit=2)
        second = embed_pending_chunks(session, FakeEmbeddingProvider(), batch_size=10, limit=2)

    assert (first.embedded, first.remaining) == (2, 1)
    assert (second.embedded, second.unchanged, second.remaining) == (1, 2, 0)


def test_embedding_backfill_pages_through_chunks_and_refreshes_stale_vectors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    LegalDocument.metadata.create_all(engine)
    monkeypatch.setattr(embeddings, "SCAN_PAGE_SIZE", 2)
    with Session(engine) as session:
        document = LegalDocument(
            document_number="05/2025/TT-BTC", title="Pages", document_type="CIRCULAR"
        )
        session.add(document)
        session.flush()
        version = DocumentVersion(
            document_id=document.id,
            legal_status="EFFECTIVE",
            raw_content_hash="e" * 64,
            raw_artifact_key="raw/pages.txt",
        )
        session.add(version)
        session.flush()
        for index in range(5):
            session.add(
                DocumentChunk(
                    document_version_id=version.id,
                    article_number=str(index + 1),
                    content=f"Chunk {index}",
                    token_count=2,
                )
            )
        session.commit()
        provider = FakeEmbeddingProvider()
        pages: list[int] = []

        first = embed_pending_chunks(
            session, provider, batch_size=2, on_progress=lambda _, checked: pages.append(checked)
        )
        changed = session.scalars(select(DocumentChunk)).first()
        assert changed is not None
        changed.content = "Chunk changed"
        session.commit()
        second = embed_pending_chunks(session, provider, batch_size=2)
        stored = session.scalars(select(DocumentEmbedding)).all()

    assert pages == [2, 4, 5]
    assert (first.embedded, first.unchanged) == (5, 0)
    assert (second.embedded, second.unchanged) == (1, 4)
    assert len(stored) == 5

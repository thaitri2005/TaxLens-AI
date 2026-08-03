from datetime import date

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from taxlens.legal_data.models import (
    DocumentChunk,
    DocumentEmbedding,
    DocumentVersion,
    LegalDocument,
)
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

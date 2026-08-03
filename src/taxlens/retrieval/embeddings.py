import hashlib
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from taxlens.config import Settings, get_settings
from taxlens.legal_data.models import DocumentChunk, DocumentEmbedding

QUERY_PREFIX = "query: "
PASSAGE_PREFIX = "passage: "


@dataclass(frozen=True)
class EmbeddingBatch:
    vectors: list[list[float]]
    truncated_inputs: int


@dataclass(frozen=True)
class EmbeddingBackfillResult:
    embedded: int
    unchanged: int
    truncated_inputs: int


class EmbeddingProvider(Protocol):
    model_id: str
    model_revision: str
    dimensions: int

    def embed_passages(self, texts: list[str]) -> EmbeddingBatch: ...

    def embed_query(self, text: str) -> EmbeddingBatch: ...


class LocalE5Embedder:
    def __init__(self, settings: Settings) -> None:
        self.model_id = settings.embedding_model_id
        self.model_revision = settings.embedding_model_revision
        self.dimensions = settings.embedding_dimensions
        self._max_tokens = settings.embedding_max_tokens
        self._batch_size = settings.embedding_batch_size
        self._model = self._load_model(settings.embedding_model_path)

    def embed_passages(self, texts: list[str]) -> EmbeddingBatch:
        return self._embed(texts, PASSAGE_PREFIX)

    def embed_query(self, text: str) -> EmbeddingBatch:
        return self._embed([text], QUERY_PREFIX)

    def _embed(self, texts: list[str], prefix: str) -> EmbeddingBatch:
        prepared_texts = [prefix + text.strip() for text in texts]
        truncated_inputs = self._count_truncated_inputs(prepared_texts)
        embeddings = self._model.encode(
            prepared_texts,
            batch_size=self._batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        vectors = [list(map(float, vector)) for vector in embeddings.tolist()]
        if any(len(vector) != self.dimensions for vector in vectors):
            raise ValueError(
                "Embedding model output dimension does not match configured dimensions"
            )
        return EmbeddingBatch(vectors=vectors, truncated_inputs=truncated_inputs)

    def _load_model(self, model_path: str) -> Any:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(model_path, device="cpu", local_files_only=True)
        model.max_seq_length = self._max_tokens
        return model

    def _count_truncated_inputs(self, texts: list[str]) -> int:
        tokens = self._model.tokenizer(
            texts,
            add_special_tokens=True,
            truncation=False,
            return_attention_mask=False,
        )
        return sum(len(token_ids) > self._max_tokens for token_ids in tokens["input_ids"])


def embed_pending_chunks(
    session: Session,
    provider: EmbeddingProvider,
    batch_size: int,
) -> EmbeddingBackfillResult:
    chunks = session.scalars(select(DocumentChunk).order_by(DocumentChunk.created_at)).all()
    pending: list[tuple[DocumentChunk, DocumentEmbedding | None, str]] = []
    unchanged = 0

    for chunk in chunks:
        content_hash = chunk_content_hash(chunk)
        existing = session.scalar(
            select(DocumentEmbedding).where(
                DocumentEmbedding.document_chunk_id == chunk.id,
                DocumentEmbedding.model_id == provider.model_id,
                DocumentEmbedding.model_revision == provider.model_revision,
            )
        )
        if existing is not None and existing.content_hash == content_hash:
            unchanged += 1
            continue
        pending.append((chunk, existing, content_hash))

    embedded = 0
    truncated_inputs = 0
    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        embedding_batch = provider.embed_passages(
            [chunk_text(chunk) for chunk, _, _ in batch]
        )
        truncated_inputs += embedding_batch.truncated_inputs
        for (chunk, existing, content_hash), vector in zip(
            batch, embedding_batch.vectors, strict=True
        ):
            if existing is None:
                session.add(
                    DocumentEmbedding(
                        document_chunk_id=chunk.id,
                        model_id=provider.model_id,
                        model_revision=provider.model_revision,
                        dimensions=provider.dimensions,
                        content_hash=content_hash,
                        embedding=vector,
                    )
                )
            else:
                existing.dimensions = provider.dimensions
                existing.content_hash = content_hash
                existing.embedding = vector
            embedded += 1

    session.commit()
    return EmbeddingBackfillResult(
        embedded=embedded,
        unchanged=unchanged,
        truncated_inputs=truncated_inputs,
    )


def chunk_content_hash(chunk: DocumentChunk) -> str:
    return hashlib.sha256(chunk_text(chunk).encode("utf-8")).hexdigest()


def chunk_text(chunk: DocumentChunk) -> str:
    return "\n".join(part for part in [chunk.heading, chunk.content] if part).strip()


@lru_cache
def get_embedding_provider() -> LocalE5Embedder:
    return LocalE5Embedder(get_settings())

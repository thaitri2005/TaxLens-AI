import hashlib
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol

from sqlalchemy import and_, select, update
from sqlalchemy.orm import Session

from taxlens.config import Settings, get_settings
from taxlens.legal_data.models import DocumentChunk, DocumentEmbedding

logger = logging.getLogger(__name__)
QUERY_PREFIX = "query: "
PASSAGE_PREFIX = "passage: "
SCAN_PAGE_SIZE = 500


@dataclass(frozen=True)
class EmbeddingBatch:
    vectors: list[list[float]]
    truncated_inputs: int


@dataclass(frozen=True)
class EmbeddingBackfillResult:
    embedded: int
    unchanged: int
    truncated_inputs: int
    remaining: int = 0


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
            verbose=False,
        )
        return sum(len(token_ids) > self._max_tokens for token_ids in tokens["input_ids"])


def embed_pending_chunks(
    session: Session,
    provider: EmbeddingProvider,
    batch_size: int,
    limit: int | None = None,
    on_progress: Callable[[EmbeddingBackfillResult, int], None] | None = None,
) -> EmbeddingBackfillResult:
    """Embed chunks without a current embedding; ``limit`` bounds one call's work.

    Chunks are scanned a page at a time, reading only their text and the stored hash,
    never the stored vectors. Loading every chunk with its embedding at once needed
    more memory than the API container has once the corpus passed 40,000 chunks, and
    the kernel killed the job. ``on_progress`` receives the running totals and the
    number of chunks checked after each page.
    """

    embedded = unchanged = truncated_inputs = remaining = checked = 0
    last_id: uuid.UUID | None = None
    while True:
        query = (
            select(
                DocumentChunk.id,
                DocumentChunk.heading,
                DocumentChunk.content,
                DocumentEmbedding.id,
                DocumentEmbedding.content_hash,
            )
            .outerjoin(
                DocumentEmbedding,
                and_(
                    DocumentEmbedding.document_chunk_id == DocumentChunk.id,
                    DocumentEmbedding.model_id == provider.model_id,
                    DocumentEmbedding.model_revision == provider.model_revision,
                ),
            )
            .order_by(DocumentChunk.id)
            .limit(SCAN_PAGE_SIZE)
        )
        if last_id is not None:
            query = query.where(DocumentChunk.id > last_id)
        rows = session.execute(query).all()
        if not rows:
            break
        last_id = rows[-1][0]
        checked += len(rows)

        pending: list[tuple[uuid.UUID, uuid.UUID | None, str, str]] = []
        for chunk_id, heading, content, embedding_id, stored_hash in rows:
            text = passage_text(heading, content)
            content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if stored_hash == content_hash:
                unchanged += 1
            elif limit is not None and embedded + len(pending) >= limit:
                remaining += 1
            else:
                pending.append((chunk_id, embedding_id, text, content_hash))

        for start in range(0, len(pending), batch_size):
            batch = pending[start : start + batch_size]
            embedding_batch = provider.embed_passages([text for _, _, text, _ in batch])
            truncated_inputs += embedding_batch.truncated_inputs
            for (pending_chunk_id, stored_id, _, pending_hash), vector in zip(
                batch, embedding_batch.vectors, strict=True
            ):
                if stored_id is None:
                    session.add(
                        DocumentEmbedding(
                            document_chunk_id=pending_chunk_id,
                            model_id=provider.model_id,
                            model_revision=provider.model_revision,
                            dimensions=provider.dimensions,
                            content_hash=pending_hash,
                            embedding=vector,
                        )
                    )
                else:
                    session.execute(
                        update(DocumentEmbedding)
                        .where(DocumentEmbedding.id == stored_id)
                        .values(
                            dimensions=provider.dimensions,
                            content_hash=pending_hash,
                            embedding=vector,
                        )
                    )
            # Commit per batch so an interrupted backfill keeps the work already done,
            # and drop the committed objects so memory stays flat.
            session.commit()
            session.expunge_all()
            embedded += len(batch)

        if on_progress is not None:
            on_progress(
                EmbeddingBackfillResult(embedded, unchanged, truncated_inputs, remaining),
                checked,
            )

    return EmbeddingBackfillResult(
        embedded=embedded,
        unchanged=unchanged,
        truncated_inputs=truncated_inputs,
        remaining=remaining,
    )


def chunk_content_hash(chunk: DocumentChunk) -> str:
    return hashlib.sha256(chunk_text(chunk).encode("utf-8")).hexdigest()


def chunk_text(chunk: DocumentChunk) -> str:
    return passage_text(chunk.heading, chunk.content)


def passage_text(heading: str | None, content: str | None) -> str:
    return "\n".join(part for part in [heading, content] if part).strip()


@lru_cache
def get_embedding_provider() -> LocalE5Embedder:
    return LocalE5Embedder(get_settings())


@lru_cache
def get_available_embedding_provider() -> LocalE5Embedder | None:
    """Return the embedding provider, or None so retrieval degrades to keyword search.

    The model is loaded from local files, so a failure is not retried per request.
    """

    try:
        return get_embedding_provider()
    except Exception:
        logger.exception("Embedding model unavailable; falling back to keyword retrieval")
        return None

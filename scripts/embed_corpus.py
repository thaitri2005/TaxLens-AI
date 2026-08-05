from sqlalchemy import func, select

from taxlens.config import get_settings
from taxlens.db import SessionLocal
from taxlens.legal_data.models import DocumentChunk
from taxlens.retrieval.embeddings import embed_pending_chunks, get_embedding_provider


def main() -> None:
    settings = get_settings()
    print("Loading embedding model and counting chunks...", flush=True)
    provider = get_embedding_provider()
    with SessionLocal() as session:
        chunk_count = session.scalar(select(func.count(DocumentChunk.id))) or 0
        print(f"Embedding {chunk_count} chunk(s) in batches...", flush=True)
        result = embed_pending_chunks(session, provider, settings.embedding_batch_size)
    print(
        "Embedding complete: "
        f"{result.embedded} embedded, {result.unchanged} unchanged, "
        f"{result.truncated_inputs} truncated"
    )


if __name__ == "__main__":
    main()

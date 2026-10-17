import argparse

from sqlalchemy import func, select

from taxlens.config import get_settings
from taxlens.db import SessionLocal
from taxlens.legal_data.models import DocumentChunk
from taxlens.retrieval.embeddings import embed_pending_chunks, get_embedding_provider


def main() -> None:
    parser = argparse.ArgumentParser(description="Embed chunks without a current embedding")
    parser.add_argument(
        "--limit",
        type=int,
        help="Embed at most this many chunks so one call stays inside request time limits",
    )
    arguments = parser.parse_args()
    if arguments.limit is not None and arguments.limit < 1:
        parser.error("--limit must be at least 1")

    settings = get_settings()
    print("Loading embedding model and counting chunks...", flush=True)
    provider = get_embedding_provider()
    with SessionLocal() as session:
        chunk_count = session.scalar(select(func.count(DocumentChunk.id))) or 0
        print(f"Checking {chunk_count} chunk(s) for missing embeddings...", flush=True)
        result = embed_pending_chunks(
            session, provider, settings.embedding_batch_size, limit=arguments.limit
        )
    print(
        "Embedding complete: "
        f"{result.embedded} embedded, {result.unchanged} unchanged, "
        f"{result.truncated_inputs} truncated, {result.remaining} remaining"
    )


if __name__ == "__main__":
    main()

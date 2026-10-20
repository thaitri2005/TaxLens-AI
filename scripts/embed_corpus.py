import argparse
import time

from sqlalchemy import func, select

from taxlens.config import get_settings
from taxlens.db import SessionLocal
from taxlens.legal_data.models import DocumentChunk
from taxlens.retrieval.embeddings import (
    EmbeddingBackfillResult,
    embed_pending_chunks,
    get_embedding_provider,
)


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
        started = time.monotonic()

        def report(progress: EmbeddingBackfillResult, checked: int) -> None:
            print(
                f"Checked {checked}/{chunk_count} chunk(s): {progress.embedded} embedded, "
                f"{progress.unchanged} already current | {_duration(time.monotonic() - started)}",
                flush=True,
            )

        result = embed_pending_chunks(
            session,
            provider,
            settings.embedding_batch_size,
            limit=arguments.limit,
            on_progress=report,
        )
    print(
        "Embedding complete: "
        f"{result.embedded} embedded, {result.unchanged} unchanged, "
        f"{result.truncated_inputs} truncated, {result.remaining} remaining"
    )


def _duration(seconds: float) -> str:
    minutes, seconds = divmod(int(seconds), 60)
    return f"{minutes}m{seconds:02d}s" if minutes else f"{seconds}s"


if __name__ == "__main__":
    main()

from taxlens.config import get_settings
from taxlens.db import SessionLocal
from taxlens.retrieval.embeddings import embed_pending_chunks, get_embedding_provider


def main() -> None:
    settings = get_settings()
    provider = get_embedding_provider()
    with SessionLocal() as session:
        result = embed_pending_chunks(session, provider, settings.embedding_batch_size)
    print(
        "Embedding complete: "
        f"{result.embedded} embedded, {result.unchanged} unchanged, "
        f"{result.truncated_inputs} truncated"
    )


if __name__ == "__main__":
    main()


import argparse
from pathlib import Path

from taxlens.db import SessionLocal
from taxlens.ingestion.seed import ingest_seed_document, load_seed_manifest
from taxlens.storage.factory import get_object_storage


def main() -> None:
    parser = argparse.ArgumentParser(description="Load the TaxLens seed corpus")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/seed/manifest.json"),
        help="Path to the seed manifest JSON file",
    )
    arguments = parser.parse_args()

    documents = load_seed_manifest(arguments.manifest)
    storage = get_object_storage()
    results = []
    with SessionLocal() as session:
        for document in documents:
            results.append(ingest_seed_document(session, storage, document))

    new_documents = sum(result.status == "NEW_DOCUMENT" for result in results)
    unchanged = sum(result.status == "UNCHANGED" for result in results)
    print(f"Seed ingestion complete: {new_documents} new, {unchanged} unchanged")


if __name__ == "__main__":
    main()

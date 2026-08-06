import argparse
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from taxlens.api.auth import hash_password
from taxlens.db import SessionLocal
from taxlens.ingestion.seed import ingest_seed_document, load_seed_manifest
from taxlens.legal_data.models import UserAccount
from taxlens.storage.factory import get_object_storage


def _seed_admin(session: Session) -> None:
    import os

    password = os.getenv("AUTH_INITIAL_ADMIN_PASSWORD")
    if not password:
        return
    username = os.getenv("AUTH_INITIAL_ADMIN_USERNAME", "admin")
    user = session.scalar(select(UserAccount).where(UserAccount.username == username))
    if user is None:
        session.add(
            UserAccount(username=username, password_hash=hash_password(password), role="admin")
        )
        session.commit()


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
        _seed_admin(session)

    new_documents = sum(result.status == "NEW_DOCUMENT" for result in results)
    unchanged = sum(result.status == "UNCHANGED" for result in results)
    print(f"Seed ingestion complete: {new_documents} new, {unchanged} unchanged")


if __name__ == "__main__":
    main()

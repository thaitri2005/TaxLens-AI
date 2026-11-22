"""Merge documents the corpus holds twice, following a reviewed plan.

    python scripts/merge_duplicate_documents.py \
        --plan data/evaluation/corpus/merge-duplicates-v2.1.json \
        --backup data/evaluation/corpus/removed-duplicates-v2.1.json [--apply]

A dry run unless --apply. For each number the plan names the version to keep and the one to
remove. The kept version moves to the document whose number has no stray spaces; the removed
version goes with its passages, embeddings, jobs, and relationships, and a document left
without versions goes too. Everything removed is written to --backup first, in one
transaction with the changes. Source records stay, so collection does not fetch the copy
again; the original files stay in blob storage. Freeze a new corpus afterwards.
"""

import argparse
import json
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from taxlens.db import SessionLocal
from taxlens.legal_data.models import (
    DocumentChunk,
    DocumentEmbedding,
    DocumentVersion,
    LegalDocument,
    LegalRelationship,
    ProcessingJob,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    arguments = parser.parse_args()

    merges = json.loads(arguments.plan.read_text(encoding="utf-8"))["merges"]
    removed: list[dict[str, Any]] = []
    with SessionLocal() as session:
        for merge in merges:
            removed.append(_merge(session, merge, arguments.apply))
        if arguments.apply:
            arguments.backup.write_text(
                json.dumps(removed, ensure_ascii=False, indent=2, default=str) + "\n",
                encoding="utf-8",
            )
            session.commit()
    passages = sum(len(item["passages"]) for item in removed)
    mode = "applied" if arguments.apply else "dry run"
    print(f"{len(removed)} versions and {passages} passages removed ({mode})")
    if arguments.apply:
        print(f"backup: {arguments.backup}")


def _merge(session: Session, merge: dict[str, str], apply: bool) -> dict[str, Any]:
    number = merge["number"]
    documents = [
        document
        for document in session.scalars(select(LegalDocument))
        if document.document_number.replace(" ", "") == number
    ]
    clean = [document for document in documents if document.document_number == number]
    if len(clean) != 1:
        raise SystemExit(f"{number}: expected one document with this exact number")
    versions = list(
        session.scalars(
            select(DocumentVersion).where(
                DocumentVersion.document_id.in_([document.id for document in documents])
            )
        )
    )
    keep = _by_prefix(versions, merge["keep"], number)
    drop = _by_prefix(versions, merge["drop"], number)
    if keep.id == drop.id or len(versions) != 2:
        raise SystemExit(f"{number}: the plan must name the two versions it holds")

    target = clean[0]
    passages = list(
        session.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.document_version_id == drop.id)
            .order_by(DocumentChunk.page_start, DocumentChunk.article_number, DocumentChunk.id)
        )
    )
    moved = keep.document_id != target.id
    print(
        f"{number}: keep {str(keep.id)[:8]}{' (moved to the clean number)' if moved else ''}, "
        f"remove {str(drop.id)[:8]} with {len(passages)} passages; {merge['reason']}"
    )
    record = {
        "number": number,
        "reason": merge["reason"],
        "kept_version": str(keep.id),
        "removed_version": {
            column.name: getattr(drop, column.key) for column in DocumentVersion.__table__.columns
        },
        "removed_from_document": next(
            document.document_number for document in documents if document.id == drop.document_id
        ),
        "passages": [
            {
                "article": passage.article_number,
                "clause": passage.clause_number,
                "heading": passage.heading,
                "pages": [passage.page_start, passage.page_end],
                "content": passage.content,
            }
            for passage in passages
        ],
    }
    if not apply:
        return record

    chunk_ids = select(DocumentChunk.id).where(DocumentChunk.document_version_id == drop.id)
    session.execute(
        delete(DocumentEmbedding).where(DocumentEmbedding.document_chunk_id.in_(chunk_ids))
    )
    session.execute(delete(DocumentChunk).where(DocumentChunk.document_version_id == drop.id))
    session.execute(delete(ProcessingJob).where(ProcessingJob.document_version_id == drop.id))
    session.execute(delete(LegalRelationship).where(LegalRelationship.source_version_id == drop.id))
    session.execute(delete(DocumentVersion).where(DocumentVersion.id == drop.id))
    if moved:
        session.execute(
            update(DocumentVersion)
            .where(DocumentVersion.id == keep.id)
            .values(document_id=target.id)
        )
    for document in documents:
        if document.id == target.id:
            continue
        session.execute(
            update(LegalRelationship)
            .where(LegalRelationship.target_document_id == document.id)
            .values(target_document_id=target.id)
        )
        session.execute(delete(LegalDocument).where(LegalDocument.id == document.id))
    return record


def _by_prefix(versions: list[DocumentVersion], prefix: str, number: str) -> DocumentVersion:
    matches = [version for version in versions if str(version.id).startswith(prefix)]
    if len(matches) != 1:
        raise SystemExit(f"{number}: version {prefix} matches {len(matches)} versions")
    return matches[0]


if __name__ == "__main__":
    main()

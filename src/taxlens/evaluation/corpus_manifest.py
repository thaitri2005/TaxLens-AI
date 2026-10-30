"""A frozen description of the corpus, so experiments run on different days compare.

The daily DAG keeps adding and reprocessing documents. A manifest records every document
version with a hash of its passages (text, article, clause) and how many are embedded by
the configured model; comparing a manifest with the live database shows whether a
retrieval run still searches the corpus the experiment froze.
"""

import hashlib
import json
import os
import subprocess
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from taxlens.legal_data.models import (
    DocumentChunk,
    DocumentEmbedding,
    DocumentVersion,
    LegalDocument,
)

MANIFEST_VERSION = 1
# Fields of a version entry that must match for the corpus to count as unchanged.
_COMPARED_FIELDS = (
    "document_type",
    "effective_date",
    "legal_status",
    "chunk_count",
    "chunks_hash",
    "embedded_chunk_count",
)


def build_corpus_manifest(
    session: Session,
    embedding_model_id: str,
    embedding_model_revision: str,
    label: str | None = None,
    code_version: str | None = None,
) -> dict[str, Any]:
    chunk_hashes: dict[Any, list[str]] = defaultdict(list)
    rows = session.execute(
        select(
            DocumentChunk.document_version_id,
            DocumentChunk.article_number,
            DocumentChunk.clause_number,
            DocumentChunk.content,
        ).execution_options(yield_per=2000)
    )
    for version_id, article, clause, content in rows:
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        chunk_hashes[version_id].append(f"{article or ''}|{clause or ''}|{content_hash}")
    embedded: dict[Any, int] = {
        version_id: count
        for version_id, count in session.execute(
            select(DocumentChunk.document_version_id, func.count(DocumentEmbedding.id))
            .join(DocumentEmbedding, DocumentEmbedding.document_chunk_id == DocumentChunk.id)
            .where(
                DocumentEmbedding.model_id == embedding_model_id,
                DocumentEmbedding.model_revision == embedding_model_revision,
            )
            .group_by(DocumentChunk.document_version_id)
        ).all()
    }
    versions = []
    for version, document in session.execute(
        select(DocumentVersion, LegalDocument)
        .join(LegalDocument, DocumentVersion.document_id == LegalDocument.id)
        .order_by(LegalDocument.document_number, DocumentVersion.raw_content_hash)
    ).all():
        hashes = sorted(chunk_hashes.get(version.id, []))
        versions.append(
            {
                "document_number": document.document_number,
                "raw_content_hash": version.raw_content_hash,
                "document_type": document.document_type,
                "effective_date": (
                    version.effective_date.isoformat() if version.effective_date else None
                ),
                "legal_status": version.legal_status,
                "chunk_count": len(hashes),
                "chunks_hash": hashlib.sha256("\n".join(hashes).encode("utf-8")).hexdigest(),
                "embedded_chunk_count": int(embedded.get(version.id, 0)),
            }
        )
    return {
        "manifest_version": MANIFEST_VERSION,
        "label": label,
        "created_at": datetime.now(UTC).isoformat(),
        "code_version": code_version,
        "embedding_model_id": embedding_model_id,
        "embedding_model_revision": embedding_model_revision,
        "document_count": len({item["document_number"] for item in versions}),
        "version_count": len(versions),
        "chunk_count": sum(item["chunk_count"] for item in versions),
        "embedded_chunk_count": sum(item["embedded_chunk_count"] for item in versions),
        "fingerprint": manifest_fingerprint(versions, embedding_model_id, embedding_model_revision),
        "versions": versions,
    }


def code_version() -> str | None:
    """The git commit of the running code, or TAXLENS_CODE_VERSION inside an image."""

    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, check=True
        ).stdout.strip()
        return f"{commit}-dirty" if dirty else commit
    except (OSError, subprocess.CalledProcessError):
        return os.environ.get("TAXLENS_CODE_VERSION") or None


def manifest_fingerprint(
    versions: list[dict[str, Any]], embedding_model_id: str, embedding_model_revision: str
) -> str:
    payload = {
        "embedding_model_id": embedding_model_id,
        "embedding_model_revision": embedding_model_revision,
        "versions": [
            {key: item[key] for key in ("document_number", "raw_content_hash", *_COMPARED_FIELDS)}
            for item in versions
        ],
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def compare_manifests(frozen: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """What changed between a frozen manifest and the current one; empty lists if nothing."""

    def keyed(manifest: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
        return {
            (item["document_number"], item["raw_content_hash"]): item
            for item in manifest["versions"]
        }

    before, after = keyed(frozen), keyed(current)
    changed = []
    for key in sorted(before.keys() & after.keys()):
        fields = [
            field for field in _COMPARED_FIELDS if before[key].get(field) != after[key].get(field)
        ]
        if fields:
            changed.append(
                {"document_number": key[0], "raw_content_hash": key[1], "fields": fields}
            )
    model_changed = (
        frozen["embedding_model_id"] != current["embedding_model_id"]
        or frozen["embedding_model_revision"] != current["embedding_model_revision"]
    )
    return {
        "unchanged": frozen["fingerprint"] == current["fingerprint"],
        "embedding_model_changed": model_changed,
        "added": [
            {"document_number": key[0], "raw_content_hash": key[1]}
            for key in sorted(after.keys() - before.keys())
        ],
        "removed": [
            {"document_number": key[0], "raw_content_hash": key[1]}
            for key in sorted(before.keys() - after.keys())
        ],
        "changed": changed,
    }

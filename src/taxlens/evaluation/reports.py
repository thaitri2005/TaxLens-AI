from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from taxlens.storage.base import ObjectStorage
from taxlens.storage.factory import get_object_storage

LATEST_RETRIEVAL_REPORT_KEY = "evaluation/retrieval/latest.json"


def persist_retrieval_report(
    report: Mapping[str, Any],
    storage: ObjectStorage | None = None,
) -> dict[str, Any]:
    """Persist the latest report and an immutable historical copy."""

    generated_at = datetime.now(UTC)
    report_id = f"{generated_at.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:12]}"
    history_key = f"evaluation/retrieval/runs/{report_id}.json"
    persisted = {
        **report,
        "report_id": report_id,
        "generated_at": generated_at.isoformat(),
        "artifact_key": history_key,
    }
    content = json.dumps(persisted, ensure_ascii=False, indent=2).encode("utf-8")
    resolved_storage = storage or get_object_storage()
    resolved_storage.put_bytes(history_key, content, content_type="application/json")
    resolved_storage.put_bytes(
        LATEST_RETRIEVAL_REPORT_KEY,
        content,
        content_type="application/json",
    )
    return persisted


def load_latest_retrieval_report(storage: ObjectStorage | None = None) -> dict[str, Any]:
    """Load the most recent durable retrieval report."""

    resolved_storage = storage or get_object_storage()
    if not resolved_storage.exists(LATEST_RETRIEVAL_REPORT_KEY):
        raise FileNotFoundError("No retrieval evaluation report has been persisted")
    report = json.loads(resolved_storage.get_bytes(LATEST_RETRIEVAL_REPORT_KEY))
    if not isinstance(report, dict):
        raise ValueError("Persisted retrieval report must be a JSON object")
    return report

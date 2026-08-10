import json

from taxlens.evaluation.reports import (
    LATEST_RETRIEVAL_REPORT_KEY,
    load_latest_retrieval_report,
    persist_retrieval_report,
)
from taxlens.storage.local import LocalObjectStorage


def test_retrieval_reports_persist_latest_and_history(tmp_path) -> None:
    storage = LocalObjectStorage(tmp_path)
    report = persist_retrieval_report(
        {"mean_hit_at_k": 0.75, "case_count": 4},
        storage=storage,
    )

    assert report["report_id"]
    assert report["artifact_key"].startswith("evaluation/retrieval/runs/")
    assert load_latest_retrieval_report(storage) == report
    assert json.loads(storage.get_bytes(LATEST_RETRIEVAL_REPORT_KEY)) == report
    assert storage.exists(report["artifact_key"])

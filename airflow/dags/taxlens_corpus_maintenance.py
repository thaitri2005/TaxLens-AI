"""Manually triggered corpus maintenance (Trigger DAG w/ config in the Airflow UI).

- ``ocr_benchmark``: compare OCR settings on a PDF with a clean text layer; read the result
  table in the task log. Needs ``document_number``.
- ``reocr_scanned_documents``: re-run OCR for every OCR'd document with the current
  settings, then re-embed. Slow (minutes per long scan) and CPU-heavy on the API.
- ``retry_failed_documents``: retry versions whose processing failed, then embed.
- ``prune_non_tax_dry_run``: list documents whose titles fail the tax filter (and sample
  seed documents) without deleting anything.
- ``prune_non_tax_apply``: delete those documents from the database.
- ``backfill_dry_run``: count historical tax documents not yet collected.
- ``backfill_corpus``: collect up to ``limit`` of them from the Ministry of Finance database
  and the government portal, then process and embed. Repeat until nothing remains.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.models.param import Param
from airflow.operators.python import PythonOperator
from taxlens_jobs import run_api_job


def run_maintenance(params: dict[str, object], **_: object) -> None:
    action = params["action"]
    if action == "ocr_benchmark":
        if not params.get("document_number"):
            raise ValueError("ocr_benchmark needs a document_number with a clean text layer")
        run_api_job(
            "/internal/airflow/ocr-benchmark",
            {"document_number": params["document_number"], "pages": params.get("pages") or 3},
        )
        return
    if action in ("backfill_dry_run", "backfill_corpus"):
        run_api_job(
            "/internal/airflow/backfill",
            {
                "from_year": params.get("from_year") or 1990,
                "limit": params.get("limit") or 300,
                "include_expired": str(bool(params.get("include_expired"))).lower(),
                "dry_run": str(action == "backfill_dry_run").lower(),
            },
        )
        if action == "backfill_corpus":
            run_api_job("/internal/airflow/process", {"limit": 1000})
            run_api_job("/internal/airflow/embed")
        return
    if action in ("prune_non_tax_dry_run", "prune_non_tax_apply"):
        run_api_job(
            "/internal/airflow/prune-non-tax",
            {"apply": str(action == "prune_non_tax_apply").lower()},
        )
        return
    process_params = {"limit": 1000}
    if action == "reocr_scanned_documents":
        process_params["reocr"] = "true"
    elif action == "retry_failed_documents":
        process_params["retry_failed"] = "true"
    else:
        raise ValueError(f"Unknown action: {action}")
    run_api_job("/internal/airflow/process", process_params)
    run_api_job("/internal/airflow/embed")


with DAG(
    dag_id="taxlens_corpus_maintenance",
    description="Manual OCR benchmark, re-OCR, and failed-document retry",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args={"owner": "taxlens", "retries": 1, "retry_delay": timedelta(minutes=2)},
    params={
        "action": Param(
            "ocr_benchmark",
            enum=[
                "ocr_benchmark",
                "reocr_scanned_documents",
                "retry_failed_documents",
                "prune_non_tax_dry_run",
                "prune_non_tax_apply",
                "backfill_dry_run",
                "backfill_corpus",
            ],
        ),
        # Only used by ocr_benchmark; optional so other actions can leave them empty.
        "document_number": Param(
            None, type=["null", "string"], description="ocr_benchmark only"
        ),
        "pages": Param(
            3, type=["null", "integer"], minimum=1, maximum=10, description="ocr_benchmark only"
        ),
        "from_year": Param(1990, type=["null", "integer"], description="backfill only"),
        "limit": Param(
            300, type=["null", "integer"], minimum=1, description="backfill: downloads per run"
        ),
        "include_expired": Param(False, type="boolean", description="backfill only"),
    },
    tags=["taxlens", "maintenance"],
) as dag:
    PythonOperator(task_id="run_maintenance", python_callable=run_maintenance)

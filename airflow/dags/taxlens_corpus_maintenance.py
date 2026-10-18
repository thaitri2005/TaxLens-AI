"""Manually triggered corpus maintenance (Trigger DAG w/ config in the Airflow UI).

- ``ocr_benchmark``: compare OCR settings on a PDF with a clean text layer; read the result
  table in the task log. Needs ``document_number``.
- ``reocr_scanned_documents``: re-run OCR for every OCR'd document with the current
  settings, then re-embed. Slow (minutes per long scan) and CPU-heavy on the API.
- ``retry_failed_documents``: retry versions whose processing failed, then embed.
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
            {"document_number": params["document_number"], "pages": params["pages"]},
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
            enum=["ocr_benchmark", "reocr_scanned_documents", "retry_failed_documents"],
        ),
        "document_number": Param("", type="string"),
        "pages": Param(3, type="integer", minimum=1, maximum=10),
    },
    tags=["taxlens", "maintenance"],
) as dag:
    PythonOperator(task_id="run_maintenance", python_callable=run_maintenance)

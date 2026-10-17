import os
import re
from datetime import datetime, timedelta

import httpx
from airflow import DAG
from airflow.operators.python import PythonOperator

# Container Apps ingress ends HTTP requests after 240 seconds, so every job runs as a
# loop of bounded calls; each call is idempotent and safe to retry.
REQUEST_TIMEOUT_SECONDS = 240


def _post(endpoint: str, params: dict[str, object] | None = None) -> str:
    base_url = os.getenv("TAXLENS_API_URL", "http://api:8000").rstrip("/")
    response = httpx.post(
        f"{base_url}{endpoint}",
        params=params,
        headers={"X-TaxLens-Internal-Token": os.environ["TAXLENS_AIRFLOW_INTERNAL_TOKEN"]},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return str(response.json().get("output", ""))


def run_api_job(endpoint: str, **_: object) -> None:
    print(_post(endpoint))


def process_documents(rechunk_outdated: bool = False, **_: object) -> None:
    """Process new versions (or re-chunk outdated ones) one bounded batch at a time."""

    batch_size = int(os.getenv("TAXLENS_PROCESS_BATCH_SIZE", "1"))
    max_batches = int(os.getenv("TAXLENS_PROCESS_MAX_BATCHES", "20"))
    if rechunk_outdated:
        # Re-chunking reads stored text (no OCR), so larger batches fit the time limit.
        batch_size, max_batches = max(batch_size, 10), max(max_batches, 50)
    if batch_size < 1 or max_batches < 1:
        raise ValueError("Processing batch settings must be at least 1")

    for batch_number in range(1, max_batches + 1):
        output = _post(
            "/internal/airflow/process",
            {"limit": batch_size, "rechunk_outdated": str(rechunk_outdated).lower()},
        )
        print(f"Processing batch {batch_number}/{max_batches}: {output}")
        if "Processing 0 document version(s)" in output:
            break


def embed_chunks(**_: object) -> None:
    batch_size = int(os.getenv("TAXLENS_EMBED_BATCH_SIZE", "400"))
    max_batches = int(os.getenv("TAXLENS_EMBED_MAX_BATCHES", "50"))
    for batch_number in range(1, max_batches + 1):
        output = _post("/internal/airflow/embed", {"limit": batch_size})
        print(f"Embedding batch {batch_number}/{max_batches}: {output}")
        remaining = re.search(r"(\d+) remaining", output)
        if remaining is None or remaining.group(1) == "0":
            break


with DAG(
    dag_id="tax_regulation_discovery_daily",
    description="Discover, process, and embed newly published Vietnamese tax documents",
    schedule="0 3 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "taxlens",
        "depends_on_past": False,
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
    },
    tags=["taxlens", "ingestion", "daily"],
) as dag:
    discover_and_ingest = PythonOperator(
        task_id="discover_and_ingest_government_sources",
        python_callable=run_api_job,
        op_kwargs={"endpoint": "/internal/airflow/ingest"},
    )
    process_pending = PythonOperator(
        task_id="process_pending_documents",
        python_callable=process_documents,
        # Existing backlog is still processed when today's portal crawl fails.
        trigger_rule="all_done",
    )
    rechunk_outdated = PythonOperator(
        task_id="rechunk_outdated_documents",
        python_callable=process_documents,
        op_kwargs={"rechunk_outdated": True},
    )
    embed = PythonOperator(
        task_id="embed_pending_chunks",
        python_callable=embed_chunks,
    )
    evaluate_retrieval = PythonOperator(
        task_id="evaluate_tax_retrieval",
        python_callable=run_api_job,
        op_kwargs={"endpoint": "/internal/airflow/evaluate-retrieval"},
    )

    discover_and_ingest >> process_pending >> rechunk_outdated >> embed >> evaluate_retrieval

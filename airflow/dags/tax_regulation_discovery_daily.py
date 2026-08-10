import os
from datetime import datetime, timedelta

import httpx
from airflow import DAG
from airflow.operators.python import PythonOperator


def run_api_job(endpoint: str, **_: object) -> None:
    base_url = os.getenv("TAXLENS_API_URL", "http://api:8000").rstrip("/")
    token = os.environ["TAXLENS_AIRFLOW_INTERNAL_TOKEN"]
    if endpoint == "/internal/airflow/process":
        _run_processing_batches(base_url, token)
        return
    response = httpx.post(
        f"{base_url}{endpoint}",
        headers={"X-TaxLens-Internal-Token": token},
        timeout=3600,
    )
    response.raise_for_status()
    print(response.text)


def _run_processing_batches(base_url: str, token: str) -> None:
    batch_size = int(os.getenv("TAXLENS_PROCESS_BATCH_SIZE", "5"))
    max_batches = int(os.getenv("TAXLENS_PROCESS_MAX_BATCHES", "20"))
    if batch_size < 1 or max_batches < 1:
        raise ValueError("Processing batch settings must be at least 1")

    for batch_number in range(1, max_batches + 1):
        response = httpx.post(
            f"{base_url}/internal/airflow/process",
            params={"limit": batch_size},
            headers={"X-TaxLens-Internal-Token": token},
            timeout=240,
        )
        response.raise_for_status()
        output = response.text
        print(f"Processing batch {batch_number}/{max_batches}: {output}")
        if '"Processing 0 document version(s)..."' in output:
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
    process_documents = PythonOperator(
        task_id="process_pending_documents",
        python_callable=run_api_job,
        op_kwargs={"endpoint": "/internal/airflow/process"},
    )
    embed_chunks = PythonOperator(
        task_id="embed_pending_chunks",
        python_callable=run_api_job,
        op_kwargs={"endpoint": "/internal/airflow/embed"},
    )
    evaluate_retrieval = PythonOperator(
        task_id="evaluate_tax_retrieval",
        python_callable=run_api_job,
        op_kwargs={"endpoint": "/internal/airflow/evaluate-retrieval"},
    )

    discover_and_ingest >> process_documents >> embed_chunks >> evaluate_retrieval

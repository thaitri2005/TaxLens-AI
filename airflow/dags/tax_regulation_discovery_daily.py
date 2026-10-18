import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from taxlens_jobs import run_api_job


def _process_limit() -> int:
    # Documents per run, kept compatible with the batch settings Terraform provides.
    batch_size = int(os.getenv("TAXLENS_PROCESS_BATCH_SIZE", "1"))
    max_batches = int(os.getenv("TAXLENS_PROCESS_MAX_BATCHES", "20"))
    return max(1, batch_size * max_batches)


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
        python_callable=run_api_job,
        op_kwargs={
            "endpoint": "/internal/airflow/process",
            "params": {"limit": _process_limit()},
        },
        # Existing backlog is still processed when today's portal crawl fails.
        trigger_rule="all_done",
    )
    rechunk_outdated = PythonOperator(
        task_id="rechunk_outdated_documents",
        python_callable=run_api_job,
        op_kwargs={
            "endpoint": "/internal/airflow/process",
            "params": {"limit": 1000, "rechunk_outdated": "true"},
        },
        # A document that fails OCR is recorded as failed; it must not block re-chunking
        # and embedding of everything else.
        trigger_rule="all_done",
    )
    embed = PythonOperator(
        task_id="embed_pending_chunks",
        python_callable=run_api_job,
        op_kwargs={"endpoint": "/internal/airflow/embed"},
        trigger_rule="all_done",
    )
    evaluate_retrieval = PythonOperator(
        task_id="evaluate_tax_retrieval",
        python_callable=run_api_job,
        op_kwargs={"endpoint": "/internal/airflow/evaluate-retrieval"},
    )

    discover_and_ingest >> process_pending >> rechunk_outdated >> embed >> evaluate_retrieval

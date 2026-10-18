"""Run TaxLens internal API jobs from Airflow tasks.

Jobs run in the background on the API; each HTTP call returns at once and the task polls
for completion. A single call must never approach the 240-second Container Apps ingress
limit, and regular polling keeps the scale-to-zero API replica alive while a job runs.
"""

import os
import time
from typing import Any

import httpx

REQUEST_TIMEOUT_SECONDS = 60
POLL_INTERVAL_SECONDS = 20
MAX_JOB_MINUTES = 370  # slightly above the API's own 6-hour job limit


def run_api_job(endpoint: str, params: dict[str, Any] | None = None, **_: object) -> str:
    """Start an internal API job (or reattach to the identical running one) and wait for it."""

    deadline = time.monotonic() + MAX_JOB_MINUTES * 60
    with httpx.Client(
        base_url=os.getenv("TAXLENS_API_URL", "http://api:8000").rstrip("/"),
        headers={"X-TaxLens-Internal-Token": os.environ["TAXLENS_AIRFLOW_INTERNAL_TOKEN"]},
        timeout=REQUEST_TIMEOUT_SECONDS,
    ) as client:
        response = client.post(endpoint, params=params)
        response.raise_for_status()
        job = response.json()
        print(f"Started {job['job']} as job {job['job_id']}")
        while job["status"] == "running":
            if time.monotonic() > deadline:
                raise TimeoutError(f"{job['job']} did not finish within {MAX_JOB_MINUTES} minutes")
            time.sleep(POLL_INTERVAL_SECONDS)
            response = client.get(f"/internal/airflow/jobs/{job['job_id']}")
            # 404 means the API restarted and lost the job; failing lets Airflow retry it.
            response.raise_for_status()
            job = response.json()
    print(job["output"])
    print(f"{job['job']} {job['status']} after {job['duration_seconds']}s")
    if job["status"] != "completed":
        raise RuntimeError(f"{job['job']} failed with exit code {job['exit_code']}")
    return str(job["output"])

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
# A scaled-to-zero API needs a few minutes to pull its image, start, and finish startup
# migrations; until then requests time out or get 502/503/504.
WARM_UP_SECONDS = 300
WARM_UP_RETRY_SECONDS = 15
_UNAVAILABLE_STATUS_CODES = {502, 503, 504}


def run_api_job(endpoint: str, params: dict[str, Any] | None = None, **_: object) -> str:
    """Start an internal API job (or reattach to the identical running one) and wait for it."""

    deadline = time.monotonic() + MAX_JOB_MINUTES * 60
    with httpx.Client(
        base_url=os.getenv("TAXLENS_API_URL", "http://api:8000").rstrip("/"),
        headers={"X-TaxLens-Internal-Token": os.environ["TAXLENS_AIRFLOW_INTERNAL_TOKEN"]},
        timeout=REQUEST_TIMEOUT_SECONDS,
    ) as client:
        # Retrying the start is safe: an identical running job is reattached, not duplicated.
        job = _request_json(client, "POST", endpoint, params)
        print(f"Started {job['job']} as job {job['job_id']}")
        while job["status"] == "running":
            if time.monotonic() > deadline:
                raise TimeoutError(f"{job['job']} did not finish within {MAX_JOB_MINUTES} minutes")
            time.sleep(POLL_INTERVAL_SECONDS)
            # 404 means the API restarted and lost the job; failing lets Airflow retry it.
            job = _request_json(client, "GET", f"/internal/airflow/jobs/{job['job_id']}")
    print(job["output"])
    print(f"{job['job']} {job['status']} after {job['duration_seconds']}s")
    if job["status"] != "completed":
        raise RuntimeError(f"{job['job']} failed with exit code {job['exit_code']}")
    return str(job["output"])


def _request_json(
    client: httpx.Client, method: str, url: str, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Send a request, retrying while the API is starting up or briefly unreachable."""

    give_up_at = time.monotonic() + WARM_UP_SECONDS
    while True:
        try:
            response = client.request(method, url, params=params)
            if response.status_code not in _UNAVAILABLE_STATUS_CODES:
                response.raise_for_status()
                result: dict[str, Any] = response.json()
                return result
            problem = f"HTTP {response.status_code}"
        except (httpx.TimeoutException, httpx.TransportError) as error:
            problem = type(error).__name__
        if time.monotonic() > give_up_at:
            raise RuntimeError(f"TaxLens API unavailable for {method} {url}: {problem}")
        print(f"TaxLens API not ready ({problem}); retrying in {WARM_UP_RETRY_SECONDS}s")
        time.sleep(WARM_UP_RETRY_SECONDS)

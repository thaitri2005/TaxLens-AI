import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest

JOBS_MODULE = Path(__file__).parents[1] / "airflow/dags/taxlens_jobs.py"


def _load_jobs_module(
    monkeypatch: pytest.MonkeyPatch, handler: Any
) -> ModuleType:
    spec = importlib.util.spec_from_file_location("taxlens_jobs", JOBS_MODULE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    real_client = httpx.Client

    def client(**kwargs: Any) -> httpx.Client:
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(module.httpx, "Client", client)
    monkeypatch.setattr(module, "POLL_INTERVAL_SECONDS", 0)
    monkeypatch.setenv("TAXLENS_AIRFLOW_INTERNAL_TOKEN", "token")
    return module


def test_run_api_job_polls_until_the_background_job_completes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    polls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-TaxLens-Internal-Token"] == "token"
        if request.method == "POST":
            return httpx.Response(202, json=_job("running"))
        polls.append(request.url.path)
        return httpx.Response(200, json=_job("running" if len(polls) < 3 else "completed"))

    jobs = _load_jobs_module(monkeypatch, handler)

    output = jobs.run_api_job("/internal/airflow/process", {"limit": 5})

    assert polls == ["/internal/airflow/jobs/abc"] * 3
    assert output == "Processing complete"


def test_run_api_job_fails_the_task_when_the_job_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(202, json=_job("running"))
        return httpx.Response(200, json=_job("failed", exit_code=1))

    jobs = _load_jobs_module(monkeypatch, handler)

    with pytest.raises(RuntimeError, match="exit code 1"):
        jobs.run_api_job("/internal/airflow/embed")


def test_run_api_job_prints_job_output_while_the_job_runs(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    pages = ["[1/2] DONE a\n", "[2/2] DONE b\n", "Processing complete\n"]
    offsets: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(202, json=_job("running", output="", offset=0))
        offsets.append(request.url.params.get("since"))
        index = len(offsets) - 1
        status = "running" if index < 2 else "completed"
        return httpx.Response(200, json=_job(status, output=pages[index], offset=index + 1))

    jobs = _load_jobs_module(monkeypatch, handler)

    output = jobs.run_api_job("/internal/airflow/process")

    assert offsets == ["0", "1", "2"]
    printed = capsys.readouterr().out
    assert printed.index("[1/2] DONE a") < printed.index("[2/2] DONE b")
    assert printed.count("[1/2] DONE a") == 1
    assert output.endswith("Processing complete\n")


def _job(
    status: str,
    exit_code: int | None = 0,
    output: str = "Processing complete",
    offset: int | None = None,
) -> dict[str, Any]:
    job: dict[str, Any] = {
        "job_id": "abc",
        "job": "process_corpus.py",
        "status": status,
        "exit_code": None if status == "running" else exit_code,
        "duration_seconds": 1.0,
        "output": output,
    }
    if offset is not None:
        job["output_offset"] = offset
    return job


def test_run_api_job_waits_for_a_cold_api_to_start(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            attempts.append("post")
            if len(attempts) == 1:
                raise httpx.ReadTimeout("cold start", request=request)
            if len(attempts) == 2:
                return httpx.Response(503, json={"detail": "not ready"})
            return httpx.Response(202, json=_job("running"))
        return httpx.Response(200, json=_job("completed"))

    jobs = _load_jobs_module(monkeypatch, handler)
    monkeypatch.setattr(jobs, "WARM_UP_RETRY_SECONDS", 0)

    assert jobs.run_api_job("/internal/airflow/ocr-benchmark") == "Processing complete"
    assert attempts == ["post", "post", "post"]


def test_run_api_job_does_not_retry_client_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Unauthorized internal job"})

    jobs = _load_jobs_module(monkeypatch, handler)

    with pytest.raises(httpx.HTTPStatusError):
        jobs.run_api_job("/internal/airflow/embed")

import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import taxlens.api.routes.internal_jobs as internal_jobs
from taxlens.api.main import create_app

TOKEN = "test-token"


def test_airflow_job_authorization_rejects_missing_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        internal_jobs,
        "get_settings",
        lambda: SimpleNamespace(airflow_internal_token=TOKEN),
    )

    with pytest.raises(HTTPException) as error:
        internal_jobs._authorize(None)

    assert error.value.status_code == 401


def test_jobs_run_in_the_background_and_report_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client_with_scripts(
        tmp_path, monkeypatch, {"embed_corpus.py": "import time\ntime.sleep(0.5)\nprint('done')\n"}
    )

    started = client.post("/internal/airflow/embed", headers={"X-TaxLens-Internal-Token": TOKEN})

    assert started.status_code == 202
    assert started.json()["status"] == "running"
    finished = _wait(client, started.json()["job_id"])
    assert finished["status"] == "completed"
    assert finished["exit_code"] == 0
    assert "done" in finished["output"]


def test_a_retry_reattaches_to_the_identical_running_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client_with_scripts(
        tmp_path, monkeypatch, {"embed_corpus.py": "import time\ntime.sleep(1)\n"}
    )
    headers = {"X-TaxLens-Internal-Token": TOKEN}

    first = client.post("/internal/airflow/embed", headers=headers).json()
    retry = client.post("/internal/airflow/embed", headers=headers).json()
    other = client.post("/internal/airflow/embed", params={"limit": 5}, headers=headers).json()

    assert retry["job_id"] == first["job_id"]
    assert other["job_id"] != first["job_id"]
    _wait(client, first["job_id"])
    _wait(client, other["job_id"])


def test_failed_jobs_report_their_exit_code_and_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client_with_scripts(
        tmp_path, monkeypatch, {"evaluate_tax_retrieval.py": "raise SystemExit('broken corpus')\n"}
    )

    started = client.post(
        "/internal/airflow/evaluate-retrieval", headers={"X-TaxLens-Internal-Token": TOKEN}
    ).json()
    finished = _wait(client, started["job_id"])

    assert finished["status"] == "failed"
    assert finished["exit_code"] == 1
    assert "broken corpus" in finished["output"]


def test_unknown_jobs_return_not_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client_with_scripts(tmp_path, monkeypatch, {})

    response = client.get(
        "/internal/airflow/jobs/missing", headers={"X-TaxLens-Internal-Token": TOKEN}
    )

    assert response.status_code == 404


def _client_with_scripts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scripts: dict[str, str]
) -> TestClient:
    scripts_directory = tmp_path / "scripts"
    scripts_directory.mkdir()
    for name, source in scripts.items():
        (scripts_directory / name).write_text(source, encoding="utf-8")
    monkeypatch.setattr(internal_jobs, "SCRIPTS_DIRECTORY", scripts_directory)
    monkeypatch.setattr(internal_jobs, "WORKING_DIRECTORY", tmp_path)
    monkeypatch.setattr(internal_jobs, "_jobs", {})
    monkeypatch.setattr(
        internal_jobs, "get_settings", lambda: SimpleNamespace(airflow_internal_token=TOKEN)
    )
    assert sys.executable
    return TestClient(create_app())


def _wait(client: TestClient, job_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        job: dict[str, Any] = client.get(
            f"/internal/airflow/jobs/{job_id}", headers={"X-TaxLens-Internal-Token": TOKEN}
        ).json()
        if job["status"] != "running":
            return job
        time.sleep(0.1)
    raise AssertionError(f"job {job_id} did not finish")

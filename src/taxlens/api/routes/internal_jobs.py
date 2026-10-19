"""Internal job endpoints for Airflow.

Jobs run as background subprocesses: a POST starts one (or reattaches to the identical job
already running) and returns at once, and Airflow polls ``GET /jobs/{job_id}``. Holding the
HTTP request open instead failed whenever a job outlasted the 240-second Container Apps
ingress limit, which a single long scanned PDF does; the API then scaled to zero and killed
the orphaned job.
"""

import hmac
import logging
import os
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, status

from taxlens.config import get_settings

router = APIRouter(prefix="/internal/airflow", tags=["internal"])
logger = logging.getLogger(__name__)

SCRIPTS_DIRECTORY = Path("/workspace/scripts")
WORKING_DIRECTORY = Path("/workspace")
MAX_JOB_SECONDS = 6 * 60 * 60
FINISHED_JOB_RETENTION_SECONDS = 24 * 60 * 60
OUTPUT_TAIL_CHARACTERS = 4000


@dataclass
class _Job:
    id: str
    script: str
    arguments: list[str]
    process: subprocess.Popen[bytes]
    output_path: Path
    started_at: float = field(default_factory=time.monotonic)
    finished_at: float | None = None
    timed_out: bool = False


_jobs: dict[str, _Job] = {}
_jobs_lock = Lock()


@router.post("/ingest", status_code=status.HTTP_202_ACCEPTED)
def run_ingestion_job(
    x_taxlens_internal_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """Daily collection: tax documents issued in the last 60 days.

    Only the government portal is used: the Ministry of Finance database refuses
    connections from Azure and is collected from a machine in Vietnam (docs/sources.md).
    """

    _authorize(x_taxlens_internal_token)
    return _start_job(
        "collect_sources.py",
        ["--source", "government", "--since-days", "60", "--limit", _source_limit()],
    )


@router.post("/backfill", status_code=status.HTTP_202_ACCEPTED)
def run_backfill_job(
    x_taxlens_internal_token: str | None = Header(default=None),
    from_year: int = Query(default=1990, ge=1945, le=2100),
    limit: int = Query(default=300, ge=1, le=2000),
    include_expired: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Historical collection, at most ``limit`` downloads per run; repeat until done."""

    _authorize(x_taxlens_internal_token)
    arguments = ["--source", "government", "--from-year", str(from_year), "--limit", str(limit)]
    if include_expired:
        arguments.append("--include-expired")
    if dry_run:
        arguments.append("--dry-run")
    return _start_job("collect_sources.py", arguments)


@router.post("/process", status_code=status.HTTP_202_ACCEPTED)
def run_processing_job(
    x_taxlens_internal_token: str | None = Header(default=None),
    limit: int = Query(default=20, ge=1, le=1000),
    retry_failed: bool = False,
    rechunk_outdated: bool = False,
    reocr: bool = False,
) -> dict[str, Any]:
    _authorize(x_taxlens_internal_token)
    arguments = ["--limit", str(limit)]
    if retry_failed:
        arguments.append("--retry-failed")
    if rechunk_outdated:
        arguments.append("--rechunk-outdated")
    if reocr:
        arguments.append("--reocr")
    return _start_job("process_corpus.py", arguments)


@router.post("/embed", status_code=status.HTTP_202_ACCEPTED)
def run_embedding_job(
    x_taxlens_internal_token: str | None = Header(default=None),
    limit: int | None = Query(default=None, ge=1),
) -> dict[str, Any]:
    _authorize(x_taxlens_internal_token)
    return _start_job("embed_corpus.py", ["--limit", str(limit)] if limit else [])


@router.post("/evaluate-retrieval", status_code=status.HTTP_202_ACCEPTED)
def run_retrieval_evaluation_job(
    x_taxlens_internal_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _authorize(x_taxlens_internal_token)
    return _start_job("evaluate_tax_retrieval.py", [])


@router.post("/ocr-benchmark", status_code=status.HTTP_202_ACCEPTED)
def run_ocr_benchmark_job(
    document_number: str = Query(min_length=1, max_length=100),
    pages: int = Query(default=3, ge=1, le=10),
    x_taxlens_internal_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _authorize(x_taxlens_internal_token)
    return _start_job(
        "benchmark_ocr.py", ["--document-number", document_number, "--pages", str(pages)]
    )


@router.post("/prune-non-tax", status_code=status.HTTP_202_ACCEPTED)
def run_prune_non_tax_job(
    apply: bool = False,
    x_taxlens_internal_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _authorize(x_taxlens_internal_token)
    return _start_job("prune_non_tax_documents.py", ["--apply"] if apply else [])


@router.get("/jobs/{job_id}")
def get_job(
    job_id: str,
    x_taxlens_internal_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _authorize(x_taxlens_internal_token)
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            # Jobs live in this process; a restart (deploy, crash) loses them.
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown job")
        return _job_status(job)


def _authorize(token: str | None) -> None:
    expected = get_settings().airflow_internal_token
    if not expected or not token or not hmac.compare_digest(token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized internal job",
        )


def _start_job(script_name: str, arguments: list[str]) -> dict[str, Any]:
    script_path = SCRIPTS_DIRECTORY / script_name
    if not script_path.is_file():
        raise HTTPException(status_code=500, detail=f"Job script is unavailable: {script_name}")
    with _jobs_lock:
        _forget_old_jobs()
        for job in _jobs.values():
            # An Airflow retry of a task whose job is still running reattaches to it
            # instead of processing the same documents twice.
            if job.script == script_name and job.arguments == arguments and _is_running(job):
                return _job_status(job)
        descriptor, output_name = tempfile.mkstemp(prefix="taxlens-job-", suffix=".log")
        os.close(descriptor)
        # The child writes through its own append-mode handle; the API reads the file by
        # path, so reading never moves the child's write position.
        with open(output_name, "ab") as output:
            process = subprocess.Popen(
                [sys.executable, str(script_path), *arguments],
                cwd=WORKING_DIRECTORY,
                env=os.environ | {"PYTHONPATH": str(WORKING_DIRECTORY / "src")},
                stdout=output,
                stderr=subprocess.STDOUT,
            )
        job = _Job(
            id=uuid.uuid4().hex,
            script=script_name,
            arguments=arguments,
            process=process,
            output_path=Path(output_name),
        )
        _jobs[job.id] = job
        logger.info("job_started", extra={"taxlens_job": script_name, "taxlens_job_id": job.id})
        return _job_status(job)


def _is_running(job: _Job) -> bool:
    if job.finished_at is not None:
        return False
    if job.process.poll() is None:
        if time.monotonic() - job.started_at <= MAX_JOB_SECONDS:
            return True
        job.process.kill()
        job.process.wait()
        job.timed_out = True
    job.finished_at = time.monotonic()
    succeeded = job.process.returncode == 0 and not job.timed_out
    logger.log(
        logging.INFO if succeeded else logging.ERROR,
        "job_completed" if succeeded else "job_failed",
        extra={
            "taxlens_job": job.script,
            "taxlens_job_id": job.id,
            "taxlens_exit_code": job.process.returncode,
            "taxlens_duration_ms": round((job.finished_at - job.started_at) * 1000, 2),
        },
    )
    return False


def _job_status(job: _Job) -> dict[str, Any]:
    running = _is_running(job)
    if running:
        state = "running"
    elif job.process.returncode == 0 and not job.timed_out:
        state = "completed"
    else:
        state = "failed"
    end = time.monotonic() if job.finished_at is None else job.finished_at
    return {
        "job_id": job.id,
        "job": job.script,
        "status": state,
        "exit_code": None if running else job.process.returncode,
        "timed_out": job.timed_out,
        "duration_seconds": round(end - job.started_at, 1),
        "output": _output_tail(job.output_path),
    }


def _output_tail(path: Path) -> str:
    try:
        with path.open("rb") as output:
            size = output.seek(0, os.SEEK_END)
            output.seek(max(0, size - OUTPUT_TAIL_CHARACTERS * 4))
            return output.read().decode("utf-8", errors="replace")[-OUTPUT_TAIL_CHARACTERS:]
    except OSError:
        return ""


def _forget_old_jobs() -> None:
    now = time.monotonic()
    for job_id in [
        job.id
        for job in _jobs.values()
        if job.finished_at is not None
        and now - job.finished_at > FINISHED_JOB_RETENTION_SECONDS
    ]:
        _jobs.pop(job_id).output_path.unlink(missing_ok=True)


def _source_limit() -> str:
    return os.getenv("TAXLENS_DAILY_SOURCE_LIMIT", "100")

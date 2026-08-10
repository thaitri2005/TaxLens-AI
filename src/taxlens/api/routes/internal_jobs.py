import logging
import os
import subprocess
import sys
import time
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, status

from taxlens.config import get_settings

router = APIRouter(prefix="/internal/airflow", tags=["internal"])
logger = logging.getLogger(__name__)


@router.post("/ingest")
def run_ingestion_job(
    x_taxlens_internal_token: str | None = Header(default=None),
) -> dict[str, str]:
    _authorize(x_taxlens_internal_token)
    return _run_script(
        "ingest_sources.py",
        [
            "--source",
            "government",
            "--limit",
            _source_limit(),
            "--pages",
            _discovery_pages(),
            "--download",
        ],
    )


@router.post("/process")
def run_processing_job(
    x_taxlens_internal_token: str | None = Header(default=None),
) -> dict[str, str]:
    _authorize(x_taxlens_internal_token)
    return _run_script("process_corpus.py", [])


@router.post("/embed")
def run_embedding_job(
    x_taxlens_internal_token: str | None = Header(default=None),
) -> dict[str, str]:
    _authorize(x_taxlens_internal_token)
    return _run_script("embed_corpus.py", [])


@router.post("/evaluate-retrieval")
def run_retrieval_evaluation_job(
    x_taxlens_internal_token: str | None = Header(default=None),
) -> dict[str, str]:
    _authorize(x_taxlens_internal_token)
    return _run_script("evaluate_tax_retrieval.py", [])


def _authorize(token: str | None) -> None:
    expected = get_settings().airflow_internal_token
    if not expected or token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized internal job",
        )


def _run_script(script_name: str, arguments: list[str]) -> dict[str, str]:
    script_path = Path("/workspace/scripts") / script_name
    if not script_path.is_file():
        raise HTTPException(status_code=500, detail=f"Job script is unavailable: {script_name}")
    environment = os.environ | {"PYTHONPATH": "/workspace/src"}
    started = time.perf_counter()
    logger.info("job_started", extra={"taxlens_job": script_name})
    try:
        result = subprocess.run(
            [sys.executable, str(script_path), *arguments],
            cwd="/workspace",
            env=environment,
            check=True,
            capture_output=True,
            text=True,
            timeout=3600,
        )
    except subprocess.CalledProcessError as error:
        logger.error(
            "job_failed",
            extra={
                "taxlens_job": script_name,
                "taxlens_duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        raise HTTPException(status_code=500, detail=error.stderr[-4000:]) from error
    except subprocess.TimeoutExpired as error:
        logger.error(
            "job_timed_out",
            extra={
                "taxlens_job": script_name,
                "taxlens_duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        raise HTTPException(status_code=504, detail=f"Job timed out: {script_name}") from error
    logger.info(
        "job_completed",
        extra={
            "taxlens_job": script_name,
            "taxlens_duration_ms": round((time.perf_counter() - started) * 1000, 2),
        },
    )
    return {"status": "completed", "job": script_name, "output": result.stdout[-4000:]}


def _source_limit() -> str:
    return os.getenv("TAXLENS_DAILY_SOURCE_LIMIT", "100")


def _discovery_pages() -> str:
    return os.getenv("TAXLENS_DISCOVERY_PAGES", "10")

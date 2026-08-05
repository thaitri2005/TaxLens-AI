import os
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, status

from taxlens.config import get_settings

router = APIRouter(prefix="/internal/airflow", tags=["internal"])


@router.post("/ingest")
def run_ingestion_job(
    x_taxlens_internal_token: str | None = Header(default=None),
) -> dict[str, str]:
    _authorize(x_taxlens_internal_token)
    return _run_script(
        "ingest_sources.py",
        ["--source", "government", "--limit", _source_limit(), "--download"],
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
        raise HTTPException(status_code=500, detail=error.stderr[-4000:]) from error
    except subprocess.TimeoutExpired as error:
        raise HTTPException(status_code=504, detail=f"Job timed out: {script_name}") from error
    return {"status": "completed", "job": script_name, "output": result.stdout[-4000:]}


def _source_limit() -> str:
    return os.getenv("TAXLENS_DAILY_SOURCE_LIMIT", "5")

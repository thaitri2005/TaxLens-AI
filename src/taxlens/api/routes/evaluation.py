from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from taxlens.api.auth import require_authenticated_user
from taxlens.evaluation.reports import load_latest_retrieval_report

router = APIRouter(
    prefix="/evaluation",
    tags=["evaluation"],
    dependencies=[Depends(require_authenticated_user)],
)


@router.get("/retrieval/latest", response_model=dict[str, Any])
def latest_retrieval_evaluation() -> dict[str, Any]:
    try:
        return load_latest_retrieval_report()
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No retrieval evaluation report has been generated yet",
        ) from error

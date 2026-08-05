from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import taxlens.api.routes.internal_jobs as internal_jobs


def test_airflow_job_authorization_rejects_missing_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        internal_jobs,
        "get_settings",
        lambda: SimpleNamespace(airflow_internal_token="test-token"),
    )

    with pytest.raises(HTTPException) as error:
        internal_jobs._authorize(None)

    assert error.value.status_code == 401

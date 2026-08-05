import logging
from collections.abc import Mapping
from contextlib import AbstractContextManager, nullcontext
from importlib import import_module
from time import time
from typing import Any, cast

import httpx

from taxlens.config import Settings, get_settings

logger = logging.getLogger(__name__)


class ExperimentTracker:
    def start_run(self, run_name: str) -> AbstractContextManager[Any]:
        return nullcontext()

    def log_params(self, params: Mapping[str, str | int | float | bool]) -> None:
        return None

    def log_metrics(self, metrics: Mapping[str, float]) -> None:
        return None


class MlflowTracker(ExperimentTracker):
    def __init__(self, settings: Settings) -> None:
        self._mlflow: Any = import_module("mlflow")
        self._mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
        self._mlflow.set_experiment(settings.mlflow_experiment_name)

    def start_run(self, run_name: str) -> AbstractContextManager[Any]:
        return cast(AbstractContextManager[Any], self._mlflow.start_run(run_name=run_name))

    def log_params(self, params: Mapping[str, str | int | float | bool]) -> None:
        self._mlflow.log_params(dict(params))

    def log_metrics(self, metrics: Mapping[str, float]) -> None:
        self._mlflow.log_metrics(dict(metrics))


class MlflowRestTracker(ExperimentTracker):
    """Small MLflow REST client for the API image's evaluation-only workflow."""

    def __init__(self, settings: Settings) -> None:
        self._client = httpx.Client(base_url=settings.mlflow_tracking_uri.rstrip("/"), timeout=15)
        response = self._client.get(
            "/api/2.0/mlflow/experiments/get-by-name",
            params={"experiment_name": settings.mlflow_experiment_name},
        )
        if response.status_code == 404:
            response = self._client.post(
                "/api/2.0/mlflow/experiments/create",
                json={"name": settings.mlflow_experiment_name},
            )
        response.raise_for_status()
        self._experiment_id = str(response.json()["experiment"]["experiment_id"])
        self._run_id: str | None = None

    def start_run(self, run_name: str) -> AbstractContextManager[Any]:
        return _MlflowRestRun(self, run_name)

    def _start(self, run_name: str) -> None:
        response = self._client.post(
            "/api/2.0/mlflow/runs/create",
            json={
                "experiment_id": self._experiment_id,
                "start_time": int(time() * 1000),
                "tags": [{"key": "mlflow.runName", "value": run_name}],
            },
        )
        response.raise_for_status()
        self._run_id = str(response.json()["run"]["info"]["run_id"])

    def _finish(self, status: str) -> None:
        if self._run_id is None:
            return
        response = self._client.post(
            "/api/2.0/mlflow/runs/update",
            json={
                "run_id": self._run_id,
                "status": status,
                "end_time": int(time() * 1000),
            },
        )
        response.raise_for_status()

    def log_params(self, params: Mapping[str, str | int | float | bool]) -> None:
        self._log_batch(
            params=[{"key": key, "value": str(value)} for key, value in params.items()]
        )

    def log_metrics(self, metrics: Mapping[str, float]) -> None:
        self._log_batch(
            metrics=[
                {"key": key, "value": value, "timestamp": int(time() * 1000), "step": 0}
                for key, value in metrics.items()
            ]
        )

    def _log_batch(
        self,
        *,
        params: list[dict[str, str]] | None = None,
        metrics: list[dict[str, float | int | str]] | None = None,
    ) -> None:
        if self._run_id is None:
            raise RuntimeError("MLflow run has not started")
        response = self._client.post(
            "/api/2.0/mlflow/runs/log-batch",
            json={"run_id": self._run_id, "params": params or [], "metrics": metrics or []},
        )
        response.raise_for_status()


class _MlflowRestRun:
    def __init__(self, tracker: MlflowRestTracker, run_name: str) -> None:
        self._tracker = tracker
        self._run_name = run_name

    def __enter__(self) -> MlflowRestTracker:
        self._tracker._start(self._run_name)
        return self._tracker

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self._tracker._finish("FAILED" if exc_type else "FINISHED")


def get_experiment_tracker(settings: Settings | None = None) -> ExperimentTracker:
    resolved_settings = settings or get_settings()
    if not resolved_settings.mlflow_enabled:
        return ExperimentTracker()
    try:
        return MlflowTracker(resolved_settings)
    except ImportError:
        try:
            return MlflowRestTracker(resolved_settings)
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            logger.warning("MLflow tracking unavailable: %s", error)
            return ExperimentTracker()

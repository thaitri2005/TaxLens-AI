import logging
from collections.abc import Mapping
from contextlib import AbstractContextManager, nullcontext
from importlib import import_module
from typing import Any, cast

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


def get_experiment_tracker(settings: Settings | None = None) -> ExperimentTracker:
    resolved_settings = settings or get_settings()
    if not resolved_settings.mlflow_enabled:
        return ExperimentTracker()
    try:
        return MlflowTracker(resolved_settings)
    except ImportError:
        logger.warning("MLflow is enabled but not installed; metrics will not be tracked")
        return ExperimentTracker()

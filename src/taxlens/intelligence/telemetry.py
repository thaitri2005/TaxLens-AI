import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelCallTelemetry:
    model: str
    provider: str | None
    latency_ms: float
    input_tokens: int | None
    output_tokens: int | None
    outcome: str


def record_model_call(telemetry: ModelCallTelemetry) -> None:
    logger.info(
        "model_call",
        extra={
            "taxlens_model": telemetry.model,
            "taxlens_provider": telemetry.provider,
            "taxlens_latency_ms": round(telemetry.latency_ms, 2),
            "taxlens_input_tokens": telemetry.input_tokens,
            "taxlens_output_tokens": telemetry.output_tokens,
            "taxlens_outcome": telemetry.outcome,
        },
    )

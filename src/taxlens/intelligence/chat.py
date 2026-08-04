from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

import httpx

from taxlens.config import Settings, get_settings
from taxlens.intelligence.telemetry import ModelCallTelemetry, record_model_call

ChatRole = Literal["system", "user", "assistant"]


class ChatProviderError(RuntimeError):
    """Raised when a configured chat provider cannot return a usable response."""


@dataclass(frozen=True)
class ChatMessage:
    role: ChatRole
    content: str


@dataclass(frozen=True)
class ChatRequest:
    messages: list[ChatMessage]
    max_output_tokens: int | None = None
    temperature: float | None = None


@dataclass(frozen=True)
class ChatResponse:
    content: str
    requested_model: str
    provider_name: str | None
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: float = 0.0


class ChatProvider(Protocol):
    def complete(self, request: ChatRequest) -> ChatResponse: ...


class HuggingFaceChatProvider:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self._token = settings.hf_token
        self._base_url = settings.hf_chat_base_url.rstrip("/")
        self._model = _routed_model(settings.hf_chat_model, settings.hf_chat_routing_policy)
        self._timeout_seconds = settings.hf_chat_timeout_seconds
        self._max_output_tokens = settings.hf_chat_max_output_tokens
        self._temperature = settings.hf_chat_temperature
        self._client = client or httpx.Client(timeout=self._timeout_seconds)

    def complete(self, request: ChatRequest) -> ChatResponse:
        from time import perf_counter

        started_at = perf_counter()
        if not self._token:
            raise ChatProviderError("HF_TOKEN is required to call Hugging Face chat inference")

        max_output_tokens = request.max_output_tokens or self._max_output_tokens
        if max_output_tokens > self._max_output_tokens:
            raise ChatProviderError("Requested output exceeds HF_CHAT_MAX_OUTPUT_TOKENS")

        try:
            response = self._client.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._token}"},
                json={
                    "model": self._model,
                    "messages": [
                        {"role": message.role, "content": message.content}
                        for message in request.messages
                    ],
                    "max_tokens": max_output_tokens,
                    "temperature": (
                        request.temperature
                        if request.temperature is not None
                        else self._temperature
                    ),
                    "stream": False,
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            record_model_call(
                ModelCallTelemetry(
                    model=self._model,
                    provider=None,
                    latency_ms=(perf_counter() - started_at) * 1000,
                    input_tokens=None,
                    output_tokens=None,
                    outcome="error",
                )
            )
            raise ChatProviderError("Hugging Face chat inference request failed") from error

        payload = response.json()
        if not isinstance(payload, dict):
            raise ChatProviderError("Hugging Face returned an invalid chat response")
        try:
            content = payload["choices"][0]["message"]["content"]
        except (IndexError, KeyError, TypeError) as error:
            raise ChatProviderError("Hugging Face returned an invalid chat response") from error
        if not isinstance(content, str) or not content.strip():
            raise ChatProviderError("Hugging Face returned an empty chat response")

        usage_value = payload.get("usage", {})
        usage = usage_value if isinstance(usage_value, dict) else {}
        latency_ms = (perf_counter() - started_at) * 1000
        record_model_call(
            ModelCallTelemetry(
                model=self._model,
                provider=_provider_name(payload),
                latency_ms=latency_ms,
                input_tokens=_optional_int(usage.get("prompt_tokens")),
                output_tokens=_optional_int(usage.get("completion_tokens")),
                outcome="success",
            )
        )
        return ChatResponse(
            content=content,
            requested_model=self._model,
            provider_name=_provider_name(payload),
            input_tokens=_optional_int(usage.get("prompt_tokens")),
            output_tokens=_optional_int(usage.get("completion_tokens")),
            latency_ms=latency_ms,
        )


def get_chat_provider() -> ChatProvider:
    return HuggingFaceChatProvider(get_settings())


def _routed_model(model: str, routing_policy: str) -> str:
    normalized_model = model.strip()
    normalized_policy = routing_policy.strip()
    if not normalized_model:
        raise ChatProviderError("HF_CHAT_MODEL must not be empty")
    if not normalized_policy:
        return normalized_model
    return f"{normalized_model}:{normalized_policy}"


def _provider_name(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    provider = payload.get("provider")
    return provider if isinstance(provider, str) else None


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) else None

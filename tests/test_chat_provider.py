import json

import httpx
import pytest

from taxlens.config import Settings
from taxlens.intelligence.chat import (
    ChatMessage,
    ChatProviderError,
    ChatRequest,
    HuggingFaceChatProvider,
)


def test_hugging_face_provider_uses_configured_model_and_policy() -> None:
    captured_request: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_request.update(json.loads(request.content))
        assert request.headers["Authorization"] == "Bearer test-token"
        return httpx.Response(
            200,
            json={
                "provider": "nscale",
                "choices": [{"message": {"content": "Trả lời có dẫn chiếu."}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 7},
            },
        )

    provider = HuggingFaceChatProvider(
        Settings(
            hf_token="test-token",
            hf_chat_model="example/vietnamese-model",
            hf_chat_routing_policy="cheapest",
            hf_chat_max_output_tokens=20,
            hf_chat_temperature=0.1,
        ),
        httpx.Client(transport=httpx.MockTransport(handler)),
    )

    response = provider.complete(
        ChatRequest(messages=[ChatMessage(role="user", content="Xin chào")])
    )

    assert captured_request["model"] == "example/vietnamese-model:cheapest"
    assert captured_request["max_tokens"] == 20
    assert captured_request["temperature"] == 0.1
    assert response.content == "Trả lời có dẫn chiếu."
    assert response.provider_name == "nscale"
    assert response.input_tokens == 12
    assert response.output_tokens == 7


def test_hugging_face_provider_rejects_missing_token_and_output_cap_bypass() -> None:
    without_token = HuggingFaceChatProvider(Settings(hf_token=None))
    with_token = HuggingFaceChatProvider(
        Settings(hf_token="test-token", hf_chat_max_output_tokens=20)
    )
    request = ChatRequest(messages=[ChatMessage(role="user", content="Xin chào")])

    with pytest.raises(ChatProviderError, match="HF_TOKEN"):
        without_token.complete(request)
    with pytest.raises(ChatProviderError, match="HF_CHAT_MAX_OUTPUT_TOKENS"):
        with_token.complete(
            ChatRequest(
                messages=[ChatMessage(role="user", content="Xin chào")], max_output_tokens=21
            )
        )

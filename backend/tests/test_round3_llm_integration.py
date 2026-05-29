from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from conftest import API_PREFIX, data_of, object_id, post_json


pytestmark = pytest.mark.contract

ROUND3_SECRET = "sk-round3-test-secret"
AUTH_SECRET = "Bearer sk-round3-test-secret"
TOKEN_SECRET = "round3-token-secret"


def serialized(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def assert_no_round3_secret(payload: Any) -> None:
    text = serialized(payload)
    forbidden = (
        ROUND3_SECRET,
        AUTH_SECRET,
        TOKEN_SECRET,
        "Authorization",
    )
    leaked = [item for item in forbidden if item in text]
    assert not leaked, f"LLM response leaked sensitive markers {leaked}: {payload!r}"


def assert_error_is_sanitized(payload: Any) -> None:
    assert_no_round3_secret(payload)
    text = serialized(payload)
    forbidden_field_names = ("api_key", "Authorization", "authorization", "token")
    leaked = [item for item in forbidden_field_names if item in text]
    assert not leaked, f"LLM error response leaked sensitive field markers {leaked}: {payload!r}"


def create_llm_config(client, *, enabled: bool = True) -> int | str:
    data = post_json(
        client,
        f"{API_PREFIX}/llm-configs",
        {
            "name": "round3-contract-llm",
            "provider": "openai-compatible",
            "model": "round3-mock-model",
            "base_url": "https://llm.round3.invalid/v1",
            "api_key": ROUND3_SECRET,
            "enabled": enabled,
            "is_enabled": enabled,
        },
    )
    assert_no_round3_secret(data)
    return object_id(data, "id", "config_id")


def usage_call_count(client) -> int:
    stats = data_of(client.get(f"{API_PREFIX}/llm-usage/statistics"))
    assert_no_round3_secret(stats)
    if isinstance(stats, dict) and isinstance(stats.get("total_calls"), int):
        return stats["total_calls"]
    modules = stats.get("by_module", []) if isinstance(stats, dict) else []
    return sum(int(item.get("count", 0)) for item in modules if isinstance(item, dict))


def assert_usage_increased(client, before: int) -> None:
    after = usage_call_count(client)
    assert after > before, f"LLM usage did not increase: before={before}, after={after}"


def block_real_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked_request(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("Round 3 LLM contract tests must not call real network")

    monkeypatch.setattr(httpx.Client, "request", blocked_request)
    monkeypatch.setattr(httpx.AsyncClient, "request", blocked_request)


class MockLlmClient:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        self.calls: list[tuple[str, Any]] = []

    def test_connection(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        self.calls.append(("test_connection", _kwargs))
        return {
            "connected": True,
            "status": "connected",
            "model": "round3-mock-model",
            "usage": {"input_tokens": 3, "output_tokens": 2},
        }

    async def atest_connection(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return self.test_connection(*_args, **_kwargs)

    def list_models(self, *_args: Any, **_kwargs: Any) -> tuple[dict[str, Any], int]:
        self.calls.append(("list_models", _kwargs))
        return {"data": [{"id": "round3-mock-model"}]}, 4

    def chat(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        self.calls.append(("chat", _kwargs))
        return {
            "reply": "round3 mock model reply",
            "content": "round3 mock model reply",
            "model": "round3-mock-model",
            "usage": {"input_tokens": 5, "output_tokens": 7},
        }

    async def achat(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return self.chat(*_args, **_kwargs)

    def chat_completions(self, *_args: Any, **_kwargs: Any) -> tuple[dict[str, Any], int]:
        self.calls.append(("chat_completions", _kwargs))
        return {
            "choices": [{"message": {"content": "round3 mock model reply"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 7},
        }, 6


def install_mock_llm_client(monkeypatch: pytest.MonkeyPatch) -> None:
    import aitest_platform.api.router as router

    monkeypatch.setattr(router, "OpenAICompatibleLLMClient", MockLlmClient, raising=False)
    monkeypatch.setattr(router, "OpenAICompatibleClient", MockLlmClient, raising=False)
    monkeypatch.setattr(router, "LlmClient", MockLlmClient, raising=False)
    monkeypatch.setattr(router, "create_llm_client", lambda *_args, **_kwargs: MockLlmClient(), raising=False)
    monkeypatch.setattr(router, "get_llm_client", lambda *_args, **_kwargs: MockLlmClient(), raising=False)


def test_llm_config_test_disabled_mode_skips_without_network_or_secret(monkeypatch, client):
    monkeypatch.delenv("AITEST_ENABLE_REAL_LLM", raising=False)
    monkeypatch.setenv("AITEST_LLM_API_KEY", ROUND3_SECRET)
    block_real_network(monkeypatch)

    config_id = create_llm_config(client, enabled=True)
    response = data_of(client.post(f"{API_PREFIX}/llm-configs/{config_id}/test"))

    assert_no_round3_secret(response)
    assert response.get("connected") is False
    assert str(response.get("status", "")).lower() in {"skipped", "disabled", "fallback"}


def test_chat_disabled_mode_returns_structured_fallback_without_secret(monkeypatch, client):
    monkeypatch.setenv("AITEST_ENABLE_REAL_LLM", "false")
    monkeypatch.setenv("AITEST_LLM_API_KEY", ROUND3_SECRET)
    block_real_network(monkeypatch)

    response = data_of(
        client.post(
            f"{API_PREFIX}/chat",
            json={
                "message": "Use the configured LLM, but never echo secrets.",
                "context": {"api_key": ROUND3_SECRET, "token": TOKEN_SECRET},
            },
            headers={"Authorization": AUTH_SECRET},
        )
    )

    assert_no_round3_secret(response)
    assert isinstance(response, dict), response
    reply = response.get("reply") or response.get("content") or response.get("message")
    assert isinstance(reply, str) and reply.strip(), response
    assert any(marker in serialized(response).lower() for marker in ("fallback", "disabled", "placeholder", "skipped")), response


def test_llm_config_test_enabled_mode_uses_mock_client_and_records_usage(monkeypatch, client):
    monkeypatch.setenv("AITEST_ENABLE_REAL_LLM", "true")
    monkeypatch.setenv("AITEST_LLM_API_KEY", ROUND3_SECRET)
    install_mock_llm_client(monkeypatch)

    config_id = create_llm_config(client, enabled=True)
    before = usage_call_count(client)
    response = data_of(client.post(f"{API_PREFIX}/llm-configs/{config_id}/test"))

    assert_no_round3_secret(response)
    assert response.get("connected") is True
    assert str(response.get("status", "")).lower() in {"connected", "ok"}
    assert_usage_increased(client, before)


def test_chat_enabled_mode_uses_mock_client_reply_and_records_usage(monkeypatch, client):
    monkeypatch.setenv("AITEST_ENABLE_REAL_LLM", "true")
    monkeypatch.setenv("AITEST_LLM_API_KEY", ROUND3_SECRET)
    install_mock_llm_client(monkeypatch)

    before = usage_call_count(client)
    response = data_of(
        client.post(
            f"{API_PREFIX}/chat",
            json={"message": "Return the mock Round 3 response.", "context": {"api_key": ROUND3_SECRET}},
            headers={"Authorization": AUTH_SECRET},
        )
    )

    assert_no_round3_secret(response)
    assert "round3 mock model reply" in serialized(response)
    assert_usage_increased(client, before)


def test_error_responses_redact_llm_secret_authorization_and_token(monkeypatch, client):
    monkeypatch.setenv("AITEST_ENABLE_REAL_LLM", "true")
    monkeypatch.setenv("AITEST_LLM_API_KEY", ROUND3_SECRET)

    responses = [
        client.post(
            f"{API_PREFIX}/llm-configs/not-an-integer/test",
            json={"api_key": ROUND3_SECRET, "token": TOKEN_SECRET},
            headers={"Authorization": AUTH_SECRET},
        ),
        client.post(
            f"{API_PREFIX}/chat",
            json={"message": "", "context": {"api_key": ROUND3_SECRET, "token": TOKEN_SECRET}},
            headers={"Authorization": AUTH_SECRET},
        ),
    ]

    for response in responses:
        assert response.status_code >= 400, response.text
        assert_error_is_sanitized(response.json())

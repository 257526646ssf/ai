from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
import pytest

from aitest_platform.services.llm_client import LlmClientError
from conftest import API_PREFIX, data_of, first_item, object_id, post_json


pytestmark = pytest.mark.contract

ROUND4_SECRET = "sk-round4-test-secret"
AGT_STYLE_SECRET = "agt_codex_round4_fake_secret"
AUTH_SECRET = "Bearer sk-round4-test-secret"
TOKEN_SECRET = "round4-token-secret"


def serialized(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def assert_no_round4_secret(payload: Any) -> None:
    text = serialized(payload)
    forbidden = (
        ROUND4_SECRET,
        AGT_STYLE_SECRET,
        AUTH_SECRET,
        TOKEN_SECRET,
        "Authorization",
    )
    leaked = [item for item in forbidden if item in text]
    assert not leaked, f"Round 4 response leaked sensitive markers {leaked}: {payload!r}"


def assert_error_is_sanitized(payload: Any) -> None:
    assert_no_round4_secret(payload)
    forbidden_field_names = ("api_key", "Authorization", "authorization", "token")
    leaked = [item for item in forbidden_field_names if item in serialized(payload)]
    assert not leaked, f"Round 4 error response leaked sensitive field markers {leaked}: {payload!r}"


def block_real_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked_request(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("Round 4 main-chain LLM tests must not call real network")

    monkeypatch.setattr(httpx.Client, "request", blocked_request)
    monkeypatch.setattr(httpx.AsyncClient, "request", blocked_request)


class MockMainChainLlmClient:
    content: str = "{}"
    calls: list[dict[str, Any]] = []
    raise_error: Exception | None = None

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        self.__class__.calls.append({"event": "init", "kwargs": dict(_kwargs)})

    def list_models(self, *_args: Any, **_kwargs: Any) -> tuple[dict[str, Any], int]:
        return {"data": [{"id": "round4-mock-model"}]}, 3

    def chat_completions(self, *_args: Any, **_kwargs: Any) -> tuple[dict[str, Any], int]:
        self.__class__.calls.append({"event": "chat_completions", "kwargs": dict(_kwargs)})
        if self.__class__.raise_error is not None:
            raise self.__class__.raise_error
        return {
            "choices": [{"message": {"content": self.__class__.content}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 13},
        }, 5


def install_mock_llm_client(
    monkeypatch: pytest.MonkeyPatch,
    content: dict[str, Any] | str,
    *,
    raise_error: Exception | None = None,
) -> None:
    import aitest_platform.api.router as router

    MockMainChainLlmClient.content = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    MockMainChainLlmClient.calls = []
    MockMainChainLlmClient.raise_error = raise_error
    monkeypatch.setattr(router, "OpenAICompatibleClient", MockMainChainLlmClient, raising=False)
    monkeypatch.setattr(router, "OpenAICompatibleLLMClient", MockMainChainLlmClient, raising=False)
    monkeypatch.setattr(router, "LlmClient", MockMainChainLlmClient, raising=False)
    monkeypatch.setattr(router, "create_llm_client", lambda *_args, **_kwargs: MockMainChainLlmClient(), raising=False)
    monkeypatch.setattr(router, "get_llm_client", lambda *_args, **_kwargs: MockMainChainLlmClient(), raising=False)


def create_project(client) -> int | str:
    suffix = uuid.uuid4().hex[:8]
    data = post_json(
        client,
        f"{API_PREFIX}/projects",
        {
            "code": f"qa-round4-{suffix}",
            "name": f"QA Round 4 Project {suffix}",
            "description": "Created by Round 4 main-chain LLM contract tests.",
            "owner_name": "qa_main_chain_llm_round4",
        },
    )
    return object_id(data, "id", "project_id")


def create_requirement_lib(client, project_id: int | str) -> int | str:
    data = post_json(
        client,
        f"{API_PREFIX}/projects/{project_id}/requirement-libs",
        {
            "name": "Round 4 Requirement Library",
            "description": "Library for Round 4 main-chain LLM tests.",
        },
    )
    return object_id(data, "id", "lib_id")


def create_requirement_document(client, project_id: int | str, lib_id: int | str) -> int | str:
    data = post_json(
        client,
        f"{API_PREFIX}/projects/{project_id}/requirement-documents",
        {
            "lib_id": lib_id,
            "document_number": f"REQ-DOC-R4-{uuid.uuid4().hex[:8]}",
            "name": "Round 4 Login Requirement Draft",
            "source_type": "text",
            "raw_content": (
                "Users can log in with username and password. Invalid credentials, locked accounts, "
                "and missing permissions must be rejected without exposing secrets."
            ),
        },
    )
    return object_id(data, "id", "document_id")


def create_document_chain(client) -> tuple[int | str, int | str, int | str]:
    project_id = create_project(client)
    lib_id = create_requirement_lib(client, project_id)
    document_id = create_requirement_document(client, project_id, lib_id)
    parsed = post_json(client, f"{API_PREFIX}/requirement-documents/{document_id}/parse", {"parse_mode": "standard"})
    assert parsed is not None
    return project_id, lib_id, document_id


def create_placeholder_item(client) -> int | str:
    _project_id, _lib_id, document_id = create_document_chain(client)
    extracted = post_json(
        client,
        f"{API_PREFIX}/requirement-documents/{document_id}/extract-items",
        {"mode": "placeholder", "include_source_anchors": True},
    )
    return object_id(first_item(extracted["items"]), "id", "item_id")


def create_llm_config(client, *, enabled: bool = True) -> int | str:
    data = post_json(
        client,
        f"{API_PREFIX}/llm-configs",
        {
            "name": "round4-main-chain-llm",
            "provider": "openai-compatible",
            "model": "round4-mock-model",
            "base_url": "https://llm.round4.invalid/v1",
            "api_key": ROUND4_SECRET,
            "enabled": enabled,
            "is_enabled": enabled,
            "is_default": True,
            "module_binding": {
                "requirement_extract": True,
                "test_point_generation": True,
                "test_case_generation": True,
            },
        },
    )
    assert_no_round4_secret(data)
    return object_id(data, "id", "config_id")


def usage_module_count(client, module: str) -> int:
    stats = data_of(client.get(f"{API_PREFIX}/llm-usage/statistics"))
    assert_no_round4_secret(stats)
    modules = stats.get("by_module", []) if isinstance(stats, dict) else []
    for item in modules:
        if isinstance(item, dict) and item.get("module") == module:
            return int(item.get("count", 0))
    return 0


def assert_usage_increased(client, module: str, before: int) -> None:
    after = usage_module_count(client, module)
    assert after > before, f"LLM usage for {module!r} did not increase: before={before}, after={after}"


def test_disabled_mode_main_chain_uses_placeholder_without_network_and_writes_db(monkeypatch, client):
    monkeypatch.setenv("AITEST_ENABLE_REAL_LLM", "false")
    monkeypatch.setenv("AITEST_LLM_API_KEY", ROUND4_SECRET)
    block_real_network(monkeypatch)

    _project_id, _lib_id, document_id = create_document_chain(client)
    extracted = post_json(client, f"{API_PREFIX}/requirement-documents/{document_id}/extract-items", {"mode": "placeholder"})
    assert_no_round4_secret(extracted)
    item = first_item(extracted["items"])
    item_id = object_id(item, "id", "item_id")

    points_response = post_json(client, f"{API_PREFIX}/requirement-items/{item_id}/generate-test-points")
    assert_no_round4_secret(points_response)
    point = first_item(points_response["test_points"])
    assert object_id(point, "id", "test_point_id")

    cases_response = post_json(client, f"{API_PREFIX}/requirement-items/{item_id}/generate-test-cases", {"mode": "placeholder"})
    assert_no_round4_secret(cases_response)
    case = first_item(cases_response["test_cases"])
    assert object_id(case, "id", "case_id")

    listed_items = data_of(client.get(f"{API_PREFIX}/requirement-documents/{document_id}/requirement-items"))
    listed_points = data_of(client.get(f"{API_PREFIX}/requirement-items/{item_id}/test-points"))
    listed_cases = data_of(client.get(f"{API_PREFIX}/requirement-items/{item_id}/test-cases"))
    assert object_id(first_item(listed_items), "id", "item_id") == item_id
    assert object_id(first_item(listed_points), "id", "test_point_id")
    assert object_id(first_item(listed_cases), "id", "case_id")


def test_enabled_mock_llm_extract_items_json_writes_requirement_item_and_usage(monkeypatch, client):
    monkeypatch.setenv("AITEST_ENABLE_REAL_LLM", "true")
    monkeypatch.setenv("AITEST_LLM_API_KEY", ROUND4_SECRET)
    create_llm_config(client)
    install_mock_llm_client(
        monkeypatch,
        {
            "items": [
                {
                    "title": "Round 4 Mock Requirement Item",
                    "summary": "Mocked extraction summary from LLM JSON.",
                    "module": "Authentication",
                    "actor": "Registered user",
                    "goal": "Log in safely with valid credentials.",
                    "business_rules": ["Reject invalid credentials."],
                    "exceptions": ["Locked accounts cannot log in."],
                    "permissions": ["login:use"],
                    "non_functional": ["Do not expose secrets."],
                    "priority": "P0",
                    "confidence": 0.91,
                }
            ]
        },
    )

    _project_id, _lib_id, document_id = create_document_chain(client)
    before = usage_module_count(client, "requirement_extract")
    response = post_json(client, f"{API_PREFIX}/requirement-documents/{document_id}/extract-items", {"mode": "llm"})

    assert_no_round4_secret(response)
    item = first_item(response["items"])
    assert item["title"] == "Round 4 Mock Requirement Item"
    assert item["module"] == "Authentication"
    assert item["priority"] == "P0"
    assert item["confidence"] == pytest.approx(0.91)
    assert MockMainChainLlmClient.calls, "Enabled extract-items did not call the mock LLM client"
    assert_usage_increased(client, "requirement_extract", before)


def test_enabled_mock_llm_generate_test_points_json_writes_fields_and_usage(monkeypatch, client):
    monkeypatch.setenv("AITEST_ENABLE_REAL_LLM", "true")
    monkeypatch.setenv("AITEST_LLM_API_KEY", ROUND4_SECRET)
    create_llm_config(client)
    install_mock_llm_client(
        monkeypatch,
        {
            "test_points": [
                {
                    "title": "Round 4 Mock Point - locked account",
                    "point_type": "security",
                    "target": "Locked accounts are rejected with a safe message.",
                    "priority": "P0",
                    "suggested_method": "api",
                    "note": "Generated by mocked Round 4 LLM JSON.",
                }
            ]
        },
    )

    item_id = create_placeholder_item(client)
    before = usage_module_count(client, "test_point_generation")
    response = post_json(client, f"{API_PREFIX}/requirement-items/{item_id}/generate-test-points", {"mode": "llm"})

    assert_no_round4_secret(response)
    point = first_item(response["test_points"])
    assert point["title"] == "Round 4 Mock Point - locked account"
    assert point["point_type"] == "security"
    assert point["target"] == "Locked accounts are rejected with a safe message."
    assert point["priority"] == "P0"
    assert point["suggested_method"] == "api"
    assert point["note"] == "Generated by mocked Round 4 LLM JSON."
    assert MockMainChainLlmClient.calls, "Enabled generate-test-points did not call the mock LLM client"
    assert_usage_increased(client, "test_point_generation", before)


def test_enabled_mock_llm_generate_test_cases_json_writes_fields_and_usage(monkeypatch, client):
    monkeypatch.setenv("AITEST_ENABLE_REAL_LLM", "true")
    monkeypatch.setenv("AITEST_LLM_API_KEY", ROUND4_SECRET)
    create_llm_config(client)
    install_mock_llm_client(
        monkeypatch,
        {
            "test_cases": [
                {
                    "title": "Round 4 Mock Case - invalid credentials",
                    "case_type": "security",
                    "precondition": "A registered user exists and the account is active.",
                    "steps": [
                        {"step": 1, "action": "Open the login API."},
                        {"step": 2, "action": "Submit an invalid password."},
                    ],
                    "expected_result": "Login is rejected and no secret is exposed.",
                    "priority": "P0",
                    "tags": ["round4", "mock-llm", "security"],
                }
            ]
        },
    )

    item_id = create_placeholder_item(client)
    post_json(client, f"{API_PREFIX}/requirement-items/{item_id}/generate-test-points", {"mode": "placeholder"})
    before = usage_module_count(client, "test_case_generation")
    response = post_json(client, f"{API_PREFIX}/requirement-items/{item_id}/generate-test-cases", {"mode": "llm"})

    assert_no_round4_secret(response)
    case = first_item(response["test_cases"])
    assert case["title"] == "Round 4 Mock Case - invalid credentials"
    assert case["case_type"] == "security"
    assert case["precondition"] == "A registered user exists and the account is active."
    assert case["steps"][1]["action"] == "Submit an invalid password."
    assert case["expected_result"] == "Login is rejected and no secret is exposed."
    assert case["priority"] == "P0"
    assert "mock-llm" in case["tags"]
    assert MockMainChainLlmClient.calls, "Enabled generate-test-cases did not call the mock LLM client"
    assert_usage_increased(client, "test_case_generation", before)


@pytest.mark.parametrize(
    ("endpoint_kind", "content", "provider_error"),
    [
        ("extract", "{bad json", None),
        ("points", {"unexpected": "shape"}, None),
        ("cases", "{}", LlmClientError(f"provider failed with {ROUND4_SECRET} and {AGT_STYLE_SECRET}")),
    ],
)
def test_bad_json_or_provider_error_falls_back_to_placeholder_without_500_or_secret(
    monkeypatch,
    client,
    endpoint_kind: str,
    content: dict[str, Any] | str,
    provider_error: Exception | None,
):
    monkeypatch.setenv("AITEST_ENABLE_REAL_LLM", "true")
    monkeypatch.setenv("AITEST_LLM_API_KEY", ROUND4_SECRET)
    create_llm_config(client)
    install_mock_llm_client(monkeypatch, content, raise_error=provider_error)

    if endpoint_kind == "extract":
        _project_id, _lib_id, document_id = create_document_chain(client)
        response = client.post(f"{API_PREFIX}/requirement-documents/{document_id}/extract-items", json={"mode": "llm"})
        data = data_of(response)
        assert first_item(data["items"])
    else:
        item_id = create_placeholder_item(client)
        if endpoint_kind == "points":
            response = client.post(f"{API_PREFIX}/requirement-items/{item_id}/generate-test-points", json={"mode": "llm"})
            data = data_of(response)
            assert first_item(data["test_points"])
        else:
            post_json(client, f"{API_PREFIX}/requirement-items/{item_id}/generate-test-points", {"mode": "placeholder"})
            response = client.post(f"{API_PREFIX}/requirement-items/{item_id}/generate-test-cases", json={"mode": "llm"})
            data = data_of(response)
            assert first_item(data["test_cases"])

    assert response.status_code == 200, response.text
    assert_no_round4_secret(data)
    assert any(marker in serialized(data).lower() for marker in ("placeholder", "fallback", "items", "test_points", "test_cases")), data


def test_main_chain_security_does_not_echo_api_key_authorization_or_token(monkeypatch, client):
    monkeypatch.setenv("AITEST_ENABLE_REAL_LLM", "false")
    monkeypatch.setenv("AITEST_LLM_API_KEY", ROUND4_SECRET)
    block_real_network(monkeypatch)

    _project_id, _lib_id, document_id = create_document_chain(client)
    extract_response = data_of(
        client.post(
            f"{API_PREFIX}/requirement-documents/{document_id}/extract-items",
            json={"mode": "placeholder", "api_key": ROUND4_SECRET, "token": TOKEN_SECRET},
            headers={"Authorization": AUTH_SECRET},
        )
    )
    assert_no_round4_secret(extract_response)

    item_id = object_id(first_item(extract_response["items"]), "id", "item_id")
    points_response = data_of(
        client.post(
            f"{API_PREFIX}/requirement-items/{item_id}/generate-test-points",
            json={"mode": "placeholder", "api_key": ROUND4_SECRET, "token": TOKEN_SECRET},
            headers={"Authorization": AUTH_SECRET},
        )
    )
    assert_no_round4_secret(points_response)

    cases_response = data_of(
        client.post(
            f"{API_PREFIX}/requirement-items/{item_id}/generate-test-cases",
            json={"mode": "placeholder", "api_key": ROUND4_SECRET, "token": TOKEN_SECRET},
            headers={"Authorization": AUTH_SECRET},
        )
    )
    assert_no_round4_secret(cases_response)


def test_main_chain_error_response_redacts_secret_markers(monkeypatch, client):
    monkeypatch.setenv("AITEST_ENABLE_REAL_LLM", "true")
    monkeypatch.setenv("AITEST_LLM_API_KEY", ROUND4_SECRET)

    response = client.post(
        f"{API_PREFIX}/requirement-items/not-an-integer/generate-test-points",
        json={"api_key": ROUND4_SECRET, "token": TOKEN_SECRET},
        headers={"Authorization": AUTH_SECRET},
    )

    assert response.status_code >= 400, response.text
    assert_error_is_sanitized(response.json())

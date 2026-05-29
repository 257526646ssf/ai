from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

import httpx
import pytest

from conftest import API_PREFIX, data_of, first_item, object_id, post_json
from test_p0_acceptance import create_project


pytestmark = pytest.mark.contract

AUTH_SECRET = "Bearer round5-auth-secret"
API_KEY_SECRET = "round5-api-key-secret"
TOKEN_SECRET = "round5-token-secret"
COOKIE_SECRET = "round5-cookie-secret"
BODY_SECRET = "round5-body-secret"


class FakeHttpxResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        json_body: Any | None = None,
        text: str | None = None,
        headers: dict[str, str] | None = None,
        elapsed_ms: int = 37,
    ) -> None:
        self.status_code = status_code
        self._json_body = json_body
        self.text = text if text is not None else json.dumps(json_body if json_body is not None else {}, ensure_ascii=False)
        self.content = self.text.encode("utf-8")
        self.headers = headers or {"content-type": "application/json", "x-runner": "round5"}
        self.elapsed = timedelta(milliseconds=elapsed_ms)

    def json(self) -> Any:
        if self._json_body is None:
            raise ValueError("No JSON body")
        return self._json_body


def install_httpx_request_mock(monkeypatch: pytest.MonkeyPatch, *, response: FakeHttpxResponse | None = None, exc: Exception | None = None) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def fake_request(self: httpx.Client, method: str, url: str, **kwargs: Any) -> FakeHttpxResponse:
        calls.append(
            {
                "method": method,
                "url": str(url),
                "headers": dict(kwargs.get("headers") or {}),
                "params": kwargs.get("params"),
                "json": kwargs.get("json"),
                "data": kwargs.get("data"),
                "content": kwargs.get("content"),
                "timeout": kwargs.get("timeout"),
            }
        )
        if exc is not None:
            raise exc
        assert response is not None, "test must provide either response or exc"
        return response

    monkeypatch.setattr(httpx.Client, "request", fake_request)
    return calls


def payload_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def assert_no_fake_secrets(payload: Any) -> None:
    dumped = payload_text(payload)
    for secret in (AUTH_SECRET, API_KEY_SECRET, TOKEN_SECRET, COOKIE_SECRET, BODY_SECRET):
        assert secret not in dumped, dumped


def assert_not_placeholder(payload: dict[str, Any]) -> None:
    dumped = payload_text(payload).lower()
    assert '"placeholder": true' not in dumped
    assert '"placeholder":true' not in dumped


def assert_execution_core(execution: dict[str, Any], *, expected_status: str, expected_http_status: int) -> None:
    assert object_id(execution, "id", "execution_id")
    assert execution.get("status") == expected_status, execution
    assert isinstance(execution.get("duration_ms"), int) and execution["duration_ms"] >= 0, execution
    assert isinstance(execution.get("request_snapshot"), dict), execution
    assert isinstance(execution.get("response_snapshot"), dict), execution
    assert execution["response_snapshot"].get("status_code") == expected_http_status, execution
    assert isinstance(execution.get("assertion_results"), list) and execution["assertion_results"], execution


def create_api_case(
    client,
    *,
    marker: str,
    expected_status: int = 200,
    request_headers: dict[str, Any] | None = None,
    request_query: dict[str, Any] | None = None,
    request_body: Any | None = None,
    create_environment: bool = True,
) -> dict[str, Any]:
    project_id = create_project(client)
    lib = post_json(client, f"{API_PREFIX}/projects/{project_id}/api-test-libs", {"name": f"{marker}-lib"})
    lib_id = object_id(lib)

    imported = post_json(
        client,
        f"{API_PREFIX}/api-test-libs/{lib_id}/apis/import",
        {
            "name": f"{marker}-endpoint",
            "method": "POST",
            "path": f"/round5/{marker}/users",
            "headers": {"x-endpoint": "schema"},
            "query": {"from_endpoint": "yes"},
            "body": {"schema": "object"},
            "response": {"status": expected_status},
        },
    )
    api_id = object_id(first_item(imported.get("apis") or imported), "id", "api_id")

    generated = post_json(
        client,
        f"{API_PREFIX}/apis/{api_id}/generate-test-cases",
        {
            "name": f"{marker}-case",
            "expected_status": expected_status,
            "request_headers": request_headers or {"X-Test-Run": marker},
            "request_query": request_query or {"page": "1"},
            "request_body": request_body if request_body is not None else {"name": marker},
            "assertions": [{"type": "status_code", "expected": expected_status}],
        },
    )
    case_id = object_id(first_item(generated.get("test_cases") or generated), "id", "case_id")

    env_id = None
    if create_environment:
        env = post_json(
            client,
            f"{API_PREFIX}/api-test-libs/{lib_id}/environments",
            {
                "name": f"{marker}-env",
                "base_url": "https://round5.example.test/base",
                "headers": {"X-Environment": "round5"},
                "variables": {"tenant": "qa"},
                "is_active": True,
            },
        )
        env_id = object_id(env, "id", "environment_id")

    return {"project_id": project_id, "lib_id": lib_id, "api_id": api_id, "case_id": case_id, "env_id": env_id}


def test_debug_api_uses_httpx_and_returns_real_response_snapshot(monkeypatch, client):
    calls = install_httpx_request_mock(
        monkeypatch,
        response=FakeHttpxResponse(status_code=201, json_body={"ok": True, "id": "created"}, elapsed_ms=45),
    )

    payload = {
        "method": "POST",
        "url": "https://round5.example.test/debug/users",
        "query": {"page": "1", "search": "alice"},
        "headers": {"X-Debug": "round5"},
        "body": {"name": "Alice", "role": "qa"},
        "expected_status": 201,
        "assertions": [{"type": "status_code", "expected": 201}],
    }
    data = post_json(client, f"{API_PREFIX}/apis/debug", payload)

    assert calls, "debug API must call the runner/httpx instead of returning a placeholder"
    call = calls[0]
    assert call["method"].upper() == "POST"
    assert call["url"] == payload["url"]
    assert call["params"] == payload["query"]
    assert call["json"] == payload["body"]

    assert data["status_code"] == 201, data
    assert data.get("duration_ms", 0) >= 0, data
    assert data.get("body") == {"ok": True, "id": "created"} or data.get("response_snapshot", {}).get("body") == {"ok": True, "id": "created"}
    assert isinstance(data.get("assertions") or data.get("assertion_results"), list), data
    assert_not_placeholder(data)


def test_execute_api_test_case_persists_passed_runner_snapshots(monkeypatch, client):
    calls = install_httpx_request_mock(
        monkeypatch,
        response=FakeHttpxResponse(status_code=200, json_body={"ok": True, "user_id": 123}, elapsed_ms=52),
    )
    ids = create_api_case(client, marker="passed")

    execution = post_json(client, f"{API_PREFIX}/api-test-cases/{ids['case_id']}/execute", {"environment_id": ids["env_id"]})

    assert calls, "case execution must use the real runner/httpx when an active environment exists"
    call = calls[0]
    assert call["method"].upper() == "POST"
    assert call["url"] == "https://round5.example.test/base/round5/passed/users"
    assert call["params"] == {"page": "1"}
    assert call["json"] == {"name": "passed"}

    assert_execution_core(execution, expected_status="passed", expected_http_status=200)
    assert execution["request_snapshot"].get("method") == "POST", execution
    assert execution["request_snapshot"].get("url") == call["url"], execution
    assert execution["response_snapshot"].get("body") == {"ok": True, "user_id": 123}, execution
    assert execution.get("environment_id") == ids["env_id"], execution
    assert_not_placeholder(execution)


def test_execute_api_test_case_failed_assertion_returns_failed_execution_not_http_500(monkeypatch, client):
    install_httpx_request_mock(
        monkeypatch,
        response=FakeHttpxResponse(status_code=500, json_body={"error": "upstream failed"}, elapsed_ms=33),
    )
    ids = create_api_case(client, marker="failed-assertion", expected_status=200)

    response = client.post(f"{API_PREFIX}/api-test-cases/{ids['case_id']}/execute", json={"environment_id": ids["env_id"]})
    data = data_of(response)

    assert response.status_code in {200, 201}, response.text
    assert_execution_core(data, expected_status="failed", expected_http_status=500)
    assert any(result.get("passed") is False for result in data["assertion_results"]), data
    assert_not_placeholder(data)


@pytest.mark.parametrize("exc", [httpx.TimeoutException("timeout token=round5-token-secret"), httpx.RequestError("request failed Authorization=Bearer round5-auth-secret")])
def test_execute_api_test_case_network_exception_returns_error_execution_with_redacted_message(monkeypatch, client, exc):
    install_httpx_request_mock(monkeypatch, exc=exc)
    ids = create_api_case(client, marker="network-error")

    response = client.post(f"{API_PREFIX}/api-test-cases/{ids['case_id']}/execute", json={"environment_id": ids["env_id"]})
    data = data_of(response)

    assert response.status_code in {200, 201}, response.text
    assert object_id(data, "id", "execution_id")
    assert data.get("status") == "error", data
    assert data.get("error_message"), data
    assert_no_fake_secrets(data)
    assert "round5-" not in data.get("error_message", ""), data


def test_batch_api_test_case_executions_reuse_real_runner(monkeypatch, client):
    calls = install_httpx_request_mock(
        monkeypatch,
        response=FakeHttpxResponse(status_code=200, json_body={"ok": True}, elapsed_ms=21),
    )
    first = create_api_case(client, marker="batch-one", create_environment=False)
    second = create_api_case(client, marker="batch-two", create_environment=False)

    data = post_json(
        client,
        f"{API_PREFIX}/api-test-cases/batch-executions",
        {"case_ids": [first["case_id"], second["case_id"]], "base_url": "https://round5.example.test/base"},
    )
    executions = data.get("executions") or data.get("items") or data

    assert isinstance(executions, list) and len(executions) == 2, data
    assert len(calls) == 2, calls
    assert {call["url"] for call in calls} == {
        "https://round5.example.test/base/round5/batch-one/users",
        "https://round5.example.test/base/round5/batch-two/users",
    }
    for execution in executions:
        assert_execution_core(execution, expected_status="passed", expected_http_status=200)
        assert_not_placeholder(execution)


def test_api_runner_redacts_secrets_from_debug_and_execution_payloads(monkeypatch, client):
    calls = install_httpx_request_mock(
        monkeypatch,
        response=FakeHttpxResponse(
            status_code=200,
            json_body={
                "ok": True,
                "Authorization": AUTH_SECRET,
                "api_key": API_KEY_SECRET,
                "nested": {"token": TOKEN_SECRET, "cookie": COOKIE_SECRET},
            },
            headers={"set-cookie": COOKIE_SECRET, "x-api-key": API_KEY_SECRET},
        ),
    )

    debug = post_json(
        client,
        f"{API_PREFIX}/apis/debug",
        {
            "method": "POST",
            "url": "https://round5.example.test/debug/secret",
            "headers": {"Authorization": AUTH_SECRET, "Cookie": COOKIE_SECRET},
            "query": {"api_key": API_KEY_SECRET, "token": TOKEN_SECRET},
            "body": {"token": TOKEN_SECRET, "nested": {"api_key": API_KEY_SECRET}, "safe": "visible"},
            "expected_status": 200,
        },
    )
    assert calls, "debug redaction path must still execute the runner"
    assert_no_fake_secrets(debug)

    ids = create_api_case(
        client,
        marker="redaction",
        request_headers={"Authorization": AUTH_SECRET, "Cookie": COOKIE_SECRET, "X-Safe": "visible"},
        request_query={"api_key": API_KEY_SECRET, "token": TOKEN_SECRET, "safe": "visible"},
        request_body={"token": TOKEN_SECRET, "nested": {"api_key": API_KEY_SECRET}, "safe": "visible"},
    )
    execution = post_json(client, f"{API_PREFIX}/api-test-cases/{ids['case_id']}/execute", {"environment_id": ids["env_id"]})

    assert_no_fake_secrets(execution)
    assert_execution_core(execution, expected_status="passed", expected_http_status=200)
    assert execution["request_snapshot"].get("headers", {}).get("X-Safe") == "visible", execution
    assert execution["request_snapshot"].get("query", {}).get("safe") == "visible", execution
    assert_not_placeholder(execution)


def test_api_test_case_without_environment_keeps_round2_placeholder_fallback(monkeypatch, client):
    calls = install_httpx_request_mock(
        monkeypatch,
        response=FakeHttpxResponse(status_code=200, json_body={"should_not": "be required"}),
    )
    ids = create_api_case(client, marker="fallback", create_environment=False)

    execution = post_json(client, f"{API_PREFIX}/api-test-cases/{ids['case_id']}/execute")

    assert execution.get("status") == "passed", execution
    assert object_id(execution, "id", "execution_id")
    assert execution.get("response_snapshot", {}).get("body", {}).get("placeholder") is True, execution
    assert calls == [], "fallback mode without environment/base_url should not require outbound httpx"

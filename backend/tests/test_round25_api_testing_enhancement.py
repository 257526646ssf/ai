from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

import httpx
import pytest

from aitest_platform.db.session import session_scope
from aitest_platform.models import ApiExecution, ApiTestCase
from conftest import API_PREFIX, data_of, first_item, object_id, post_json
from test_p0_acceptance import create_project


pytestmark = pytest.mark.contract

AUTH_SECRET = "Bearer round25-auth-secret"
API_KEY_SECRET = "round25-api-key-secret"
TOKEN_SECRET = "round25-token-secret"
COOKIE_SECRET = "round25_session=round25-cookie-secret"
BODY_SECRET = "round25-body-secret"
SCRIPT_SECRET = "round25-script-secret"
SECRET_MARKERS = (AUTH_SECRET, API_KEY_SECRET, TOKEN_SECRET, COOKIE_SECRET, BODY_SECRET, SCRIPT_SECRET)


class FakeHttpxResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        json_body: Any | None = None,
        text: str | None = None,
        headers: dict[str, str] | None = None,
        elapsed_ms: int = 31,
    ) -> None:
        self.status_code = status_code
        self._json_body = json_body
        self.text = text if text is not None else json.dumps(json_body if json_body is not None else {}, ensure_ascii=False)
        self.content = self.text.encode("utf-8")
        self.headers = headers or {"content-type": "application/json"}
        self.elapsed = timedelta(milliseconds=elapsed_ms)

    def json(self) -> Any:
        if self._json_body is None:
            raise ValueError("No JSON body")
        return self._json_body


def payload_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def assert_no_fake_secrets(payload: Any) -> None:
    dumped = payload_text(payload)
    for secret in SECRET_MARKERS:
        assert secret not in dumped, dumped


def list_items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        for key in ("list", "items", "records", "results", "data", "apis", "test_cases", "rules"):
            nested = value.get(key)
            if isinstance(nested, list):
                assert all(isinstance(item, dict) for item in nested), nested
                return nested
        if "id" in value:
            return [value]
    if isinstance(value, list):
        assert all(isinstance(item, dict) for item in value), value
        return value
    pytest.fail(f"Expected list-like response, got: {value!r}", pytrace=False)


def first_api(import_response: Any) -> dict[str, Any]:
    return first_item(import_response.get("apis") if isinstance(import_response, dict) else import_response)


def schema_of(endpoint: dict[str, Any], name: str) -> Any:
    return endpoint.get(f"{name}_schema") if f"{name}_schema" in endpoint else endpoint.get(name)


def first_saved_case(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("saved_case", "test_case", "case"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    pytest.fail(f"Debug response must include saved_case/test_case data, got: {payload!r}", pytrace=False)


def response_payload(response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        pytest.fail(f"Expected JSON response, got: {response.text!r}", pytrace=False)
    assert isinstance(payload, dict), payload
    return payload


def data_or_payload(response) -> Any:
    payload = response_payload(response)
    if {"code", "message", "data"} <= payload.keys():
        return payload["data"]
    return payload


def assert_not_500_or_404(response) -> Any:
    assert response.status_code != 500, response.text
    assert response.status_code != 404, response.text
    assert response.status_code in {200, 201, 400, 422}, response.text
    payload = response_payload(response)
    assert_no_fake_secrets(payload)
    return payload.get("data", payload)


def create_api_lib(client, marker: str) -> dict[str, Any]:
    project_id = create_project(client)
    lib = post_json(
        client,
        f"{API_PREFIX}/projects/{project_id}/api-test-libs",
        {"name": f"round25-{marker}-lib", "description": "Round 25 API testing enhancement contracts."},
    )
    return {"project_id": project_id, "lib_id": object_id(lib)}


def create_api_endpoint(
    client,
    *,
    lib_id: int | str,
    marker: str,
    method: str = "POST",
    path: str | None = None,
    response_status: int = 200,
) -> dict[str, Any]:
    endpoint_path = path or f"/round25/{marker}/users"
    imported = post_json(
        client,
        f"{API_PREFIX}/api-test-libs/{lib_id}/apis/import",
        {
            "name": f"round25-{marker}-endpoint",
            "method": method,
            "path": endpoint_path,
            "headers": {"Content-Type": "application/json"},
            "query": {"source": "contract"},
            "body": {"type": "object", "properties": {"marker": {"type": "string"}}},
            "response": {"status": response_status},
        },
    )
    endpoint = first_api(imported)
    return {"api_id": object_id(endpoint, "id", "api_id"), "endpoint": endpoint}


def create_api_case(
    client,
    *,
    lib_id: int | str,
    marker: str,
    method: str = "POST",
    path: str | None = None,
    request_headers: dict[str, Any] | None = None,
    request_query: dict[str, Any] | None = None,
    request_body: Any | None = None,
    expected_status: int = 200,
    pre_script: str | None = None,
    post_script: str | None = None,
) -> dict[str, Any]:
    endpoint_info = create_api_endpoint(
        client,
        lib_id=lib_id,
        marker=marker,
        method=method,
        path=path,
        response_status=expected_status,
    )
    payload: dict[str, Any] = {
        "name": f"round25-{marker}-case",
        "request_headers": request_headers or {"X-Case": marker},
        "request_query": request_query or {},
        "request_body": request_body if request_body is not None else {"marker": marker},
        "expected_status": expected_status,
        "assertions": [{"type": "status_code", "expected": expected_status}],
    }
    if pre_script is not None:
        payload["pre_script"] = pre_script
    if post_script is not None:
        payload["post_script"] = post_script
    generated = post_json(client, f"{API_PREFIX}/apis/{endpoint_info['api_id']}/generate-test-cases", payload)
    case = first_item(generated.get("test_cases") or generated)
    return {
        **endpoint_info,
        "case_id": object_id(case, "id", "case_id"),
        "case": case,
    }


def create_api_environment(
    client,
    *,
    lib_id: int | str,
    marker: str,
    base_url: str = "https://round25.example.test/base",
    headers: dict[str, Any] | None = None,
    variables: dict[str, Any] | None = None,
) -> dict[str, Any]:
    env = post_json(
        client,
        f"{API_PREFIX}/api-test-libs/{lib_id}/environments",
        {
            "name": f"round25-{marker}-env",
            "base_url": base_url,
            "headers": headers or {"Authorization": AUTH_SECRET, "X-Environment": "round25"},
            "variables": variables or {"tenant": "env-tenant", "api_key": API_KEY_SECRET},
            "is_active": True,
        },
    )
    return {"env_id": object_id(env, "id", "environment_id"), "environment": env}


def install_ordered_httpx_mock(monkeypatch: pytest.MonkeyPatch, responses: list[FakeHttpxResponse]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def fake_request(self: httpx.Client, method: str, url: str, **kwargs: Any) -> FakeHttpxResponse:
        calls.append(
            {
                "method": method,
                "url": str(url),
                "headers": dict(kwargs.get("headers") or {}),
                "params": kwargs.get("params"),
                "json": kwargs.get("json"),
                "content": kwargs.get("content"),
                "timeout": kwargs.get("timeout"),
            }
        )
        assert responses, "test executed more HTTP requests than expected"
        return responses.pop(0)

    monkeypatch.setattr(httpx.Client, "request", fake_request)
    return calls


def block_httpx_requests(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def fake_request(self: httpx.Client, method: str, url: str, **kwargs: Any) -> FakeHttpxResponse:
        calls.append({"method": method, "url": str(url)})
        return FakeHttpxResponse(status_code=599, json_body={"unexpected_outbound": True})

    monkeypatch.setattr(httpx.Client, "request", fake_request)
    return calls


def get_api_case(case_id: int | str) -> dict[str, Any]:
    with session_scope() as session:
        case = session.get(ApiTestCase, int(case_id))
        assert case is not None, f"ApiTestCase({case_id}) was not persisted"
        return {
            "id": case.id,
            "endpoint_id": case.endpoint_id,
            "lib_id": case.lib_id,
            "name": case.name,
            "request_headers": case.request_headers,
            "request_query": case.request_query,
            "request_body": case.request_body,
            "expected_status": case.expected_status,
            "assertions": case.assertions,
            "pre_script": case.pre_script,
            "post_script": case.post_script,
        }


def get_api_execution(execution_id: int | str) -> dict[str, Any]:
    with session_scope() as session:
        execution = session.get(ApiExecution, int(execution_id))
        assert execution is not None, f"ApiExecution({execution_id}) was not persisted"
        return {
            "id": execution.id,
            "case_id": execution.case_id,
            "environment_id": execution.environment_id,
            "status": execution.status,
            "request_snapshot": execution.request_snapshot,
            "response_snapshot": execution.response_snapshot,
            "assertion_results": execution.assertion_results,
            "error_message": execution.error_message,
        }


def status_code_of(value: dict[str, Any]) -> Any:
    response = value.get("response") if isinstance(value.get("response"), dict) else value
    return response.get("status_code", response.get("status"))


def response_headers_of(value: dict[str, Any]) -> dict[str, Any]:
    response = value.get("response") if isinstance(value.get("response"), dict) else value
    headers = response.get("headers") or {}
    assert isinstance(headers, dict), response
    return headers


def response_body_of(value: dict[str, Any]) -> Any:
    response = value.get("response") if isinstance(value.get("response"), dict) else value
    return response.get("body")


def test_openapi_yaml_import_generates_case_with_query_schema_and_expected_status(client):
    ids = create_api_lib(client, "openapi-yaml")
    yaml_document = """
openapi: 3.0.3
info:
  title: Round25 YAML Contract
  version: 1.0.0
paths:
  /round25/yaml/users:
    get:
      summary: List Round25 YAML users
      operationId: listRound25YamlUsers
      parameters:
        - name: page
          in: query
          required: false
          schema:
            type: integer
        - name: include_archived
          in: query
          required: false
          schema:
            type: boolean
      responses:
        "206":
          description: Partial user list
          content:
            application/json:
              schema:
                type: object
                properties:
                  items:
                    type: array
                    items:
                      type: object
"""

    imported = post_json(
        client,
        f"{API_PREFIX}/api-test-libs/{ids['lib_id']}/import-documents",
        {
            "source_type": "openapi",
            "format": "openapi_yaml",
            "content": yaml_document,
            "generate_cases": True,
            "create_cases": True,
            "create_test_cases": True,
        },
    )
    assert_no_fake_secrets(imported)

    endpoints = list_items(data_of(client.get(f"{API_PREFIX}/api-test-libs/{ids['lib_id']}/apis")))
    endpoint = next((item for item in endpoints if item.get("path") == "/round25/yaml/users"), None)
    assert endpoint is not None, endpoints
    assert endpoint.get("method") == "GET", endpoint
    query_schema = schema_of(endpoint, "query") or {}
    response_schema = schema_of(endpoint, "response") or {}
    assert "page" in payload_text(query_schema) and "integer" in payload_text(query_schema), endpoint
    assert "include_archived" in payload_text(query_schema), endpoint
    assert response_schema.get("status") == 206, endpoint

    cases = list_items(data_of(client.get(f"{API_PREFIX}/apis/{object_id(endpoint)}/test-cases")))
    case = first_item(cases)
    assert case.get("expected_status") == 206, case
    assert "page" in payload_text(case.get("request_query") or {}), case
    assert any(item.get("type") == "status_code" and item.get("expected") == 206 for item in case.get("assertions") or []), case
    assert_no_fake_secrets(cases)


def test_har_import_generates_case_without_echoing_authorization_token_or_cookie(client):
    ids = create_api_lib(client, "har")
    har_document = {
        "log": {
            "version": "1.2",
            "creator": {"name": "round25-contract", "version": "1.0"},
            "entries": [
                {
                    "request": {
                        "method": "POST",
                        "url": f"https://api.example.invalid/round25/har/orders?page=2&token={TOKEN_SECRET}",
                        "headers": [
                            {"name": "Authorization", "value": AUTH_SECRET},
                            {"name": "Cookie", "value": COOKIE_SECRET},
                            {"name": "Content-Type", "value": "application/json"},
                        ],
                        "postData": {
                            "mimeType": "application/json",
                            "text": json.dumps({"sku": "R25-SKU", "quantity": 2, "token": BODY_SECRET}),
                        },
                    },
                    "response": {
                        "status": 202,
                        "headers": [
                            {"name": "Set-Cookie", "value": COOKIE_SECRET},
                            {"name": "X-Trace", "value": "trace-har"},
                        ],
                        "content": {"mimeType": "application/json", "text": json.dumps({"accepted": True, "token": TOKEN_SECRET})},
                    },
                }
            ],
        }
    }

    imported = post_json(
        client,
        f"{API_PREFIX}/api-test-libs/{ids['lib_id']}/apis/import",
        {
            "source_type": "har",
            "format": "har",
            "document": har_document,
            "generate_cases": True,
            "create_cases": True,
        },
    )
    assert_no_fake_secrets(imported)

    endpoint = first_api(imported)
    assert endpoint.get("method") == "POST", endpoint
    assert endpoint.get("path") == "/round25/har/orders", endpoint
    assert "?" not in endpoint.get("path", ""), endpoint
    assert "page" in payload_text(schema_of(endpoint, "query") or {}), endpoint
    assert "R25-SKU" in payload_text(schema_of(endpoint, "body") or {}), endpoint
    assert (schema_of(endpoint, "response") or {}).get("status") == 202, endpoint
    assert_no_fake_secrets(endpoint)

    case = first_item(imported.get("test_cases") or data_of(client.get(f"{API_PREFIX}/apis/{object_id(endpoint)}/test-cases")))
    assert case.get("expected_status") == 202, case
    assert "page" in payload_text(case.get("request_query") or {}), case
    assert "R25-SKU" in payload_text(case.get("request_body") or {}), case
    assert_no_fake_secrets(case)


def test_debug_api_save_as_case_persists_sanitized_case_after_real_httpx_response(monkeypatch, client):
    ids = create_api_lib(client, "debug-save")
    endpoint_info = create_api_endpoint(client, lib_id=ids["lib_id"], marker="debug-save", path="/round25/debug/users", response_status=201)
    calls = install_ordered_httpx_mock(
        monkeypatch,
        [
            FakeHttpxResponse(
                status_code=201,
                json_body={"id": "user-201", "token": TOKEN_SECRET},
                headers={"content-type": "application/json", "set-cookie": COOKIE_SECRET},
            )
        ],
    )

    debug = post_json(
        client,
        f"{API_PREFIX}/apis/debug",
        {
            "api_id": endpoint_info["api_id"],
            "lib_id": ids["lib_id"],
            "save_as_case": True,
            "case_name": "round25 debug saved case",
            "method": "POST",
            "url": "https://round25.example.test/round25/debug/users",
            "query": {"source": "debug", "token": TOKEN_SECRET},
            "headers": {"Authorization": AUTH_SECRET, "Cookie": COOKIE_SECRET, "X-Debug": "round25"},
            "body": {"name": "Ada", "token": BODY_SECRET},
            "expected_status": 201,
            "assertions": [{"type": "status_code", "expected": 201}],
        },
    )
    assert calls, "debug API must still execute the mocked httpx request before saving the case"
    assert debug.get("status_code") == 201, debug
    saved_case = first_saved_case(debug)
    case_id = object_id(saved_case, "id", "case_id")
    persisted = get_api_case(case_id)

    assert persisted["expected_status"] == 201, persisted
    assert persisted["request_headers"].get("X-Debug") == "round25", persisted
    assert persisted["request_query"].get("source") == "debug", persisted
    assert persisted["request_body"].get("name") == "Ada", persisted
    assert any(item.get("type") == "status_code" and item.get("expected") == 201 for item in persisted["assertions"] or []), persisted
    assert_no_fake_secrets(debug)
    assert_no_fake_secrets(persisted)


def test_api_case_execute_applies_runtime_variable_and_header_precedence_without_leaking_secrets(monkeypatch, client):
    ids = create_api_lib(client, "execute-precedence")
    env = create_api_environment(
        client,
        lib_id=ids["lib_id"],
        marker="execute-precedence",
        headers={"Authorization": AUTH_SECRET, "X-Merge": "env-header", "X-Env-Only": "env-only"},
        variables={"tenant": "env-tenant", "mode": "env-mode", "trace_id": "env-trace", "api_key": API_KEY_SECRET},
    )
    case = create_api_case(
        client,
        lib_id=ids["lib_id"],
        marker="execute-precedence",
        path="/round25/execute/{{tenant}}/users",
        request_headers={"X-Merge": "case-header", "X-Case-Only": "case-only", "X-Trace": "{{trace_id}}"},
        request_query={"tenant": "{{tenant}}", "mode": "{{mode}}", "api_key": API_KEY_SECRET},
        request_body={"tenant": "{{tenant}}", "trace_id": "{{trace_id}}", "body_secret": BODY_SECRET},
        expected_status=200,
    )
    calls = install_ordered_httpx_mock(
        monkeypatch,
        [FakeHttpxResponse(status_code=200, json_body={"ok": True, "token": TOKEN_SECRET}, headers={"content-type": "application/json"})],
    )

    execution = post_json(
        client,
        f"{API_PREFIX}/api-test-cases/{case['case_id']}/execute",
        {
            "environment_id": env["env_id"],
            "variables": {"tenant": "runtime-tenant", "mode": "runtime-mode", "trace_id": "runtime-trace"},
            "headers": {"X-Merge": "execute-header", "X-Execute-Only": "execute-only"},
        },
    )

    assert len(calls) == 1, calls
    call = calls[0]
    assert call["url"] == "https://round25.example.test/base/round25/execute/runtime-tenant/users", call
    assert call["params"]["tenant"] == "runtime-tenant", call
    assert call["params"]["mode"] == "runtime-mode", call
    assert call["headers"]["X-Merge"] == "execute-header", call
    assert call["headers"]["X-Case-Only"] == "case-only", call
    assert call["headers"]["X-Env-Only"] == "env-only", call
    assert call["headers"]["X-Trace"] == "runtime-trace", call
    assert call["headers"]["X-Execute-Only"] == "execute-only", call
    assert call["json"]["tenant"] == "runtime-tenant", call
    assert call["json"]["trace_id"] == "runtime-trace", call

    assert execution.get("status") == "passed", execution
    persisted = get_api_execution(object_id(execution, "id", "execution_id"))
    assert_no_fake_secrets(execution)
    assert_no_fake_secrets(persisted)


def test_scenario_data_mappings_extract_shape_injects_step_variables_and_ignores_missing_paths(monkeypatch, client):
    ids = create_api_lib(client, "scenario-mapping")
    env = create_api_environment(client, lib_id=ids["lib_id"], marker="scenario-mapping")
    create_case = create_api_case(
        client,
        lib_id=ids["lib_id"],
        marker="scenario-create",
        path="/round25/scenario/users",
        request_body={"name": "Ada", "token": BODY_SECRET},
    )
    use_case = create_api_case(
        client,
        lib_id=ids["lib_id"],
        marker="scenario-use",
        path="/round25/scenario/users/{{user_id}}/traces/{{trace_id}}",
        request_headers={"X-User": "{{user_id}}", "X-Trace": "{{trace_id}}"},
        request_query={"trace_id": "{{trace_id}}"},
        request_body={"user_id": "{{user_id}}", "trace_id": "{{trace_id}}", "optional": "{{missing_optional}}"},
    )
    scenario = post_json(
        client,
        f"{API_PREFIX}/api-test-libs/{ids['lib_id']}/scenarios",
        {
            "name": "round25 data-mappings extract scenario",
            "nodes": [
                {"id": "create-user", "type": "case", "case_id": create_case["case_id"], "order": 1},
                {"id": "use-user", "type": "case", "case_id": use_case["case_id"], "order": 2},
            ],
            "edges": [{"source": "create-user", "target": "use-user"}],
            "data_mappings": {
                "extract": {
                    "create-user": {
                        "user_id": "$.body.user.id",
                        "trace_id": "$.headers.x-trace-id",
                        "missing_optional": "$.body.user.missing",
                    }
                }
            },
        },
    )
    calls = install_ordered_httpx_mock(
        monkeypatch,
        [
            FakeHttpxResponse(
                status_code=200,
                json_body={"user": {"id": "user-r25"}, "ok": True},
                headers={"content-type": "application/json", "x-trace-id": "trace-r25"},
            ),
            FakeHttpxResponse(status_code=200, json_body={"ok": True, "session": "session-r25"}),
        ],
    )

    result = post_json(client, f"{API_PREFIX}/api-scenarios/{object_id(scenario, 'id', 'scenario_id')}/execute", {"environment_id": env["env_id"]})

    assert len(calls) == 2, calls
    assert calls[1]["url"].endswith("/round25/scenario/users/user-r25/traces/trace-r25"), calls
    assert calls[1]["headers"].get("X-User") == "user-r25", calls
    assert calls[1]["headers"].get("X-Trace") == "trace-r25", calls
    assert calls[1]["params"].get("trace_id") == "trace-r25", calls
    assert calls[1]["json"].get("user_id") == "user-r25", calls
    assert calls[1]["json"].get("trace_id") == "trace-r25", calls
    assert result.get("summary", {}).get("total") == 2, result
    assert result.get("summary", {}).get("passed") == 2, result
    assert result.get("variables", {}).get("user_id") == "user-r25", result
    assert result.get("variables", {}).get("trace_id") == "trace-r25", result
    assert_no_fake_secrets(result)


def test_mock_service_rule_create_list_dispatch_hit_and_miss_are_structured(client):
    ids = create_api_lib(client, "mock-service")
    created = post_json(
        client,
        f"{API_PREFIX}/api-test-libs/{ids['lib_id']}/mock-rules",
        {
            "name": "round25 configured mock rule",
            "enabled": True,
            "priority": 10,
            "method": "POST",
            "path": "/round25/mock/users",
            "match": {"query": {"mode": "contract"}, "headers": {"X-Mock-Target": "users"}},
            "response": {
                "status_code": 207,
                "headers": {"X-Mock-Rule": "round25"},
                "body": {"ok": True, "source": "configured-mock"},
            },
        },
    )
    rule_id = object_id(created, "id", "rule_id")
    assert_no_fake_secrets(created)

    rules = list_items(data_of(client.get(f"{API_PREFIX}/api-test-libs/{ids['lib_id']}/mock-rules")))
    assert any(str(object_id(rule, "id", "rule_id")) == str(rule_id) for rule in rules), rules
    assert_no_fake_secrets(rules)

    hit = post_json(
        client,
        f"{API_PREFIX}/api-test-libs/{ids['lib_id']}/mock/dispatch",
        {
            "method": "POST",
            "path": "/round25/mock/users",
            "query": {"mode": "contract"},
            "headers": {"X-Mock-Target": "users", "Authorization": AUTH_SECRET, "Cookie": COOKIE_SECRET},
            "body": {"name": "Ada"},
        },
    )
    assert hit.get("matched") is True, hit
    assert status_code_of(hit) == 207, hit
    assert response_headers_of(hit).get("X-Mock-Rule") == "round25", hit
    assert response_body_of(hit) == {"ok": True, "source": "configured-mock"}, hit
    assert_no_fake_secrets(hit)

    miss = post_json(
        client,
        f"{API_PREFIX}/api-test-libs/{ids['lib_id']}/mock/dispatch",
        {"method": "GET", "path": "/round25/mock/missing", "headers": {"Authorization": AUTH_SECRET}},
    )
    assert miss.get("matched") is False, miss
    assert status_code_of(miss) == 404, miss
    assert miss.get("error") or miss.get("message") or response_body_of(miss), miss
    assert_no_fake_secrets(miss)


def test_controlled_pre_and_post_scripts_can_mutate_request_assert_response_and_set_variables(monkeypatch, client):
    ids = create_api_lib(client, "script-allowlist")
    env = create_api_environment(
        client,
        lib_id=ids["lib_id"],
        marker="script-allowlist",
        headers={"Authorization": AUTH_SECRET, "X-Environment": "round25"},
        variables={"tenant": "env-tenant", "trace_id": "env-trace", "script_token": SCRIPT_SECRET},
    )
    case = create_api_case(
        client,
        lib_id=ids["lib_id"],
        marker="script-allowlist",
        path="/round25/scripts/users",
        request_body={"name": "before-script", "token": SCRIPT_SECRET},
        pre_script=(
            "set_header('X-Pre-Trace', variables['trace_id'])\n"
            "set_body({'name': 'from-pre-script', 'tenant': variables['tenant']})"
        ),
        post_script=(
            "assert_json_path('$.id', 'script-user-25')\n"
            "set_variable('created_user_id', '$.id')"
        ),
    )
    calls = install_ordered_httpx_mock(
        monkeypatch,
        [FakeHttpxResponse(status_code=200, json_body={"id": "script-user-25", "ok": True}, headers={"content-type": "application/json"})],
    )

    execution = post_json(
        client,
        f"{API_PREFIX}/api-test-cases/{case['case_id']}/execute",
        {"environment_id": env["env_id"], "variables": {"tenant": "runtime-tenant", "trace_id": "runtime-trace"}},
    )

    assert len(calls) == 1, calls
    assert calls[0]["headers"].get("X-Pre-Trace") == "runtime-trace", calls
    assert calls[0]["json"] == {"name": "from-pre-script", "tenant": "runtime-tenant"}, calls
    assert execution.get("status") == "passed", execution
    assert any(item.get("passed") is True and "json_path" in str(item.get("type")) for item in execution.get("assertion_results") or []), execution
    assert execution.get("variables", {}).get("created_user_id") == "script-user-25", execution
    assert_no_fake_secrets(execution)


@pytest.mark.parametrize(
    "dangerous_script",
    [
        f"import os\nset_header('Authorization', '{AUTH_SECRET}')",
        f"open('round25-forbidden.txt')\nset_body({{'token': '{SCRIPT_SECRET}'}})",
    ],
)
def test_dangerous_scripts_are_rejected_without_httpx_side_effects_or_secret_leakage(monkeypatch, client, dangerous_script):
    ids = create_api_lib(client, "script-reject")
    env = create_api_environment(client, lib_id=ids["lib_id"], marker="script-reject")
    case = create_api_case(
        client,
        lib_id=ids["lib_id"],
        marker="script-reject",
        path="/round25/scripts/reject",
        request_headers={"Authorization": AUTH_SECRET},
        request_body={"token": SCRIPT_SECRET},
        pre_script=dangerous_script,
    )
    calls = block_httpx_requests(monkeypatch)

    response = client.post(f"{API_PREFIX}/api-test-cases/{case['case_id']}/execute", json={"environment_id": env["env_id"]})
    result = assert_not_500_or_404(response)

    assert calls == [], calls
    result_text = payload_text(result).lower()
    assert any(marker in result_text for marker in ("script", "forbidden", "rejected", "not allowed", "unsafe")), result
    if isinstance(result, dict) and result.get("status") is not None:
        assert result["status"] in {"error", "failed", "rejected"}, result
    assert_no_fake_secrets(result)

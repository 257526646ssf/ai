from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

import httpx
import pytest

from aitest_platform.db.session import session_scope
from aitest_platform.models import ApiExecution, ApiSchedule
from conftest import API_PREFIX, data_of, first_item, object_id, post_json
from test_p0_acceptance import create_project


pytestmark = pytest.mark.contract

ROUND7_SECRET = "sk-round7-fake-secret"
ROUND7_AUTH = f"Bearer {ROUND7_SECRET}"
ROUND7_COOKIE = "round7_session=sk-round7-fake-secret"
SECRET_MARKERS = (ROUND7_SECRET, ROUND7_AUTH, ROUND7_COOKIE)


class FakeHttpxResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        json_body: Any | None = None,
        text: str | None = None,
        headers: dict[str, str] | None = None,
        elapsed_ms: int = 29,
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


def assert_no_round7_secret(payload: Any) -> None:
    dumped = payload_text(payload)
    for marker in SECRET_MARKERS:
        assert marker not in dumped, dumped


def list_items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        for key in ("list", "items", "records", "results", "data", "apis", "test_cases", "executions"):
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


def create_api_lib(client, marker: str) -> dict[str, Any]:
    project_id = create_project(client)
    lib = post_json(
        client,
        f"{API_PREFIX}/projects/{project_id}/api-test-libs",
        {"name": f"round7-{marker}-lib", "description": "Round 7 contract test lib."},
    )
    return {"project_id": project_id, "lib_id": object_id(lib)}


def create_endpoint_case_environment(client, *, marker: str) -> dict[str, Any]:
    ids = create_api_lib(client, marker)
    imported = post_json(
        client,
        f"{API_PREFIX}/api-test-libs/{ids['lib_id']}/apis/import",
        {
            "name": f"round7-{marker}-endpoint",
            "method": "POST",
            "path": f"/round7/{marker}/users",
            "headers": {"Content-Type": "application/json"},
            "body": {"type": "object", "properties": {"name": {"type": "string"}}},
            "response": {"status": 200},
        },
    )
    api_id = object_id(first_api(imported), "id", "api_id")
    generated = post_json(
        client,
        f"{API_PREFIX}/apis/{api_id}/generate-test-cases",
        {
            "name": f"round7-{marker}-case",
            "request_headers": {"X-Round": "7"},
            "request_body": {"name": marker},
            "expected_status": 200,
            "assertions": [{"type": "status_code", "expected": 200}],
        },
    )
    case_id = object_id(first_item(generated.get("test_cases") or generated), "id", "case_id")
    environment = post_json(
        client,
        f"{API_PREFIX}/api-test-libs/{ids['lib_id']}/environments",
        {
            "name": f"round7-{marker}-env",
            "base_url": "https://round7.example.invalid/base",
            "headers": {"Authorization": ROUND7_AUTH, "Cookie": ROUND7_COOKIE},
            "is_active": True,
        },
    )
    ids.update({"api_id": api_id, "case_id": case_id, "env_id": object_id(environment, "id", "environment_id")})
    return ids


def install_httpx_mock(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def fake_request(self: httpx.Client, method: str, url: str, **kwargs: Any) -> FakeHttpxResponse:
        calls.append(
            {
                "method": method,
                "url": str(url),
                "headers": dict(kwargs.get("headers") or {}),
                "params": kwargs.get("params"),
                "json": kwargs.get("json"),
            }
        )
        return FakeHttpxResponse(
            status_code=200,
            json_body={"ok": True, "secret": ROUND7_SECRET},
            headers={"set-cookie": ROUND7_COOKIE, "x-safe": "visible"},
        )

    monkeypatch.setattr(httpx.Client, "request", fake_request)
    return calls


def get_schedule(schedule_id: int | str) -> dict[str, Any]:
    with session_scope() as session:
        schedule = session.get(ApiSchedule, int(schedule_id))
        assert schedule is not None, f"schedule {schedule_id} was not persisted"
        return {
            "id": schedule.id,
            "is_enabled": schedule.is_enabled,
            "last_run_at": schedule.last_run_at,
            "last_result": schedule.last_result,
        }


def get_api_executions(execution_ids: list[int | str]) -> list[dict[str, Any]]:
    with session_scope() as session:
        executions = [session.get(ApiExecution, int(execution_id)) for execution_id in execution_ids]
        assert all(execution is not None for execution in executions), execution_ids
        return [
            {
                "id": execution.id,
                "case_id": execution.case_id,
                "schedule_id": execution.schedule_id,
                "status": execution.status,
                "request_snapshot": execution.request_snapshot,
                "response_snapshot": execution.response_snapshot,
            }
            for execution in executions
            if execution is not None
        ]


def execution_ids_from(payload: Any) -> list[int | str]:
    if isinstance(payload, dict):
        if isinstance(payload.get("execution_ids"), list):
            return payload["execution_ids"]
        if payload.get("execution_id") is not None:
            return [payload["execution_id"]]
        executions = payload.get("executions")
        if isinstance(executions, list):
            return [object_id(item, "id", "execution_id") for item in executions if isinstance(item, dict)]
        if payload.get("id") is not None:
            return [payload["id"]]
    return []


def test_openapi_json_import_persists_endpoint_and_can_generate_api_test_case(client):
    ids = create_api_lib(client, "openapi")
    document = {
        "openapi": "3.0.3",
        "info": {"title": "Round7 OpenAPI", "version": "1.0.0"},
        "paths": {
            "/round7/openapi/orders": {
                "post": {
                    "summary": "Create round7 order",
                    "operationId": "createRound7Order",
                    "parameters": [{"name": "dry_run", "in": "query", "schema": {"type": "boolean"}}],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {"sku": {"type": "string"}, "quantity": {"type": "integer"}},
                                    "required": ["sku"],
                                }
                            }
                        }
                    },
                    "responses": {"201": {"description": "created"}},
                }
            }
        },
    }

    imported = post_json(
        client,
        f"{API_PREFIX}/api-test-libs/{ids['lib_id']}/import-documents",
        {
            "source_type": "openapi",
            "format": "openapi_json",
            "document": document,
            "content": json.dumps(document),
            "generate_cases": True,
            "create_cases": True,
            "create_test_cases": True,
        },
    )
    assert_no_round7_secret(imported)

    endpoints = list_items(data_of(client.get(f"{API_PREFIX}/api-test-libs/{ids['lib_id']}/apis")))
    endpoint = next((item for item in endpoints if item.get("path") == "/round7/openapi/orders"), None)
    assert endpoint is not None, endpoints
    assert endpoint.get("method") == "POST", endpoint
    assert endpoint.get("name") in {"Create round7 order", "createRound7Order", "POST /round7/openapi/orders"}, endpoint

    cases = list_items(data_of(client.get(f"{API_PREFIX}/apis/{object_id(endpoint)}/test-cases")))
    assert cases, "OpenAPI import with generate_cases/create_cases/create_test_cases=true must persist ApiTestCase rows."
    assert all(str(case.get("endpoint_id") or case.get("api_id")) == str(object_id(endpoint)) for case in cases), cases
    assert_no_round7_secret(cases)


def test_postman_collection_import_flattens_nested_items_and_preserves_method_path_name(client):
    ids = create_api_lib(client, "postman")
    collection = {
        "info": {"name": "Round7 Postman", "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"},
        "item": [
            {
                "name": "Orders",
                "item": [
                    {
                        "name": "Create Postman Order",
                        "request": {
                            "method": "POST",
                            "header": [{"key": "Content-Type", "value": "application/json"}],
                            "url": {
                                "raw": "https://api.example.invalid/round7/postman/orders?source=collection",
                                "path": ["round7", "postman", "orders"],
                                "query": [{"key": "source", "value": "collection"}],
                            },
                            "body": {"mode": "raw", "raw": "{\"sku\":\"A-100\",\"quantity\":2}"},
                        },
                    }
                ],
            }
        ],
    }

    imported = post_json(
        client,
        f"{API_PREFIX}/api-test-libs/{ids['lib_id']}/apis/import",
        {"source_type": "postman_collection", "collection": collection},
    )
    assert_no_round7_secret(imported)

    endpoints = list_items(data_of(client.get(f"{API_PREFIX}/api-test-libs/{ids['lib_id']}/apis")))
    endpoint = next((item for item in endpoints if item.get("path") == "/round7/postman/orders"), None)
    assert endpoint is not None, endpoints
    assert endpoint.get("method") == "POST", endpoint
    assert endpoint.get("name") == "Create Postman Order", endpoint


def test_curl_import_parses_patch_query_headers_body_and_redacts_fake_secret(client):
    ids = create_api_lib(client, "curl")
    command = (
        "curl -X PATCH 'https://api.example.invalid/round7/curl/users/42?debug=true&page=2' "
        f"-H 'Authorization: {ROUND7_AUTH}' "
        "-H 'Content-Type: application/json' "
        f"-H 'Cookie: {ROUND7_COOKIE}' "
        "--data '{\"status\":\"active\",\"token\":\"sk-round7-fake-secret\"}'"
    )

    imported = post_json(
        client,
        f"{API_PREFIX}/api-test-libs/{ids['lib_id']}/apis/import",
        {"source_type": "curl", "curl": command, "generate_cases": True, "create_cases": True},
    )
    assert_no_round7_secret(imported)

    endpoint = first_api(imported)
    assert endpoint.get("method") == "PATCH", endpoint
    assert endpoint.get("path") == "/round7/curl/users/42", endpoint
    assert "debug=true" not in endpoint.get("path", ""), endpoint

    query_schema = schema_of(endpoint, "query") or {}
    headers_schema = schema_of(endpoint, "headers") or {}
    body_schema = schema_of(endpoint, "body") or {}
    endpoint_text = payload_text(endpoint)

    assert "debug" in payload_text(query_schema) and "page" in payload_text(query_schema), endpoint
    assert "Content-Type" in payload_text(headers_schema) or "content-type" in payload_text(headers_schema).lower(), endpoint
    assert "Authorization" in endpoint_text or "authorization" in endpoint_text.lower(), endpoint
    assert "status" in payload_text(body_schema), endpoint
    assert_no_round7_secret(endpoint)


def test_schedule_manual_run_creates_execution_and_updates_schedule_last_result(monkeypatch, client):
    calls = install_httpx_mock(monkeypatch)
    ids = create_endpoint_case_environment(client, marker="manual-schedule")
    schedule = post_json(
        client,
        f"{API_PREFIX}/api-test-libs/{ids['lib_id']}/schedules",
        {
            "name": "round7-manual-schedule",
            "cron_expression": "* * * * *",
            "target_type": "case",
            "target_ids": [ids["case_id"]],
            "is_enabled": True,
            "environment_id": ids["env_id"],
        },
    )
    schedule_id = object_id(schedule, "id", "schedule_id")

    result = post_json(client, f"{API_PREFIX}/api-schedules/{schedule_id}/run", {"environment_id": ids["env_id"]})
    assert calls, "manual schedule run must execute the scheduled API case without requiring real network."
    assert_no_round7_secret(result)

    execution_ids = execution_ids_from(result)
    assert execution_ids, result
    executions = get_api_executions(execution_ids)
    assert any(str(execution["case_id"]) == str(ids["case_id"]) for execution in executions), executions
    assert any(str(execution.get("schedule_id")) == str(schedule_id) for execution in executions) or execution_ids_from(result), executions
    assert_no_round7_secret(executions)

    persisted = get_schedule(schedule_id)
    assert persisted["last_run_at"] is not None, persisted
    assert isinstance(persisted["last_result"], dict) and persisted["last_result"], persisted
    assert_no_round7_secret(persisted)


def test_run_due_executes_only_enabled_due_schedule_and_skips_disabled(monkeypatch, client):
    calls = install_httpx_mock(monkeypatch)
    ids = create_endpoint_case_environment(client, marker="run-due")
    enabled = post_json(
        client,
        f"{API_PREFIX}/api-test-libs/{ids['lib_id']}/schedules",
        {
            "name": "round7-enabled-due",
            "cron_expression": "* * * * *",
            "target_type": "case",
            "target_ids": [ids["case_id"]],
            "is_enabled": True,
            "environment_id": ids["env_id"],
        },
    )
    disabled = post_json(
        client,
        f"{API_PREFIX}/api-test-libs/{ids['lib_id']}/schedules",
        {
            "name": "round7-disabled-due",
            "cron_expression": "* * * * *",
            "target_type": "case",
            "target_ids": [ids["case_id"]],
            "is_enabled": False,
            "environment_id": ids["env_id"],
        },
    )
    enabled_id = object_id(enabled, "id", "schedule_id")
    disabled_id = object_id(disabled, "id", "schedule_id")

    result = post_json(client, f"{API_PREFIX}/api-schedules/run-due", {"lib_id": ids["lib_id"], "environment_id": ids["env_id"]})
    assert calls, "run-due must execute at least the enabled due schedule."
    assert_no_round7_secret(result)

    enabled_after = get_schedule(enabled_id)
    disabled_after = get_schedule(disabled_id)
    assert enabled_after["last_run_at"] is not None, enabled_after
    assert isinstance(enabled_after["last_result"], dict) and enabled_after["last_result"], enabled_after
    assert disabled_after["last_run_at"] is None, disabled_after
    assert disabled_after["last_result"] in (None, {}, []), disabled_after

    result_text = payload_text(result)
    assert str(enabled_id) in result_text, result
    assert str(disabled_id) not in payload_text(result.get("executed") or result.get("execution_ids") or []), result

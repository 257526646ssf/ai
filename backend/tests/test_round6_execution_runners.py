from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from conftest import API_PREFIX, data_of, first_item, object_id, post_json
from test_p0_acceptance import create_project


pytestmark = pytest.mark.contract

AUTH_SECRET = "Bearer round6-token-secret"
API_KEY_SECRET = "round6-api-key-secret"
TOKEN_SECRET = "round6-token-secret"
COOKIE_SECRET = "round6-cookie-secret"
BODY_SECRET = "round6-body-secret"
SECRET_MARKERS = (AUTH_SECRET, API_KEY_SECRET, TOKEN_SECRET, COOKIE_SECRET, BODY_SECRET)


class FakeHttpxResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        json_body: Any | None = None,
        text: str | None = None,
        headers: dict[str, str] | None = None,
        elapsed_ms: int = 25,
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


def assert_not_http_500(response) -> Any:
    assert response.status_code in {200, 201}, response.text
    return data_of(response)


def install_subprocess_mock(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[list[str], dict[str, Any]], subprocess.CompletedProcess[str]],
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def fake_run(cmd: Any, *args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        cmd_list = [str(item) for item in (cmd if isinstance(cmd, (list, tuple)) else [cmd])]
        calls.append({"cmd": cmd_list, "args": args, "kwargs": kwargs})
        return handler(cmd_list, kwargs)

    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls


def create_auto_project(client, *, marker: str, generate_case: bool) -> dict[str, Any]:
    project_id = create_project(client)
    auto_project = post_json(
        client,
        f"{API_PREFIX}/projects/{project_id}/auto-projects",
        {
            "name": f"round6-auto-{marker}",
            "type": "ui",
            "language": "python",
            "framework": "pytest",
            "config": {"runner": "pytest", "token": TOKEN_SECRET},
        },
    )
    auto_project_id = object_id(auto_project, "id", "auto_project_id")
    case_file_id = None
    if generate_case:
        generated = post_json(client, f"{API_PREFIX}/auto-projects/{auto_project_id}/generate-cases")
        case_file_id = object_id(first_item(generated.get("cases") or generated), "id", "case_file_id")
    return {"project_id": project_id, "auto_project_id": auto_project_id, "case_file_id": case_file_id}


def create_perf_plan(client, *, marker: str, use_jmeter: bool = True, include_jmx: bool = True) -> dict[str, Any]:
    project_id = create_project(client)
    plan = post_json(
        client,
        f"{API_PREFIX}/projects/{project_id}/perf-plans",
        {
            "name": f"round6-perf-{marker}",
            "target_doc": "Round 6 performance runner contract.",
            "plan_schema": {"tool": "jmeter", "use_jmeter": use_jmeter, "threads": 2},
            "jmx_script": "<jmeterTestPlan><hashTree /></jmeterTestPlan>" if include_jmx else None,
            "status": "scripted" if include_jmx else "planned",
        },
    )
    return {"project_id": project_id, "plan_id": object_id(plan, "id", "plan_id")}


def create_api_lib_and_environment(client, *, marker: str) -> dict[str, Any]:
    project_id = create_project(client)
    lib = post_json(client, f"{API_PREFIX}/projects/{project_id}/api-test-libs", {"name": f"round6-api-{marker}"})
    lib_id = object_id(lib)
    env = post_json(
        client,
        f"{API_PREFIX}/api-test-libs/{lib_id}/environments",
        {
            "name": f"round6-env-{marker}",
            "base_url": "https://round6.example.test/base",
            "headers": {"Authorization": AUTH_SECRET, "Cookie": COOKIE_SECRET},
            "variables": {"tenant": "qa", "api_key": API_KEY_SECRET},
            "is_active": True,
        },
    )
    return {"project_id": project_id, "lib_id": lib_id, "env_id": object_id(env, "id", "environment_id")}


def create_api_case_in_lib(
    client,
    *,
    lib_id: int | str,
    marker: str,
    path: str,
    request_headers: dict[str, Any] | None = None,
    request_query: dict[str, Any] | None = None,
    request_body: Any | None = None,
    expected_status: int = 200,
) -> int | str:
    imported = post_json(
        client,
        f"{API_PREFIX}/api-test-libs/{lib_id}/apis/import",
        {"name": f"{marker}-endpoint", "method": "POST", "path": path, "response": {"status": expected_status}},
    )
    api_id = object_id(first_item(imported.get("apis") or imported), "id", "api_id")
    generated = post_json(
        client,
        f"{API_PREFIX}/apis/{api_id}/generate-test-cases",
        {
            "name": f"{marker}-case",
            "expected_status": expected_status,
            "request_headers": request_headers or {"X-Round": "6"},
            "request_query": request_query or {},
            "request_body": request_body if request_body is not None else {"marker": marker},
            "assertions": [{"type": "status_code", "expected": expected_status}],
        },
    )
    return object_id(first_item(generated.get("test_cases") or generated), "id", "case_id")


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
                "timeout": kwargs.get("timeout"),
            }
        )
        assert responses, "scenario executed more HTTP requests than expected"
        return responses.pop(0)

    monkeypatch.setattr(httpx.Client, "request", fake_request)
    return calls


def create_variable_scenario(client, *, stop_on_failure: bool = False) -> dict[str, Any]:
    ids = create_api_lib_and_environment(client, marker="scenario")
    create_case_id = create_api_case_in_lib(
        client,
        lib_id=ids["lib_id"],
        marker="create-user",
        path="/round6/users",
        request_body={"name": "Ada", "token": TOKEN_SECRET},
        expected_status=200,
    )
    use_case_id = create_api_case_in_lib(
        client,
        lib_id=ids["lib_id"],
        marker="use-user",
        path="/round6/users/{{created_user_id}}/sessions",
        request_headers={"X-Scenario-Value": "{{created_user_id}}", "X-Safe": "visible"},
        request_query={"api_key": API_KEY_SECRET, "tenant": "{{tenant}}"},
        request_body={"user_id": "{{created_user_id}}", "secret": BODY_SECRET},
    )
    scenario = post_json(
        client,
        f"{API_PREFIX}/api-test-libs/{ids['lib_id']}/scenarios",
        {
            "name": f"round6-variable-scenario-stop-{stop_on_failure}",
            "nodes": [
                {
                    "id": "create-user",
                    "type": "case",
                    "case_id": create_case_id,
                    "order": 1,
                    "extract": {"created_user_id": "$.body.user.id"},
                    "extract_variables": {"created_user_id": "body.user.id"},
                },
                {"id": "use-user", "type": "case", "case_id": use_case_id, "order": 2},
            ],
            "edges": [{"source": "create-user", "target": "use-user"}],
            "data_mappings": {
                "stop_on_failure": stop_on_failure,
                "extract": {"create-user": {"created_user_id": "$.body.user.id"}},
            },
        },
    )
    ids.update({"scenario_id": object_id(scenario, "id", "scenario_id"), "create_case_id": create_case_id, "use_case_id": use_case_id})
    return ids


def test_auto_execute_uses_real_runner_when_case_files_exist_and_persists_result(monkeypatch, client):
    calls = install_subprocess_mock(
        monkeypatch,
        lambda cmd, kwargs: subprocess.CompletedProcess(
            cmd,
            0,
            stdout="2 passed in 0.12s\ntoken=round6-token-secret should be redacted\n",
            stderr="",
        ),
    )
    ids = create_auto_project(client, marker="real-runner", generate_case=True)

    execution = post_json(client, f"{API_PREFIX}/auto-projects/{ids['auto_project_id']}/execute")

    assert calls, "AutoProject execution with AutoCaseFile must invoke the local runner path"
    assert execution.get("status") == "completed", execution
    assert execution.get("summary", {}).get("total", 0) >= 1, execution
    assert execution.get("summary", {}).get("passed", 0) >= 1, execution
    assert isinstance(execution.get("artifacts"), dict) and execution["artifacts"], execution
    assert isinstance(execution.get("log_excerpt"), str) and execution["log_excerpt"], execution
    assert isinstance(execution.get("duration_ms"), int) and execution["duration_ms"] >= 0, execution
    assert_no_fake_secrets(execution)


def test_auto_execute_without_case_files_keeps_placeholder_fallback(monkeypatch, client):
    calls = install_subprocess_mock(monkeypatch, lambda cmd, kwargs: pytest.fail("fallback must not call subprocess"))
    ids = create_auto_project(client, marker="fallback", generate_case=False)

    execution = post_json(client, f"{API_PREFIX}/auto-projects/{ids['auto_project_id']}/execute")

    assert calls == []
    assert execution.get("status") == "completed", execution
    assert execution.get("summary", {}).get("total") == 0, execution
    assert "placeholder" in payload_text(execution).lower(), execution
    assert_no_fake_secrets(execution)


@pytest.mark.parametrize(
    ("handler", "expected_status"),
    [
        (
            lambda cmd, kwargs: subprocess.CompletedProcess(
                cmd,
                2,
                stdout="collected 1 item\ntoken=round6-token-secret\n",
                stderr="Authorization=Bearer round6-token-secret\npytest failed\n",
            ),
            "failed",
        ),
        (
            lambda cmd, kwargs: (_ for _ in ()).throw(
                subprocess.TimeoutExpired(cmd=cmd, timeout=1, output="token=round6-token-secret", stderr="timeout cookie=round6-cookie-secret")
            ),
            "error",
        ),
    ],
)
def test_auto_execute_runner_failure_or_timeout_returns_structured_result_without_500(monkeypatch, client, handler, expected_status):
    install_subprocess_mock(monkeypatch, handler)
    ids = create_auto_project(client, marker=f"{expected_status}-path", generate_case=True)

    response = client.post(f"{API_PREFIX}/auto-projects/{ids['auto_project_id']}/execute")
    execution = assert_not_http_500(response)

    assert execution.get("status") == expected_status, execution
    assert execution.get("summary"), execution
    assert execution.get("log_excerpt") or execution.get("error_message"), execution
    assert_no_fake_secrets(execution)


def test_perf_execute_uses_jmeter_runner_and_parses_summary_data(monkeypatch, tmp_path, client):
    monkeypatch.setattr("shutil.which", lambda name: "jmeter" if name == "jmeter" else None)

    def fake_jmeter(cmd: list[str], kwargs: dict[str, Any]) -> subprocess.CompletedProcess[str]:
        assert any("jmeter" in part.lower() for part in cmd), cmd
        if "-l" in cmd:
            jtl_path = Path(cmd[cmd.index("-l") + 1])
            jtl_path.parent.mkdir(parents=True, exist_ok=True)
            jtl_path.write_text(
                "timeStamp,elapsed,label,responseCode,success,bytes,Latency\n"
                "1,100,GET /a,200,true,1000,80\n"
                "2,240,GET /b,200,true,1200,200\n"
                "3,360,GET /c,500,false,900,300\n",
                encoding="utf-8",
            )
        return subprocess.CompletedProcess(cmd, 0, stdout="Created the tree successfully\n", stderr="")

    calls = install_subprocess_mock(monkeypatch, fake_jmeter)
    ids = create_perf_plan(client, marker="jmeter-success", use_jmeter=True, include_jmx=True)

    data = post_json(client, f"{API_PREFIX}/perf-plans/{ids['plan_id']}/execute", {"use_jmeter": True})
    result = data.get("result") if isinstance(data, dict) and isinstance(data.get("result"), dict) else data

    assert calls, "Perf execution with JMX/use_jmeter must invoke the JMeter runner"
    assert result.get("status") in {"completed", "failed"}, result
    summary = result.get("summary_data") or result.get("summary") or {}
    assert summary.get("total") == 3 or summary.get("sample_count") == 3, result
    assert summary.get("failed") == 1 or summary.get("error_count") == 1, result
    assert summary.get("p95_ms", 0) >= 240 or summary.get("max_ms", 0) >= 360, result
    assert isinstance(result.get("artifacts"), dict), result
    assert_no_fake_secrets(data)


@pytest.mark.parametrize(
    ("which_result", "handler"),
    [
        (None, lambda cmd, kwargs: pytest.fail("JMeter must not be called when the tool is missing")),
        ("jmeter", lambda cmd, kwargs: subprocess.CompletedProcess(cmd, 1, stdout="", stderr="api_key=round6-api-key-secret jmeter failed")),
    ],
)
def test_perf_execute_missing_tool_or_jmeter_error_returns_error_result_without_500(monkeypatch, client, which_result, handler):
    monkeypatch.setattr("shutil.which", lambda name: which_result if name == "jmeter" else None)
    install_subprocess_mock(monkeypatch, handler)
    ids = create_perf_plan(client, marker="jmeter-error", use_jmeter=True, include_jmx=True)

    response = client.post(f"{API_PREFIX}/perf-plans/{ids['plan_id']}/execute", json={"use_jmeter": True})
    data = assert_not_http_500(response)
    result = data.get("result") if isinstance(data, dict) and isinstance(data.get("result"), dict) else data

    assert result.get("status") == "error", result
    assert result.get("error_details") or result.get("summary_data", {}).get("error_message"), result
    assert_no_fake_secrets(data)


def test_api_scenario_executes_case_nodes_in_order_extracts_and_injects_variables(monkeypatch, client):
    calls = install_ordered_httpx_mock(
        monkeypatch,
        [
            FakeHttpxResponse(status_code=200, json_body={"user": {"id": "u-1001"}, "token": "scenario-visible-token"}),
            FakeHttpxResponse(status_code=200, json_body={"ok": True, "session": "s-2002"}),
        ],
    )
    ids = create_variable_scenario(client, stop_on_failure=False)

    data = post_json(client, f"{API_PREFIX}/api-scenarios/{ids['scenario_id']}/execute", {"environment_id": ids["env_id"]})

    assert len(calls) == 2, calls
    assert calls[0]["url"].endswith("/round6/users"), calls
    assert calls[1]["url"].endswith("/round6/users/u-1001/sessions"), calls
    assert calls[1]["headers"].get("X-Scenario-Value") == "u-1001", calls
    assert calls[1]["json"].get("user_id") == "u-1001", calls
    assert isinstance(data.get("executions"), list) and len(data["executions"]) == 2, data
    assert data.get("summary", {}).get("total") == 2, data
    assert data.get("summary", {}).get("passed") == 2, data
    assert data.get("variables", {}).get("created_user_id") == "u-1001", data
    assert_no_fake_secrets(data)


def test_api_scenario_stop_on_failure_stops_before_dependent_case(monkeypatch, client):
    calls = install_ordered_httpx_mock(
        monkeypatch,
        [FakeHttpxResponse(status_code=500, json_body={"error": "failed", "token": TOKEN_SECRET})],
    )
    ids = create_variable_scenario(client, stop_on_failure=True)

    response = client.post(f"{API_PREFIX}/api-scenarios/{ids['scenario_id']}/execute", json={"environment_id": ids["env_id"], "stop_on_failure": True})
    data = assert_not_http_500(response)

    assert len(calls) == 1, calls
    assert isinstance(data.get("executions"), list) and len(data["executions"]) in {1, 2}, data
    if len(data["executions"]) == 2:
        assert data["executions"][1].get("status") == "skipped", data
    assert data.get("summary", {}).get("total") == 2, data
    assert data.get("summary", {}).get("executed") == 1 or data.get("summary", {}).get("skipped") == 1, data
    assert data.get("summary", {}).get("failed") == 1, data
    assert data.get("status") in {"failed", "error"} or data.get("summary", {}).get("status") in {"failed", "error"}, data
    assert_no_fake_secrets(data)

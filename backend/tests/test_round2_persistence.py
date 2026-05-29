from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

import pytest

from conftest import API_PREFIX, data_of, first_item, object_id, post_json
from test_p0_acceptance import create_project


pytestmark = pytest.mark.contract

ROUND2_SECRET = "sk-secret-round2"


def assert_no_secret(payload: Any, secret: str = ROUND2_SECRET) -> None:
    assert secret not in json.dumps(payload, ensure_ascii=False), payload


def list_items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        for key in ("list", "items", "records", "results", "data"):
            nested = value.get(key)
            if isinstance(nested, list):
                assert all(isinstance(item, dict) for item in nested), nested
                return nested
        if "id" in value:
            return [value]
    if isinstance(value, list):
        assert all(isinstance(item, dict) for item in value), value
        return value
    pytest.fail(f"Expected a list-like response, got: {value!r}", pytrace=False)


def assert_list_contains_id(value: Any, expected_id: int | str, *, label: str) -> dict[str, Any]:
    items = list_items(value)
    for item in items:
        if str(object_id(item)) == str(expected_id):
            return item
    pytest.fail(f"{label} list did not contain id {expected_id!r}; items={items!r}", pytrace=False)


def assert_search_finds(client, keyword: str, expected_types: Iterable[str]) -> None:
    data = data_of(client.get(f"{API_PREFIX}/search", params={"q": keyword}))
    items = list_items(data)
    found_types = {str(item.get("type")) for item in items}
    missing = set(expected_types) - found_types
    assert not missing, f"search({keyword!r}) missing resource types {sorted(missing)}; results={items!r}"


def test_round2_api_test_persistence_chain_lists_created_assets(client):
    project_id = create_project(client)
    marker = f"round2-api-{project_id}"

    lib = post_json(
        client,
        f"{API_PREFIX}/projects/{project_id}/api-test-libs",
        {"name": f"{marker}-lib", "description": "Round 2 API contract lib."},
    )
    lib_id = object_id(lib)
    assert_list_contains_id(data_of(client.get(f"{API_PREFIX}/projects/{project_id}/api-test-libs")), lib_id, label="api-test-lib")

    imported = post_json(
        client,
        f"{API_PREFIX}/api-test-libs/{lib_id}/apis/import",
        {"name": f"{marker}-endpoint", "method": "POST", "path": f"/round2/{project_id}/login"},
    )
    api_id = object_id(first_item(imported.get("apis") or imported), "id", "api_id")
    assert_list_contains_id(data_of(client.get(f"{API_PREFIX}/api-test-libs/{lib_id}/apis")), api_id, label="api endpoint")

    generated = post_json(client, f"{API_PREFIX}/apis/{api_id}/generate-test-cases", {"mode": "contract"})
    case_id = object_id(first_item(generated.get("test_cases") or generated), "id", "case_id")
    assert_list_contains_id(data_of(client.get(f"{API_PREFIX}/apis/{api_id}/test-cases")), case_id, label="api test case")

    single_execution = post_json(client, f"{API_PREFIX}/api-test-cases/{case_id}/execute")
    assert object_id(single_execution, "id", "execution_id")

    batch_execution = post_json(client, f"{API_PREFIX}/api-test-cases/batch-executions", {"case_ids": [case_id]})
    assert first_item(batch_execution.get("executions") or batch_execution)

    environment = post_json(
        client,
        f"{API_PREFIX}/api-test-libs/{lib_id}/environments",
        {"name": f"{marker}-env", "base_url": "https://example.invalid", "variables": {"tenant": "round2"}},
    )
    env_id = object_id(environment, "id", "environment_id")
    assert_list_contains_id(data_of(client.get(f"{API_PREFIX}/api-test-libs/{lib_id}/environments")), env_id, label="api environment")

    scenario = post_json(
        client,
        f"{API_PREFIX}/api-test-libs/{lib_id}/scenarios",
        {"name": f"{marker}-scenario", "nodes": [{"id": str(api_id), "case_id": case_id}], "edges": []},
    )
    scenario_id = object_id(scenario, "id", "scenario_id")
    assert_list_contains_id(data_of(client.get(f"{API_PREFIX}/api-test-libs/{lib_id}/scenarios")), scenario_id, label="api scenario")
    assert object_id(post_json(client, f"{API_PREFIX}/api-scenarios/{scenario_id}/execute"), "id", "execution_id")

    schedule = post_json(
        client,
        f"{API_PREFIX}/api-test-libs/{lib_id}/schedules",
        {"name": f"{marker}-schedule", "cron_expression": "0 9 * * *", "target_type": "scenario", "target_ids": [scenario_id]},
    )
    schedule_id = object_id(schedule, "id", "schedule_id")
    assert_list_contains_id(data_of(client.get(f"{API_PREFIX}/api-test-libs/{lib_id}/schedules")), schedule_id, label="api schedule")


def test_round2_automation_persistence_chain_has_case_files_events_and_download_metadata(client):
    project_id = create_project(client)
    marker = f"round2-auto-{project_id}"

    auto_project = post_json(
        client,
        f"{API_PREFIX}/projects/{project_id}/auto-projects",
        {"name": f"{marker}-project", "type": "web", "language": "python", "framework": "playwright"},
    )
    auto_project_id = object_id(auto_project, "id", "auto_project_id")
    assert_list_contains_id(data_of(client.get(f"{API_PREFIX}/projects/{project_id}/auto-projects")), auto_project_id, label="auto project")

    framework = post_json(client, f"{API_PREFIX}/auto-projects/{auto_project_id}/generate-framework")
    assert object_id(framework.get("job") or framework, "id", "job_id")
    assert framework.get("files"), framework

    generated_cases = post_json(client, f"{API_PREFIX}/auto-projects/{auto_project_id}/generate-cases")
    case_files = generated_cases.get("cases") or generated_cases.get("files") or []
    assert case_files, "generate-cases must persist and return at least one AutoCaseFile placeholder."
    assert object_id(first_item(case_files), "id", "case_file_id")

    execution = post_json(client, f"{API_PREFIX}/auto-projects/{auto_project_id}/execute")
    execution_id = object_id(execution, "id", "execution_id")

    events = client.get(f"{API_PREFIX}/auto-executions/{execution_id}/events")
    assert events.status_code == 200, events.text
    assert str(execution_id) in events.text

    download = data_of(client.get(f"{API_PREFIX}/auto-projects/{auto_project_id}/download"))
    assert str(download.get("auto_project_id")) == str(auto_project_id), download
    assert download.get("download_url"), download


def test_round2_performance_persistence_chain_lists_results_and_report_metadata(client):
    project_id = create_project(client)
    marker = f"round2-perf-{project_id}"

    plan = post_json(
        client,
        f"{API_PREFIX}/projects/{project_id}/perf-plans",
        {"name": f"{marker}-plan", "target_doc": "p95 <= 500ms, error rate <= 1%"},
    )
    plan_id = object_id(plan, "id", "plan_id")
    assert_list_contains_id(data_of(client.get(f"{API_PREFIX}/projects/{project_id}/perf-plans")), plan_id, label="perf plan")

    generated_plan = post_json(client, f"{API_PREFIX}/perf-plans/{plan_id}/generate-plan")
    assert object_id(generated_plan.get("job") or generated_plan, "id", "job_id")
    assert generated_plan.get("plan"), generated_plan

    generated_script = post_json(client, f"{API_PREFIX}/perf-plans/{plan_id}/generate-script")
    assert object_id(generated_script.get("job") or generated_script, "id", "job_id")
    assert generated_script.get("script"), generated_script

    execution = post_json(client, f"{API_PREFIX}/perf-plans/{plan_id}/execute")
    result_id = object_id(execution.get("result") or execution, "id", "result_id")
    assert_list_contains_id(data_of(client.get(f"{API_PREFIX}/perf-plans/{plan_id}/results")), result_id, label="perf result")

    report = post_json(client, f"{API_PREFIX}/perf-plans/{plan_id}/generate-report")
    report_id = object_id(report.get("report") or report, "id", "report_id")
    assert report_id
    assert_search_finds(client, marker, {"perf_plans"})


def test_round2_configuration_contracts_and_secret_redaction(client):
    marker = "round2-config-contract"
    responses: list[Any] = []

    report_template = post_json(
        client,
        f"{API_PREFIX}/report-templates",
        {"name": f"{marker}-report", "type": "performance", "sections": ["summary", "risks"], "enabled": True},
    )
    responses.append(report_template)
    template_id = object_id(report_template, "id", "template_id")
    responses.append(data_of(client.get(f"{API_PREFIX}/report-templates")))
    assert_list_contains_id(responses[-1], template_id, label="report template")
    responses.append(data_of(client.patch(f"{API_PREFIX}/report-templates/{template_id}", json={"name": f"{marker}-report-updated"})))

    llm_config = post_json(
        client,
        f"{API_PREFIX}/llm-configs",
        {
            "name": f"{marker}-llm",
            "provider": "openai-compatible",
            "model": "round2-model",
            "base_url": "https://llm.example.invalid",
            "api_key": ROUND2_SECRET,
            "enabled": True,
        },
    )
    responses.append(llm_config)
    config_id = object_id(llm_config, "id", "config_id")
    responses.append(data_of(client.patch(f"{API_PREFIX}/llm-configs/{config_id}", json={"api_key": ROUND2_SECRET, "model": "round2-model-updated"})))
    responses.append(post_json(client, f"{API_PREFIX}/llm-configs/{config_id}/test"))
    responses.append(data_of(client.get(f"{API_PREFIX}/llm-usage/statistics")))
    responses.append(data_of(client.get(f"{API_PREFIX}/llm-configs")))
    assert_list_contains_id(responses[-1], config_id, label="llm config")

    prompt_templates = data_of(client.get(f"{API_PREFIX}/prompt-templates"))
    responses.append(prompt_templates)
    prompt_template_id = object_id(first_item(prompt_templates), "id", "template_id")
    responses.append(data_of(client.patch(f"{API_PREFIX}/prompt-templates/{prompt_template_id}", json={"content": f"{marker} {{requirement}}"})))
    responses.append(post_json(client, f"{API_PREFIX}/prompt-templates/{prompt_template_id}/test", {"variables": {"requirement": "round2"}}))

    for payload in responses:
        assert_no_secret(payload)


def test_round2_system_logs_and_search_return_second_round_assets(client):
    project_id = create_project(client)
    marker = f"round2-search-{project_id}"

    lib = post_json(client, f"{API_PREFIX}/projects/{project_id}/api-test-libs", {"name": f"{marker}-api-lib"})
    auto_project = post_json(
        client,
        f"{API_PREFIX}/projects/{project_id}/auto-projects",
        {"name": f"{marker}-auto", "type": "api", "language": "python", "framework": "pytest"},
    )
    perf_plan = post_json(client, f"{API_PREFIX}/projects/{project_id}/perf-plans", {"name": f"{marker}-perf"})

    logs = data_of(client.get(f"{API_PREFIX}/system/operation-logs"))
    log_items = list_items(logs)
    assert log_items, "operation logs must include persisted Round 2 actions."
    log_text = json.dumps(log_items, ensure_ascii=False)
    for created in (lib, auto_project, perf_plan):
        assert str(object_id(created)) in log_text, f"operation logs do not include created asset {created!r}"

    assert_search_finds(client, marker, {"api_test_libs", "auto_projects", "perf_plans"})

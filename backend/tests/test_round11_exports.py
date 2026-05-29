from __future__ import annotations

import base64
import io
import json
import zipfile
from typing import Any

import pytest

from conftest import API_PREFIX, data_of, first_item, object_id, post_json
from test_p0_acceptance import (
    create_project,
    create_requirement_document,
    create_requirement_lib,
    extract_requirement_item,
    extract_test_case_id,
)


pytestmark = pytest.mark.contract

ROUND11_SECRET = "sk-round11-fake-secret"
SENSITIVE_STRINGS = (ROUND11_SECRET, "Authorization", "token")


def payload_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def assert_no_sensitive(payload: Any) -> None:
    dumped = payload_text(payload)
    for sensitive in SENSITIVE_STRINGS:
        assert sensitive not in dumped, dumped


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
    pytest.fail(f"Expected list-like payload, got: {value!r}", pytrace=False)


def create_case_context(client) -> dict[str, Any]:
    project_id = create_project(client)
    lib_id = create_requirement_lib(client, project_id)
    document_id = create_requirement_document(client, project_id, lib_id)
    item_id = extract_requirement_item(client, document_id)
    post_json(client, f"{API_PREFIX}/requirement-items/{item_id}/generate-test-points")
    generated_cases = post_json(client, f"{API_PREFIX}/requirement-items/{item_id}/generate-test-cases", {"mode": "round11"})
    case_id = extract_test_case_id(generated_cases)
    patched_case = data_of(
        client.patch(
            f"{API_PREFIX}/test-cases/{case_id}",
            json={
                "title": f"Round 11 export case {project_id}",
                "case_type": "functional",
                "expected_result": f"Authorization: Bearer {ROUND11_SECRET} token={ROUND11_SECRET}",
            },
        )
    )
    execution = post_json(
        client,
        f"{API_PREFIX}/executions",
        {
            "project_id": project_id,
            "case_id": case_id,
            "status": "failed",
            "actual_result": f"Authorization: Bearer {ROUND11_SECRET}",
            "defect_title": f"Round 11 defect {project_id} {ROUND11_SECRET}",
            "create_defect": True,
        },
    )
    defects = list_items(data_of(client.get(f"{API_PREFIX}/defects", params={"projectId": project_id})))
    return {
        "project_id": project_id,
        "lib_id": lib_id,
        "document_id": document_id,
        "requirement_item_id": item_id,
        "case_id": case_id,
        "case_title": patched_case["title"],
        "execution_id": object_id(execution, "id", "execution_id"),
        "defect_id": object_id(first_item(defects), "id", "defect_id"),
    }


def create_auto_context(client, project_id: int | str) -> dict[str, Any]:
    auto_project = post_json(
        client,
        f"{API_PREFIX}/projects/{project_id}/auto-projects",
        {"name": f"round11-auto-{project_id}", "type": "ui", "language": "python", "framework": "pytest", "config": {"token": ROUND11_SECRET}},
    )
    auto_project_id = object_id(auto_project, "id", "auto_project_id")
    post_json(client, f"{API_PREFIX}/auto-projects/{auto_project_id}/generate-framework")
    generated_cases = post_json(client, f"{API_PREFIX}/auto-projects/{auto_project_id}/generate-cases")
    case_file_id = object_id(first_item(generated_cases.get("files") or generated_cases.get("cases") or generated_cases), "id", "case_file_id")
    return {"auto_project_id": auto_project_id, "case_file_id": case_file_id}


def create_perf_context(client, project_id: int | str) -> dict[str, Any]:
    plan = post_json(
        client,
        f"{API_PREFIX}/projects/{project_id}/perf-plans",
        {"name": f"round11-perf-{project_id}", "target_assets": {"auth": {"token": ROUND11_SECRET}}},
    )
    plan_id = object_id(plan, "id", "plan_id")
    post_json(client, f"{API_PREFIX}/perf-plans/{plan_id}/generate-script")
    execution = post_json(client, f"{API_PREFIX}/perf-plans/{plan_id}/execute")
    result = execution.get("result") if isinstance(execution.get("result"), dict) else execution
    return {"perf_plan_id": plan_id, "perf_result_id": object_id(result, "id", "result_id")}


@pytest.mark.parametrize(("fmt", "expected_ext", "expected_mime"), [("markdown", ".md", "text/markdown"), ("csv", ".csv", "text/csv"), ("json", ".json", "application/json")])
def test_test_case_export_supports_formats_filters_and_redaction(client, fmt: str, expected_ext: str, expected_mime: str):
    context = create_case_context(client)

    exported = data_of(
        client.get(
            f"{API_PREFIX}/test-cases/export",
            params={"projectId": context["project_id"], "caseIds": str(context["case_id"]), "format": fmt},
        )
    )

    assert exported["format"] == fmt, exported
    assert exported["filename"].endswith(expected_ext), exported
    assert exported["mime_type"].startswith(expected_mime), exported
    assert exported["count"] >= 1, exported
    assert context["case_title"] in exported["content"], exported
    assert_no_sensitive(exported)


@pytest.mark.parametrize("fmt", ["markdown", "csv", "json"])
def test_defect_export_supports_project_status_filter_and_redaction(client, fmt: str):
    context = create_case_context(client)

    exported = data_of(client.get(f"{API_PREFIX}/defects/export", params={"projectId": context["project_id"], "status": "open", "format": fmt}))

    assert exported["format"] == fmt, exported
    assert exported["count"] >= 1, exported
    assert "Round 11 defect" in exported["content"], exported
    assert_no_sensitive(exported)


def test_auto_project_download_returns_decodable_zip_without_placeholder_or_secrets(client):
    context = create_case_context(client)
    auto_context = create_auto_context(client, context["project_id"])

    download = data_of(client.get(f"{API_PREFIX}/auto-projects/{auto_context['auto_project_id']}/download"))

    assert download["filename"].endswith(".zip"), download
    assert download["mime_type"] == "application/zip", download
    assert download["file_count"] >= 2, download
    raw_zip = base64.b64decode(download["content_base64"])
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as archive:
        names = set(archive.namelist())
        assert "README.md" in names, names
        assert "pytest.ini" in names, names
        assert any(name.startswith("tests/") and name.endswith(".py") for name in names), names
    assert "placeholder" not in payload_text(download).lower(), download
    assert_no_sensitive(download)


def test_perf_plan_script_and_result_download_are_structured_and_redacted(client):
    context = create_case_context(client)
    perf_context = create_perf_context(client, context["project_id"])

    script = data_of(client.get(f"{API_PREFIX}/perf-plans/{perf_context['perf_plan_id']}/download-script"))
    result = data_of(client.get(f"{API_PREFIX}/perf-plans/{perf_context['perf_plan_id']}/results/{perf_context['perf_result_id']}/download"))

    assert script["format"] == "jmx", script
    assert script["filename"].endswith(".jmx"), script
    assert "<jmeterTestPlan" in script["content"], script
    assert result["format"] == "json", result
    assert result["filename"].endswith(".json"), result
    assert str(perf_context["perf_result_id"]) in result["content"], result
    assert "raw_file_available" in result, result
    assert_no_sensitive(script)
    assert_no_sensitive(result)

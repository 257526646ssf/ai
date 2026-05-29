from __future__ import annotations

import json
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

ROUND10_SECRET = "sk-round10-fake-secret"
SENSITIVE_STRINGS = (ROUND10_SECRET, "Authorization", "token")


def payload_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def assert_no_sensitive_values(payload: Any) -> None:
    dumped = payload_text(payload)
    for sensitive in SENSITIVE_STRINGS:
        assert sensitive not in dumped, dumped


def assert_not_placeholder(payload: Any) -> None:
    dumped = payload_text(payload).lower()
    assert "placeholder" not in dumped, dumped


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


def created_report(payload: dict[str, Any]) -> dict[str, Any]:
    report = payload.get("report") if isinstance(payload.get("report"), dict) else payload
    assert isinstance(report, dict), payload
    assert object_id(report, "id", "report_id")
    return report


def get_source_refs(report: dict[str, Any]) -> dict[str, Any]:
    refs = report.get("source_refs") or report.get("source_refs_json") or report.get("data_snapshot", {}).get("source_refs")
    assert isinstance(refs, dict) and refs, report
    return refs


def get_summary(snapshot: dict[str, Any], key: str) -> dict[str, Any]:
    summary = snapshot.get(key)
    if isinstance(summary, dict) and isinstance(summary.get("summary"), dict):
        summary = summary["summary"]
    assert isinstance(summary, dict) and summary, snapshot
    return summary


def assert_count(summary: dict[str, Any], expected_minimum: int = 1) -> None:
    numeric_values = [value for value in summary.values() if isinstance(value, int | float)]
    assert numeric_values and max(numeric_values) >= expected_minimum, summary


def create_api_assets(client, project_id: int | str, marker: str) -> dict[str, Any]:
    lib = post_json(
        client,
        f"{API_PREFIX}/projects/{project_id}/api-test-libs",
        {"name": f"{marker}-api-lib", "description": "Round 10 reporting API assets."},
    )
    lib_id = object_id(lib, "id", "lib_id")
    imported = post_json(
        client,
        f"{API_PREFIX}/api-test-libs/{lib_id}/apis/import",
        {
            "name": f"{marker}-checkout-endpoint",
            "method": "POST",
            "path": f"/round10/{project_id}/checkout",
            "headers": {"Authorization": f"Bearer {ROUND10_SECRET}"},
            "query": {"token": ROUND10_SECRET},
            "body": {"order_id": marker},
            "generate_cases": True,
        },
    )
    endpoint = first_item(imported.get("apis") or imported)
    endpoint_id = object_id(endpoint, "id", "api_id")
    generated = post_json(client, f"{API_PREFIX}/apis/{endpoint_id}/generate-test-cases", {"mode": "reporting"})
    api_case_id = object_id(first_item(generated.get("test_cases") or generated), "id", "case_id")
    api_execution = post_json(client, f"{API_PREFIX}/api-test-cases/{api_case_id}/execute")
    return {
        "api_lib_id": lib_id,
        "api_endpoint_id": endpoint_id,
        "api_case_id": api_case_id,
        "api_execution_id": object_id(api_execution, "id", "execution_id"),
    }


def create_auto_assets(client, project_id: int | str, marker: str) -> dict[str, Any]:
    auto_project = post_json(
        client,
        f"{API_PREFIX}/projects/{project_id}/auto-projects",
        {
            "name": f"{marker}-auto-project",
            "type": "api",
            "language": "python",
            "framework": "pytest",
            "config": {"token": ROUND10_SECRET},
        },
    )
    auto_project_id = object_id(auto_project, "id", "auto_project_id")
    post_json(client, f"{API_PREFIX}/auto-projects/{auto_project_id}/generate-framework")
    generated_cases = post_json(client, f"{API_PREFIX}/auto-projects/{auto_project_id}/generate-cases")
    auto_case_id = object_id(first_item(generated_cases.get("cases") or generated_cases.get("files") or generated_cases), "id", "case_file_id")
    auto_execution = post_json(client, f"{API_PREFIX}/auto-projects/{auto_project_id}/execute")
    return {
        "auto_project_id": auto_project_id,
        "auto_case_id": auto_case_id,
        "auto_execution_id": object_id(auto_execution, "id", "execution_id"),
    }


def create_perf_assets(client, project_id: int | str, marker: str) -> dict[str, Any]:
    plan = post_json(
        client,
        f"{API_PREFIX}/projects/{project_id}/perf-plans",
        {
            "name": f"{marker}-perf-plan",
            "target_doc": "Round 10 reporting p95 <= 250ms and error rate <= 1%.",
            "target_assets": {"auth": {"token": ROUND10_SECRET}},
        },
    )
    plan_id = object_id(plan, "id", "plan_id")
    post_json(client, f"{API_PREFIX}/perf-plans/{plan_id}/generate-plan")
    post_json(client, f"{API_PREFIX}/perf-plans/{plan_id}/generate-script")
    execution = post_json(client, f"{API_PREFIX}/perf-plans/{plan_id}/execute")
    result = execution.get("result") if isinstance(execution.get("result"), dict) else execution
    return {"perf_plan_id": plan_id, "perf_result_id": object_id(result, "id", "result_id"), "perf_result": result}


def create_round10_context(client) -> dict[str, Any]:
    project_id = create_project(client)
    marker = f"round10-reporting-{project_id}"
    lib_id = create_requirement_lib(client, project_id)
    document_id = create_requirement_document(client, project_id, lib_id)
    item_id = extract_requirement_item(client, document_id)
    post_json(client, f"{API_PREFIX}/requirement-items/{item_id}/confirm")
    post_json(client, f"{API_PREFIX}/requirement-items/{item_id}/generate-test-points")
    test_points = list_items(data_of(client.get(f"{API_PREFIX}/requirement-items/{item_id}/test-points")))

    generated_cases = post_json(
        client,
        f"{API_PREFIX}/requirement-items/{item_id}/generate-test-cases",
        {"case_types": ["functional"], "mode": "reporting"},
    )
    case_id = extract_test_case_id(generated_cases)
    execution = post_json(
        client,
        f"{API_PREFIX}/executions",
        {
            "project_id": project_id,
            "case_id": case_id,
            "executor_type": "manual",
            "status": "failed",
            "actual_result": "Round 10 reporting failure evidence.",
            "defect_title": f"{marker}-defect",
            "create_defect": True,
        },
    )
    defects = list_items(data_of(client.get(f"{API_PREFIX}/defects", params={"projectId": project_id})))

    return {
        "project_id": project_id,
        "marker": marker,
        "requirement_lib_id": lib_id,
        "document_id": document_id,
        "requirement_item_id": item_id,
        "test_point_id": object_id(first_item(test_points), "id", "point_id"),
        "test_case_id": case_id,
        "execution_id": object_id(execution, "id", "execution_id"),
        "defect_id": object_id(first_item(defects), "id", "defect_id"),
        **create_api_assets(client, project_id, marker),
        **create_auto_assets(client, project_id, marker),
        **create_perf_assets(client, project_id, marker),
    }


def create_comprehensive_report(client, context: dict[str, Any]) -> dict[str, Any]:
    payload = post_json(
        client,
        f"{API_PREFIX}/reports/comprehensive",
        {
            "project_id": context["project_id"],
            "type": "comprehensive",
            "title": f"{context['marker']}-comprehensive",
            "scope": {"project_id": context["project_id"]},
        },
    )
    return created_report(payload)


def test_comprehensive_report_snapshot_aggregates_all_round10_sources_without_placeholders(client):
    context = create_round10_context(client)
    report = create_comprehensive_report(client, context)

    snapshot = report.get("data_snapshot")
    assert isinstance(snapshot, dict) and snapshot, report
    for key in ("requirements", "test_cases", "executions", "defects", "api", "auto", "perf"):
        assert_count(get_summary(snapshot, key))

    refs = get_source_refs(report)
    expected_refs = {
        "requirement_item_ids": context["requirement_item_id"],
        "test_case_ids": context["test_case_id"],
        "execution_ids": context["execution_id"],
        "defect_ids": context["defect_id"],
        "api_test_lib_ids": context["api_lib_id"],
        "api_endpoint_ids": context["api_endpoint_id"],
        "api_test_case_ids": context["api_case_id"],
        "api_execution_ids": context["api_execution_id"],
        "auto_project_ids": context["auto_project_id"],
        "auto_execution_ids": context["auto_execution_id"],
        "perf_plan_ids": context["perf_plan_id"],
        "perf_result_ids": context["perf_result_id"],
    }
    refs_text = payload_text(refs)
    for label, expected_id in expected_refs.items():
        assert label in refs, refs
        assert str(expected_id) in refs_text, refs

    assert_not_placeholder(report)
    assert_no_sensitive_values(report)


@pytest.mark.parametrize(
    ("fmt", "expected_mime"),
    [
        ("markdown", "text/markdown"),
        ("html", "text/html"),
        ("json", "application/json"),
    ],
)
def test_report_download_returns_requested_format_mime_content_and_filename(client, fmt: str, expected_mime: str):
    context = create_round10_context(client)
    report = create_comprehensive_report(client, context)
    report_id = object_id(report, "id", "report_id")

    download = data_of(client.get(f"{API_PREFIX}/reports/{report_id}/download", params={"format": fmt}))

    assert download.get("format") == fmt, download
    assert str(download.get("mime_type", "")).startswith(expected_mime), download
    assert isinstance(download.get("content"), str) and download["content"].strip(), download
    assert str(download.get("filename", "")).endswith(f".{fmt if fmt != 'markdown' else 'md'}"), download
    assert_not_placeholder(download)
    assert_no_sensitive_values(download)


def test_lightweight_conclusions_reuse_project_context_and_can_save_report(client):
    context = create_round10_context(client)

    conclusion = post_json(
        client,
        f"{API_PREFIX}/reports/lightweight-conclusions",
        {
            "project_id": context["project_id"],
            "save": True,
            "title": f"{context['marker']}-lightweight",
            "question": "Summarize release risk from current test evidence.",
            "notes": {"token": ROUND10_SECRET},
        },
    )

    metrics = conclusion.get("metrics")
    assert isinstance(metrics, dict) and metrics, conclusion
    for key in ("requirements", "test_cases", "executions", "defects", "api", "auto", "perf"):
        assert_count(get_summary(metrics, key))
    refs = conclusion.get("source_refs")
    assert isinstance(refs, dict) and refs, conclusion
    assert isinstance(conclusion.get("conclusion"), str) and conclusion["conclusion"].strip(), conclusion

    saved_report_id = conclusion.get("report_id") or object_id(conclusion.get("report") or {}, "id", "report_id")
    saved_report = data_of(client.get(f"{API_PREFIX}/reports/{saved_report_id}"))
    assert saved_report.get("type") in {"lightweight_conclusion", "lightweight", "conclusion"}, saved_report
    assert_no_sensitive_values(conclusion)
    assert_no_sensitive_values(saved_report)


def test_perf_plan_generate_report_uses_latest_perf_result_metrics_in_snapshot(client):
    context = create_round10_context(client)
    expected_summary = context["perf_result"].get("summary_data") or context["perf_result"].get("summary")
    assert isinstance(expected_summary, dict) and expected_summary, context["perf_result"]

    payload = post_json(client, f"{API_PREFIX}/perf-plans/{context['perf_plan_id']}/generate-report")
    report = created_report(payload)
    snapshot = report.get("data_snapshot")
    assert isinstance(snapshot, dict) and snapshot, report

    snapshot_text = payload_text(snapshot)
    for metric_key, metric_value in expected_summary.items():
        assert metric_key in snapshot_text, snapshot
        if isinstance(metric_value, int | float | str):
            assert str(metric_value) in snapshot_text, snapshot

    refs = get_source_refs(report)
    assert str(context["perf_plan_id"]) in payload_text(refs), refs
    assert str(context["perf_result_id"]) in payload_text(refs), refs
    assert_not_placeholder(report)
    assert_no_sensitive_values(report)


def test_reporting_responses_do_not_expose_sensitive_values_or_field_names(client):
    context = create_round10_context(client)
    report = create_comprehensive_report(client, context)
    report_id = object_id(report, "id", "report_id")

    responses = [
        report,
        data_of(client.get(f"{API_PREFIX}/reports/{report_id}/download", params={"format": "json"})),
        post_json(
            client,
            f"{API_PREFIX}/reports/lightweight-conclusions",
            {"project_id": context["project_id"], "save": True, "Authorization": f"Bearer {ROUND10_SECRET}", "token": ROUND10_SECRET},
        ),
        post_json(client, f"{API_PREFIX}/perf-plans/{context['perf_plan_id']}/generate-report"),
    ]

    for response in responses:
        assert_no_sensitive_values(response)

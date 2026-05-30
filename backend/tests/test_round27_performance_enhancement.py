from __future__ import annotations

import base64
import io
import json
import shutil
import subprocess
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from aitest_platform.db.session import session_scope
from aitest_platform.models import PerfResult
from conftest import API_PREFIX, data_of, object_id, post_json
from test_p0_acceptance import create_project


pytestmark = pytest.mark.contract

FAKE_SECRET = "round27-fake-secret-value"
AUTH_SECRET = f"Bearer {FAKE_SECRET}"
API_KEY_SECRET = f"round27-api-key-{FAKE_SECRET}"
COOKIE_SECRET = f"round27-cookie-{FAKE_SECRET}"
SECRET_MARKERS = (FAKE_SECRET, AUTH_SECRET, API_KEY_SECRET, COOKIE_SECRET)

DEFAULT_JMX = """
<jmeterTestPlan version="1.2">
  <hashTree>
    <stringProp name="HTTPSampler.domain">${__P(base_url,default.round27.test)}</stringProp>
    <stringProp name="ThreadGroup.num_threads">${__P(threads,1)}</stringProp>
    <stringProp name="ThreadGroup.ramp_time">${__P(ramp_up_seconds,1)}</stringProp>
    <stringProp name="Round27.authorization">${__P(auth_token,)}</stringProp>
  </hashTree>
</jmeterTestPlan>
""".strip()


def payload_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def assert_no_fake_secrets(payload: Any) -> None:
    dumped = payload_text(payload)
    for secret in SECRET_MARKERS:
        assert secret not in dumped, dumped


def response_payload(response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        pytest.fail(f"Expected JSON response, got: {response.text!r}", pytrace=False)
    assert isinstance(payload, dict), payload
    return payload


def assert_error_response(response, *, expected_statuses: set[int] | None = None) -> dict[str, Any]:
    statuses = expected_statuses or {400, 422}
    assert response.status_code in statuses, response.text
    payload = response_payload(response)
    assert {"code", "message", "data"} <= payload.keys(), payload
    assert payload.get("code") not in {0, 200, 201}, payload
    assert isinstance(payload.get("message"), str) and payload["message"], payload
    assert_no_fake_secrets(payload)
    return payload


def list_items(value: Any, *, keys: tuple[str, ...] = ("list", "items", "records", "results", "data")) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        for key in keys:
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


def create_perf_plan(
    client,
    *,
    marker: str,
    project_id: int | str | None = None,
    jmx_script: str | None = DEFAULT_JMX,
) -> dict[str, Any]:
    pid = project_id if project_id is not None else create_project(client)
    plan = post_json(
        client,
        f"{API_PREFIX}/projects/{pid}/perf-plans",
        {
            "name": f"round27-perf-{marker}",
            "target_doc": "Round 27 performance enhancement contract: p95 <= 300ms, error_rate <= 2%.",
            "target_assets": {
                "Authorization": AUTH_SECRET,
                "api_key": API_KEY_SECRET,
                "cookie": COOKIE_SECRET,
            },
            "plan_schema": {
                "tool": "jmeter",
                "template": "http_request",
                "jmeter_parameters": {
                    "base_url": "https://default.round27.test",
                    "threads": 1,
                    "ramp_up_seconds": 1,
                },
                "thresholds": {"p95_ms": 300, "error_rate": 0.02},
            },
            "jmx_script": jmx_script,
            "status": "scripted" if jmx_script else "planned",
        },
    )
    assert_no_fake_secrets(plan)
    return {"project_id": pid, "plan_id": object_id(plan, "id", "plan_id"), "plan": plan}


def get_plan_from_list(client, *, project_id: int | str, plan_id: int | str) -> dict[str, Any]:
    listed = data_of(client.get(f"{API_PREFIX}/projects/{project_id}/perf-plans"))
    plans = list_items(listed)
    found = next((item for item in plans if str(object_id(item, "id", "plan_id")) == str(plan_id)), None)
    assert found is not None, listed
    return found


def jmeter_parameters_from(plan: dict[str, Any]) -> dict[str, Any]:
    schema = plan.get("plan_schema") or {}
    candidates = [
        plan.get("jmeter_parameters"),
        schema.get("template_params") if isinstance(schema, dict) else None,
        schema.get("jmeter_parameters") if isinstance(schema, dict) else None,
        schema.get("template_parameters") if isinstance(schema, dict) else None,
        (schema.get("jmeter") or {}).get("parameters") if isinstance(schema, dict) and isinstance(schema.get("jmeter"), dict) else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, dict):
            return candidate
    pytest.fail(f"Plan does not expose persisted JMeter template parameters: {plan!r}", pytrace=False)


def result_of_perf_execute(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
    assert isinstance(result, dict), payload
    return result


def threshold_results_of(result: dict[str, Any]) -> Any:
    summary = result.get("summary_data") or result.get("summary") or {}
    for container in (result, summary):
        if isinstance(container, dict):
            for key in ("threshold_results", "threshold", "thresholds"):
                value = container.get(key)
                if value:
                    return value
    pytest.fail(f"Performance result must include threshold_results: {result!r}", pytrace=False)


def threshold_metric(results: Any, metric: str) -> dict[str, Any]:
    if isinstance(results, dict):
        value = results.get(metric)
        if isinstance(value, dict):
            return value
        for item in results.values():
            if isinstance(item, dict) and item.get("metric") == metric:
                return item
    if isinstance(results, list):
        for item in results:
            if isinstance(item, dict) and item.get("metric") == metric:
                return item
    pytest.fail(f"Missing threshold metric {metric!r} in {results!r}", pytrace=False)


def assert_threshold_metric(results: Any, metric: str, *, passed: bool) -> None:
    item = threshold_metric(results, metric)
    assert item.get("passed") is passed, item
    assert item.get("actual") is not None or item.get("value") is not None, item
    assert item.get("threshold") is not None or item.get("limit") is not None, item


def evidence_kinds(artifacts: dict[str, Any]) -> set[str]:
    evidence = artifacts.get("evidence") or artifacts.get("files") or []
    assert isinstance(evidence, list), artifacts
    return {str(item.get("kind") or item.get("type")) for item in evidence if isinstance(item, dict)}


def install_jmeter_mock(
    monkeypatch: pytest.MonkeyPatch,
    *,
    samples: list[dict[str, Any]],
    returncode: int = 0,
) -> list[list[str]]:
    monkeypatch.setattr(shutil, "which", lambda name: "jmeter" if name == "jmeter" else None)
    calls: list[list[str]] = []

    def fake_run(cmd: Any, *args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        cmd_list = [str(item) for item in (cmd if isinstance(cmd, (list, tuple)) else [cmd])]
        calls.append(cmd_list)
        if "-l" in cmd_list:
            jtl_path = Path(cmd_list[cmd_list.index("-l") + 1])
            jtl_path.parent.mkdir(parents=True, exist_ok=True)
            rows = ["timeStamp,elapsed,label,responseCode,success,bytes,Latency"]
            for index, sample in enumerate(samples, start=1):
                label = sample.get("label") or f"GET /round27/{index}"
                rows.append(
                    f"{index * 1000},{sample['elapsed']},{label},"
                    f"{sample.get('response_code', 200)},{str(sample.get('success', True)).lower()},1024,{sample['elapsed']}"
                )
            jtl_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
        return subprocess.CompletedProcess(
            cmd_list,
            returncode,
            stdout=f"round27 stdout token={FAKE_SECRET}",
            stderr=f"round27 stderr Cookie={COOKIE_SECRET}",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls


def seed_perf_result(
    *,
    plan_id: int | str,
    project_id: int | str,
    status: str = "completed",
    summary_data: dict[str, Any] | None = None,
    timeline_data: list[Any] | None = None,
    artifacts: dict[str, Any] | None = None,
    is_baseline: bool = False,
    executed_at: datetime | None = None,
) -> int:
    with session_scope() as session:
        result = PerfResult(
            plan_id=int(plan_id),
            project_id=int(project_id),
            status=status,
            summary_data=summary_data or {"total": 10, "passed": 10, "failed": 0, "avg_ms": 100, "p95_ms": 200, "error_rate": 0},
            timeline_data=timeline_data or [{"second": 1, "avg_ms": 100}],
            error_details=[],
            raw_data_path=None,
            artifacts=artifacts or {"evidence": []},
            is_baseline=is_baseline,
            duration=60,
            executed_at=executed_at,
        )
        session.add(result)
        session.flush()
        return result.id


def get_perf_result_snapshot(result_id: int | str) -> dict[str, Any]:
    with session_scope() as session:
        result = session.get(PerfResult, int(result_id))
        assert result is not None, f"PerfResult({result_id}) was not persisted"
        return {
            "id": result.id,
            "plan_id": result.plan_id,
            "project_id": result.project_id,
            "status": result.status,
            "summary_data": result.summary_data,
            "artifacts": result.artifacts,
            "is_baseline": result.is_baseline,
        }


def decode_manifest(download: dict[str, Any]) -> dict[str, Any]:
    raw_zip = base64.b64decode(download["content_base64"])
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as archive:
        assert "manifest.json" in set(archive.namelist()), archive.namelist()
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
    assert isinstance(manifest, dict), manifest
    return manifest


def test_jmeter_template_parameters_patch_persist_download_and_invalid_patch_does_not_pollute_config(client):
    ids = create_perf_plan(client, marker="template-params")
    valid_parameters = {
        "base_url": "https://round27.example.test",
        "threads": 12,
        "ramp_up_seconds": 5,
        "duration_seconds": 60,
        "headers": {
            "Authorization": AUTH_SECRET,
            "X-Api-Key": API_KEY_SECRET,
            "Cookie": COOKIE_SECRET,
            "X-Round": "27",
        },
    }

    patched = data_of(
        client.patch(
            f"{API_PREFIX}/perf-plans/{ids['plan_id']}",
            json={"template_params": valid_parameters},
        )
    )
    assert_no_fake_secrets(patched)

    stored = get_plan_from_list(client, project_id=ids["project_id"], plan_id=ids["plan_id"])
    persisted_parameters = jmeter_parameters_from(stored)
    assert persisted_parameters.get("base_url") == valid_parameters["base_url"], stored
    assert int(persisted_parameters.get("threads")) == 12, stored
    assert int(persisted_parameters.get("ramp_up_seconds")) == 5, stored
    assert_no_fake_secrets(stored)

    script = data_of(client.get(f"{API_PREFIX}/perf-plans/{ids['plan_id']}/download-script"))
    assert "round27.example.test" in script.get("content", ""), script
    assert "12" in script.get("content", ""), script
    assert_no_fake_secrets(script)

    invalid = client.patch(
        f"{API_PREFIX}/perf-plans/{ids['plan_id']}",
        json={
            "template_params": {
                "base_url": "javascript:alert(1)",
                "threads": 0,
                "ramp_up_seconds": -1,
                "duration_seconds": "not-a-number",
                "auth_token": AUTH_SECRET,
            }
        },
    )
    assert_error_response(invalid)

    stored_after_invalid = get_plan_from_list(client, project_id=ids["project_id"], plan_id=ids["plan_id"])
    parameters_after_invalid = jmeter_parameters_from(stored_after_invalid)
    assert parameters_after_invalid.get("base_url") == valid_parameters["base_url"], stored_after_invalid
    assert int(parameters_after_invalid.get("threads")) == 12, stored_after_invalid
    assert "javascript:alert" not in payload_text(stored_after_invalid), stored_after_invalid
    assert_no_fake_secrets(stored_after_invalid)


def test_perf_execute_threshold_failure_keeps_result_artifacts_and_redacts_manifest(monkeypatch, tmp_path, client):
    calls = install_jmeter_mock(
        monkeypatch,
        samples=[
            {"elapsed": 100, "success": True},
            {"elapsed": 280, "success": True},
            {"elapsed": 620, "success": True},
            {"elapsed": 700, "success": False, "response_code": 500, "label": f"GET /round27/fail token={FAKE_SECRET}"},
        ],
    )
    ids = create_perf_plan(client, marker="threshold-failure")

    data = post_json(
        client,
        f"{API_PREFIX}/perf-plans/{ids['plan_id']}/execute",
        {
            "use_jmeter": True,
            "artifact_root": str(tmp_path / "threshold-failure"),
            "run_id": "round27-threshold-failure",
            "thresholds": {"p95_ms": 300, "error_rate": 0.1},
            "jmeter_parameters": {"base_url": "https://round27.example.test", "auth_token": AUTH_SECRET},
        },
    )
    result = result_of_perf_execute(data)

    assert calls, "JMeter runner must be invoked for threshold evaluation"
    assert result.get("status") in {"failed", "threshold_failed"}, result
    summary = result.get("summary_data") or {}
    assert summary.get("p95_ms", 0) > 300, result
    assert summary.get("error_rate", 0) > 0.1, result
    thresholds = threshold_results_of(result)
    assert_threshold_metric(thresholds, "p95_ms", passed=False)
    assert_threshold_metric(thresholds, "error_rate", passed=False)
    artifacts = result.get("artifacts")
    assert isinstance(artifacts, dict) and "jtl" in evidence_kinds(artifacts), result
    assert result.get("raw_data_path") and Path(str(result["raw_data_path"])).exists(), result
    assert_no_fake_secrets(result)

    artifact_download = data_of(client.get(f"{API_PREFIX}/perf-results/{object_id(result, 'id', 'result_id')}/artifacts/download"))
    manifest = decode_manifest(artifact_download)
    assert manifest.get("status") in {"failed", "threshold_failed"}, manifest
    assert_no_fake_secrets(manifest)
    assert_no_fake_secrets(artifact_download)


def test_perf_execute_threshold_boundary_equal_values_pass(monkeypatch, tmp_path, client):
    install_jmeter_mock(
        monkeypatch,
        samples=[
            {"elapsed": 100, "success": True},
            {"elapsed": 200, "success": True},
            {"elapsed": 300, "success": True},
            {"elapsed": 400, "success": False, "response_code": 500},
        ],
    )
    ids = create_perf_plan(client, marker="threshold-boundary")

    data = post_json(
        client,
        f"{API_PREFIX}/perf-plans/{ids['plan_id']}/execute",
        {
            "use_jmeter": True,
            "artifact_root": str(tmp_path / "threshold-boundary"),
            "run_id": "round27-threshold-boundary",
            "thresholds": {"p95_ms": 400, "error_rate": 0.25},
        },
    )
    result = result_of_perf_execute(data)

    assert result.get("status") == "completed", result
    thresholds = threshold_results_of(result)
    assert_threshold_metric(thresholds, "p95_ms", passed=True)
    assert_threshold_metric(thresholds, "error_rate", passed=True)
    assert_no_fake_secrets(result)


@pytest.mark.parametrize(
    "thresholds",
    [
        {"p95_ms": -1, "error_rate": 0.01},
        {"p95_ms": 300, "error_rate": 1.01},
        {"p95_ms": "fast", "error_rate": 0.01},
    ],
)
def test_perf_execute_invalid_thresholds_are_rejected_without_result(monkeypatch, tmp_path, client, thresholds: dict[str, Any]):
    install_jmeter_mock(monkeypatch, samples=[{"elapsed": 100, "success": True}])
    ids = create_perf_plan(client, marker=f"invalid-threshold-{payload_text(thresholds)}")
    before = {object_id(item, "id", "result_id") for item in list_items(data_of(client.get(f"{API_PREFIX}/perf-plans/{ids['plan_id']}/results")))}

    response = client.post(
        f"{API_PREFIX}/perf-plans/{ids['plan_id']}/execute",
        json={
            "use_jmeter": True,
            "artifact_root": str(tmp_path / "invalid-threshold"),
            "run_id": "round27-invalid-threshold",
            "thresholds": thresholds,
        },
    )
    assert_error_response(response)

    after = {object_id(item, "id", "result_id") for item in list_items(data_of(client.get(f"{API_PREFIX}/perf-plans/{ids['plan_id']}/results")))}
    assert after == before, {"before": before, "after": after, "thresholds": thresholds}


def test_perf_result_abort_running_is_idempotent_and_completed_cannot_abort(client):
    ids = create_perf_plan(client, marker="abort")
    running_id = seed_perf_result(plan_id=ids["plan_id"], project_id=ids["project_id"], status="running")

    first = post_json(client, f"{API_PREFIX}/perf-results/{running_id}/abort")
    first_result = first.get("result") if isinstance(first.get("result"), dict) else first
    first_abort = first.get("abort") if isinstance(first.get("abort"), dict) else first
    assert first_abort.get("aborted") is True, first
    assert first_result.get("status") in {"aborted", "cancelled", "canceled"}, first
    assert get_perf_result_snapshot(running_id)["status"] in {"aborted", "cancelled", "canceled"}
    assert_no_fake_secrets(first)

    second = post_json(client, f"{API_PREFIX}/perf-results/{running_id}/abort")
    second_result = second.get("result") if isinstance(second.get("result"), dict) else second
    second_abort = second.get("abort") if isinstance(second.get("abort"), dict) else second
    assert second_abort.get("aborted") is True, second
    assert second_abort.get("idempotent") is True, second
    assert str(object_id(second_result, "id", "result_id")) == str(running_id), second
    assert get_perf_result_snapshot(running_id)["status"] in {"aborted", "cancelled", "canceled"}
    assert_no_fake_secrets(second)

    completed_id = seed_perf_result(plan_id=ids["plan_id"], project_id=ids["project_id"], status="completed")
    response = client.post(f"{API_PREFIX}/perf-results/{completed_id}/abort")
    assert_error_response(response, expected_statuses={400, 409, 422})
    assert get_perf_result_snapshot(completed_id)["status"] == "completed"


def test_perf_result_history_compare_reports_delta_regressions_and_rejects_cross_scope_baseline(client):
    ids = create_perf_plan(client, marker="compare")
    baseline_id = seed_perf_result(
        plan_id=ids["plan_id"],
        project_id=ids["project_id"],
        is_baseline=True,
        summary_data={"total": 50, "passed": 50, "failed": 0, "avg_ms": 100, "p95_ms": 200, "error_rate": 0.01},
    )
    current_id = seed_perf_result(
        plan_id=ids["plan_id"],
        project_id=ids["project_id"],
        summary_data={"total": 50, "passed": 48, "failed": 2, "avg_ms": 140, "p95_ms": 280, "error_rate": 0.04},
    )

    compared = data_of(
        client.get(
            f"{API_PREFIX}/perf-plans/{ids['plan_id']}/results/{current_id}/compare",
            params={"baselineId": baseline_id},
        )
    )
    comparison = compared.get("comparison") if isinstance(compared.get("comparison"), dict) else compared
    assert str((comparison.get("baseline") or {}).get("id") or comparison.get("baseline_result_id")) == str(baseline_id), comparison
    assert str((comparison.get("current") or {}).get("id") or comparison.get("current_result_id")) == str(current_id), comparison
    delta = comparison.get("delta") or comparison.get("deltas")
    assert isinstance(delta, dict), comparison
    p95_delta = delta["p95_ms"].get("absolute") if isinstance(delta.get("p95_ms"), dict) else delta.get("p95_ms")
    error_rate_delta = delta["error_rate"].get("absolute") if isinstance(delta.get("error_rate"), dict) else delta.get("error_rate")
    assert p95_delta == pytest.approx(80), comparison
    assert error_rate_delta == pytest.approx(0.03), comparison
    regressions = comparison.get("regressions")
    assert isinstance(regressions, list) and regressions, comparison
    assert {"p95_ms", "error_rate"} <= {str(item.get("metric")) for item in regressions if isinstance(item, dict)}, comparison
    assert_no_fake_secrets(compared)

    other_plan = create_perf_plan(client, marker="compare-other-plan", project_id=ids["project_id"])
    other_plan_baseline_id = seed_perf_result(plan_id=other_plan["plan_id"], project_id=ids["project_id"], is_baseline=True)
    other_project = create_perf_plan(client, marker="compare-other-project")
    other_project_baseline_id = seed_perf_result(
        plan_id=other_project["plan_id"],
        project_id=other_project["project_id"],
        is_baseline=True,
    )

    for rejected_baseline_id in (other_plan_baseline_id, other_project_baseline_id):
        response = client.get(
            f"{API_PREFIX}/perf-plans/{ids['plan_id']}/results/{current_id}/compare",
            params={"baselineId": rejected_baseline_id},
        )
        assert_error_response(response, expected_statuses={400, 409, 422})


def test_project_performance_trend_fills_days_orders_dates_and_summarizes_failures(client):
    ids = create_perf_plan(client, marker="trend")
    today = datetime.now(timezone.utc).date()
    seed_perf_result(
        plan_id=ids["plan_id"],
        project_id=ids["project_id"],
        executed_at=datetime.combine(today - timedelta(days=6), datetime.min.time(), tzinfo=timezone.utc),
        summary_data={"total": 20, "passed": 20, "failed": 0, "avg_ms": 100, "p95_ms": 180, "error_rate": 0},
    )
    seed_perf_result(
        plan_id=ids["plan_id"],
        project_id=ids["project_id"],
        status="failed",
        executed_at=datetime.combine(today - timedelta(days=3), datetime.min.time(), tzinfo=timezone.utc),
        summary_data={
            "total": 20,
            "passed": 18,
            "failed": 2,
            "avg_ms": 180,
            "p95_ms": 360,
            "error_rate": 0.1,
            "threshold_status": "failed",
            "threshold_results": [{"metric": "p95_ms", "passed": False, "actual": 360, "threshold": 300}],
        },
    )
    seed_perf_result(
        plan_id=ids["plan_id"],
        project_id=ids["project_id"],
        executed_at=datetime.combine(today - timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc),
        summary_data={
            "total": 20,
            "passed": 20,
            "failed": 0,
            "avg_ms": 130,
            "p95_ms": 260,
            "error_rate": 0.01,
            "comparison": {"regressions": [{"metric": "p95_ms", "delta": 80}]},
        },
    )

    trend = data_of(client.get(f"{API_PREFIX}/projects/{ids['project_id']}/performance-trend", params={"days": 7}))
    assert trend.get("project_id") == ids["project_id"], trend
    assert trend.get("days") == 7, trend
    points = trend.get("points") or trend.get("items") or trend.get("trend")
    assert isinstance(points, list) and len(points) == 7, trend
    expected_dates = [(today - timedelta(days=offset)).isoformat() for offset in range(6, -1, -1)]
    dates = [point.get("date") for point in points]
    assert dates == expected_dates, points
    assert dates == sorted(dates), points
    point_by_date = {point["date"]: point for point in points}
    assert point_by_date[(today - timedelta(days=5)).isoformat()].get("total") == 0, points
    summary = trend.get("summary")
    assert isinstance(summary, dict), trend
    assert summary.get("result_count", summary.get("total", 0)) >= 3, summary
    assert "threshold_failed_count" in summary and summary["threshold_failed_count"] >= 1, summary
    assert "regression_count" in summary and summary["regression_count"] >= 1, summary
    assert_no_fake_secrets(trend)


def test_perf_generate_report_snapshot_includes_threshold_comparison_risks_recommendations_and_redacts(client):
    ids = create_perf_plan(client, marker="risk-report")
    baseline_id = seed_perf_result(
        plan_id=ids["plan_id"],
        project_id=ids["project_id"],
        is_baseline=True,
        summary_data={"total": 40, "passed": 40, "failed": 0, "avg_ms": 100, "p95_ms": 180, "error_rate": 0},
    )
    current_id = seed_perf_result(
        plan_id=ids["plan_id"],
        project_id=ids["project_id"],
        status="failed",
        summary_data={
            "total": 40,
            "passed": 35,
            "failed": 5,
            "avg_ms": 220,
            "p95_ms": 520,
            "error_rate": 0.125,
            "threshold_status": "failed",
            "threshold_results": [
                {"metric": "p95_ms", "passed": False, "actual": 520, "threshold": 300},
                {"metric": "error_rate", "passed": False, "actual": 0.125, "threshold": 0.02},
            ],
            "comparison": {
                "baseline_result_id": baseline_id,
                "current_result_id": "latest",
                "delta": {"p95_ms": 340, "error_rate": 0.125},
                "regressions": [{"metric": "p95_ms", "delta": 340}, {"metric": "error_rate", "delta": 0.125}],
            },
            "diagnostic_note": f"Authorization: {AUTH_SECRET}",
        },
        artifacts={"warnings": [{"type": "secret-warning", "message": f"token={FAKE_SECRET}"}]},
    )

    generated = post_json(client, f"{API_PREFIX}/perf-plans/{ids['plan_id']}/generate-report")
    report = generated.get("report") if isinstance(generated.get("report"), dict) else generated
    assert object_id(report, "id", "report_id"), generated
    snapshot = report.get("data_snapshot")
    assert isinstance(snapshot, dict) and snapshot, report
    expected_keys = ("performance_summary", "threshold", "comparison", "risk_items", "recommendations")
    missing_keys = [key for key in expected_keys if key not in snapshot]
    generated_text = payload_text(generated)
    leaked_secret_labels = [
        label
        for label, marker in {
            "FAKE_SECRET": FAKE_SECRET,
            "AUTH_SECRET": AUTH_SECRET,
            "API_KEY_SECRET": API_KEY_SECRET,
            "COOKIE_SECRET": COOKIE_SECRET,
        }.items()
        if marker in generated_text
    ]
    assert not missing_keys and not leaked_secret_labels, {
        "missing_snapshot_keys": missing_keys,
        "leaked_secret_labels": leaked_secret_labels,
        "snapshot_keys": sorted(snapshot),
    }
    assert str(current_id) in payload_text(snapshot.get("performance_summary")), snapshot
    assert snapshot["threshold"], snapshot
    assert snapshot["comparison"], snapshot
    assert isinstance(snapshot["risk_items"], list) and snapshot["risk_items"], snapshot
    assert isinstance(snapshot["recommendations"], list) and snapshot["recommendations"], snapshot

    download = data_of(client.get(f"{API_PREFIX}/reports/{object_id(report, 'id', 'report_id')}/download", params={"format": "json"}))
    assert_no_fake_secrets(download)

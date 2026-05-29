from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select

from aitest_platform.db.session import session_scope
from aitest_platform.models import (
    Defect,
    Execution,
    LlmConfig,
    LlmUsage,
    RequirementDocument,
    RequirementItem,
    RequirementLib,
    TestCase as DbTestCase,
    TestPoint as DbTestPoint,
)
from conftest import API_PREFIX, data_of, object_id, post_json


ROUND20_SECRET = "sk-round20-topbar-secret"


def _create_project(client, name: str) -> int:
    marker = uuid4().hex[:10]
    project = post_json(
        client,
        f"{API_PREFIX}/projects",
        {
            "code": f"round20-{marker}",
            "name": f"{name} {marker}",
            "description": "Round 20 dashboard/topbar backend contract.",
            "owner_name": "round20_backend_worker",
        },
    )
    return int(object_id(project, "id", "project_id"))


def _assert_no_secret_payload(payload: dict, secret: str = ROUND20_SECRET) -> None:
    serialized = json.dumps(payload, ensure_ascii=False).lower()
    assert secret.lower() not in serialized, serialized
    assert "api_key" not in serialized, serialized
    assert "apikey" not in serialized, serialized
    assert "api_key_ref" not in serialized, serialized


def test_empty_project_dashboard_round20_fields_are_stable(client):
    project_id = _create_project(client, "Round20 Empty Dashboard")

    dashboard = data_of(client.get(f"{API_PREFIX}/projects/{project_id}/dashboard"))

    trend = dashboard["execution_trend"]
    assert trend["days"] == 14
    assert len(trend["points"]) == 14
    assert all({"date", "passed", "failed", "blocked", "other", "total", "pass_rate"} <= set(point) for point in trend["points"])
    assert all(point["total"] == 0 and point["pass_rate"] == 0 for point in trend["points"])

    coverage = dashboard["requirement_coverage"]
    assert coverage["total"] == 0
    assert coverage["covered"] == 0
    assert coverage["partial"] == 0
    assert coverage["uncovered"] == 0
    assert coverage["rate"] == 0

    heatmap = dashboard["module_heatmap"]
    assert heatmap["dimensions"] == [
        {"key": "requirements", "label": "需求"},
        {"key": "test_cases", "label": "用例"},
        {"key": "executions", "label": "执行"},
        {"key": "defects", "label": "缺陷"},
    ]
    assert heatmap["rows"] == []


def _seed_dashboard_facts(project_id: int) -> dict[str, str]:
    marker = uuid4().hex[:10]
    now = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    with session_scope() as session:
        lib = RequirementLib(project_id=project_id, name=f"Round20 Lib {marker}", description="dashboard facts")
        session.add(lib)
        session.flush()

        document = RequirementDocument(
            project_id=project_id,
            lib_id=lib.id,
            document_number=f"REQ-R20-{marker}",
            name=f"Round20 Requirement {marker}",
            source_type="text",
            raw_content="Checkout and profile requirements for dashboard fact aggregation.",
        )
        session.add(document)
        session.flush()

        covered_item = RequirementItem(
            project_id=project_id,
            lib_id=lib.id,
            document_id=document.id,
            item_number=f"R20-COVERED-{marker}",
            title="Covered checkout requirement",
            module="Checkout",
        )
        partial_item = RequirementItem(
            project_id=project_id,
            lib_id=lib.id,
            document_id=document.id,
            item_number=f"R20-PARTIAL-{marker}",
            title="Partial checkout requirement",
            module="Checkout",
        )
        uncovered_item = RequirementItem(
            project_id=project_id,
            lib_id=lib.id,
            document_id=document.id,
            item_number=f"R20-UNCOVERED-{marker}",
            title="Uncovered profile requirement",
            module="Profile",
        )
        session.add_all([covered_item, partial_item, uncovered_item])
        session.flush()

        covered_point = DbTestPoint(requirement_item_id=covered_item.id, title="Covered point", point_type="functional")
        partial_point = DbTestPoint(requirement_item_id=partial_item.id, title="Partial covered point", point_type="functional")
        missing_point = DbTestPoint(requirement_item_id=partial_item.id, title="Partial missing point", point_type="exception")
        session.add_all([covered_point, partial_point, missing_point])
        session.flush()

        covered_case = DbTestCase(
            project_id=project_id,
            lib_id=lib.id,
            document_id=document.id,
            requirement_item_id=covered_item.id,
            test_point_id=covered_point.id,
            case_number=f"TC-R20-COVERED-{marker}",
            title="Covered checkout case",
            case_type="functional",
            steps=[],
            expected_result="Checkout succeeds.",
        )
        partial_case = DbTestCase(
            project_id=project_id,
            lib_id=lib.id,
            document_id=document.id,
            requirement_item_id=partial_item.id,
            test_point_id=partial_point.id,
            case_number=f"TC-R20-PARTIAL-{marker}",
            title="Partial checkout case",
            case_type="exception",
            steps=[],
            expected_result="Payment failure keeps cart.",
        )
        session.add_all([covered_case, partial_case])
        session.flush()

        passed = Execution(
            project_id=project_id,
            lib_id=lib.id,
            document_id=document.id,
            requirement_item_id=covered_item.id,
            case_id=covered_case.id,
            status="pass",
            executed_at=now,
        )
        failed = Execution(
            project_id=project_id,
            lib_id=lib.id,
            document_id=document.id,
            requirement_item_id=partial_item.id,
            case_id=partial_case.id,
            status="fail",
            executed_at=now,
        )
        blocked = Execution(
            project_id=project_id,
            lib_id=lib.id,
            document_id=document.id,
            requirement_item_id=partial_item.id,
            case_id=partial_case.id,
            status="blocked",
            executed_at=now - timedelta(days=1),
        )
        skipped = Execution(
            project_id=project_id,
            lib_id=lib.id,
            document_id=document.id,
            requirement_item_id=partial_item.id,
            case_id=partial_case.id,
            status="skipped",
            executed_at=now,
        )
        session.add_all([passed, failed, blocked, skipped])
        session.flush()

        defect = Defect(
            defect_number=f"DEF-R20-{marker}",
            project_id=project_id,
            execution_id=failed.id,
            case_id=partial_case.id,
            requirement_item_id=partial_item.id,
            title="Checkout payment failure defect",
            severity="major",
            status="open",
        )
        session.add(defect)
        return {"today": now.date().isoformat(), "yesterday": (now - timedelta(days=1)).date().isoformat()}


def test_dashboard_round20_fields_use_requirement_case_execution_and_defect_facts(client):
    project_id = _create_project(client, "Round20 Fact Dashboard")
    dates = _seed_dashboard_facts(project_id)

    dashboard = data_of(client.get(f"{API_PREFIX}/projects/{project_id}/dashboard"))

    coverage = dashboard["requirement_coverage"]
    assert coverage["total"] == 3
    assert coverage["covered"] == 1
    assert coverage["partial"] == 1
    assert coverage["uncovered"] == 1
    assert coverage["rate"] == 33.33
    assert coverage["test_points"] == 3
    assert coverage["test_cases"] == 2

    points_by_date = {point["date"]: point for point in dashboard["execution_trend"]["points"]}
    assert points_by_date[dates["today"]]["passed"] == 1
    assert points_by_date[dates["today"]]["failed"] == 1
    assert points_by_date[dates["today"]]["other"] == 1
    assert points_by_date[dates["today"]]["total"] == 3
    assert points_by_date[dates["today"]]["pass_rate"] == 33.33
    assert points_by_date[dates["yesterday"]]["blocked"] == 1
    assert points_by_date[dates["yesterday"]]["total"] == 1

    rows = {row["module"]: row for row in dashboard["module_heatmap"]["rows"]}
    assert rows["Checkout"]["requirements"] == 2
    assert rows["Checkout"]["test_cases"] == 2
    assert rows["Checkout"]["executions"] == 4
    assert rows["Checkout"]["defects"] == 1
    assert rows["Profile"]["requirements"] == 1
    assert rows["Profile"]["test_cases"] == 0
    assert rows["Profile"]["executions"] == 0
    assert rows["Profile"]["defects"] == 0


def _disable_llm_configs_for_test() -> list[tuple[int, bool, bool]]:
    with session_scope() as session:
        configs = list(session.scalars(select(LlmConfig)))
        snapshot = [(config.id, bool(config.is_enabled), bool(config.is_default)) for config in configs]
        for config in configs:
            config.is_enabled = False
            config.is_default = False
        return snapshot


def _restore_llm_configs(snapshot: list[tuple[int, bool, bool]]) -> None:
    with session_scope() as session:
        for config_id, is_enabled, is_default in snapshot:
            config = session.get(LlmConfig, config_id)
            if config is not None:
                config.is_enabled = is_enabled
                config.is_default = is_default


def test_llm_status_unconfigured_response_is_stable_without_provider_call(monkeypatch, client):
    monkeypatch.setenv("AITEST_ENABLE_REAL_LLM", "true")
    monkeypatch.delenv("AITEST_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("AITEST_LLM_MODEL", raising=False)
    monkeypatch.delenv("AITEST_LLM_API_KEY", raising=False)
    snapshot = _disable_llm_configs_for_test()
    try:
        status = data_of(client.get(f"{API_PREFIX}/system/llm-status"))
    finally:
        _restore_llm_configs(snapshot)

    assert status["status"] == "unconfigured"
    assert status["configured"] is False
    assert status["provider_call_performed"] is False
    assert status["provider_check"] == "not_performed"
    assert status["config"] is None
    assert status["runtime"]["base_url_configured"] is False
    assert status["runtime"]["credentials_configured"] is False
    assert set(status["runtime"]["missing"]) == {"base_url", "model", "credentials"}
    assert status["usage"]["usage_count"] >= 0
    assert status["usage"]["total_tokens"] >= 0
    _assert_no_secret_payload(status)


def test_llm_status_configured_response_reports_runtime_and_usage_without_secret(monkeypatch, client):
    marker = f"round20-llm-{uuid4().hex[:10]}"
    monkeypatch.setenv("AITEST_ENABLE_REAL_LLM", "true")
    monkeypatch.setenv("AITEST_LLM_BASE_URL", "https://round20.example.invalid/v1")
    monkeypatch.setenv("AITEST_LLM_MODEL", "round20-env-model")
    monkeypatch.setenv("AITEST_LLM_API_KEY", ROUND20_SECRET)

    config = post_json(
        client,
        f"{API_PREFIX}/llm-configs",
        {
            "name": marker,
            "base_url": "https://round20.config.invalid/v1",
            "api_key": ROUND20_SECRET,
            "model": "round20-model",
            "is_default": True,
            "is_enabled": True,
            "sort_order": -200000,
        },
    )
    config_id = int(object_id(config, "id", "config_id"))
    with session_scope() as session:
        for other in session.scalars(select(LlmConfig).where(LlmConfig.id != config_id)):
            other.is_default = False
        session.add(LlmUsage(config_id=config_id, module="round20_topbar", input_tokens=11, output_tokens=7, duration_ms=3))

    status = data_of(client.get(f"{API_PREFIX}/system/llm-status"))

    assert status["status"] == "ready"
    assert status["configured"] is True
    assert status["provider_call_performed"] is False
    assert status["config_id"] == config_id
    assert status["config_name"] == marker
    assert status["model"] == "round20-model"
    assert status["runtime"]["base_url_configured"] is True
    assert status["runtime"]["credentials_configured"] is True
    assert status["config"]["base_url_configured"] is True
    assert status["config"]["credential_ref_configured"] is True
    assert status["selected_config_usage"]["usage_count"] == 1
    assert status["selected_config_usage"]["total_tokens"] == 18
    assert status["usage"]["usage_count"] >= 1
    assert status["usage"]["total_tokens"] >= 18
    _assert_no_secret_payload(status)

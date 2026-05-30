from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import pytest

from aitest_platform.db.session import session_scope
from aitest_platform.models import (
    ApiEndpoint,
    ApiExecution,
    ApiTestCase,
    ApiTestLib,
    AutoExecution,
    AutoProject,
    Defect,
    Execution,
    PerfPlan,
    PerfResult,
    Project,
    Report,
    RequirementDocument,
    RequirementItem,
    RequirementLib,
    TestCase as CaseModel,
)
from conftest import API_PREFIX, data_of, object_id, post_json


pytestmark = pytest.mark.contract

FAKE_SECRET = "round28-fake-secret-value"
AUTH_SECRET = f"Bearer {FAKE_SECRET}"
API_KEY_SECRET = f"round28-api-key-{FAKE_SECRET}"
COOKIE_SECRET = f"round28-cookie-{FAKE_SECRET}"
SECRET_MARKERS = (FAKE_SECRET, AUTH_SECRET, API_KEY_SECRET, COOKIE_SECRET)

SECTION_TITLES = {
    "overview": "Overview",
    "requirements": "Requirements",
    "executions": "Executions",
    "defects": "Defects",
    "api": "API",
    "automation": "Automation",
    "performance": "Performance",
    "risks": "Risks",
    "todos": "Todos",
}
ALL_TEMPLATE_SECTIONS = tuple(SECTION_TITLES)


def payload_text(payload: Any) -> str:
    return payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def assert_no_sensitive_markers(payload: Any) -> None:
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


def assert_structured_error(
    response,
    *,
    expected_statuses: set[int] | None = None,
    field: str | None = None,
) -> dict[str, Any]:
    statuses = expected_statuses or {400, 422}
    assert response.status_code in statuses, response.text
    payload = response_payload(response)
    assert {"code", "message", "data", "trace_id"} <= payload.keys(), payload
    assert payload["code"] not in {0, 200, 201}, payload
    assert isinstance(payload["message"], str) and payload["message"], payload
    assert isinstance(payload["data"], dict), payload
    assert payload["data"].get("error_code") or payload["data"].get("errors") or payload["data"].get("field_errors"), payload
    if field is not None:
        dumped = payload_text(payload).lower()
        assert field.lower() in dumped, payload
    assert_no_sensitive_markers(payload)
    return payload


def list_items(
    value: Any,
    *,
    keys: tuple[str, ...] = ("list", "items", "records", "results", "data"),
) -> list[dict[str, Any]]:
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


def created_report(payload: dict[str, Any]) -> dict[str, Any]:
    report = payload.get("report") if isinstance(payload.get("report"), dict) else payload
    assert isinstance(report, dict), payload
    assert object_id(report, "id", "report_id")
    return report


def get_summary(container: dict[str, Any], key: str) -> dict[str, Any]:
    value = container.get(key)
    if isinstance(value, dict) and isinstance(value.get("summary"), dict):
        return value["summary"]
    assert isinstance(value, dict), container
    return value


def assert_count(summary: dict[str, Any], expected_minimum: int = 1) -> None:
    numeric_values = [value for value in summary.values() if isinstance(value, int | float)]
    assert numeric_values and max(numeric_values) >= expected_minimum, summary


def seed_round28_context(marker: str | None = None) -> dict[str, Any]:
    marker = marker or uuid4().hex[:10]
    malicious_title = f"Round28 checkout <script>alert('{marker}')</script>"
    now = datetime.now(timezone.utc)
    with session_scope() as session:
        project = Project(
            code=f"r28-{marker}",
            name=f"Round28 Report Center {marker}",
            description=f"Project description token={FAKE_SECRET}",
            owner_name="round28_qa",
        )
        session.add(project)
        session.flush()

        lib = RequirementLib(
            project_id=project.id,
            name=f"Round28 Requirement Library {marker}",
            description=f"Requirement lib Authorization: {AUTH_SECRET}",
        )
        session.add(lib)
        session.flush()

        document = RequirementDocument(
            project_id=project.id,
            lib_id=lib.id,
            document_number=f"REQ-R28-{marker}",
            name=f"Round28 Source Document {marker}",
            source_type="markdown",
            source_file_name=f"round28-{marker}.md",
            raw_content=f"# Report Center\n\nDo not leak api_key={API_KEY_SECRET}.",
            parser_status="completed",
            parser_metadata={"source": "round28", "cookie": COOKIE_SECRET},
        )
        session.add(document)
        session.flush()

        item = RequirementItem(
            project_id=project.id,
            lib_id=lib.id,
            document_id=document.id,
            item_number=f"R28-{marker}-001",
            title=malicious_title,
            summary=f"Report center must keep snapshots. Authorization: {AUTH_SECRET}",
            module="report-center",
            priority="P0",
            status="confirmed",
            confidence=0.96,
            case_status="generated",
            business_rules_json=[{"rule": "risk todo idempotency", "token": FAKE_SECRET}],
        )
        session.add(item)
        session.flush()

        case = CaseModel(
            project_id=project.id,
            lib_id=lib.id,
            document_id=document.id,
            requirement_item_id=item.id,
            case_number=f"TC-R28-{marker}-001",
            title=f"Round28 report center end to end {marker}",
            case_type="functional",
            steps=[{"step": 1, "action": "Generate report center snapshot."}],
            expected_result=f"Report output is redacted token={FAKE_SECRET}.",
            priority="P0",
            status="active",
        )
        session.add(case)
        session.flush()

        execution = Execution(
            project_id=project.id,
            lib_id=lib.id,
            document_id=document.id,
            requirement_item_id=item.id,
            case_id=case.id,
            executor_type="manual",
            status="failed",
            actual_result=f"Snapshot drift found. Authorization: {AUTH_SECRET}",
            response_snapshot={"body": "failed", "headers": {"Set-Cookie": COOKIE_SECRET}},
            artifact_summary_json={"log": f"api_key={API_KEY_SECRET}"},
            executed_at=now - timedelta(minutes=40),
        )
        session.add(execution)
        session.flush()

        defect = Defect(
            defect_number=f"BUG-R28-{marker}-001",
            project_id=project.id,
            execution_id=execution.id,
            case_id=case.id,
            requirement_item_id=item.id,
            title=f"Round28 report snapshot drift {marker}",
            actual_result=f"Drilldown reads live data api_key={API_KEY_SECRET}",
            severity="critical",
            status="open",
            remark="Release blocker for report center.",
        )
        session.add(defect)
        session.flush()

        api_lib = ApiTestLib(
            project_id=project.id,
            source_document_id=document.id,
            name=f"Round28 API Lib {marker}",
            description=f"API lib cookie={COOKIE_SECRET}",
            import_source="round28-contract",
        )
        session.add(api_lib)
        session.flush()

        endpoint = ApiEndpoint(
            lib_id=api_lib.id,
            requirement_item_id=item.id,
            name=f"Round28 report endpoint {marker}",
            method="POST",
            path=f"/round28/{marker}/reports",
            headers_schema={"Authorization": AUTH_SECRET},
            response_schema={"status": "failed"},
        )
        session.add(endpoint)
        session.flush()

        api_case = ApiTestCase(
            endpoint_id=endpoint.id,
            lib_id=api_lib.id,
            requirement_item_id=item.id,
            name=f"Round28 report endpoint contract {marker}",
            category="contract",
            request_headers={"X-Api-Key": API_KEY_SECRET},
            request_body={"template_id": "required"},
            assertions=[{"jsonpath": "$.data.report.id", "operator": "exists"}],
            status="active",
        )
        session.add(api_case)
        session.flush()

        api_execution = ApiExecution(
            lib_id=api_lib.id,
            endpoint_id=endpoint.id,
            case_id=api_case.id,
            run_type="case",
            status="failed",
            request_snapshot={"headers": {"Authorization": AUTH_SECRET}},
            response_snapshot={"status_code": 500, "body": f"token={FAKE_SECRET}"},
            assertion_results=[{"passed": False, "message": "report id missing"}],
            duration_ms=860,
            error_message=f"api_key={API_KEY_SECRET}",
            executed_at=now - timedelta(minutes=35),
        )
        session.add(api_execution)
        session.flush()

        auto_project = AutoProject(
            project_id=project.id,
            name=f"Round28 automation {marker}",
            type="ui",
            language="python",
            framework="pytest",
            extra_config={"cookie": COOKIE_SECRET},
        )
        session.add(auto_project)
        session.flush()

        auto_execution = AutoExecution(
            auto_project_id=auto_project.id,
            status="failed",
            summary={"total": 3, "passed": 2, "failed": 1, "errors": 0},
            artifacts={"screenshots": ["round28.png"], "secret": f"token={FAKE_SECRET}"},
            log_excerpt=f"Round28 automation failure Authorization: {AUTH_SECRET}",
            duration_ms=1200,
            executed_at=now - timedelta(minutes=30),
        )
        session.add(auto_execution)
        session.flush()

        perf_plan = PerfPlan(
            project_id=project.id,
            source_document_id=document.id,
            name=f"Round28 performance {marker}",
            requirement_item_ids_json=[item.id],
            target_assets_json={"api_key": API_KEY_SECRET, "cookie": COOKIE_SECRET},
            target_doc="p95 <= 300ms and error_rate <= 2%",
            plan_schema={"thresholds": {"p95_ms": 300, "error_rate": 0.02}},
            status="scripted",
        )
        session.add(perf_plan)
        session.flush()

        perf_result = PerfResult(
            plan_id=perf_plan.id,
            project_id=project.id,
            status="failed",
            summary_data={
                "total": 40,
                "passed": 35,
                "failed": 5,
                "avg_ms": 240,
                "p95_ms": 620,
                "error_rate": 0.125,
                "threshold_status": "failed",
                "threshold_results": [
                    {"metric": "p95_ms", "passed": False, "actual": 620, "threshold": 300},
                    {"metric": "error_rate", "passed": False, "actual": 0.125, "threshold": 0.02},
                ],
                "diagnostic_note": f"secret={FAKE_SECRET}",
            },
            timeline_data=[{"second": 1, "p95_ms": 620}],
            error_details=[{"type": "threshold", "message": f"Authorization: {AUTH_SECRET}"}],
            artifacts={"raw": f"cookie={COOKIE_SECRET}"},
            duration=60,
            executed_at=now - timedelta(minutes=20),
        )
        session.add(perf_result)
        session.flush()

        return {
            "marker": marker,
            "project_id": project.id,
            "lib_id": lib.id,
            "document_id": document.id,
            "requirement_item_id": item.id,
            "case_id": case.id,
            "execution_id": execution.id,
            "defect_id": defect.id,
            "api_lib_id": api_lib.id,
            "api_endpoint_id": endpoint.id,
            "api_case_id": api_case.id,
            "api_execution_id": api_execution.id,
            "auto_project_id": auto_project.id,
            "auto_execution_id": auto_execution.id,
            "perf_plan_id": perf_plan.id,
            "perf_result_id": perf_result.id,
            "original_requirement_title": malicious_title,
        }


def create_template(
    client,
    *,
    marker: str,
    report_type: str = "comprehensive",
    sections: list[str] | None = None,
    supported_formats: list[str] | None = None,
    is_default: bool = False,
    version: str = "v28",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": f"round28-template-{marker}",
        "report_type": report_type,
        "sections": sections or list(ALL_TEMPLATE_SECTIONS),
        "is_default": is_default,
        "template_version": version,
    }
    if supported_formats is not None:
        payload["supported_formats"] = supported_formats
    return post_json(client, f"{API_PREFIX}/report-templates", payload)


def generate_report(
    client,
    context: dict[str, Any],
    *,
    template_id: int | str | None = None,
    report_type: str = "comprehensive",
    title: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "project_id": context["project_id"],
        "type": report_type,
        "title": title or f"round28-report-{context['marker']}",
        "scope": {
            "project_id": context["project_id"],
            "requirement_item_ids": [context["requirement_item_id"]],
        },
        "requirement_item_ids": [context["requirement_item_id"]],
    }
    if template_id is not None:
        payload["template_id"] = template_id
    result = post_json(client, f"{API_PREFIX}/reports/comprehensive", payload)
    assert_no_sensitive_markers(result)
    return created_report(result)


def download_report(client, report_id: int | str, fmt: str) -> dict[str, Any]:
    payload = data_of(client.get(f"{API_PREFIX}/reports/{report_id}/download", params={"format": fmt}))
    assert payload.get("format") == fmt, payload
    assert isinstance(payload.get("content"), str) and payload["content"].strip(), payload
    assert_no_sensitive_markers(payload)
    return payload


def report_records(client, project_id: int | str, params: dict[str, Any]) -> list[dict[str, Any]]:
    payload = data_of(client.get(f"{API_PREFIX}/projects/{project_id}/reports", params={"pageSize": 100, **params}))
    records = list_items(payload)
    assert_no_sensitive_markers(records)
    return records


def seed_filter_report(
    context: dict[str, Any],
    *,
    name: str,
    report_type: str,
    generated_at: datetime,
    requirement_item_ids: list[int] | None = None,
    source_document_ids: list[int] | None = None,
) -> int:
    with session_scope() as session:
        report = Report(
            project_id=context["project_id"],
            name=name,
            type=report_type,
            status="generated",
            related_module="project",
            related_scope_json={"project_id": context["project_id"], "marker": context["marker"]},
            requirement_item_ids_json=requirement_item_ids or [],
            source_document_ids_json=source_document_ids or [],
            scope_snapshot={
                "project_id": context["project_id"],
                "template": {"id": None, "version": "seed", "sections": ["overview"]},
                "generated_at": generated_at.isoformat(),
            },
            data_snapshot={"summary_metrics": {}, "risk_items": [], "marker": context["marker"]},
            source_refs_json={
                "project_id": context["project_id"],
                "requirement_item_ids": requirement_item_ids or [],
                "source_document_ids": source_document_ids or [],
            },
            content=f"# {name}\n\nfilter-marker={context['marker']}\n",
            template_version="seed",
            ai_summary_version="rules-v1",
            generated_at=generated_at,
        )
        session.add(report)
        session.flush()
        return report.id


def assert_report_template_snapshot(report: dict[str, Any], *, template_id: int | str, version: str, sections: list[str]) -> None:
    assert str(report.get("template_id")) == str(template_id), report
    assert report.get("template_version") == version, report
    template_snapshot = (report.get("scope_snapshot") or {}).get("template")
    assert isinstance(template_snapshot, dict), report
    assert str(template_snapshot.get("id")) == str(template_id), template_snapshot
    assert template_snapshot.get("version") == version, template_snapshot
    assert template_snapshot.get("sections") == sections, template_snapshot


def assert_markdown_sections(content: str, sections: list[str]) -> None:
    for section in sections:
        assert f"## {SECTION_TITLES[section]}" in content, content
    for section in set(ALL_TEMPLATE_SECTIONS) - set(sections):
        assert f"## {SECTION_TITLES[section]}" not in content, content


def assert_html_sections(content: str, sections: list[str]) -> None:
    for section in sections:
        assert SECTION_TITLES[section] in content, content
    for section in set(ALL_TEMPLATE_SECTIONS) - set(sections):
        assert SECTION_TITLES[section] not in content, content


def risk_items(payload: Any) -> list[dict[str, Any]]:
    return list_items(payload, keys=("risks", "risk_items", "items", "records", "data"))


def todo_items(payload: Any) -> list[dict[str, Any]]:
    return list_items(payload, keys=("todos", "items", "records", "data"))


def risk_key_of(risk: dict[str, Any]) -> str:
    risk_key = risk.get("risk_key") or risk.get("key") or risk.get("id")
    assert isinstance(risk_key, str) and risk_key, risk
    return risk_key


def create_first_risk_todo(client, report_id: int | str) -> dict[str, Any]:
    risks_payload = data_of(client.get(f"{API_PREFIX}/reports/{report_id}/risks"))
    risks = risk_items(risks_payload)
    assert risks, risks_payload
    risk_key = risk_key_of(risks[0])
    todo = post_json(
        client,
        f"{API_PREFIX}/reports/{report_id}/risks/{quote(risk_key, safe='')}/todos",
        {
            "title": "Round28 investigate report center risk",
            "owner": "round28_qa",
            "status": "open",
            "source_refs": {"risk_key": risk_key, "note": f"token={FAKE_SECRET}"},
        },
    )
    assert_no_sensitive_markers(todo)
    return todo


def mutate_seeded_sources(context: dict[str, Any]) -> None:
    marker = context["marker"]
    with session_scope() as session:
        session.get(RequirementItem, int(context["requirement_item_id"])).title = f"{marker}-mutated-requirement"
        session.get(Execution, int(context["execution_id"])).actual_result = f"{marker}-mutated-execution"
        session.get(Defect, int(context["defect_id"])).title = f"{marker}-mutated-defect"
        session.get(ApiEndpoint, int(context["api_endpoint_id"])).path = f"/{marker}/mutated-api"
        session.get(AutoExecution, int(context["auto_execution_id"])).summary = {"total": 99, "passed": 99, "failed": 0}
        session.get(PerfResult, int(context["perf_result_id"])).summary_data = {"total": 99, "p95_ms": 1, "error_rate": 0}


def test_report_template_crud_default_uniqueness_and_validation(client):
    marker = uuid4().hex[:8]
    report_type = f"round28_{marker}"
    first = create_template(
        client,
        marker=f"{marker}-first",
        report_type=report_type,
        sections=["overview", "risks"],
        supported_formats=["markdown", "html"],
        is_default=True,
        version="v28.1",
    )
    second = create_template(
        client,
        marker=f"{marker}-second",
        report_type=report_type,
        sections=["overview", "todos"],
        supported_formats=["markdown", "html", "json"],
        is_default=True,
        version="v28.2",
    )

    first_id = object_id(first, "id", "template_id")
    second_id = object_id(second, "id", "template_id")
    listed = data_of(client.get(f"{API_PREFIX}/report-templates", params={"report_type": report_type, "pageSize": 100}))
    same_type = [item for item in list_items(listed) if item.get("report_type") == report_type]
    defaults = [item for item in same_type if item.get("is_default") is True]
    assert [str(object_id(item, "id", "template_id")) for item in defaults] == [str(second_id)], same_type
    first_from_list = next(item for item in same_type if str(object_id(item, "id", "template_id")) == str(first_id))
    assert first_from_list.get("is_default") is False, same_type

    patched = data_of(
        client.patch(
            f"{API_PREFIX}/report-templates/{second_id}",
            json={"name": f"round28-template-{marker}-patched", "sections": ["overview", "requirements"], "supported_formats": ["markdown"]},
        )
    )
    assert patched["name"].endswith("-patched"), patched
    assert patched["sections"] == ["overview", "requirements"], patched
    assert patched["supported_formats"] == ["markdown"], patched
    assert_no_sensitive_markers(patched)

    deleted = data_of(client.delete(f"{API_PREFIX}/report-templates/{first_id}"))
    assert deleted.get("deleted") is True and str(deleted.get("id")) == str(first_id), deleted

    invalid_sections = client.post(
        f"{API_PREFIX}/report-templates",
        json={"name": f"round28-invalid-sections-{marker}", "report_type": report_type, "sections": ["overview", "unknown_section"]},
    )
    assert_structured_error(invalid_sections, field="sections")

    invalid_formats = client.post(
        f"{API_PREFIX}/report-templates",
        json={
            "name": f"round28-invalid-formats-{marker}",
            "report_type": report_type,
            "sections": ["overview"],
            "supported_formats": ["markdown", "exe"],
        },
    )
    assert_structured_error(invalid_formats, field="supported_formats")


def test_comprehensive_report_applies_template_and_exports_selected_sections(client):
    context = seed_round28_context()
    sections = ["overview", "requirements", "executions", "risks"]
    template = create_template(
        client,
        marker=context["marker"],
        report_type="comprehensive",
        sections=sections,
        supported_formats=["markdown", "html", "json"],
        version="v28-template-freeze",
    )
    template_id = object_id(template, "id", "template_id")

    report = generate_report(client, context, template_id=template_id)
    report_id = object_id(report, "id", "report_id")
    assert_report_template_snapshot(report, template_id=template_id, version="v28-template-freeze", sections=sections)

    data_of(
        client.patch(
            f"{API_PREFIX}/report-templates/{template_id}",
            json={"sections": ["overview"], "template_version": "v28-mutated"},
        )
    )
    fetched = data_of(client.get(f"{API_PREFIX}/reports/{report_id}"))
    assert_report_template_snapshot(fetched, template_id=template_id, version="v28-template-freeze", sections=sections)

    markdown = download_report(client, report_id, "markdown")
    html = download_report(client, report_id, "html")
    assert_markdown_sections(markdown["content"], sections)
    assert_html_sections(html["content"], sections)


def test_report_list_filters_type_query_requirement_document_date_and_sort(client):
    context = seed_round28_context()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    match_q = f"{context['marker']}-filter-target"
    old_id = seed_filter_report(
        context,
        name=f"{match_q}-old",
        report_type="daily_report",
        generated_at=now - timedelta(days=3),
        requirement_item_ids=[context["requirement_item_id"]],
        source_document_ids=[context["document_id"]],
    )
    new_id = seed_filter_report(
        context,
        name=f"{match_q}-new",
        report_type="comprehensive",
        generated_at=now - timedelta(days=1),
        requirement_item_ids=[context["requirement_item_id"]],
        source_document_ids=[context["document_id"]],
    )
    other_id = seed_filter_report(
        context,
        name=f"{context['marker']}-filter-other",
        report_type="performance",
        generated_at=now - timedelta(days=2),
        requirement_item_ids=[],
        source_document_ids=[],
    )

    by_type = report_records(client, context["project_id"], {"type": "comprehensive", "q": context["marker"]})
    by_type_ids = {str(object_id(item, "id", "report_id")) for item in by_type}
    assert str(new_id) in by_type_ids and str(old_id) not in by_type_ids and str(other_id) not in by_type_ids, by_type

    by_q = report_records(client, context["project_id"], {"q": match_q})
    by_q_ids = {str(object_id(item, "id", "report_id")) for item in by_q}
    assert {str(old_id), str(new_id)} <= by_q_ids and str(other_id) not in by_q_ids, by_q
    assert all(match_q in payload_text(item) for item in by_q), by_q

    by_item = report_records(client, context["project_id"], {"requirementItemId": context["requirement_item_id"], "q": context["marker"]})
    assert str(other_id) not in {str(object_id(item, "id", "report_id")) for item in by_item}, by_item
    assert all(context["requirement_item_id"] in (item.get("requirement_item_ids_json") or []) for item in by_item), by_item

    by_document = report_records(client, context["project_id"], {"sourceDocumentId": context["document_id"], "q": context["marker"]})
    assert str(other_id) not in {str(object_id(item, "id", "report_id")) for item in by_document}, by_document
    assert all(context["document_id"] in (item.get("source_document_ids_json") or []) for item in by_document), by_document

    in_range = report_records(
        client,
        context["project_id"],
        {
            "q": match_q,
            "dateFrom": (now - timedelta(days=2)).date().isoformat(),
            "dateTo": (now + timedelta(days=1)).date().isoformat(),
        },
    )
    in_range_ids = {str(object_id(item, "id", "report_id")) for item in in_range}
    assert str(new_id) in in_range_ids and str(old_id) not in in_range_ids, in_range

    sorted_records = report_records(client, context["project_id"], {"q": match_q, "sort": "generated_at:asc"})
    sorted_ids = [str(object_id(item, "id", "report_id")) for item in sorted_records]
    assert sorted_ids.index(str(old_id)) < sorted_ids.index(str(new_id)), sorted_records


def test_report_drilldown_uses_snapshot_and_is_immutable_after_source_changes(client):
    context = seed_round28_context()
    report = generate_report(client, context)
    report_id = object_id(report, "id", "report_id")

    drilldown = data_of(client.get(f"{API_PREFIX}/reports/{report_id}/drilldown"))
    for key in ("requirements", "executions", "defects", "api", "automation", "performance", "risks"):
        assert key in drilldown, drilldown
        assert drilldown[key], drilldown
    assert_no_sensitive_markers(drilldown)

    initial_text = payload_text(drilldown)
    assert context["original_requirement_title"] in initial_text, drilldown
    assert str(context["execution_id"]) in initial_text, drilldown
    assert str(context["defect_id"]) in initial_text, drilldown
    assert str(context["api_execution_id"]) in initial_text, drilldown
    assert str(context["auto_execution_id"]) in initial_text, drilldown
    assert str(context["perf_result_id"]) in initial_text, drilldown

    mutate_seeded_sources(context)
    drilldown_after_mutation = data_of(client.get(f"{API_PREFIX}/reports/{report_id}/drilldown"))
    mutated_text = payload_text(drilldown_after_mutation)
    assert context["original_requirement_title"] in mutated_text, drilldown_after_mutation
    assert f"{context['marker']}-mutated-" not in mutated_text, drilldown_after_mutation
    assert_no_sensitive_markers(drilldown_after_mutation)


def test_report_risks_create_idempotent_todos_and_patch_status(client):
    context = seed_round28_context()
    report = generate_report(client, context)
    report_id = object_id(report, "id", "report_id")

    risks_payload = data_of(client.get(f"{API_PREFIX}/reports/{report_id}/risks"))
    risks = risk_items(risks_payload)
    assert risks, risks_payload
    assert_no_sensitive_markers(risks_payload)
    risk_key = risk_key_of(risks[0])

    todo_payload = {
        "title": "Round28 mitigate report risk",
        "owner": "round28_qa",
        "status": "open",
        "source_refs": {
            "report_id": report_id,
            "risk_key": risk_key,
            "defect_ids": [context["defect_id"]],
            "note": f"Authorization: {AUTH_SECRET}",
        },
    }
    first = post_json(client, f"{API_PREFIX}/reports/{report_id}/risks/{quote(risk_key, safe='')}/todos", todo_payload)
    second = post_json(client, f"{API_PREFIX}/reports/{report_id}/risks/{quote(risk_key, safe='')}/todos", todo_payload)
    first_id = object_id(first, "id", "todo_id")
    second_id = object_id(second, "id", "todo_id")
    assert str(first_id) == str(second_id), {"first": first, "second": second}
    assert_no_sensitive_markers(first)
    assert_no_sensitive_markers(second)

    listed = data_of(client.get(f"{API_PREFIX}/report-todos", params={"reportId": report_id, "riskKey": risk_key, "pageSize": 100}))
    todos = [item for item in todo_items(listed) if str(item.get("report_id")) == str(report_id) and item.get("risk_key") == risk_key]
    assert len(todos) == 1, listed
    todo = todos[0]
    assert str(todo.get("report_id")) == str(report_id), todo
    assert todo.get("risk_key") == risk_key, todo
    assert isinstance(todo.get("source_refs"), dict) and todo["source_refs"], todo
    assert todo.get("status") in {"open", "todo", "pending"}, todo
    assert_no_sensitive_markers(listed)

    patched = data_of(client.patch(f"{API_PREFIX}/report-todos/{first_id}", json={"status": "done", "note": f"cookie={COOKIE_SECRET}"}))
    assert str(patched.get("report_id")) == str(report_id), patched
    assert patched.get("risk_key") == risk_key, patched
    assert patched.get("status") == "done", patched
    assert isinstance(patched.get("source_refs"), dict) and patched["source_refs"], patched
    assert_no_sensitive_markers(patched)


def test_markdown_html_outputs_include_sections_tables_risks_todos_escape_and_recursive_redaction(client):
    context = seed_round28_context()
    template = create_template(
        client,
        marker=f"{context['marker']}-full-output",
        sections=list(ALL_TEMPLATE_SECTIONS),
        supported_formats=["markdown", "html", "json"],
        version="v28-output",
    )
    title = f"Round28 output <script>alert('{context['marker']}')</script>"
    report = generate_report(client, context, template_id=object_id(template, "id", "template_id"), title=title)
    report_id = object_id(report, "id", "report_id")
    todo = create_first_risk_todo(client, report_id)
    todo_id = object_id(todo, "id", "todo_id")

    markdown = download_report(client, report_id, "markdown")
    html = download_report(client, report_id, "html")

    assert_markdown_sections(markdown["content"], list(ALL_TEMPLATE_SECTIONS))
    assert_html_sections(html["content"], list(ALL_TEMPLATE_SECTIONS))
    assert "| " in markdown["content"] and "\n| ---" in markdown["content"], markdown["content"]
    assert "<table" in html["content"].lower() and "</table>" in html["content"].lower(), html["content"]
    for expected in ("Risks", "Todos", str(todo_id)):
        assert expected in markdown["content"], markdown["content"]
        assert expected in html["content"], html["content"]
    assert f"<script>alert('{context['marker']}')</script>" not in html["content"], html["content"]
    assert "&lt;script&gt;" in html["content"] or "&lt;script" in html["content"], html["content"]
    assert_no_sensitive_markers(markdown)
    assert_no_sensitive_markers(html)


@pytest.mark.parametrize("fmt", ["pdf", "word", "docx"])
def test_pdf_and_word_download_requests_return_structured_unsupported_errors_without_fake_files(client, fmt: str):
    context = seed_round28_context()
    report = generate_report(client, context)
    report_id = object_id(report, "id", "report_id")

    response = client.get(f"{API_PREFIX}/reports/{report_id}/download", params={"format": fmt})
    payload = assert_structured_error(response, expected_statuses={400, 415})
    dumped = payload_text(payload).lower()
    assert "unsupported" in dumped, payload
    assert "placeholder" not in dumped, payload
    assert "content_base64" not in dumped and "application/pdf" not in dumped and "officedocument" not in dumped, payload


@pytest.mark.parametrize(
    "conclusion_type",
    ["daily_report", "test_submission_feedback", "release_advice", "risk_list"],
)
def test_lightweight_conclusions_support_report_center_types_from_real_aggregation_context(client, conclusion_type: str):
    context = seed_round28_context()

    conclusion = post_json(
        client,
        f"{API_PREFIX}/reports/lightweight-conclusions",
        {
            "project_id": context["project_id"],
            "type": conclusion_type,
            "save": True,
            "title": f"round28-{conclusion_type}-{context['marker']}",
            "notes": {"token": FAKE_SECRET},
        },
    )
    assert (conclusion.get("type") or conclusion.get("conclusion_type")) == conclusion_type, conclusion
    assert isinstance(conclusion.get("conclusion"), str) and conclusion["conclusion"].strip(), conclusion
    metrics = conclusion.get("metrics")
    assert isinstance(metrics, dict), conclusion
    for key in ("requirements", "executions", "defects", "api", "perf"):
        assert_count(get_summary(metrics, key))
    automation = metrics.get("automation") or metrics.get("auto")
    assert isinstance(automation, dict), metrics
    assert_count(automation.get("summary") if isinstance(automation.get("summary"), dict) else automation)
    refs = conclusion.get("source_refs")
    assert isinstance(refs, dict), conclusion
    for expected_id in (
        context["requirement_item_id"],
        context["execution_id"],
        context["defect_id"],
        context["api_execution_id"],
        context["auto_execution_id"],
        context["perf_result_id"],
    ):
        assert str(expected_id) in payload_text(refs), refs
    report = conclusion.get("report")
    assert isinstance(report, dict) and object_id(report, "id", "report_id"), conclusion
    assert conclusion_type in payload_text(report.get("data_snapshot") or report.get("related_scope_json") or conclusion), conclusion
    assert_no_sensitive_markers(conclusion)

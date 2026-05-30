from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from aitest_platform.db.session import session_scope
from aitest_platform.models import (
    ApiEndpoint,
    ApiExecution,
    ApiTestCase,
    ApiTestLib,
    BackupSnapshot,
    Execution,
    Project,
    RequirementDocument,
    RequirementItem,
    RequirementLib,
    TestCase as CaseModel,
)
from conftest import API_PREFIX, data_of, object_id


pytestmark = pytest.mark.contract

FAKE_SECRET = "round29-fake-secret-value"
AUTH_SECRET = f"Bearer {FAKE_SECRET}"
API_KEY_SECRET = f"round29-api-key-{FAKE_SECRET}"
COOKIE_SECRET = f"round29-cookie-{FAKE_SECRET}"
SECRET_MARKERS = (FAKE_SECRET, AUTH_SECRET, API_KEY_SECRET, COOKIE_SECRET)
PII_MARKERS = (
    "Ada Sensitive",
    "ada.sensitive@real-person.invalid",
    "alice.real@example.co",
    "13800138000",
    "4111111111111111",
)
OLD_HISTORY_DAYS = 3650


def payload_text(payload: Any) -> str:
    return payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def response_payload(response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        pytest.fail(f"Expected JSON response, got: {response.text!r}", pytrace=False)
    assert isinstance(payload, dict), payload
    return payload


def assert_no_sensitive_markers(payload: Any) -> None:
    dumped = payload_text(payload)
    for marker in (*SECRET_MARKERS, *PII_MARKERS):
        assert marker not in dumped, dumped


def assert_structured_error(response, *, expected_statuses: set[int] | None = None, field: str | None = None) -> dict[str, Any]:
    statuses = expected_statuses or {400, 403, 404, 409, 422}
    assert response.status_code in statuses, response.text
    payload = response_payload(response)
    assert {"code", "message", "data"} <= payload.keys(), payload
    assert payload["code"] not in {0, 200, 201}, payload
    assert isinstance(payload["message"], str) and payload["message"], payload
    if field is not None:
        assert field.lower() in payload_text(payload).lower(), payload
    assert_no_sensitive_markers(payload)
    return payload


def assert_reserved_email_values(payload: Any) -> None:
    dumped = payload_text(payload)
    emails = set(re.findall(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", dumped))
    reserved_domains = ("example.com", "example.org", "example.net", "example.test", "invalid.test")
    unexpected = [email for email in emails if not email.lower().endswith(reserved_domains)]
    assert not unexpected, {"unexpected_email_values": unexpected, "payload": payload}


def list_items(value: Any, *, keys: tuple[str, ...] = ("items", "samples", "records", "results", "list", "data", "suggestions")) -> list[dict[str, Any]]:
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


def generated_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        for key in ("items", "samples", "records", "results", "test_data", "cases", "parameters", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                assert all(isinstance(item, dict) for item in value), value
                return value
        mode_items: list[dict[str, Any]] = []
        for mode in ("normal", "boundary", "invalid", "empty", "special"):
            value = payload.get(mode)
            if isinstance(value, list):
                assert all(isinstance(item, dict) for item in value), value
                mode_items.extend({**item, "mode": item.get("mode") or mode} for item in value)
        if mode_items:
            return mode_items
    return list_items(payload)


def sample_mode(item: dict[str, Any]) -> str:
    for key in ("mode", "case_type", "scenario", "category", "type"):
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def recursive_has_key(value: Any, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(recursive_has_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(recursive_has_key(item, key) for item in value)
    return False


def target_payload(sample: dict[str, Any], target: str) -> Any:
    direct_keys = (target, f"request_{target}", f"{target}_data", f"{target}_params")
    for key in direct_keys:
        value = sample.get(key)
        if isinstance(value, dict):
            return value
    for container_key in ("request", "request_payload", "payload", "mapping", "mappings", "mapped"):
        container = sample.get(container_key)
        if isinstance(container, dict):
            for key in direct_keys:
                value = container.get(key)
                if isinstance(value, dict):
                    return value
    pytest.fail(f"Generated sample does not expose {target!r} mapping: {sample!r}", pytrace=False)


def numeric_values_for_key(payload: Any, key_fragments: tuple[str, ...]) -> list[int]:
    values: list[int] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            lowered = str(key).lower()
            if any(fragment in lowered for fragment in key_fragments) and isinstance(value, int | float) and not isinstance(value, bool):
                values.append(int(value))
            values.extend(numeric_values_for_key(value, key_fragments))
    elif isinstance(payload, list):
        for item in payload:
            values.extend(numeric_values_for_key(item, key_fragments))
    return values


def max_numeric_for_key(payload: Any, key_fragments: tuple[str, ...]) -> int:
    values = numeric_values_for_key(payload, key_fragments)
    assert values, {"missing_numeric_keys": key_fragments, "payload": payload}
    return max(values)


def first_present(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def seed_project_only(marker: str | None = None) -> int:
    marker = marker or uuid4().hex[:10]
    with session_scope() as session:
        project = Project(
            code=f"r29-{marker}",
            name=f"Round29 Project {marker}",
            description=f"Round29 seed project token={FAKE_SECRET}",
            owner_name="round29_qa",
        )
        session.add(project)
        session.flush()
        return project.id


def seed_backup_snapshot(project_id: int, *, name: str, created_at: datetime) -> int:
    with session_scope() as session:
        snapshot = BackupSnapshot(
            project_id=project_id,
            name=name,
            scope_json={"project_id": project_id, "source": "round29"},
            data_json={"projects": [{"id": project_id, "name": name}], "token": FAKE_SECRET},
            created_at=created_at,
        )
        session.add(snapshot)
        session.flush()
        return snapshot.id


def seed_round29_context(marker: str | None = None, *, history_days_old: int = OLD_HISTORY_DAYS + 30) -> dict[str, Any]:
    marker = marker or uuid4().hex[:10]
    now = datetime.now(timezone.utc)
    executed_at = now - timedelta(days=history_days_old)
    with session_scope() as session:
        project = Project(
            code=f"r29-{marker}",
            name=f"Round29 Data Factory {marker}",
            description=f"Round29 project Authorization: {AUTH_SECRET}",
            owner_name="round29_qa",
        )
        session.add(project)
        session.flush()

        lib = RequirementLib(
            project_id=project.id,
            name=f"Round29 Requirement Library {marker}",
            description=f"Library cookie={COOKIE_SECRET}",
        )
        session.add(lib)
        session.flush()

        document = RequirementDocument(
            project_id=project.id,
            lib_id=lib.id,
            document_number=f"REQ-R29-{marker}",
            name=f"Round29 Source Document {marker}",
            source_type="markdown",
            source_file_name=f"round29-{marker}.md",
            raw_content=f"# Round29\nDo not leak api_key={API_KEY_SECRET}.",
            parser_status="completed",
            parser_metadata={"source": "round29", "token": FAKE_SECRET},
        )
        session.add(document)
        session.flush()

        item = RequirementItem(
            project_id=project.id,
            lib_id=lib.id,
            document_id=document.id,
            item_number=f"R29-{marker}-001",
            title=f"Round29 checkout data factory {marker}",
            summary="Generate request data for warehouse_zone and loyalty_tier checkout paths.",
            module="data-factory",
            actor="qa",
            goal="Create safe synthetic request data.",
            preconditions_json=[{"name": "warehouse_zone", "value": "north"}],
            business_rules_json=[{"field": "loyalty_tier", "values": ["gold", "silver"]}],
            priority="P0",
            status="confirmed",
            confidence=0.98,
            case_status="generated",
        )
        session.add(item)
        session.flush()

        case = CaseModel(
            project_id=project.id,
            lib_id=lib.id,
            document_id=document.id,
            requirement_item_id=item.id,
            case_number=f"TC-R29-{marker}-001",
            title=f"Round29 generated data suggestions {marker}",
            case_type="functional",
            precondition=(
                "User has warehouse_zone=north and loyalty_tier=gold. "
                f"Do not expose password={FAKE_SECRET} cookie={COOKIE_SECRET}."
            ),
            steps=[
                {"step": 1, "action": "Submit cart_id and retry_count with a special coupon_code."},
                {"step": 2, "action": f"Call checkout API with Authorization {AUTH_SECRET}."},
            ],
            expected_result=f"Order is accepted and response never echoes token={API_KEY_SECRET}.",
            priority="P0",
            tags=["round29", "data-factory"],
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
            actual_result=f"Old execution contains token={FAKE_SECRET}",
            request_snapshot={"headers": {"Authorization": AUTH_SECRET}},
            response_snapshot={"headers": {"Set-Cookie": COOKIE_SECRET}},
            artifact_summary_json={"path": f"round29/{marker}/old.log"},
            executed_at=executed_at,
        )
        session.add(execution)
        session.flush()

        api_lib = ApiTestLib(
            project_id=project.id,
            source_document_id=document.id,
            name=f"Round29 API Lib {marker}",
            description=f"API library secret={FAKE_SECRET}",
            import_source="round29-contract",
        )
        session.add(api_lib)
        session.flush()

        endpoint = ApiEndpoint(
            lib_id=api_lib.id,
            requirement_item_id=item.id,
            name=f"Round29 checkout endpoint {marker}",
            method="POST",
            path=f"/round29/{marker}/checkout",
            headers_schema={"Authorization": AUTH_SECRET, "X-Api-Key": API_KEY_SECRET},
            query_schema={"page": {"type": "integer", "minimum": 1}, "trace_id": {"type": "string"}},
            body_schema={
                "type": "object",
                "properties": {
                    "customer": {
                        "type": "object",
                        "properties": {
                            "email": {"type": "string", "format": "email", "example": "alice.real@example.co"},
                            "phone": {"type": "string", "example": "13800138000"},
                            "name": {"type": "string", "example": "Ada Sensitive"},
                        },
                    },
                    "payment": {
                        "type": "object",
                        "properties": {
                            "card_number": {"type": "string", "example": "4111111111111111"},
                            "amount": {"type": "number", "minimum": 0, "maximum": 9999},
                        },
                    },
                },
            },
            response_schema={"status": "ok", "order_id": "string"},
            description=f"Checkout API Cookie={COOKIE_SECRET}",
        )
        session.add(endpoint)
        session.flush()

        api_case = ApiTestCase(
            endpoint_id=endpoint.id,
            lib_id=api_lib.id,
            requirement_item_id=item.id,
            name=f"Round29 checkout contract {marker}",
            category="contract",
            request_headers={"Authorization": AUTH_SECRET, "Cookie": COOKIE_SECRET},
            request_query={"page": 1, "trace_id": "{{trace_id}}", "api_key": API_KEY_SECRET},
            request_body={"customer": {"email": "alice.real@example.co"}, "payment": {"card_number": "4111111111111111"}},
            content_type="application/json",
            expected_status=200,
            assertions=[{"jsonpath": "$.order_id", "operator": "exists"}],
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
            request_snapshot={"headers": {"Authorization": AUTH_SECRET, "Cookie": COOKIE_SECRET}},
            response_snapshot={"status_code": 500, "body": f"token={FAKE_SECRET}"},
            assertion_results=[{"passed": False, "message": f"api_key={API_KEY_SECRET}"}],
            duration_ms=1200,
            error_message=f"Round29 old API execution token={FAKE_SECRET}",
            executed_at=executed_at,
        )
        session.add(api_execution)
        session.flush()

        return {
            "marker": marker,
            "project_id": project.id,
            "lib_id": lib.id,
            "document_id": document.id,
            "requirement_item_id": item.id,
            "case_id": case.id,
            "execution_id": execution.id,
            "api_lib_id": api_lib.id,
            "api_endpoint_id": endpoint.id,
            "api_case_id": api_case.id,
            "api_execution_id": api_execution.id,
        }


def rows_exist(context: dict[str, Any]) -> dict[str, bool]:
    with session_scope() as session:
        case = session.get(CaseModel, context["case_id"])
        api_case = session.get(ApiTestCase, context["api_case_id"])
        return {
            "test_case": case is not None and case.is_deleted is False,
            "api_test_case": api_case is not None and api_case.is_deleted is False,
            "execution": session.get(Execution, context["execution_id"]) is not None,
            "api_execution": session.get(ApiExecution, context["api_execution_id"]) is not None,
        }


def generate_payload(context: dict[str, Any], *, count: int = 99, max_count: int = 12) -> dict[str, Any]:
    return {
        "api_case_id": context["api_case_id"],
        "count": count,
        "max_count": max_count,
        "modes": ["normal", "boundary", "invalid", "empty", "special"],
        "targets": ["body", "query", "variables"],
        "fields": [
            {
                "name": "customer.email",
                "location": "body",
                "type": "string",
                "format": "email",
                "required": True,
                "example": "alice.real@example.co",
                "pii": True,
            },
            {
                "name": "customer.phone",
                "location": "body",
                "type": "string",
                "format": "phone",
                "example": "13800138000",
                "pii": True,
            },
            {"name": "payment.amount", "location": "body", "type": "number", "minimum": 0, "maximum": 9999},
            {"name": "page", "location": "query", "type": "integer", "minimum": 1, "maximum": 10},
            {"name": "trace_id", "location": "variables", "type": "string", "example": API_KEY_SECRET},
        ],
        "schema": {
            "body": {
                "type": "object",
                "properties": {
                    "customer": {
                        "type": "object",
                        "properties": {
                            "email": {"type": "string", "format": "email"},
                            "phone": {"type": "string"},
                        },
                        "required": ["email"],
                    },
                    "payment": {
                        "type": "object",
                        "properties": {"amount": {"type": "number", "minimum": 0, "maximum": 9999}},
                    },
                },
            },
            "query": {"page": {"type": "integer", "minimum": 1, "maximum": 10}},
            "variables": {"trace_id": {"type": "string"}},
        },
        "examples": {
            "Authorization": AUTH_SECRET,
            "Cookie": COOKIE_SECRET,
            "card_number": "4111111111111111",
            "full_name": "Ada Sensitive",
        },
    }


def test_api_parameter_generate_supports_sources_modes_limit_synthetic_pii_and_redaction(client):
    context = seed_round29_context()

    generated = data_of(client.post(f"{API_PREFIX}/data-factory/api-parameters/generate", json=generate_payload(context)))
    items = generated_items(generated)

    assert 1 <= len(items) <= 12, generated
    modes = {sample_mode(item) for item in items}
    assert {"normal", "boundary", "invalid", "empty", "special"} <= modes, {"modes": modes, "payload": generated}
    dumped = payload_text(generated)
    for expected_field in ("customer", "email", "phone", "payment", "amount", "page", "trace_id"):
        assert expected_field in dumped, generated
    assert_no_sensitive_markers(generated)
    assert_reserved_email_values(generated)


def test_generated_data_maps_to_request_body_query_and_variables(client):
    context = seed_round29_context()

    generated = data_of(
        client.post(
            f"{API_PREFIX}/data-factory/api-parameters/generate",
            json=generate_payload(context, count=5, max_count=5),
        )
    )
    items = generated_items(generated)
    normal = next((item for item in items if sample_mode(item) == "normal"), items[0])

    body = target_payload(normal, "body")
    query = target_payload(normal, "query")
    variables = target_payload(normal, "variables")

    assert recursive_has_key(body, "customer") and recursive_has_key(body, "email"), normal
    assert recursive_has_key(body, "payment") and recursive_has_key(body, "amount"), normal
    assert recursive_has_key(query, "page"), normal
    assert recursive_has_key(variables, "trace_id"), normal
    assert_no_sensitive_markers(generated)


def test_case_data_suggestions_use_case_text_redact_secrets_and_unknown_case_404(client):
    context = seed_round29_context()

    suggestions = data_of(client.get(f"{API_PREFIX}/test-cases/{context['case_id']}/test-data-suggestions"))
    items = list_items(suggestions)
    dumped = payload_text(suggestions).lower()

    assert items, suggestions
    for expected in ("warehouse_zone", "loyalty_tier", "cart_id", "retry_count", "coupon_code"):
        assert expected in dumped, suggestions
    assert_no_sensitive_markers(suggestions)

    response = client.get(f"{API_PREFIX}/test-cases/987654321/test-data-suggestions")
    assert_structured_error(response, expected_statuses={404}, field="case")


def test_backup_status_handles_empty_existing_stale_and_backup_refresh(client):
    empty_project_id = seed_project_only()
    empty_status = data_of(client.get(f"{API_PREFIX}/system/backup-status", params={"projectId": empty_project_id}))
    assert empty_status.get("needs_backup") is True, empty_status
    assert empty_status.get("latest") in (None, {}, []) or empty_status.get("latest_backup") in (None, {}, []), empty_status

    fresh_project_id = seed_project_only()
    fresh_id = seed_backup_snapshot(
        fresh_project_id,
        name=f"round29-fresh-{fresh_project_id}",
        created_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    fresh_status = data_of(client.get(f"{API_PREFIX}/system/backup-status", params={"projectId": fresh_project_id}))
    latest_fresh = fresh_status.get("latest") or fresh_status.get("latest_backup")
    assert fresh_status.get("needs_backup") is False, fresh_status
    assert isinstance(latest_fresh, dict) and str(latest_fresh.get("id") or latest_fresh.get("backup_id")) == str(fresh_id), fresh_status

    stale_project_id = seed_project_only()
    stale_id = seed_backup_snapshot(
        stale_project_id,
        name=f"round29-stale-{stale_project_id}",
        created_at=datetime.now(timezone.utc) - timedelta(days=8, minutes=5),
    )
    stale_status = data_of(client.get(f"{API_PREFIX}/system/backup-status", params={"projectId": stale_project_id}))
    latest_stale = stale_status.get("latest") or stale_status.get("latest_backup")
    assert stale_status.get("needs_backup") is True, stale_status
    assert isinstance(latest_stale, dict) and str(latest_stale.get("id") or latest_stale.get("backup_id")) == str(stale_id), stale_status

    created = data_of(
        client.post(
            f"{API_PREFIX}/system/backup",
            json={"project_id": stale_project_id, "name": f"round29-refresh-{stale_project_id}"},
        )
    )
    refreshed = data_of(client.get(f"{API_PREFIX}/system/backup-status", params={"projectId": stale_project_id}))
    latest_refreshed = refreshed.get("latest") or refreshed.get("latest_backup")
    assert refreshed.get("needs_backup") is False, refreshed
    assert isinstance(latest_refreshed, dict), refreshed
    assert str(latest_refreshed.get("id") or latest_refreshed.get("backup_id")) == str(object_id(created, "id", "backup_id")), refreshed
    assert_no_sensitive_markers({"empty": empty_status, "fresh": fresh_status, "stale": stale_status, "created": created, "refreshed": refreshed})


def test_storage_summary_reports_sized_sections_without_absolute_paths(client):
    summary = data_of(client.get(f"{API_PREFIX}/system/storage-summary"))
    sections = summary.get("sections") or summary.get("modules") or summary

    for section_name in ("db", "artifacts", "backups", "modules"):
        section = sections.get(section_name) if isinstance(sections, dict) else None
        assert isinstance(section, dict), {"section": section_name, "summary": summary}
        bytes_value = first_present(section, "bytes", "size_bytes", "total_bytes")
        count_value = first_present(section, "count", "file_count", "records", "record_count")
        human = first_present(section, "human_readable", "human", "size_human", "display_size")
        assert isinstance(bytes_value, int) and bytes_value >= 0, section
        assert isinstance(count_value, int) and count_value >= 0, section
        assert isinstance(human, str) and human.strip(), section

    dumped = payload_text(summary)
    assert re.search(r"\b[A-Za-z]:\\\\", dumped) is None, dumped
    assert str(Path.cwd()) not in dumped, dumped
    assert_no_sensitive_markers(summary)


def test_cleanup_dry_run_reports_impacts_without_db_or_file_mutation(client, tmp_path):
    context = seed_round29_context()
    artifact_root = tmp_path / "round29-artifacts"
    artifact_root.mkdir()
    old_file = artifact_root / "round29-old.log"
    old_file.write_text(f"runner output token={FAKE_SECRET}\n", encoding="utf-8")
    before = rows_exist(context)
    assert before == {"test_case": True, "api_test_case": True, "execution": True, "api_execution": True}

    result = data_of(
        client.post(
            f"{API_PREFIX}/system/cleanup",
            json={
                "dry_run": True,
                "project_id": context["project_id"],
                "modules": ["execution_history", "api_execution_history", "artifacts"],
                "older_than_days": OLD_HISTORY_DAYS,
                "artifact_root": str(artifact_root),
            },
        )
    )

    assert result.get("dry_run") is True or result.get("mode") == "dry_run", result
    assert max_numeric_for_key(result, ("record", "row")) >= 2, result
    assert max_numeric_for_key(result, ("file",)) >= 1, result
    assert max_numeric_for_key(result, ("byte", "size")) >= old_file.stat().st_size, result
    assert rows_exist(context) == before
    assert old_file.exists()
    assert_no_sensitive_markers(result)


def test_cleanup_rejects_missing_confirm_unknown_modules_and_unsafe_paths(client, tmp_path):
    context = seed_round29_context()
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    outside_file = tmp_path / "outside.log"
    outside_file.write_text("outside", encoding="utf-8")

    invalid_requests = [
        (
            {"dry_run": False, "project_id": context["project_id"], "modules": ["execution_history"], "older_than_days": OLD_HISTORY_DAYS},
            "confirm",
        ),
        (
            {"dry_run": True, "project_id": context["project_id"], "modules": ["projects"], "older_than_days": OLD_HISTORY_DAYS},
            "module",
        ),
        (
            {
                "dry_run": False,
                "confirm_text": "CLEANUP",
                "project_id": context["project_id"],
                "modules": ["artifacts"],
                "artifact_root": str(allowed_root),
                "paths": ["../outside.log"],
            },
            "path",
        ),
        (
            {
                "dry_run": False,
                "confirm_text": "CLEANUP",
                "project_id": context["project_id"],
                "modules": ["artifacts"],
                "artifact_root": str(allowed_root),
                "paths": [str(outside_file)],
            },
            "path",
        ),
    ]

    for payload, field in invalid_requests:
        response = client.post(f"{API_PREFIX}/system/cleanup", json=payload)
        assert_structured_error(response, expected_statuses={400, 403, 409, 422}, field=field)

    assert outside_file.exists()
    assert rows_exist(context)["execution"] is True
    assert rows_exist(context)["api_execution"] is True


def test_cleanup_history_modules_remove_only_execution_records_not_case_definitions(client):
    context = seed_round29_context()

    result = data_of(
        client.post(
            f"{API_PREFIX}/system/cleanup",
            json={
                "dry_run": False,
                "confirm_text": "CLEANUP",
                "project_id": context["project_id"],
                "modules": ["execution_history", "api_execution_history"],
                "older_than_days": OLD_HISTORY_DAYS,
            },
        )
    )

    assert max_numeric_for_key(result, ("record", "row")) >= 2, result
    after = rows_exist(context)
    assert after["execution"] is False, after
    assert after["api_execution"] is False, after
    assert after["test_case"] is True, after
    assert after["api_test_case"] is True, after
    assert_no_sensitive_markers(result)

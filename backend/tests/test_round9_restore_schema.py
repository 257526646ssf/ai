from __future__ import annotations

import json
import re
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from aitest_platform.db.session import session_scope
from aitest_platform.models import ApiEndpoint, ApiEnvironment, ApiTestCase, ApiTestLib, Project
from conftest import API_PREFIX, assert_response_envelope, data_of


pytestmark = pytest.mark.contract

ROUND9_FAKE_SECRETS = (
    "round9-fake-api-key-123",
    "round9-fake-token-456",
    "round9_session=round9-fake-cookie-789",
    "round9-fake-secret-abc",
    "round9-fake-password-def",
)

LOCAL_PATH_PATTERNS = (
    re.compile(r"[A-Za-z]:\\[^\\\s]+\\"),
    re.compile(r"/(?:Users|home|var|tmp|private|opt)/[^\s]+"),
)


def payload_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def assert_no_round9_secret(payload: Any) -> None:
    dumped = payload_text(payload)
    for secret in ROUND9_FAKE_SECRETS:
        assert secret not in dumped, dumped


def assert_no_local_path(payload: Any) -> None:
    dumped = payload_text(payload)
    for pattern in LOCAL_PATH_PATTERNS:
        assert pattern.search(dumped) is None, dumped


def assert_list_like(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        for key in ("list", "items", "records", "results", "data", "apis", "test_cases"):
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


def find_by_field(items: list[dict[str, Any]], field: str, expected: str) -> dict[str, Any]:
    for item in items:
        if item.get(field) == expected:
            return item
    pytest.fail(f"Could not find {field}={expected!r} in {items!r}", pytrace=False)


def find_project_by_code(client, code: str) -> dict[str, Any]:
    page_size = 2000
    page = 1
    while True:
        payload = data_of(client.get(f"{API_PREFIX}/projects", params={"page": page, "pageSize": page_size}))
        projects = assert_list_like(payload)
        for project in projects:
            if project.get("code") == code:
                return project

        total = payload.get("total") if isinstance(payload, dict) else None
        if not projects or (isinstance(total, int) and page * page_size >= total):
            pytest.fail(f"Could not find code={code!r} across project pages; last_page={page}, total={total}", pytrace=False)
        page += 1


def marker_counts(marker: str) -> dict[str, int]:
    with session_scope() as session:
        return {
            "projects": session.scalar(select(func.count()).select_from(Project).where(Project.code == marker)) or 0,
            "api_test_libs": session.scalar(select(func.count()).select_from(ApiTestLib).where(ApiTestLib.name == f"{marker}-lib")) or 0,
            "api_endpoints": session.scalar(select(func.count()).select_from(ApiEndpoint).where(ApiEndpoint.path == f"/round9/{marker}/endpoint")) or 0,
            "api_test_cases": session.scalar(select(func.count()).select_from(ApiTestCase).where(ApiTestCase.name == f"{marker}-case")) or 0,
            "api_environments": session.scalar(select(func.count()).select_from(ApiEnvironment).where(ApiEnvironment.name == f"{marker}-env")) or 0,
        }


def backup_like_data(marker: str, *, include_fake_secrets: bool = False) -> dict[str, Any]:
    suffix = int(marker.rsplit("-", 1)[-1], 16)
    project_id = 10_000_000_000_000 + suffix * 10
    lib_id = project_id + 1
    endpoint_id = project_id + 2
    case_id = project_id + 3
    environment_id = project_id + 4

    headers = {"X-Round": "9"}
    variables = {"tenant": marker}
    body = {"name": marker}
    if include_fake_secrets:
        headers.update(
            {
                "X-API-Key": ROUND9_FAKE_SECRETS[0],
                "Authorization": f"Bearer {ROUND9_FAKE_SECRETS[1]}",
                "Cookie": ROUND9_FAKE_SECRETS[2],
            }
        )
        variables.update({"secret": ROUND9_FAKE_SECRETS[3], "password": ROUND9_FAKE_SECRETS[4]})
        body.update({"token": ROUND9_FAKE_SECRETS[1], "password": ROUND9_FAKE_SECRETS[4]})

    return {
        "schema_version": "round9-contract-v1",
        "projects": [
            {
                "id": project_id,
                "code": marker,
                "name": f"{marker}-project",
                "description": "Round 9 restore contract project.",
                "owner_name": "qa_restore_engineer_round9",
            }
        ],
        "api_test_libs": [
            {
                "id": lib_id,
                "project_id": project_id,
                "name": f"{marker}-lib",
                "description": "Round 9 restore contract API lib.",
                "import_source": "round9-restore-contract",
            }
        ],
        "api_endpoints": [
            {
                "id": endpoint_id,
                "lib_id": lib_id,
                "name": f"{marker}-endpoint",
                "method": "POST",
                "path": f"/round9/{marker}/endpoint",
                "headers_schema": headers,
                "query_schema": {"q": "round9"},
                "body_schema": {"type": "object", "example": body},
                "response_schema": {"status": 200},
                "description": "Round 9 restored endpoint.",
            }
        ],
        "api_test_cases": [
            {
                "id": case_id,
                "endpoint_id": endpoint_id,
                "lib_id": lib_id,
                "name": f"{marker}-case",
                "category": "contract",
                "request_headers": headers,
                "request_query": {"q": "round9"},
                "request_body": body,
                "content_type": "application/json",
                "expected_status": 200,
                "assertions": [{"type": "status_code", "expected": 200}],
                "status": "ready",
                "sort_order": 1,
            }
        ],
        "api_environments": [
            {
                "id": environment_id,
                "lib_id": lib_id,
                "name": f"{marker}-env",
                "base_url": "https://round9.example.invalid",
                "headers": headers,
                "variables": variables,
                "is_active": True,
                "sort_order": 1,
            }
        ],
    }


def restore_payload(marker: str, **overrides: Any) -> dict[str, Any]:
    payload = {"mode": "merge", "dry_run": False, "data": backup_like_data(marker)}
    payload.update(overrides)
    return payload


def test_schema_status_contract_is_structured_and_sanitized(client):
    payload = assert_response_envelope(client.get(f"{API_PREFIX}/system/schema-status"), allow_created=False)
    data = payload["data"]

    assert isinstance(data, dict), data
    assert data.get("status") in {"ok", "warning", "error"}, data
    for key in ("tables_total", "tables_present", "missing_tables", "missing_columns", "schema_version"):
        assert key in data, data
    assert isinstance(data["tables_total"], int) and data["tables_total"] >= 0, data
    assert isinstance(data["tables_present"], int) and data["tables_present"] >= 0, data
    assert isinstance(data["missing_tables"], list), data
    assert isinstance(data["missing_columns"], (dict, list)), data
    assert data["schema_version"] is not None, data
    assert_no_local_path(payload)
    assert_no_round9_secret(payload)


def test_restore_dry_run_reports_summary_without_writing_database(client):
    marker = f"round9-dry-{uuid4().hex[:10]}"
    before = marker_counts(marker)

    response = client.post(f"{API_PREFIX}/system/restore", json=restore_payload(marker, dry_run=True))
    payload = assert_response_envelope(response, allow_created=False)
    data = payload["data"]

    assert isinstance(data, dict), data
    assert data.get("dry_run") is True or data.get("preview") is True, data
    assert data.get("restored") is False, data
    summary = data.get("summary")
    assert isinstance(summary, dict), data
    for table in ("projects", "api_test_libs", "api_endpoints"):
        table_summary = summary.get(table)
        assert isinstance(table_summary, dict), summary
        assert table_summary.get("records") == 1 or table_summary.get("count") == 1, table_summary

    assert marker_counts(marker) == before
    assert_no_round9_secret(payload)


def test_restore_merge_restores_project_api_assets_and_lists_can_read_them(client):
    marker = f"round9-merge-{uuid4().hex[:10]}"
    response = client.post(f"{API_PREFIX}/system/restore", json=restore_payload(marker))
    payload = assert_response_envelope(response)
    data = payload["data"]

    assert isinstance(data, dict), data
    assert data.get("restored") is True, data
    assert_no_round9_secret(payload)

    project = find_project_by_code(client, marker)
    project_id = project["id"]

    libs = assert_list_like(data_of(client.get(f"{API_PREFIX}/projects/{project_id}/api-test-libs")))
    lib = find_by_field(libs, "name", f"{marker}-lib")
    lib_id = lib["id"]

    endpoints = assert_list_like(data_of(client.get(f"{API_PREFIX}/api-test-libs/{lib_id}/apis")))
    endpoint = find_by_field(endpoints, "path", f"/round9/{marker}/endpoint")
    endpoint_id = endpoint["id"]

    cases = assert_list_like(data_of(client.get(f"{API_PREFIX}/apis/{endpoint_id}/test-cases")))
    find_by_field(cases, "name", f"{marker}-case")

    environments = assert_list_like(data_of(client.get(f"{API_PREFIX}/api-test-libs/{lib_id}/environments")))
    find_by_field(environments, "name", f"{marker}-env")


def test_restore_overwrite_requires_confirmation_and_does_not_clear_database(client):
    marker = f"round9-guard-{uuid4().hex[:10]}"
    before = marker_counts(marker)
    payload = restore_payload(marker, mode="overwrite")
    payload.pop("confirm_text", None)

    response = client.post(f"{API_PREFIX}/system/restore", json=payload)
    response_payload = response.json()

    assert response.status_code == 400 or response_payload.get("code") not in (0, 200), response_payload
    assert marker_counts(marker) == before
    assert_no_round9_secret(response_payload)


def test_restore_redacts_fake_secrets_from_response_and_readback_lists(client):
    marker = f"round9-secret-{uuid4().hex[:10]}"
    payload = restore_payload(marker, data=backup_like_data(marker, include_fake_secrets=True))

    restore_response = assert_response_envelope(client.post(f"{API_PREFIX}/system/restore", json=payload))
    assert restore_response["data"].get("restored") is True, restore_response
    assert_no_round9_secret(restore_response)

    project = find_project_by_code(client, marker)
    libs = assert_list_like(data_of(client.get(f"{API_PREFIX}/projects/{project['id']}/api-test-libs")))
    lib = find_by_field(libs, "name", f"{marker}-lib")
    endpoints = assert_list_like(data_of(client.get(f"{API_PREFIX}/api-test-libs/{lib['id']}/apis")))
    endpoint = find_by_field(endpoints, "path", f"/round9/{marker}/endpoint")
    cases = assert_list_like(data_of(client.get(f"{API_PREFIX}/apis/{endpoint['id']}/test-cases")))
    environments = assert_list_like(data_of(client.get(f"{API_PREFIX}/api-test-libs/{lib['id']}/environments")))

    assert_no_round9_secret({"projects": [project], "libs": libs, "endpoints": endpoints, "cases": cases, "environments": environments})

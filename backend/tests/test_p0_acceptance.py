from __future__ import annotations

import pytest

from conftest import API_PREFIX, assert_response_envelope, data_of, first_item, object_id, post_json


pytestmark = pytest.mark.contract


def create_project(client) -> int | str:
    data = post_json(
        client,
        f"{API_PREFIX}/projects",
        {
            "code": "qa-contract-p0",
            "name": "QA Contract P0 Project",
            "description": "Created by pytest contract tests.",
            "owner_name": "devops_qa_engineer",
        },
    )
    return object_id(data, "id", "project_id")


def create_requirement_lib(client, project_id) -> int | str:
    data = post_json(
        client,
        f"{API_PREFIX}/projects/{project_id}/requirement-libs",
        {
            "name": "P0 Requirement Library",
            "description": "Library for backend P0 acceptance.",
        },
    )
    return object_id(data, "id", "lib_id")


def create_requirement_document(client, project_id, lib_id) -> int | str:
    data = post_json(
        client,
        f"{API_PREFIX}/projects/{project_id}/requirement-documents",
        {
            "lib_id": lib_id,
            "document_number": "REQ-DOC-P0-001",
            "name": "Login Requirement Draft",
            "source_type": "text",
            "raw_content": "Users can log in with username and password. Invalid credentials must be rejected.",
        },
    )
    return object_id(data, "id", "document_id")


def extract_requirement_item(client, document_id) -> int | str:
    parse_data = post_json(client, f"{API_PREFIX}/requirement-documents/{document_id}/parse", {"parse_mode": "standard"})
    assert parse_data is not None

    extracted = post_json(
        client,
        f"{API_PREFIX}/requirement-documents/{document_id}/extract-items",
        {"mode": "placeholder", "include_source_anchors": True},
    )
    if isinstance(extracted, dict) and extracted.get("items"):
        return object_id(first_item(extracted["items"]), "id", "item_id")
    if isinstance(extracted, list) and extracted:
        return object_id(first_item(extracted), "id", "item_id")

    listed = data_of(client.get(f"{API_PREFIX}/requirement-documents/{document_id}/requirement-items"))
    return object_id(first_item(listed), "id", "item_id")


def extract_test_case_id(data) -> int | str:
    if isinstance(data, dict) and data.get("cases"):
        return object_id(first_item(data["cases"]), "id", "case_id")
    if isinstance(data, dict) and data.get("test_cases"):
        return object_id(first_item(data["test_cases"]), "id", "case_id")
    return object_id(data, "id", "case_id")


def test_projects_endpoint_returns_unified_response(client):
    payload = assert_response_envelope(client.get(f"{API_PREFIX}/projects"))
    assert isinstance(payload["data"], (dict, list)), payload


def test_create_project_requirement_lib_and_document(client):
    project_id = create_project(client)
    lib_id = create_requirement_lib(client, project_id)
    document_id = create_requirement_document(client, project_id, lib_id)

    assert project_id
    assert lib_id
    assert document_id

    document = data_of(client.get(f"{API_PREFIX}/requirement-documents/{document_id}"))
    assert object_id(document, "id", "document_id") == document_id


def test_requirement_document_parse_extract_confirm_chain(client):
    project_id = create_project(client)
    lib_id = create_requirement_lib(client, project_id)
    document_id = create_requirement_document(client, project_id, lib_id)
    item_id = extract_requirement_item(client, document_id)

    confirmed = post_json(client, f"{API_PREFIX}/requirement-items/{item_id}/confirm")
    assert confirmed is not None


def test_requirement_item_generates_test_points(client):
    project_id = create_project(client)
    lib_id = create_requirement_lib(client, project_id)
    document_id = create_requirement_document(client, project_id, lib_id)
    item_id = extract_requirement_item(client, document_id)

    generated = post_json(client, f"{API_PREFIX}/requirement-items/{item_id}/generate-test-points")
    assert generated is not None

    points = data_of(client.get(f"{API_PREFIX}/requirement-items/{item_id}/test-points"))
    assert first_item(points)


def test_requirement_item_generates_test_cases_and_executions(client):
    project_id = create_project(client)
    lib_id = create_requirement_lib(client, project_id)
    document_id = create_requirement_document(client, project_id, lib_id)
    item_id = extract_requirement_item(client, document_id)

    generated_cases = post_json(
        client,
        f"{API_PREFIX}/requirement-items/{item_id}/generate-test-cases",
        {"case_types": ["functional", "exception"], "mode": "placeholder"},
    )
    case_id = extract_test_case_id(generated_cases)

    single_execution = post_json(
        client,
        f"{API_PREFIX}/executions",
        {
            "project_id": project_id,
            "case_id": case_id,
            "executor_type": "manual",
            "status": "passed",
            "actual_result": "Contract execution passed.",
        },
    )
    assert object_id(single_execution, "id", "execution_id")

    batch_execution = post_json(
        client,
        f"{API_PREFIX}/executions/batch",
        {
            "project_id": project_id,
            "executions": [
                {
                    "case_id": case_id,
                    "executor_type": "manual",
                    "status": "blocked",
                    "block_reason": "Placeholder batch contract.",
                }
            ],
        },
    )
    assert batch_execution is not None


def test_report_snapshot_and_backup_export(client):
    project_id = create_project(client)

    report = post_json(
        client,
        f"{API_PREFIX}/reports/comprehensive",
        {
            "project_id": project_id,
            "type": "comprehensive",
            "scope": {"project_id": project_id},
            "template_version": "v1",
        },
    )
    assert object_id(report, "id", "report_id", "snapshot_id")

    backup = post_json(client, f"{API_PREFIX}/system/backup", {"format": "json"})
    assert backup is not None
    assert isinstance(backup, (dict, list, str)), backup

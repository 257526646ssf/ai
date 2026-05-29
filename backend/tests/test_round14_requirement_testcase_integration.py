from __future__ import annotations

from conftest import API_PREFIX, data_of, first_item, object_id, post_json
from test_p0_acceptance import (
    create_project,
    create_requirement_document,
    create_requirement_lib,
    extract_requirement_item,
    extract_test_case_id,
)


def test_requirement_lib_frontend_lists_documents_and_items(client):
    project_id = create_project(client)
    lib_id = create_requirement_lib(client, project_id)
    document_id = create_requirement_document(client, project_id, lib_id)
    item_id = extract_requirement_item(client, document_id)

    docs = data_of(client.get(f"{API_PREFIX}/requirement-libs/{lib_id}/documents", params={"page": 1, "pageSize": 10}))
    items = data_of(client.get(f"{API_PREFIX}/requirement-libs/{lib_id}/requirement-items", params={"page": 1, "pageSize": 10}))

    assert str(document_id) in {str(doc["id"]) for doc in docs["list"]}
    assert str(item_id) in {str(item["id"]) for item in items["list"]}


def test_project_test_cases_frontend_list_and_export(client):
    project_id = create_project(client)
    lib_id = create_requirement_lib(client, project_id)
    document_id = create_requirement_document(client, project_id, lib_id)
    item_id = extract_requirement_item(client, document_id)
    post_json(client, f"{API_PREFIX}/requirement-items/{item_id}/generate-test-points")
    generated_cases = post_json(client, f"{API_PREFIX}/requirement-items/{item_id}/generate-test-cases", {"mode": "standard"})
    case_id = extract_test_case_id(generated_cases)

    project_cases = data_of(client.get(f"{API_PREFIX}/projects/{project_id}/test-cases", params={"page": 1, "pageSize": 20}))
    item_cases = data_of(
        client.get(
            f"{API_PREFIX}/projects/{project_id}/test-cases",
            params={"requirementItemId": item_id, "page": 1, "pageSize": 20},
        )
    )
    exported = data_of(client.get(f"{API_PREFIX}/test-cases/export", params={"projectId": project_id, "format": "csv"}))

    assert str(case_id) in {str(case["id"]) for case in project_cases["list"]}
    assert str(case_id) in {str(case["id"]) for case in item_cases["list"]}
    assert exported["format"] == "csv"
    assert exported["filename"].endswith(".csv")
    assert first_item(project_cases)


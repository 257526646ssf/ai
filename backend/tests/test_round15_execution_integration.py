from __future__ import annotations

from uuid import uuid4

from conftest import API_PREFIX, data_of, first_item, object_id, post_json


def create_round15_project(client) -> int | str:
    marker = uuid4().hex[:10]
    data = post_json(
        client,
        f"{API_PREFIX}/projects",
        {
            "code": f"round15-{marker}",
            "name": f"Round15 Execution Project {marker}",
            "description": "Round15 backend execution integration contract.",
            "owner_name": "round15_backend_worker",
        },
    )
    return object_id(data, "id", "project_id")


def create_round15_requirement_document(client, project_id) -> tuple[int | str, int | str, int | str]:
    marker = uuid4().hex[:10]
    lib = post_json(
        client,
        f"{API_PREFIX}/projects/{project_id}/requirement-libs",
        {
            "name": f"Round15 Requirement Library {marker}",
            "description": "Execution page integration library.",
        },
    )
    lib_id = object_id(lib, "id", "lib_id")

    document = post_json(
        client,
        f"{API_PREFIX}/projects/{project_id}/requirement-documents",
        {
            "lib_id": lib_id,
            "document_number": f"REQ-R15-{marker}",
            "name": "Round15 Checkout Requirement",
            "source_type": "text",
            "raw_content": "Users can submit an order. Payment failure must show a clear error and keep the cart unchanged.",
        },
    )
    document_id = object_id(document, "id", "document_id")
    return lib_id, document_id, marker


def extract_round15_requirement_item(client, document_id) -> int | str:
    post_json(client, f"{API_PREFIX}/requirement-documents/{document_id}/parse", {"parse_mode": "standard"})
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


def extract_round15_test_case_ids(payload) -> list[int | str]:
    cases = []
    if isinstance(payload, dict):
        for key in ("cases", "test_cases", "list"):
            value = payload.get(key)
            if isinstance(value, list):
                cases = value
                break
    elif isinstance(payload, list):
        cases = payload
    if not cases:
        cases = [first_item(payload)]
    return [object_id(case, "id", "case_id") for case in cases[:2]]


def test_execution_page_backend_contracts(client):
    project_id = create_round15_project(client)
    _, document_id, _ = create_round15_requirement_document(client, project_id)
    item_id = extract_round15_requirement_item(client, document_id)
    generated_cases = post_json(
        client,
        f"{API_PREFIX}/requirement-items/{item_id}/generate-test-cases",
        {"case_types": ["functional", "exception"], "mode": "placeholder"},
    )
    case_ids = extract_round15_test_case_ids(generated_cases)
    assert case_ids

    test_round = post_json(
        client,
        f"{API_PREFIX}/projects/{project_id}/test-rounds",
        {
            "name": "Round15 Execution Regression",
            "requirement_item_id": item_id,
            "document_id": document_id,
        },
    )
    round_id = object_id(test_round, "id", "round_id")

    round_list = data_of(
        client.get(
            f"{API_PREFIX}/projects/{project_id}/test-rounds",
            params={"page": 1, "pageSize": 10, "status": "in_progress"},
        )
    )
    assert round_list["page"] == 1
    assert round_list["pageSize"] == 10
    assert str(round_id) in {str(item["id"]) for item in round_list["list"]}
    assert all(item["status"] == "in_progress" for item in round_list["list"])

    failed_case_id = case_ids[-1]
    batch = post_json(
        client,
        f"{API_PREFIX}/executions/batch",
        {
            "round_id": round_id,
            "executor_type": "manual",
            "executions": [
                {
                    "case_id": case_ids[0],
                    "status": "passed",
                    "actual_result": "Order submission succeeded.",
                },
                {
                    "case_id": failed_case_id,
                    "status": "failed",
                    "actual_result": "Payment failure cleared the cart unexpectedly.",
                    "defect_title": "Payment failure clears cart",
                },
            ],
        },
    )
    execution_ids = {str(item["id"]) for item in batch["executions"]}
    assert batch["summary"]["total"] == 2
    assert batch["summary"]["passed"] == 1

    refreshed_round = data_of(client.get(f"{API_PREFIX}/test-rounds/{round_id}"))
    assert refreshed_round["total_count"] == 2
    assert refreshed_round["pass_count"] == 1
    assert refreshed_round["fail_count"] == 1

    history = data_of(client.get(f"{API_PREFIX}/executions/history", params={"projectId": project_id, "page": 1, "pageSize": 10}))
    assert execution_ids.issubset({str(item["id"]) for item in history["list"]})
    assert {str(item["project_id"]) for item in history["list"]} == {str(project_id)}

    statistics = data_of(client.get(f"{API_PREFIX}/executions/statistics", params={"projectId": project_id}))
    assert statistics["total"] == 2
    assert statistics["passed"] == 1
    assert statistics["failed"] == 1

    defects = data_of(client.get(f"{API_PREFIX}/defects", params={"projectId": project_id, "page": 1, "pageSize": 10}))
    assert defects["total"] == 1
    defect = first_item(defects)
    assert str(defect["project_id"]) == str(project_id)
    assert str(defect["case_id"]) == str(failed_case_id)
    assert defect["title"] == "Payment failure clears cart"

from __future__ import annotations

import json
from typing import Any

import pytest

from conftest import API_PREFIX, data_of, object_id, post_json
from test_p0_acceptance import (
    create_project,
    create_requirement_document,
    create_requirement_lib,
    extract_requirement_item,
    extract_test_case_id,
)


pytestmark = pytest.mark.contract

ROUND12_SECRET = "sk-round12-fake-secret"
SENSITIVE_STRINGS = (ROUND12_SECRET, "Authorization", "token")


def payload_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def assert_no_sensitive(payload: Any) -> None:
    dumped = payload_text(payload)
    for sensitive in SENSITIVE_STRINGS:
        assert sensitive not in dumped, dumped


def create_case(client) -> dict[str, Any]:
    project_id = create_project(client)
    lib_id = create_requirement_lib(client, project_id)
    document_id = create_requirement_document(client, project_id, lib_id)
    item_id = extract_requirement_item(client, document_id)
    post_json(client, f"{API_PREFIX}/requirement-items/{item_id}/generate-test-points")
    generated_cases = post_json(client, f"{API_PREFIX}/requirement-items/{item_id}/generate-test-cases")
    case_id = extract_test_case_id(generated_cases)
    return {"project_id": project_id, "requirement_item_id": item_id, "case_id": case_id}


def test_system_recycle_bin_lists_and_restores_soft_deleted_db_items(client):
    context = create_case(client)
    deleted = data_of(client.delete(f"{API_PREFIX}/test-cases/{context['case_id']}"))
    assert deleted.get("deleted") is True, deleted

    recycle_bin = data_of(client.get(f"{API_PREFIX}/system/recycle-bin"))
    items = recycle_bin.get("list") or []
    recycle_item = next(
        (
            item
            for item in items
            if item.get("type") == "test_cases" and str(item.get("record_id")) == str(context["case_id"])
        ),
        None,
    )
    assert recycle_item, recycle_bin
    recycle_id = recycle_item["id"]
    assert recycle_id == f"test_cases:{context['case_id']}", recycle_item

    restored = post_json(client, f"{API_PREFIX}/system/recycle-bin/{recycle_id}/restore")
    assert restored.get("restored") is True, restored

    cases = data_of(client.get(f"{API_PREFIX}/requirement-items/{context['requirement_item_id']}/test-cases"))
    assert str(context["case_id"]) in payload_text(cases), cases
    assert_no_sensitive(recycle_bin)
    assert_no_sensitive(restored)


def test_system_preferences_are_persisted_and_redacted(client):
    key = f"last-location-{create_project(client)}"
    payload = {
        "value": {
            "active_tab": "reports",
            "route": "/reports",
            "Authorization": f"Bearer {ROUND12_SECRET}",
            "token": ROUND12_SECRET,
        }
    }

    saved = post_json(client, f"{API_PREFIX}/system/preferences/{key}", payload)
    loaded = data_of(client.get(f"{API_PREFIX}/system/preferences/{key}"))
    listed = data_of(client.get(f"{API_PREFIX}/system/preferences"))

    assert saved.get("key") == key, saved
    assert loaded.get("value", {}).get("active_tab") == "reports", loaded
    assert key in payload_text(listed), listed
    assert_no_sensitive(saved)
    assert_no_sensitive(loaded)
    assert_no_sensitive(listed)


def test_system_recent_activities_are_persisted_filterable_and_redacted(client):
    project_id = create_project(client)
    activity = post_json(
        client,
        f"{API_PREFIX}/system/recent-activities",
        {
            "project_id": project_id,
            "title": f"Round 12 activity {project_id}",
            "route": "/requirements",
            "target_type": "requirement_item",
            "target_id": 123,
            "token": ROUND12_SECRET,
        },
    )
    activities = data_of(client.get(f"{API_PREFIX}/system/recent-activities", params={"projectId": project_id, "limit": 5}))

    assert object_id(activity, "id")
    assert f"Round 12 activity {project_id}" in payload_text(activities), activities
    assert_no_sensitive(activity)
    assert_no_sensitive(activities)

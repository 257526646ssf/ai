from __future__ import annotations

from conftest import API_PREFIX, data_of, post_json


def test_local_frontend_origin_is_allowed_by_cors(client):
    response = client.options(
        f"{API_PREFIX}/projects",
        headers={
            "Origin": "http://127.0.0.1:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code in {200, 204}, response.text
    assert response.headers.get("access-control-allow-origin") == "http://127.0.0.1:3000"
    assert "GET" in response.headers.get("access-control-allow-methods", "")


def test_unified_response_does_not_reuse_stale_content_length(client):
    response = client.get(f"{API_PREFIX}/projects", params={"page": 1, "pageSize": 1})

    assert response.status_code == 200, response.text
    assert int(response.headers["content-length"]) == len(response.content)


def test_frontend_dashboard_settings_contracts_are_stable(client):
    project = post_json(client, f"{API_PREFIX}/projects", {"name": "Round 13 Frontend Contract"})
    project_id = project["id"]

    dashboard = data_of(client.get(f"{API_PREFIX}/projects/{project_id}/dashboard"))
    assert dashboard["project_id"] == project_id
    for key in ("requirement_libs", "requirement_items", "test_cases", "executions", "defects", "updated_at"):
        assert key in dashboard, dashboard

    activity = post_json(
        client,
        f"{API_PREFIX}/system/recent-activities",
        {"project_id": project_id, "title": "Round 13 browser sync", "target_type": "dashboard"},
    )
    activities = data_of(client.get(f"{API_PREFIX}/system/recent-activities", params={"projectId": project_id, "limit": 5}))
    assert activity["id"] in {item["id"] for item in activities["list"]}

    preference = post_json(
        client,
        f"{API_PREFIX}/system/preferences/runtime-settings",
        {"value": {"logLevel": "info", "maxWorkers": 8, "timeoutLimit": 30}},
    )
    assert preference["key"] == "runtime-settings"
    assert preference["value"]["maxWorkers"] == 8

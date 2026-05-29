from __future__ import annotations

from conftest import API_PREFIX, data_of, post_json


def test_dashboard_daily_and_weekly_summary_use_project_facts(client):
    project = post_json(client, f"{API_PREFIX}/projects", {"name": "Round 19 Quality Summary"})
    project_id = project["id"]

    daily = data_of(client.post(f"{API_PREFIX}/projects/{project_id}/dashboard/daily-summary", json={"requested_by": "round19"}))
    weekly = data_of(client.post(f"{API_PREFIX}/projects/{project_id}/dashboard/weekly-summary", json={}))

    for payload, period in ((daily, "daily"), (weekly, "weekly")):
        assert payload["project_id"] == project_id
        assert payload["period"] == period
        assert "质量摘要" in payload["summary"]
        assert "占位" not in payload["summary"]
        assert "placeholder" not in payload["summary"].lower()
        assert payload["metrics"]["test_case_count"] >= 0
        assert payload["risk_level"] in {"低", "中", "高"}
        assert payload["risk_items"]
        assert payload["next_actions"]
        assert payload["source_refs"]["project_id"] == project_id


def test_chat_fallback_uses_backend_project_context(client):
    project = post_json(client, f"{API_PREFIX}/projects", {"name": "Round 19 Chat Facts"})
    project_id = project["id"]

    response = data_of(
        client.post(
            f"{API_PREFIX}/chat",
            json={
                "message": "请总结当前项目的准出风险和待办",
                "context": {"project_id": project_id, "active_tab": "dashboard"},
            },
        )
    )

    assert response["status"] in {"fallback", "disabled", "skipped", "ok"}
    assert "Round 19 Chat Facts" in response["reply"]
    assert "通过率" in response["reply"]
    assert "placeholder" not in response["reply"].lower()
    assert "占位" not in response["reply"]
    assert response["context"]["project_facts"]["metrics"]["test_case_count"] >= 0

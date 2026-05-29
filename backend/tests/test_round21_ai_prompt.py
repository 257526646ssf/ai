from __future__ import annotations

import json
from uuid import uuid4

from sqlalchemy import select

from aitest_platform.db.session import session_scope
from aitest_platform.models import LlmConfig, OperationLog, PromptTemplate
from conftest import API_PREFIX, data_of, object_id, post_json


ROUND21_SECRET = "sk-round21-context-secret"


def _payload_text(payload) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def _assert_no_sensitive(payload) -> None:
    dumped = _payload_text(payload).lower()
    assert ROUND21_SECRET.lower() not in dumped, dumped
    for marker in ("api_key", "apikey", "authorization", "cookie", "password", "secret=", "token="):
        assert marker not in dumped, dumped


def _create_project(client, name: str = "Round21 AI Prompt") -> int:
    marker = uuid4().hex[:10]
    project = post_json(
        client,
        f"{API_PREFIX}/projects",
        {
            "code": f"round21-{marker}",
            "name": f"{name} {marker}",
            "description": "Round 21 assistant and prompt contract.",
            "owner_name": "round21_backend_worker",
        },
    )
    return int(object_id(project, "id", "project_id"))


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


def test_prompt_template_create_render_delete_and_builtin_protection(client):
    marker = uuid4().hex[:10]
    created = post_json(
        client,
        f"{API_PREFIX}/prompt-templates",
        {
            "name": f"Round21 common prompt {marker}",
            "content": "Hello {{actor}}, cover {scope}.",
            "variables": ["actor", "scope", "api_key"],
            "api_key": ROUND21_SECRET,
        },
    )

    template_id = int(object_id(created, "id", "template_id"))
    assert created["scene"]
    assert created["is_builtin"] is False
    assert created["variables"] == ["actor", "scope"]
    _assert_no_sensitive(created)

    created_again = post_json(
        client,
        f"{API_PREFIX}/prompt-templates",
        {"name": f"Round21 common prompt {marker}", "content": "Second {{actor}}."},
    )
    assert created_again["scene"] != created["scene"]

    nested = post_json(
        client,
        f"{API_PREFIX}/prompt-templates/{template_id}/test",
        {"variables": {"actor": "QA", "scope": "checkout", "token": ROUND21_SECRET}},
    )
    assert nested["rendered"] == "Hello QA, cover checkout."
    _assert_no_sensitive(nested)

    flat = post_json(client, f"{API_PREFIX}/prompt-templates/{template_id}/test", {"actor": "Dev", "scope": "billing"})
    assert flat["rendered"] == "Hello Dev, cover billing."

    deleted = data_of(client.delete(f"{API_PREFIX}/prompt-templates/{template_id}"))
    assert deleted == {"deleted": True, "id": template_id}

    builtin_scene = f"round21_builtin_{marker}"
    with session_scope() as session:
        builtin = PromptTemplate(
            scene=builtin_scene,
            name=f"Round21 builtin {marker}",
            content="Builtin {{requirement}}",
            variables=["requirement"],
            is_builtin=True,
        )
        session.add(builtin)
        session.flush()
        builtin_id = builtin.id

    response = client.delete(f"{API_PREFIX}/prompt-templates/{builtin_id}")
    assert response.status_code == 400, response.text
    with session_scope() as session:
        assert session.get(PromptTemplate, builtin_id) is not None


def test_assistant_context_returns_safe_summaries(client):
    project_id = _create_project(client, "Round21 Assistant Context")
    marker = uuid4().hex[:10]
    post_json(
        client,
        f"{API_PREFIX}/system/recent-activities",
        {
            "project_id": project_id,
            "title": f"Round21 activity {marker}",
            "route": "/requirements",
            "target_type": "requirement_item",
            "target_id": 123,
            "token": ROUND21_SECRET,
            "note": f"Authorization: Bearer {ROUND21_SECRET}",
        },
    )
    with session_scope() as session:
        session.add(
            OperationLog(
                module="round21",
                action="assistant_context",
                target_type="project",
                target_id=project_id,
                detail={"api_key": ROUND21_SECRET, "safe": "visible", "nested": {"cookie": ROUND21_SECRET}},
            )
        )

    context = data_of(client.get(f"{API_PREFIX}/assistant/context", params={"project_id": project_id, "activeTab": "dashboard"}))

    assert context["project_id"] == project_id
    assert context["active_tab"] == "dashboard"
    assert context["recent_activities"]["list"]
    assert any(item.get("title") == f"Round21 activity {marker}" for item in context["recent_activities"]["list"])
    assert context["operation_logs"]["list"]
    assert context["prompt_templates"]["list"]
    assert "metrics" in context["project_facts"]
    assert context["provider_call_performed"] is False
    _assert_no_sensitive(context)


def test_assistant_drafts_are_deterministic_and_do_not_call_provider(client):
    context = {"active_tab": "requirements", "api_key": ROUND21_SECRET, "project_facts": {"metrics": {"open_defect_count": 1}}}

    test_points = post_json(
        client,
        f"{API_PREFIX}/assistant/drafts",
        {"type": "test_points", "message": "Checkout coupon rule", "context": context},
    )
    questions = post_json(
        client,
        f"{API_PREFIX}/assistant/drafts",
        {"draft_type": "clarifying_questions", "message": "Checkout coupon rule", "context": context},
    )
    defect_note = post_json(
        client,
        f"{API_PREFIX}/assistant/drafts",
        {"type": "defect_note", "message": "Coupon discount is not applied", "context": context},
    )

    assert test_points["type"] == "test_points"
    assert len(test_points["draft"]["items"]) >= 4
    assert questions["type"] == "clarifying_questions"
    assert len(questions["draft"]["items"]) >= 3
    assert defect_note["type"] == "defect_note"
    assert defect_note["draft"]["note"]["status"] == "open"
    for payload in (test_points, questions, defect_note):
        assert payload["provider_call_performed"] is False
        assert payload["llm_provider_called"] is False
        _assert_no_sensitive(payload)


def test_chat_fallback_uses_assistant_context_without_provider_call(monkeypatch, client):
    project_id = _create_project(client, "Round21 Chat Context")
    marker = uuid4().hex[:10]
    post_json(
        client,
        f"{API_PREFIX}/system/recent-activities",
        {"project_id": project_id, "title": f"Round21 chat activity {marker}", "route": "/dashboard"},
    )
    assistant_context = data_of(client.get(f"{API_PREFIX}/assistant/context", params={"projectId": project_id, "activeTab": "dashboard"}))

    def fail_provider_call(*_args, **_kwargs):
        raise AssertionError("chat must not call a real provider in Round 21 fallback contract")

    monkeypatch.setattr("aitest_platform.api.router.OpenAICompatibleClient.chat_completions", fail_provider_call)
    snapshot = _disable_llm_configs_for_test()
    try:
        response = data_of(
            client.post(
                f"{API_PREFIX}/chat",
                json={
                    "message": "Summarize the current assistant context",
                    "context": {"project_id": project_id, "active_tab": "dashboard", "assistant_context": assistant_context},
                },
            )
        )
    finally:
        _restore_llm_configs(snapshot)

    assert response["status"] == "fallback"
    assert response["provider_call_performed"] is False
    assert response["llm_provider_called"] is False
    assert f"Round21 chat activity {marker}" in response["reply"]
    _assert_no_sensitive(response)

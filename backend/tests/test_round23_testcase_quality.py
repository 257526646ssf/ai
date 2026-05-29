from __future__ import annotations

import json
from uuid import uuid4

import pytest

from aitest_platform.db.session import session_scope
from aitest_platform.models import TestCase as DbCase
from conftest import API_PREFIX, data_of, object_id, post_json


pytestmark = pytest.mark.contract

ROUND23_SECRET = "sk-round23-secret"
REDACTED_MARKERS = ("authorization", "cookie", "token", "api_key", ROUND23_SECRET.lower())


def _records(value):
    if isinstance(value, dict):
        for key in ("list", "items", "records", "results", "data", "test_points", "test_cases", "cases"):
            nested = value.get(key)
            if isinstance(nested, list):
                return nested
    if isinstance(value, list):
        return value
    pytest.fail(f"Expected list-like payload with one of the supported item keys, got type={type(value).__name__}", pytrace=False)


def _assert_no_sensitive_text(payload) -> None:
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    lowered = text.lower()
    for marker in REDACTED_MARKERS:
        assert marker not in lowered, f"Response leaked sensitive marker: {marker}"


def _secret_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {ROUND23_SECRET}",
        "Cookie": f"round23_session={ROUND23_SECRET}",
    }


def _secret_payload() -> dict:
    return {
        "credentials": {
            "api_key": ROUND23_SECRET,
            "token": ROUND23_SECRET,
            "cookie": f"round23_session={ROUND23_SECRET}",
        }
    }


def _db_case_status(case_id: int) -> str:
    with session_scope() as session:
        case = session.get(DbCase, case_id)
        assert case is not None and not case.is_deleted, f"TestCase({case_id}) was not persisted"
        return case.status


def _create_round23_quality_context(client) -> dict:
    marker = uuid4().hex[:10]
    project = post_json(
        client,
        f"{API_PREFIX}/projects",
        {
            "code": f"round23-{marker}",
            "name": f"Round23 Testcase Quality {marker}",
            "description": "R23 QA contract test project.",
            "owner_name": "round23_qa_contract",
        },
    )
    project_id = int(object_id(project, "id", "project_id"))

    lib = post_json(
        client,
        f"{API_PREFIX}/projects/{project_id}/requirement-libs",
        {
            "name": f"Round23 Requirement Library {marker}",
            "description": "Library for testcase quality review contracts.",
        },
    )
    lib_id = int(object_id(lib, "id", "lib_id"))

    document = post_json(
        client,
        f"{API_PREFIX}/projects/{project_id}/requirement-documents",
        {
            "lib_id": lib_id,
            "document_number": f"REQ-R23-{marker}",
            "name": f"Checkout Quality Requirement {marker}",
            "source_type": "markdown",
            "source_file_name": f"round23-{marker}.md",
            "raw_content": "\n".join(
                [
                    "# Checkout Quality",
                    "",
                    "The checkout service must validate stock, approve payment, and create an auditable order.",
                    "High-priority checkout requirements must be covered by executable and assertable test cases.",
                    "Duplicate or near-duplicate test case titles must be detected before review approval.",
                ]
            ),
        },
    )
    document_id = int(object_id(document, "id", "document_id"))

    post_json(client, f"{API_PREFIX}/requirement-documents/{document_id}/parse", {"parse_mode": "standard"})
    extracted = post_json(
        client,
        f"{API_PREFIX}/requirement-documents/{document_id}/extract-items",
        {"mode": "standard", "include_source_anchors": True, "min_items": 1},
    )
    requirement_items = _records(extracted.get("items", extracted) if isinstance(extracted, dict) else extracted)
    item_id = int(object_id(requirement_items[0], "id", "item_id"))

    item = data_of(
        client.patch(
            f"{API_PREFIX}/requirement-items/{item_id}",
            json={
                "title": "Round23 checkout order creation requires auditable P0 validation",
                "summary": "Validate stock, payment approval, and order audit trail before order creation.",
                "module": "checkout",
                "priority": "P0",
            },
        )
    )
    assert item["priority"] == "P0", item

    for _ in range(3):
        post_json(client, f"{API_PREFIX}/requirement-items/{item_id}/generate-test-points", {"mode": "standard"})
    points = _records(
        data_of(client.get(f"{API_PREFIX}/requirement-items/{item_id}/test-points", params={"page": 1, "pageSize": 20}))
    )
    assert len(points) >= 5, points

    generated_cases = post_json(
        client,
        f"{API_PREFIX}/requirement-items/{item_id}/generate-test-cases",
        {"mode": "round23-quality", "test_point_ids": [int(object_id(point, "id")) for point in points[:5]]},
    )
    cases = _records(generated_cases)
    assert len(cases) >= 5, generated_cases
    case_ids = [int(object_id(case, "id", "case_id")) for case in cases[:5]]

    case_updates = [
        {
            "title": "Checkout creates auditable paid order when stock and payment are valid",
            "precondition": "Buyer is authenticated, cart contains one in-stock SKU, and payment sandbox is available.",
            "steps": [
                {"step": 1, "action": "Open checkout for an in-stock SKU."},
                {"step": 2, "action": "Submit a valid payment method and confirm the order."},
                {"step": 3, "action": "Read the created order detail and audit log."},
            ],
            "expected_result": "Order status is PAID, stock is reduced by 1, and audit log contains order_id, payment_id, and buyer_id.",
            "priority": "P0",
            "tags": ["round23", "good"],
        },
        {
            "title": "Checkout payment failure behavior is documented",
            "precondition": "Payment sandbox is available.",
            "steps": [],
            "expected_result": "System works as expected.",
            "priority": "P0",
            "tags": ["round23", "unexecutable"],
        },
        {
            "title": "Checkout rejects order when selected SKU is out of stock",
            "precondition": "Buyer is authenticated and selected SKU inventory is 0.",
            "steps": [
                {"step": 1, "action": "Open checkout for the out-of-stock SKU."},
                {"step": 2, "action": "Click submit order."},
            ],
            "expected_result": "Submit is blocked, no order row is created, and the response contains OUT_OF_STOCK.",
            "priority": "P0",
            "tags": ["round23", "duplicate-a"],
        },
        {
            "title": "Checkout should reject order if selected SKU is out of stock",
            "precondition": "Buyer is authenticated and selected SKU inventory is 0.",
            "steps": [
                {"step": 1, "action": "Open checkout for the out-of-stock SKU."},
                {"step": 2, "action": "Click submit order."},
            ],
            "expected_result": "Submit is blocked, no order row is created, and the response contains OUT_OF_STOCK.",
            "priority": "P0",
            "tags": ["round23", "duplicate-b"],
        },
        {
            "title": "Checkout creates audit trail for P0 payment approval",
            "precondition": "Buyer is authenticated and payment sandbox is available.",
            "steps": [
                {"step": 1, "action": "Submit checkout with a valid payment method."},
                {"step": 2, "action": "Query the payment approval audit record."},
            ],
            "expected_result": "Audit record contains approval_id, order_id, amount, actor, and created_at.",
            "priority": "P3",
            "tags": ["round23", "priority-mismatch"],
        },
    ]
    for case_id, update in zip(case_ids, case_updates, strict=True):
        updated = data_of(client.patch(f"{API_PREFIX}/test-cases/{case_id}", json=update))
        assert updated["title"] == update["title"], updated

    return {
        "project_id": project_id,
        "lib_id": lib_id,
        "document_id": document_id,
        "item_id": item_id,
        "good_case_id": case_ids[0],
        "unexecutable_case_id": case_ids[1],
        "duplicate_case_ids": case_ids[2:4],
        "priority_mismatch_case_id": case_ids[4],
        "case_ids": case_ids,
    }


def _assert_quality_payload(payload: dict, *, expected_case_id: int | None = None) -> None:
    assert isinstance(payload, dict), payload
    if expected_case_id is not None:
        assert str(payload.get("case_id") or payload.get("id") or payload.get("test_case_id")) == str(expected_case_id), payload
    assert "score" in payload, payload
    assert "quality_score" in payload, payload
    assert isinstance(payload["score"], (int, float)), payload
    assert isinstance(payload["quality_score"], (int, float)), payload
    assert 0 <= payload["score"] <= 100, payload
    assert 0 <= payload["quality_score"] <= 100, payload
    assert isinstance(payload.get("issues"), list), payload
    assert isinstance(payload.get("suggested_actions"), list), payload
    assert isinstance(payload.get("duplicate_candidates"), list), payload
    assert isinstance(payload.get("checks"), (dict, list)), payload
    assert payload.get("review_status") in {"review_passed", "needs_review"}, payload
    assert payload.get("provider_call_performed") is False, payload
    assert payload.get("llm_provider_called") is False, payload


def test_single_case_quality_review_returns_rule_result_updates_status_and_redacts_secrets(client):
    context = _create_round23_quality_context(client)

    good_review = data_of(
        client.post(
            f"{API_PREFIX}/test-cases/{context['good_case_id']}/quality-review",
            json={
                "checks": ["completeness", "assertability", "duplicates", "priority_alignment"],
                "project_id": context["project_id"],
                **_secret_payload(),
            },
            headers=_secret_headers(),
        )
    )
    _assert_quality_payload(good_review, expected_case_id=context["good_case_id"])
    assert good_review["review_status"] == "review_passed", good_review
    assert _db_case_status(context["good_case_id"]) == "review_passed"
    _assert_no_sensitive_text(good_review)

    bad_review = data_of(
        client.post(
            f"{API_PREFIX}/test-cases/{context['unexecutable_case_id']}/quality-review",
            json={"project_id": context["project_id"], **_secret_payload()},
            headers=_secret_headers(),
        )
    )
    _assert_quality_payload(bad_review, expected_case_id=context["unexecutable_case_id"])
    assert bad_review["review_status"] == "needs_review", bad_review
    assert bad_review["issues"], bad_review
    assert _db_case_status(context["unexecutable_case_id"]) == "needs_review"
    _assert_no_sensitive_text(bad_review)


def test_batch_review_accepts_case_ids_or_project_id_and_returns_summary(client):
    context = _create_round23_quality_context(client)

    by_ids = data_of(
        client.post(
            f"{API_PREFIX}/test-cases/review-batch",
            json={"case_ids": context["case_ids"], "project_id": context["project_id"], **_secret_payload()},
            headers=_secret_headers(),
        )
    )
    items = _records(by_ids.get("items", by_ids))
    assert {int(item["case_id"]) for item in items} == set(context["case_ids"]), by_ids
    for item in items:
        _assert_quality_payload(item)

    summary = by_ids.get("summary")
    assert isinstance(summary, dict), by_ids
    assert summary["total"] == len(context["case_ids"]), summary
    assert summary["pass"] >= 1, summary
    assert summary["needs_review"] >= 1, summary
    assert isinstance(summary["avg_score"], (int, float)), summary
    assert 0 <= summary["avg_score"] <= 100, summary
    assert isinstance(summary["issue_counts"], dict) and summary["issue_counts"], summary
    _assert_no_sensitive_text(by_ids)

    by_project = data_of(client.post(f"{API_PREFIX}/test-cases/review-batch", json={"project_id": context["project_id"]}))
    assert len(_records(by_project.get("items", by_project))) >= len(context["case_ids"]), by_project
    assert by_project["summary"]["total"] >= len(context["case_ids"]), by_project


def test_project_quality_summary_reports_duplicate_priority_and_unexecutable_metrics(client):
    context = _create_round23_quality_context(client)
    post_json(client, f"{API_PREFIX}/test-cases/review-batch", {"case_ids": context["case_ids"], "project_id": context["project_id"]})

    summary = data_of(
        client.get(
            f"{API_PREFIX}/projects/{context['project_id']}/test-case-quality-summary",
            headers=_secret_headers(),
        )
    )

    assert isinstance(summary.get("issue_counts"), dict) and summary["issue_counts"], summary
    assert isinstance(summary.get("duplicate_groups"), list) and summary["duplicate_groups"], summary
    assert isinstance(summary.get("priority_mismatches"), list) and summary["priority_mismatches"], summary
    assert summary.get("unexecutable_count", 0) >= 1, summary
    nested_summary = summary.get("summary") if isinstance(summary.get("summary"), dict) else {}
    score = summary.get("avg_score", summary.get("quality_score", nested_summary.get("avg_score")))
    assert isinstance(score, (int, float)), summary
    assert 0 <= score <= 100, summary
    summary_text = json.dumps(summary, ensure_ascii=False, sort_keys=True, default=str)
    assert str(context["priority_mismatch_case_id"]) in summary_text, summary
    assert all(str(case_id) in summary_text for case_id in context["duplicate_case_ids"]), summary
    _assert_no_sensitive_text(summary)


def test_review_opinions_persist_manual_decisions_and_update_case_status(client):
    context = _create_round23_quality_context(client)

    approved = data_of(
        client.post(
            f"{API_PREFIX}/test-cases/{context['good_case_id']}/review-opinions",
            json={
                "reviewer": "round23_qa",
                "decision": "approved",
                "opinion": "Good testcase is executable and assertable.",
                **_secret_payload(),
            },
            headers=_secret_headers(),
        )
    )
    approved_opinion = approved.get("opinion", approved)
    assert approved_opinion.get("decision") == "approved", approved
    assert approved_opinion.get("case_id") == context["good_case_id"], approved
    assert _db_case_status(context["good_case_id"]) in {"review_passed", "approved", "reviewed"}, approved
    _assert_no_sensitive_text(approved)

    changing = data_of(
        client.post(
            f"{API_PREFIX}/test-cases/{context['priority_mismatch_case_id']}/review-opinions",
            json={
                "reviewer": "round23_qa",
                "decision": "changing",
                "opinion": "Priority must align with the P0 source requirement before approval.",
            },
        )
    )
    changing_opinion = changing.get("opinion", changing)
    assert changing_opinion.get("decision") == "changing", changing
    assert changing_opinion.get("case_id") == context["priority_mismatch_case_id"], changing
    assert _db_case_status(context["priority_mismatch_case_id"]) in {"needs_review", "changing"}, changing


def test_legacy_rule_validate_and_ai_review_return_real_rule_results_and_redact_secrets(client):
    context = _create_round23_quality_context(client)

    rule_result = data_of(
        client.post(
            f"{API_PREFIX}/test-cases/rule-validate",
            json={"case_ids": context["case_ids"], "project_id": context["project_id"], **_secret_payload()},
            headers=_secret_headers(),
        )
    )
    assert "items" in rule_result, f"rule-validate must return reviewed items, got keys={sorted(rule_result)}"
    assert "input" not in rule_result, "rule-validate must not echo raw input or credentials"
    rule_items = _records(rule_result.get("items", rule_result))
    assert {int(item["case_id"]) for item in rule_items} == set(context["case_ids"]), rule_result
    assert isinstance(rule_result.get("summary"), dict), rule_result
    for item in rule_items:
        _assert_quality_payload(item)
    _assert_no_sensitive_text(rule_result)

    payload_item = {
        "id": "payload-case-1",
        "title": "Payload checkout case has no assertable expected result",
        "steps": [{"step": 1, "action": "Run checkout."}],
        "expected_result": "Looks good.",
        "priority": "P3",
        "requirement_priority": "P0",
    }
    ai_result = data_of(
        client.post(
            f"{API_PREFIX}/test-cases/ai-review",
            json={"items": [payload_item], **_secret_payload()},
            headers=_secret_headers(),
        )
    )
    assert "items" in ai_result, f"ai-review must return reviewed items, got keys={sorted(ai_result)}"
    assert "input" not in ai_result, "ai-review must not echo raw input or credentials"
    ai_items = _records(ai_result.get("items", ai_result))
    assert len(ai_items) == 1, ai_result
    reviewed = ai_items[0]
    assert reviewed.get("case_id") == "payload-case-1", reviewed
    assert isinstance(reviewed.get("issues"), list) and reviewed["issues"], reviewed
    assert isinstance(reviewed.get("suggested_actions"), list) and reviewed["suggested_actions"], reviewed
    assert reviewed.get("provider_call_performed") is False, reviewed
    assert reviewed.get("llm_provider_called") is False, reviewed
    _assert_no_sensitive_text(ai_result)

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from conftest import API_PREFIX, assert_response_envelope, data_of, first_item, object_id, post_json
from aitest_platform.services.execution_defect_loop import redact_sensitive_text, sanitize_loop_payload


pytestmark = pytest.mark.contract

ROUND24_SECRET = "sk-round24-secret"
SENSITIVE_MARKERS = ("authorization", "token", "cookie", "api_key", ROUND24_SECRET.lower())


def _records(value):
    if isinstance(value, dict):
        for key in (
            "list",
            "items",
            "records",
            "results",
            "data",
            "templates",
            "executions",
            "defects",
            "trend",
            "recent_trend",
            "top_failed_cases",
        ):
            nested = value.get(key)
            if isinstance(nested, list):
                return nested
        if "id" in value:
            return [value]
    if isinstance(value, list):
        return value
    pytest.fail(f"Expected list-like payload, got: {value!r}", pytrace=False)


def _template_records(value) -> list[dict]:
    if isinstance(value, dict) and {"failed", "blocked", "skipped"}.issubset(value):
        return [value[key] for key in ("failed", "blocked", "skipped")]
    return _records(value)


def _payload_text(payload) -> str:
    return payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def _assert_no_sensitive_text(payload) -> None:
    text = _payload_text(payload)
    lowered = text.lower()
    for marker in SENSITIVE_MARKERS:
        assert marker not in lowered, f"Response leaked sensitive marker {marker!r}: {text}"


def test_round24_redaction_preserves_plain_defect_text_while_masking_secrets():
    title = redact_sensitive_text(f"Round 11 defect checkout regression {ROUND24_SECRET}")
    assert title == "Round 11 defect checkout regression ***"
    _assert_no_sensitive_text(title)

    credential_text = redact_sensitive_text(
        f"Authorization: Bearer {ROUND24_SECRET}; token={ROUND24_SECRET}; "
        f"password={ROUND24_SECRET}; secret={ROUND24_SECRET}; api_key={ROUND24_SECRET}"
    )
    lowered = credential_text.lower()
    for marker in ("authorization", "bearer", "token", "password", "secret", "api_key", ROUND24_SECRET.lower()):
        assert marker not in lowered, credential_text
    assert credential_text.count("***") >= 5

    sanitized = sanitize_loop_payload(
        {
            "title": f"Round 11 defect checkout regression {ROUND24_SECRET}",
            "safe": "Round 11 defect checkout regression",
            "credentials": {
                "token": ROUND24_SECRET,
                "password": ROUND24_SECRET,
                "secret": ROUND24_SECRET,
                "api_key": ROUND24_SECRET,
            },
        }
    )
    assert sanitized["title"] == "Round 11 defect checkout regression ***"
    assert sanitized["safe"] == "Round 11 defect checkout regression"
    assert sanitized["credentials"] == {
        "token": "***",
        "password": "***",
        "secret": "***",
        "api_key": "***",
    }


def _secret_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {ROUND24_SECRET}",
        "Cookie": f"round24_session={ROUND24_SECRET}",
    }


def _secret_payload() -> dict:
    return {
        "notes": f"Authorization: Bearer {ROUND24_SECRET}; token={ROUND24_SECRET}; cookie={ROUND24_SECRET}",
        "credentials": {
            "api_key": ROUND24_SECRET,
            "token": ROUND24_SECRET,
            "cookie": f"round24_session={ROUND24_SECRET}",
        },
    }


def _extract_case_ids(payload) -> list[int]:
    cases = _records(payload)
    return [int(object_id(case, "id", "case_id")) for case in cases]


def _assert_count(payload: dict, key: str, minimum: int = 1) -> None:
    assert key in payload, payload
    assert isinstance(payload[key], int | float), payload
    assert payload[key] >= minimum, payload


def _canonical_execution_status(execution: dict) -> str | None:
    status = execution.get("status_alias") or execution.get("status")
    return {"pass": "passed", "fail": "failed"}.get(status, status)


def _create_round24_context(client) -> dict:
    marker = uuid4().hex[:10]
    project = post_json(
        client,
        f"{API_PREFIX}/projects",
        {
            "code": f"round24-{marker}",
            "name": f"Round24 Execution Defect Loop {marker}",
            "description": "R24 execution and defect loop contract.",
            "owner_name": "round24_qa_contract",
        },
    )
    project_id = int(object_id(project, "id", "project_id"))

    lib = post_json(
        client,
        f"{API_PREFIX}/projects/{project_id}/requirement-libs",
        {
            "name": f"Round24 Requirement Library {marker}",
            "description": "Library for execution and defect closure contracts.",
        },
    )
    lib_id = int(object_id(lib, "id", "lib_id"))

    document = post_json(
        client,
        f"{API_PREFIX}/projects/{project_id}/requirement-documents",
        {
            "lib_id": lib_id,
            "document_number": f"REQ-R24-{marker}",
            "name": f"Round24 Checkout Requirement {marker}",
            "source_type": "markdown",
            "source_file_name": f"round24-{marker}.md",
            "raw_content": "\n".join(
                [
                    "# Checkout Execution Loop",
                    "",
                    "Checkout must preserve cart state when payment fails.",
                    "Checkout must show actionable blocking messages when inventory service is unavailable.",
                    "Users can skip optional coupon validation without creating a defect.",
                    "Every failed or blocked execution needs reproducible defect guidance and retest planning.",
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
    items = _records(extracted.get("items", extracted) if isinstance(extracted, dict) else extracted)
    item_id = int(object_id(items[0], "id", "item_id"))

    for _ in range(2):
        post_json(client, f"{API_PREFIX}/requirement-items/{item_id}/generate-test-cases", {"mode": "round24-contract"})
    listed_cases = data_of(
        client.get(f"{API_PREFIX}/requirement-items/{item_id}/test-cases", params={"page": 1, "pageSize": 20})
    )
    case_ids = _extract_case_ids(listed_cases)
    assert len(case_ids) >= 4, listed_cases

    case_updates = [
        {
            "title": "Round24 checkout completes successfully for an in-stock SKU",
            "precondition": "Buyer is authenticated and selected SKU is in stock.",
            "steps": [{"step": 1, "action": "Submit checkout with valid payment."}],
            "expected_result": "Order is paid, stock is reduced, and receipt is visible.",
            "priority": "P1",
        },
        {
            "title": "Round24 payment failure preserves cart state",
            "precondition": "Payment sandbox can reject card authorization.",
            "steps": [{"step": 1, "action": "Submit checkout with a rejected payment method."}],
            "expected_result": "Cart remains unchanged and retry guidance is displayed.",
            "priority": "P0",
        },
        {
            "title": "Round24 inventory outage blocks checkout with actionable guidance",
            "precondition": "Inventory service returns timeout.",
            "steps": [{"step": 1, "action": "Submit checkout while inventory service is unavailable."}],
            "expected_result": "Checkout is blocked and no order is created.",
            "priority": "P0",
        },
        {
            "title": "Round24 optional coupon validation can be skipped",
            "precondition": "Coupon service is under maintenance.",
            "steps": [{"step": 1, "action": "Skip optional coupon validation and continue checkout."}],
            "expected_result": "Checkout continues without a defect.",
            "priority": "P2",
        },
    ]
    for case_id, update in zip(case_ids[:4], case_updates, strict=True):
        data_of(client.patch(f"{API_PREFIX}/test-cases/{case_id}", json=update))

    test_round = post_json(
        client,
        f"{API_PREFIX}/projects/{project_id}/test-rounds",
        {
            "name": f"Round24 Execution Regression {marker}",
            "requirement_item_id": item_id,
            "document_id": document_id,
        },
    )
    round_id = int(object_id(test_round, "id", "round_id"))

    batch = post_json(
        client,
        f"{API_PREFIX}/executions/batch",
        {
            "project_id": project_id,
            "round_id": round_id,
            "executor_type": "manual",
            "executions": [
                {
                    "case_id": case_ids[0],
                    "status": "passed",
                    "actual_result": "Checkout completed and receipt was visible.",
                    "create_defect": False,
                },
                {
                    "case_id": case_ids[1],
                    "status": "failed",
                    "actual_result": "Cart was cleared after payment rejection.",
                    "defect_title": "Round24 payment failure clears cart",
                    "create_defect": False,
                },
                {
                    "case_id": case_ids[2],
                    "status": "blocked",
                    "block_reason": "Inventory timeout blocks checkout.",
                    "actual_result": "Checkout waited indefinitely and gave no operator guidance.",
                    "create_defect": False,
                },
                {
                    "case_id": case_ids[3],
                    "status": "skipped",
                    "skip_reason": "Coupon service maintenance is outside this round.",
                    "actual_result": "Skipped optional coupon validation.",
                    "create_defect": False,
                },
            ],
        },
    )
    executions = _records(batch.get("executions", batch))
    by_status = {_canonical_execution_status(execution): execution for execution in executions}
    assert {"passed", "failed", "blocked", "skipped"}.issubset(by_status), batch

    return {
        "project_id": project_id,
        "lib_id": lib_id,
        "document_id": document_id,
        "item_id": item_id,
        "case_ids": case_ids[:4],
        "round_id": round_id,
        "batch": batch,
        "executions": executions,
        "passed_execution_id": int(object_id(by_status["passed"], "id", "execution_id")),
        "failed_execution_id": int(object_id(by_status["failed"], "id", "execution_id")),
        "blocked_execution_id": int(object_id(by_status["blocked"], "id", "execution_id")),
        "skipped_execution_id": int(object_id(by_status["skipped"], "id", "execution_id")),
    }


def _create_round24_defect(client, context: dict, *, execution_key: str = "failed_execution_id") -> dict:
    execution_id = context[execution_key]
    created = data_of(
        client.post(
            f"{API_PREFIX}/executions/{execution_id}/create-defect",
            json={
                "title": "Round24 linked execution defect",
                "severity": "critical",
                "impact": "Checkout revenue flow can lose buyer cart state.",
                "retest_suggestion": "Retest payment rejection and cart persistence after the fix.",
                **_secret_payload(),
            },
            headers=_secret_headers(),
        )
    )
    _assert_no_sensitive_text(created)
    defect = created.get("defect") if isinstance(created.get("defect"), dict) else created
    defect_id = object_id(defect, "id", "defect_id")
    assert defect_id, created
    return {"created": created, "defect": defect, "defect_id": int(defect_id), "execution_id": execution_id}


def _seed_round24_defect_from_failed_execution(client, context: dict) -> dict:
    execution = post_json(
        client,
        f"{API_PREFIX}/executions",
        {
            "project_id": context["project_id"],
            "round_id": context["round_id"],
            "case_id": context["case_ids"][1],
            "executor_type": "manual",
            "status": "failed",
            "actual_result": "Round24 seeded defect evidence: payment failure clears cart.",
            "defect_title": "Round24 seeded payment failure defect",
            "create_defect": True,
        },
    )
    defects = data_of(client.get(f"{API_PREFIX}/defects", params={"projectId": context["project_id"], "page": 1, "pageSize": 20}))
    defect = next(
        (
            item
            for item in _records(defects)
            if str(item.get("execution_id")) == str(object_id(execution, "id", "execution_id"))
            or str(item.get("case_id")) == str(context["case_ids"][1])
        ),
        first_item(defects),
    )
    return {
        "execution": execution,
        "defect": defect,
        "defect_id": int(object_id(defect, "id", "defect_id")),
        "execution_id": int(object_id(execution, "id", "execution_id")),
    }


def test_round24_execution_records_cover_statuses_and_templates(client):
    context = _create_round24_context(client)
    batch_summary = context["batch"].get("summary")
    assert isinstance(batch_summary, dict), context["batch"]
    for key in ("total", "passed", "failed", "blocked", "skipped", "created_defects"):
        assert key in batch_summary, batch_summary
    assert batch_summary["total"] == 4, batch_summary
    assert batch_summary["passed"] == 1, batch_summary
    assert batch_summary["failed"] == 1, batch_summary
    assert batch_summary["blocked"] == 1, batch_summary
    assert batch_summary["skipped"] == 1, batch_summary
    assert batch_summary["created_defects"] == 0, batch_summary

    templates = data_of(client.get(f"{API_PREFIX}/executions/templates"))
    template_records = _template_records(templates)
    template_by_status = {item.get("status") or item.get("key"): item for item in template_records}
    for status in ("failed", "blocked", "skipped"):
        template = template_by_status.get(status)
        assert isinstance(template, dict), templates
        assert template.get("status") == status or template.get("key") == status, template
        assert template.get("required_fields") or template.get("fields") or template.get("default_payload"), template
        assert template.get("suggested_defect_fields") or template.get("defect_template") or template.get("template"), template


def test_defect_suggestion_for_failed_and_blocked_executions_is_rule_based_and_redacted(client):
    context = _create_round24_context(client)
    required_keys = {
        "title",
        "severity",
        "steps_to_reproduce",
        "expected_result",
        "actual_result",
        "impact",
        "retest_suggestion",
    }

    for execution_id in (context["failed_execution_id"], context["blocked_execution_id"]):
        suggestion = data_of(
            client.post(
                f"{API_PREFIX}/executions/{execution_id}/defect-suggestion",
                json={"include_case_context": True, **_secret_payload()},
                headers=_secret_headers(),
            )
        )
        assert required_keys.issubset(suggestion), suggestion
        assert suggestion["title"], suggestion
        assert suggestion["severity"] in {"critical", "high", "medium", "low", "normal", "blocker", "major", "minor"}, suggestion
        assert isinstance(suggestion["steps_to_reproduce"], list) and suggestion["steps_to_reproduce"], suggestion
        assert suggestion["expected_result"], suggestion
        assert suggestion["actual_result"], suggestion
        assert suggestion["impact"], suggestion
        assert suggestion["retest_suggestion"], suggestion
        assert suggestion.get("provider_call_performed") is False, suggestion
        assert suggestion.get("llm_provider_called") is False, suggestion
        _assert_no_sensitive_text(suggestion)


def test_create_defect_link_unlink_case_and_retest_reminder(client):
    context = _create_round24_context(client)
    created = _create_round24_defect(client, context)
    defect_id = created["defect_id"]

    history = data_of(client.get(f"{API_PREFIX}/executions/history", params={"projectId": context["project_id"], "page": 1, "pageSize": 20}))
    execution = next(
        (item for item in _records(history) if str(item.get("id") or item.get("execution_id")) == str(created["execution_id"])),
        {},
    )
    linked_in_create_response = created["created"].get("defect_id") or created["created"].get("defect")
    linked_in_execution = execution.get("defect_id") or execution.get("defect")
    assert linked_in_create_response or linked_in_execution, {"create_response": created["created"], "execution": execution}

    case_id = context["case_ids"][0]
    linked = data_of(
        client.post(
            f"{API_PREFIX}/defects/{defect_id}/link-case",
            json={"case_id": case_id, "reason": "Round24 verifies case-defect traceability.", **_secret_payload()},
            headers=_secret_headers(),
        )
    )
    assert str(case_id) in _payload_text(linked), linked
    _assert_no_sensitive_text(linked)

    unlinked = data_of(
        client.post(
            f"{API_PREFIX}/defects/{defect_id}/unlink-case",
            json={"case_id": case_id, "reason": "Round24 verifies traceability removal.", **_secret_payload()},
            headers=_secret_headers(),
        )
    )
    assert str(case_id) not in {str(item.get("id") or item.get("case_id")) for item in _records(unlinked)} or unlinked.get("linked") is False, unlinked
    _assert_no_sensitive_text(unlinked)

    reminder = data_of(
        client.post(
            f"{API_PREFIX}/defects/{defect_id}/retest-reminder",
            json={
                "assignee": "round24_qa",
                "days": 2,
                "message": f"Retest checkout closure. token={ROUND24_SECRET}",
                **_secret_payload(),
            },
            headers=_secret_headers(),
        )
    )
    assert {"due_at", "assignee", "message"}.issubset(reminder), reminder
    assert reminder["assignee"] == "round24_qa", reminder
    assert reminder["due_at"], reminder
    assert reminder["message"], reminder
    _assert_no_sensitive_text(reminder)


def test_project_execution_trend_aggregates_execution_and_defect_facts(client):
    context = _create_round24_context(client)
    _seed_round24_defect_from_failed_execution(client, context)

    trend = data_of(client.get(f"{API_PREFIX}/projects/{context['project_id']}/execution-trend"))
    trend_rows = _records(trend)
    assert trend_rows, trend
    aggregate_row = next((row for row in trend_rows if row.get("total", 0) >= 4), None)
    assert aggregate_row is not None, trend
    for key in ("passed", "failed", "blocked", "total", "pass_rate"):
        assert key in aggregate_row, aggregate_row
    assert aggregate_row["passed"] >= 1, aggregate_row
    assert aggregate_row["failed"] >= 1, aggregate_row
    assert aggregate_row["blocked"] >= 1, aggregate_row
    assert aggregate_row["total"] >= 4, aggregate_row
    assert 0 <= aggregate_row["pass_rate"] <= 100, aggregate_row
    assert aggregate_row.get("defects", aggregate_row.get("defect_count", 0)) >= 1, aggregate_row


def test_project_defect_loop_summary_reports_closure_linkage_and_top_failed_cases(client):
    context = _create_round24_context(client)
    _seed_round24_defect_from_failed_execution(client, context)

    summary = data_of(client.get(f"{API_PREFIX}/projects/{context['project_id']}/defect-loop-summary"))
    for key in ("open", "closed", "by_severity", "retest_due", "linked", "unlinked", "top_failed_cases"):
        assert key in summary, summary
    assert summary["open"] >= 1, summary
    assert isinstance(summary["closed"], int), summary
    assert isinstance(summary["by_severity"], dict) and summary["by_severity"], summary
    assert isinstance(summary["retest_due"], int), summary
    assert summary["linked"] >= 1, summary
    assert isinstance(summary["unlinked"], int), summary
    top_failed_cases = _records(summary["top_failed_cases"])
    assert any(str(item.get("case_id") or item.get("id")) == str(context["case_ids"][1]) for item in top_failed_cases), summary


def test_execution_statistics_exposes_round24_enhanced_metrics(client):
    context = _create_round24_context(client)
    _seed_round24_defect_from_failed_execution(client, context)

    statistics = data_of(client.get(f"{API_PREFIX}/executions/statistics", params={"projectId": context["project_id"]}))
    for key in ("pass_rate", "open_defects", "retest_due", "recent_trend"):
        assert key in statistics, statistics
    assert 0 <= statistics["pass_rate"] <= 100, statistics
    assert statistics["open_defects"] >= 1, statistics
    assert isinstance(statistics["retest_due"], int), statistics
    assert isinstance(statistics["recent_trend"], list), statistics


def test_defect_filters_patch_and_copy_text_contracts(client):
    context = _create_round24_context(client)
    created = _seed_round24_defect_from_failed_execution(client, context)
    defect_id = created["defect_id"]
    case_id = context["case_ids"][1]

    patched = data_of(
        client.patch(
            f"{API_PREFIX}/defects/{defect_id}",
            json={"status": "open", "severity": "critical", "remark": "Round24 filter setup.", **_secret_payload()},
            headers=_secret_headers(),
        )
    )
    assert patched["status"] == "open", patched
    assert patched["severity"] == "critical", patched
    _assert_no_sensitive_text(patched)

    by_status = data_of(client.get(f"{API_PREFIX}/defects", params={"projectId": context["project_id"], "status": "open"}))
    assert any(str(item.get("id") or item.get("defect_id")) == str(defect_id) for item in _records(by_status)), by_status

    by_severity = data_of(client.get(f"{API_PREFIX}/defects", params={"projectId": context["project_id"], "severity": "critical"}))
    assert any(str(item.get("id") or item.get("defect_id")) == str(defect_id) for item in _records(by_severity)), by_severity

    by_case = data_of(client.get(f"{API_PREFIX}/defects", params={"projectId": context["project_id"], "caseId": case_id}))
    assert any(str(item.get("id") or item.get("defect_id")) == str(defect_id) for item in _records(by_case)), by_case

    closed = data_of(
        client.patch(
            f"{API_PREFIX}/defects/{defect_id}",
            json={"status": "closed", "severity": "high", "remark": "Round24 retest passed."},
        )
    )
    assert closed["status"] == "closed", closed
    assert closed["severity"] == "high", closed

    copy_text = data_of(client.get(f"{API_PREFIX}/defects/{defect_id}/copy-text", headers=_secret_headers()))
    text = copy_text.get("text") if isinstance(copy_text, dict) else str(copy_text)
    lowered = text.lower()
    for phrase in ("\u590d\u73b0", "\u5b9e\u9645", "\u9884\u671f", "\u590d\u6d4b\u5efa\u8bae"):
        assert phrase in text, text
    assert "round24" in lowered, text
    _assert_no_sensitive_text(copy_text)


def test_batch_summary_counts_created_defects_and_defect_creation_failures_do_not_500(client):
    context = _create_round24_context(client)
    response = client.post(
        f"{API_PREFIX}/executions/batch",
        json={
            "project_id": context["project_id"],
            "round_id": context["round_id"],
            "executor_type": "manual",
            "executions": [
                {
                    "case_id": context["case_ids"][0],
                    "status": "passed",
                    "actual_result": "Second pass execution remains green.",
                    "create_defect": False,
                },
                {
                    "case_id": context["case_ids"][1],
                    "status": "failed",
                    "actual_result": "Payment failure still clears cart.",
                    "create_defect": True,
                    "defect_title": "Round24 batch creates failed execution defect",
                },
                {
                    "case_id": context["case_ids"][2],
                    "status": "blocked",
                    "actual_result": "Inventory outage blocks execution.",
                    "create_defect": True,
                    "defect": {"title": "", "severity": "invalid", "token": ROUND24_SECRET},
                },
                {
                    "case_id": context["case_ids"][3],
                    "status": "skipped",
                    "actual_result": "Skipped optional coupon validation.",
                    "create_defect": False,
                },
            ],
            **_secret_payload(),
        },
        headers=_secret_headers(),
    )
    assert response.status_code != 500, response.text
    payload = assert_response_envelope(response)
    _assert_no_sensitive_text(payload)
    batch = payload["data"]
    summary = batch.get("summary")
    assert isinstance(summary, dict), batch
    expected = {
        "total": 4,
        "passed": 1,
        "failed": 1,
        "blocked": 1,
        "skipped": 1,
    }
    for key, value in expected.items():
        assert summary.get(key) == value, summary
    _assert_count(summary, "created_defects", minimum=1)

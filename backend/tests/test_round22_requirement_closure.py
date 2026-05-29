from __future__ import annotations

import json
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from aitest_platform.db.session import session_scope
from aitest_platform.models import RequirementDocumentBlock, RequirementItem, RequirementLib
from conftest import API_PREFIX, data_of, object_id, post_json


pytestmark = pytest.mark.contract

ROUND22_SECRET = "sk-round22-secret"


def _records(value):
    if isinstance(value, dict):
        for key in ("list", "items", "records", "results", "data", "blocks", "children", "test_points", "test_cases"):
            nested = value.get(key)
            if isinstance(nested, list):
                return nested
    if isinstance(value, list):
        return value
    pytest.fail(f"Expected list-like payload, got: {value!r}", pytrace=False)


def _assert_no_sensitive_text(payload) -> None:
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    lowered = text.lower()
    assert ROUND22_SECRET.lower() not in lowered, text
    for marker in ("authorization", "cookie", "token"):
        assert marker not in lowered, text


def _create_round22_context(client, *, raw_content: str | None = None) -> dict[str, int]:
    marker = uuid4().hex[:10]
    project = post_json(
        client,
        f"{API_PREFIX}/projects",
        {
            "code": f"round22-{marker}",
            "name": f"Round22 Requirement Closure {marker}",
            "description": "R22 contract test project.",
            "owner_name": "round22_qa_contract",
        },
    )
    project_id = int(object_id(project, "id", "project_id"))

    lib = post_json(
        client,
        f"{API_PREFIX}/projects/{project_id}/requirement-libs",
        {
            "name": f"Round22 Requirement Library {marker}",
            "description": "Library for markdown parsing and confirmation closure.",
        },
    )
    lib_id = int(object_id(lib, "id", "lib_id"))

    document = post_json(
        client,
        f"{API_PREFIX}/projects/{project_id}/requirement-documents",
        {
            "lib_id": lib_id,
            "document_number": f"REQ-R22-{marker}",
            "name": f"Checkout Markdown Requirement {marker}",
            "source_type": "markdown",
            "source_file_name": f"round22-{marker}.md",
            "raw_content": raw_content or _round22_markdown_content(),
        },
    )
    document_id = int(object_id(document, "id", "document_id"))
    return {"project_id": project_id, "lib_id": lib_id, "document_id": document_id}


def _round22_markdown_content() -> str:
    return "\n".join(
        [
            "# Checkout",
            "",
            "The checkout flow must support authenticated buyers placing orders.",
            "",
            "## Cart Validation",
            "",
            "- Buyers cannot submit an empty cart.",
            "- Each selected item must be in stock before payment starts.",
            "",
            "## Payment",
            "",
            "The system must authorize a selected payment method and persist the payment intent.",
            "",
            "### Failure Handling",
            "",
            "If authorization fails, the order stays unpaid and the buyer can retry with another method.",
            "",
            "## Notification",
            "",
            "- A successful order sends an email receipt.",
            "- The receipt includes order number, total amount, and payment status.",
        ]
    )


def _parse_document(client, document_id: int) -> dict:
    return post_json(
        client,
        f"{API_PREFIX}/requirement-documents/{document_id}/parse",
        {"parse_mode": "standard", "preserve_line_numbers": True},
    )


def _extract_items(client, document_id: int) -> dict:
    return post_json(
        client,
        f"{API_PREFIX}/requirement-documents/{document_id}/extract-items",
        {"mode": "standard", "include_source_anchors": True, "min_items": 3},
    )


def _list_items_for_document(client, document_id: int) -> list[dict]:
    return _records(data_of(client.get(f"{API_PREFIX}/requirement-documents/{document_id}/requirement-items", params={"page": 1, "pageSize": 50})))


def _list_items_for_lib(client, lib_id: int) -> list[dict]:
    return _records(data_of(client.get(f"{API_PREFIX}/requirement-libs/{lib_id}/requirement-items", params={"page": 1, "pageSize": 50})))


def _require_db_item(item_id: int) -> dict:
    assert isinstance(item_id, int), f"Expected DB integer id, got {item_id!r}"
    with session_scope() as session:
        item = session.get(RequirementItem, item_id)
        assert item is not None and not item.is_deleted, f"RequirementItem({item_id}) was not persisted in DB"
        return {
            "id": item.id,
            "lib_id": item.lib_id,
            "document_id": item.document_id,
            "title": item.title,
            "status": item.status,
            "version": item.version,
            "granularity_flag": item.granularity_flag,
            "source_anchor_ids": item.source_anchor_ids or [],
        }


def _create_parsed_items(client) -> dict:
    context = _create_round22_context(client)
    parse_data = _parse_document(client, context["document_id"])
    blocks = _records(parse_data.get("blocks", []))
    assert len(blocks) >= 4, parse_data
    extract_data = _extract_items(client, context["document_id"])
    items = _records(extract_data.get("items", extract_data))
    assert len(items) >= 3, extract_data
    context["block_keys"] = [block["block_key"] for block in blocks]
    context["item_ids"] = [int(object_id(item, "id", "item_id")) for item in items]
    return context


def test_markdown_parse_creates_stable_line_mapped_blocks_without_duplication(client):
    context = _create_round22_context(client)
    document_id = context["document_id"]

    first_parse = _parse_document(client, document_id)
    first_blocks = _records(first_parse.get("blocks", []))

    assert len(first_blocks) >= 4, first_parse
    first_keys = [block.get("block_key") for block in first_blocks]
    assert len(first_keys) == len(set(first_keys))
    assert all(isinstance(key, str) and key for key in first_keys)

    for block in first_blocks:
        assert block.get("section_path"), block
        metadata = block.get("metadata_json")
        assert isinstance(metadata, dict), block
        assert isinstance(metadata.get("line_start"), int), block
        assert isinstance(metadata.get("line_end"), int), block
        assert metadata["line_start"] <= metadata["line_end"], block

    section_paths = {block["section_path"] for block in first_blocks}
    assert any("Checkout" in path for path in section_paths)
    assert any("Payment" in path for path in section_paths)

    second_parse = _parse_document(client, document_id)
    second_blocks = _records(second_parse.get("blocks", []))
    assert [block.get("block_key") for block in second_blocks] == first_keys
    assert len(second_blocks) == len(first_blocks), second_parse

    listed_blocks = _records(data_of(client.get(f"{API_PREFIX}/requirement-documents/{document_id}/blocks", params={"page": 1, "pageSize": 50})))
    assert [block.get("block_key") for block in listed_blocks] == first_keys

    with session_scope() as session:
        db_count = session.scalar(
            select(func.count())
            .select_from(RequirementDocumentBlock)
            .where(RequirementDocumentBlock.document_id == document_id)
        )
    assert db_count == len(first_blocks)


def test_extract_items_persists_multiple_anchor_backed_items_readable_by_document_and_lib(client):
    context = _create_parsed_items(client)
    document_id = context["document_id"]
    lib_id = context["lib_id"]
    block_keys = set(context["block_keys"])

    document_items = _list_items_for_document(client, document_id)
    lib_items = _list_items_for_lib(client, lib_id)
    document_item_ids = {int(object_id(item, "id", "item_id")) for item in document_items}
    lib_item_ids = {int(object_id(item, "id", "item_id")) for item in lib_items}

    assert set(context["item_ids"]).issubset(document_item_ids)
    assert set(context["item_ids"]).issubset(lib_item_ids)

    for item in document_items:
        if int(object_id(item, "id", "item_id")) not in context["item_ids"]:
            continue
        anchors = item.get("source_anchor_ids")
        assert isinstance(anchors, list) and anchors, item
        assert set(anchors).issubset(block_keys), item
        assert isinstance(item.get("granularity_flag"), str) and item["granularity_flag"], item


def test_requirement_item_edit_confirm_and_shelve_close_status_loop(client):
    context = _create_parsed_items(client)
    item_id = context["item_ids"][0]
    before = _require_db_item(item_id)

    edited = data_of(
        client.patch(
            f"{API_PREFIX}/requirement-items/{item_id}",
            json={
                "title": "R22 Edited Checkout Payment Authorization",
                "summary": "Buyer payment authorization must be retryable and auditable.",
                "module": "checkout",
                "priority": "P1",
            },
        )
    )

    assert edited["title"] == "R22 Edited Checkout Payment Authorization"
    assert edited["summary"] == "Buyer payment authorization must be retryable and auditable."
    assert edited["module"] == "checkout"
    assert edited["priority"] == "P1"
    assert edited["version"] == before["version"] + 1

    confirmed = post_json(client, f"{API_PREFIX}/requirement-items/{item_id}/confirm")
    assert confirmed["status"] == "confirmed"
    assert confirmed["version"] == edited["version"] + 1

    shelved = post_json(
        client,
        f"{API_PREFIX}/requirement-items/{item_id}/shelve",
        {"reason": "Duplicate candidate after stakeholder review."},
    )
    assert shelved["status"] == "shelved"
    assert _require_db_item(item_id)["status"] == "shelved"


def test_split_and_merge_use_database_items_and_preserve_source_relations(client):
    context = _create_parsed_items(client)
    source_id, merge_peer_id = context["item_ids"][:2]
    source = _require_db_item(source_id)

    split_data = post_json(
        client,
        f"{API_PREFIX}/requirement-items/{source_id}/split",
        {
            "children": [
                {"title": "R22 split child - validation", "summary": "Validate cart before payment."},
                {"title": "R22 split child - retry", "summary": "Allow retry after payment failure."},
            ],
            "reason": "Split compound checkout requirement into atomic child items.",
        },
    )
    children = _records(split_data.get("children", split_data))
    assert len(children) >= 2, split_data

    child_ids = [object_id(child, "id", "item_id") for child in children]
    assert all(isinstance(child_id, int) for child_id in child_ids), split_data
    for child_id in child_ids:
        child = _require_db_item(child_id)
        assert child["lib_id"] == source["lib_id"]
        assert child["document_id"] == source["document_id"]
        assert set(source["source_anchor_ids"]).issubset(set(child["source_anchor_ids"])), child

    merge_data = post_json(
        client,
        f"{API_PREFIX}/requirement-items/merge",
        {
            "item_ids": [child_ids[0], merge_peer_id],
            "title": "R22 merged checkout validation and notification",
            "reason": "Merge overlapping stakeholder wording into a single canonical item.",
        },
    )
    merged = merge_data.get("merged") if isinstance(merge_data, dict) else merge_data
    merged_id = object_id(merged, "id", "item_id")
    assert isinstance(merged_id, int), merge_data
    merged_db = _require_db_item(merged_id)
    assert merged_db["status"] in {"draft", "confirmed"}
    assert set(source["source_anchor_ids"]).intersection(set(merged_db["source_anchor_ids"])), merged_db

    source_after_merge = [_require_db_item(child_ids[0]), _require_db_item(merge_peer_id)]
    relation_payload = json.dumps(merge_data, ensure_ascii=False, sort_keys=True, default=str)
    relation_mentions_sources = all(str(item_id) in relation_payload for item_id in (child_ids[0], merge_peer_id))
    assert all(item["status"] == "merged" for item in source_after_merge) or relation_mentions_sources


def test_quality_check_reports_actionable_result_and_updates_granularity_flag(client):
    context = _create_parsed_items(client)
    item_id = context["item_ids"][0]

    quality = post_json(
        client,
        f"{API_PREFIX}/requirement-items/{item_id}/quality-check",
        {"dimensions": ["clarity", "atomicity", "testability", "traceability"]},
    )

    assert isinstance(quality.get("score"), (int, float)), quality
    assert 0 <= quality["score"] <= 100, quality
    assert isinstance(quality.get("issues"), list), quality
    assert isinstance(quality.get("suggested_actions"), list), quality
    assert isinstance(quality.get("source_anchors"), list) and quality["source_anchors"], quality
    assert isinstance(quality.get("granularity_flag"), str) and quality["granularity_flag"], quality
    assert _require_db_item(item_id)["granularity_flag"] == quality["granularity_flag"]


def test_brain_analysis_and_traceability_use_db_blocks_items_and_persist_summary(client):
    context = _create_parsed_items(client)
    lib_id = context["lib_id"]
    item_id = context["item_ids"][0]

    brain = post_json(client, f"{API_PREFIX}/requirement-libs/{lib_id}/brain/analyze")
    assert brain.get("summary") or brain.get("brain", {}).get("summary"), brain
    assert brain.get("items") or brain.get("requirement_items") or brain.get("brain", {}).get("items"), brain
    assert brain.get("source_blocks") or brain.get("blocks") or brain.get("brain", {}).get("source_blocks"), brain

    brain_readback = data_of(client.get(f"{API_PREFIX}/requirement-libs/{lib_id}/brain"))
    assert brain_readback, brain_readback
    with session_scope() as session:
        lib = session.get(RequirementLib, lib_id)
        assert lib is not None
        assert isinstance(lib.brain_summary, dict) and lib.brain_summary, lib.brain_summary

    post_json(client, f"{API_PREFIX}/requirement-items/{item_id}/generate-test-points", {"mode": "standard"})
    post_json(client, f"{API_PREFIX}/requirement-items/{item_id}/generate-test-cases", {"mode": "standard"})
    traceability = post_json(client, f"{API_PREFIX}/requirement-items/{item_id}/traceability/refresh")

    assert isinstance(traceability.get("source_blocks"), list) and traceability["source_blocks"], traceability
    assert isinstance(traceability.get("coverage"), dict), traceability
    assert isinstance(traceability["coverage"].get("coverage_rate"), (int, float)), traceability
    assert isinstance(traceability.get("test_points"), list) and traceability["test_points"], traceability
    assert isinstance(traceability.get("test_cases"), list) and traceability["test_cases"], traceability


def test_requirement_closure_responses_redact_secret_tokens_and_auth_headers(client):
    context = _create_round22_context(client)
    document_id = context["document_id"]
    headers = {
        "Authorization": f"Bearer {ROUND22_SECRET}",
        "Cookie": f"session={ROUND22_SECRET}",
    }

    parse_response = client.post(
        f"{API_PREFIX}/requirement-documents/{document_id}/parse",
        headers=headers,
        json={
            "parse_mode": "standard",
            "token": ROUND22_SECRET,
            "notes": f"Authorization: Bearer {ROUND22_SECRET}; cookie={ROUND22_SECRET}; token={ROUND22_SECRET}",
        },
    )
    assert parse_response.status_code in {200, 201}, parse_response.text
    _assert_no_sensitive_text(parse_response.text)

    extract_response = client.post(
        f"{API_PREFIX}/requirement-documents/{document_id}/extract-items",
        headers=headers,
        json={
            "mode": "standard",
            "include_source_anchors": True,
            "cookie": ROUND22_SECRET,
            "nested": {"Authorization": f"Bearer {ROUND22_SECRET}", "access_token": ROUND22_SECRET},
        },
    )
    assert extract_response.status_code in {200, 201}, extract_response.text
    _assert_no_sensitive_text(extract_response.text)

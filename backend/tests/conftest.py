from __future__ import annotations

import importlib
from collections.abc import Iterable
from typing import Any

import pytest
from fastapi.testclient import TestClient


API_PREFIX = "/api/v2"
SUCCESS_CODES = {0, 200}


@pytest.fixture(scope="session")
def app():
    try:
        module = importlib.import_module("aitest_platform.main")
    except ModuleNotFoundError:
        pytest.fail(
            "Cannot import aitest_platform.main. "
            "API worker must provide backend/aitest_platform/main.py with a FastAPI app.",
            pytrace=False,
        )

    application = getattr(module, "app", None)
    if application is None:
        pytest.fail("aitest_platform.main must expose a FastAPI instance named app.", pytrace=False)
    return application


@pytest.fixture()
def client(app):
    with TestClient(app) as test_client:
        yield test_client


def assert_response_envelope(response, *, allow_created: bool = True) -> dict[str, Any]:
    expected_statuses = {200}
    if allow_created:
        expected_statuses.add(201)

    assert response.status_code in expected_statuses, response.text
    payload = response.json()
    assert isinstance(payload, dict), payload

    missing = {"code", "message", "data"} - payload.keys()
    assert not missing, f"Unified response envelope is missing keys: {sorted(missing)}"
    assert payload["code"] in SUCCESS_CODES, payload
    assert isinstance(payload["message"], str) and payload["message"], payload
    assert "trace_id" in payload or "timestamp" in payload, payload
    return payload


def data_of(response) -> Any:
    return assert_response_envelope(response)["data"]


def first_item(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        for key in ("list", "items", "records", "results", "data"):
            nested = value.get(key)
            if isinstance(nested, list) and nested:
                assert isinstance(nested[0], dict), nested[0]
                return nested[0]
        if "id" in value:
            return value
    if isinstance(value, list) and value:
        assert isinstance(value[0], dict), value[0]
        return value[0]
    pytest.fail(f"Expected a non-empty list-like response or object with id, got: {value!r}", pytrace=False)


def object_id(value: Any, *preferred_keys: str) -> Any:
    candidate = first_item(value) if isinstance(value, (list, dict)) and "id" not in value else value
    if not isinstance(candidate, dict):
        pytest.fail(f"Expected object response with an id, got: {candidate!r}", pytrace=False)

    keys: Iterable[str] = preferred_keys or ("id",)
    for key in (*keys, "id", "project_id", "lib_id", "document_id", "item_id", "case_id", "report_id", "backup_id"):
        if candidate.get(key) is not None:
            return candidate[key]
    pytest.fail(f"Response object does not contain an id-like key: {candidate!r}", pytrace=False)


def post_json(client: TestClient, path: str, payload: dict[str, Any] | None = None) -> Any:
    return data_of(client.post(path, json=payload or {}))

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import text

from aitest_platform.services.api_runner import sanitize_api_payload


MOCK_RESOURCE_TYPE = "api_mock"


def create_api_mock(session: Any, lib: Any, payload: dict[str, Any]) -> dict[str, Any]:
    _ensure_table(session)
    data = _normalize_mock_payload(payload)
    timestamp = _now_iso(session)
    result = session.execute(
        text(
            """
            INSERT INTO round2_resource(resource_type, project_id, parent_type, parent_id, name, payload_json, created_at, updated_at)
            VALUES (:resource_type, :project_id, :parent_type, :parent_id, :name, :payload_json, :created_at, :updated_at)
            """
        ),
        {
            "resource_type": MOCK_RESOURCE_TYPE,
            "project_id": getattr(lib, "project_id", None),
            "parent_type": "lib_id",
            "parent_id": str(getattr(lib, "id")),
            "name": data.get("name"),
            "payload_json": json.dumps(data, ensure_ascii=False),
            "created_at": timestamp,
            "updated_at": timestamp,
        },
    )
    row = session.execute(text("SELECT * FROM round2_resource WHERE id = :id"), {"id": result.lastrowid}).mappings().one()
    return _decode(row)


def list_api_mocks(session: Any, lib_id: int, page_num: int = 1, page_size: int = 20) -> dict[str, Any]:
    _ensure_table(session)
    total = session.scalar(
        text(
            """
            SELECT COUNT(*)
            FROM round2_resource
            WHERE resource_type = :resource_type AND parent_type = 'lib_id' AND parent_id = :lib_id AND is_deleted = 0
            """
        ),
        {"resource_type": MOCK_RESOURCE_TYPE, "lib_id": str(lib_id)},
    ) or 0
    rows = session.execute(
        text(
            """
            SELECT *
            FROM round2_resource
            WHERE resource_type = :resource_type AND parent_type = 'lib_id' AND parent_id = :lib_id AND is_deleted = 0
            ORDER BY id DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {
            "resource_type": MOCK_RESOURCE_TYPE,
            "lib_id": str(lib_id),
            "limit": int(page_size),
            "offset": (int(page_num) - 1) * int(page_size),
        },
    ).mappings()
    items = [_decode(row) for row in rows]
    return {"list": items, "total": total, "page": page_num, "pageSize": page_size}


def dispatch_api_mock(session: Any, payload: dict[str, Any]) -> dict[str, Any]:
    _ensure_table(session)
    method = str(payload.get("method") or "GET").upper()
    path = _normalize_path(payload.get("path") or payload.get("url") or "/")
    rows = session.execute(
        text(
            """
            SELECT *
            FROM round2_resource
            WHERE resource_type = :resource_type AND is_deleted = 0
            ORDER BY id DESC
            """
        ),
        {"resource_type": MOCK_RESOURCE_TYPE},
    ).mappings()
    lib_id = payload.get("lib_id") or payload.get("libId")
    for row in rows:
        if lib_id is not None and str(row.parent_id) != str(lib_id):
            continue
        mock = _decode(row)
        if not mock.get("enabled", True):
            continue
        if str(mock.get("method") or "GET").upper() == method and _normalize_path(mock.get("path") or "/") == path and _mock_matches(mock, payload):
            response = mock.get("response") if isinstance(mock.get("response"), dict) else {}
            status_code = response.get("status_code") if "status_code" in response else response.get("statusCode")
            headers = response.get("headers") if "headers" in response else mock.get("headers")
            body = response.get("body") if "body" in response else mock.get("body")
            return sanitize_api_payload(
                {
                    "matched": True,
                    "mock_id": mock["id"],
                    "rule_id": mock["id"],
                    "lib_id": mock.get("lib_id") or mock.get("parent_id"),
                    "method": method,
                    "path": path,
                    "status_code": int(status_code or mock.get("status_code") or 200),
                    "headers": headers or {},
                    "body": body,
                    "response": {
                        "status_code": int(status_code or mock.get("status_code") or 200),
                        "headers": headers or {},
                        "body": body,
                    },
                }
            )
    return sanitize_api_payload(
        {
            "matched": False,
            "method": method,
            "path": path,
            "status_code": 404,
            "error": {"code": "mock_not_found", "message": "No enabled API mock matched the request."},
        }
    )


def _ensure_table(session: Any) -> None:
    session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS round2_resource (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                resource_type TEXT NOT NULL,
                project_id INTEGER,
                parent_type TEXT,
                parent_id TEXT,
                name TEXT,
                payload_json TEXT NOT NULL,
                is_deleted INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
    )
    session.execute(text("CREATE INDEX IF NOT EXISTS idx_round2_resource_type_parent ON round2_resource(resource_type, parent_id, is_deleted)"))
    session.execute(text("CREATE INDEX IF NOT EXISTS idx_round2_resource_project ON round2_resource(project_id, resource_type, is_deleted)"))


def _normalize_mock_payload(payload: dict[str, Any]) -> dict[str, Any]:
    method = str(payload.get("method") or "GET").upper()
    path = _normalize_path(payload.get("path") or payload.get("url") or "/")
    response = payload.get("response") if isinstance(payload.get("response"), dict) else {}
    try:
        status_code = int(response.get("status_code") or response.get("statusCode") or payload.get("status_code") or payload.get("statusCode") or 200)
    except (TypeError, ValueError):
        status_code = 200
    headers = response.get("headers") if "headers" in response else payload.get("headers")
    body = response.get("body") if "body" in response else payload.get("body")
    return sanitize_api_payload(
        {
            "name": payload.get("name") or f"{method} {path}",
            "method": method,
            "path": path,
            "priority": int(payload.get("priority", 0) or 0),
            "match": payload.get("match") or {},
            "status_code": status_code,
            "headers": headers or {},
            "body": body,
            "response": {"status_code": status_code, "headers": headers or {}, "body": body},
            "enabled": bool(payload.get("enabled", True)),
        }
    )


def _mock_matches(mock: dict[str, Any], payload: dict[str, Any]) -> bool:
    match = mock.get("match") if isinstance(mock.get("match"), dict) else {}
    for key in ("query", "headers", "body"):
        expected = match.get(key)
        if not isinstance(expected, dict) or not expected:
            continue
        actual = payload.get(key) if isinstance(payload.get(key), dict) else {}
        if key == "headers":
            actual_lower = {str(header_key).lower(): value for header_key, value in actual.items()}
            for expected_key, expected_value in expected.items():
                if actual_lower.get(str(expected_key).lower()) != expected_value:
                    return False
        else:
            for expected_key, expected_value in expected.items():
                if actual.get(expected_key) != expected_value:
                    return False
    return True


def _normalize_path(value: Any) -> str:
    text_value = str(value or "/").strip() or "/"
    parsed = urlparse(text_value)
    path = parsed.path if parsed.scheme or parsed.netloc else text_value.split("?", 1)[0]
    if not path.startswith("/"):
        path = "/" + path.strip("/")
    return path or "/"


def _decode(row: Any) -> dict[str, Any]:
    data = json.loads(row.payload_json or "{}")
    data.update(
        {
            "id": str(row.id),
            "project_id": row.project_id if row.project_id is not None else data.get("project_id"),
            "lib_id": row.parent_id,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
    )
    return sanitize_api_payload(data)


def _now_iso(session: Any) -> str:
    value = session.execute(text("SELECT CURRENT_TIMESTAMP")).scalar()
    return str(value)

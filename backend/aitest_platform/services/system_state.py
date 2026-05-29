from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from aitest_platform.models import (
    ApiEndpoint,
    ApiEnvironment,
    ApiSchedule,
    ApiTestCase,
    ApiTestLib,
    AutoCaseFile,
    AutoProject,
    PerfPlan,
    Project,
    RequirementItem,
    RequirementLib,
    TestCase,
)

SENSITIVE_MARKERS = ("authorization", "api_key", "api-key", "apikey", "token", "cookie", "password", "secret", "git_auth")

RECYCLE_MODELS: dict[str, type[Any]] = {
    "projects": Project,
    "requirement_libs": RequirementLib,
    "requirement_items": RequirementItem,
    "test_cases": TestCase,
    "api_test_libs": ApiTestLib,
    "api_endpoints": ApiEndpoint,
    "api_test_cases": ApiTestCase,
    "api_environments": ApiEnvironment,
    "api_schedules": ApiSchedule,
    "auto_projects": AutoProject,
    "auto_case_files": AutoCaseFile,
    "perf_plans": PerfPlan,
}


class SystemStateError(ValueError):
    pass


def list_db_recycle_items(session: Session) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for resource_type, model in RECYCLE_MODELS.items():
        rows = list(session.scalars(select(model).where(model.is_deleted.is_(True)).order_by(model.id.desc()).limit(200)))
        for row in rows:
            record = _public_model_dict(row)
            title = record.get("name") or record.get("title") or record.get("case_number") or record.get("path") or str(row.id)
            items.append(
                {
                    "id": f"{resource_type}:{row.id}",
                    "recycle_id": f"{resource_type}:{row.id}",
                    "record_id": row.id,
                    "type": resource_type,
                    "title": title,
                    "record": record,
                    "deleted": True,
                }
            )
    return items


def restore_db_recycle_item(session: Session, recycle_id: str) -> dict[str, Any]:
    if ":" not in recycle_id:
        raise SystemStateError("recycle id must use type:id format")
    resource_type, raw_id = recycle_id.split(":", 1)
    model = RECYCLE_MODELS.get(resource_type)
    if model is None:
        raise SystemStateError(f"unsupported recycle type: {resource_type}")
    try:
        item_id = int(raw_id)
    except ValueError as exc:
        raise SystemStateError("recycle record id must be an integer") from exc
    item = session.get(model, item_id)
    if item is None:
        raise SystemStateError(f"{resource_type}({item_id}) not found")
    item.is_deleted = False
    session.flush()
    return {"restored": True, "id": recycle_id, "type": resource_type, "record": _public_model_dict(item)}


def list_preferences(session: Session) -> dict[str, Any]:
    _ensure_resource_table(session)
    rows = session.execute(
        text(
            """
            SELECT *
            FROM round2_resource
            WHERE resource_type = 'user_preference' AND is_deleted = 0
            ORDER BY name ASC
            """
        )
    )
    preferences = [_decode_resource(row) for row in rows]
    return {"list": preferences, "total": len(preferences)}


def get_preference(session: Session, key: str) -> dict[str, Any]:
    _ensure_resource_table(session)
    row = session.execute(
        text(
            """
            SELECT *
            FROM round2_resource
            WHERE resource_type = 'user_preference' AND name = :name AND is_deleted = 0
            ORDER BY id DESC
            LIMIT 1
            """
        ),
        {"name": key},
    ).first()
    if row is None:
        raise SystemStateError(f"preference({key}) not found")
    return _decode_resource(row)


def save_preference(session: Session, key: str, value: Any) -> dict[str, Any]:
    if not key.strip():
        raise SystemStateError("preference key is required")
    _ensure_resource_table(session)
    now = _now_iso()
    payload = {"key": key, "value": sanitize_system_payload(value)}
    existing = session.execute(
        text(
            """
            SELECT id
            FROM round2_resource
            WHERE resource_type = 'user_preference' AND name = :name AND is_deleted = 0
            ORDER BY id DESC
            LIMIT 1
            """
        ),
        {"name": key},
    ).first()
    if existing:
        session.execute(
            text(
                """
                UPDATE round2_resource
                SET payload_json = :payload, updated_at = :updated_at
                WHERE id = :id
                """
            ),
            {"id": existing.id, "payload": json.dumps(payload, ensure_ascii=False), "updated_at": now},
        )
        resource_id = existing.id
    else:
        result = session.execute(
            text(
                """
                INSERT INTO round2_resource(resource_type, project_id, parent_type, parent_id, name, payload_json, is_deleted, created_at, updated_at)
                VALUES('user_preference', NULL, NULL, NULL, :name, :payload, 0, :created_at, :updated_at)
                """
            ),
            {"name": key, "payload": json.dumps(payload, ensure_ascii=False), "created_at": now, "updated_at": now},
        )
        resource_id = result.lastrowid
    return {"id": str(resource_id), **payload, "updated_at": now}


def record_recent_activity(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    _ensure_resource_table(session)
    now = _now_iso()
    clean = sanitize_system_payload(payload)
    title = clean.get("title") or clean.get("name") or clean.get("route") or "recent activity"
    result = session.execute(
        text(
            """
            INSERT INTO round2_resource(resource_type, project_id, parent_type, parent_id, name, payload_json, is_deleted, created_at, updated_at)
            VALUES('recent_activity', :project_id, :parent_type, :parent_id, :name, :payload, 0, :created_at, :updated_at)
            """
        ),
        {
            "project_id": clean.get("project_id"),
            "parent_type": clean.get("target_type"),
            "parent_id": str(clean.get("target_id")) if clean.get("target_id") is not None else None,
            "name": str(title),
            "payload": json.dumps(clean, ensure_ascii=False),
            "created_at": now,
            "updated_at": now,
        },
    )
    return {"id": str(result.lastrowid), "created_at": now, **clean}


def list_recent_activities(session: Session, project_id: int | None = None, limit: int = 20) -> dict[str, Any]:
    _ensure_resource_table(session)
    criteria = "resource_type = 'recent_activity' AND is_deleted = 0"
    params: dict[str, Any] = {"limit": max(1, min(int(limit or 20), 100))}
    if project_id is not None:
        criteria += " AND project_id = :project_id"
        params["project_id"] = project_id
    rows = session.execute(
        text(
            f"""
            SELECT *
            FROM round2_resource
            WHERE {criteria}
            ORDER BY id DESC
            LIMIT :limit
            """
        ),
        params,
    )
    activities = [_decode_resource(row) for row in rows]
    return {"list": activities, "total": len(activities)}


def sanitize_system_payload(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            if _is_sensitive_key(str(key)):
                continue
            clean[key] = sanitize_system_payload(item)
        return clean
    if isinstance(value, list):
        return [sanitize_system_payload(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _ensure_resource_table(session: Session) -> None:
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


def _decode_resource(row: Any) -> dict[str, Any]:
    payload = json.loads(row.payload_json or "{}")
    return sanitize_system_payload(
        {
            "id": str(row.id),
            "key": payload.get("key") or row.name,
            "name": row.name,
            "value": payload.get("value", payload),
            "project_id": row.project_id,
            "target_type": row.parent_type,
            "target_id": row.parent_id,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            **payload,
        }
    )


def _public_model_dict(model: Any) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for column in model.__table__.columns:
        value = getattr(model, column.name)
        if isinstance(value, datetime):
            value = value.isoformat()
        data[column.name] = value
    return sanitize_system_payload(data)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in SENSITIVE_MARKERS) or lowered.endswith("_token") or lowered.endswith("-token")


def _redact_text(value: str) -> str:
    lowered = value.lower()
    if any(pattern in lowered for pattern in ("bearer ", "basic ", "api_key=", "token=", "password=", "secret=", "authorization:")):
        return "***"
    return value.replace("sk-round12-fake-secret", "***")

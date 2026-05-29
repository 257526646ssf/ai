from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from aitest_platform.models import (
    ApiEndpoint,
    ApiEnvironment,
    ApiScenario,
    ApiSchedule,
    ApiTestCase,
    ApiTestLib,
    AutoCaseFile,
    AutoProject,
    LlmConfig,
    PerfPlan,
    Project,
    PromptTemplate,
    ReportTemplate,
)


SENSITIVE_KEY_PARTS = ("authorization", "api_key", "api-key", "apikey", "token", "cookie", "secret", "password")
SENSITIVE_TEXT_PATTERN = re.compile(
    r"(?i)(authorization|api[_-]?key|token|cookie|secret|password)(\s*[:=]\s*)(Bearer\s+)?[^\s,;}\"]+"
)


RESTORE_TABLES: tuple[tuple[str, type[Any]], ...] = (
    ("projects", Project),
    ("api_test_libs", ApiTestLib),
    ("api_endpoints", ApiEndpoint),
    ("api_test_cases", ApiTestCase),
    ("api_environments", ApiEnvironment),
    ("api_scenarios", ApiScenario),
    ("api_schedules", ApiSchedule),
    ("auto_projects", AutoProject),
    ("auto_case_files", AutoCaseFile),
    ("perf_plans", PerfPlan),
    ("report_templates", ReportTemplate),
    ("prompt_templates", PromptTemplate),
)

LLM_CONFIG_ALLOWED_FIELDS = {
    "id",
    "name",
    "base_url",
    "model_name",
    "max_tokens",
    "temperature",
    "is_default",
    "is_enabled",
    "module_binding",
    "sort_order",
}


class RestorePayloadError(ValueError):
    pass


def restore_system_backup(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RestorePayloadError("restore payload must be an object")

    mode = _restore_mode(payload)
    dry_run = _is_dry_run(payload, mode)
    overwrite_requested = mode == "overwrite"
    if overwrite_requested and payload.get("confirm_text") != "RESTORE":
        raise RestorePayloadError('overwrite restore requires confirm_text="RESTORE"')

    data = _restore_data(payload)
    if not isinstance(data, dict):
        raise RestorePayloadError("restore data must be an object")

    summary = _empty_summary(mode=mode, dry_run=dry_run, overwrite_requested=overwrite_requested)
    if overwrite_requested:
        summary["overwrite_requested"] = True

    available_ids = _collect_existing_ids(session) if dry_run else None
    for table_name, model in RESTORE_TABLES:
        records = _table_records(data, table_name)
        _restore_table(session, model, table_name, records, dry_run, summary, available_ids)

    if _table_records(data, "llm_configs"):
        _restore_table(
            session,
            LlmConfig,
            "llm_configs",
            _table_records(data, "llm_configs"),
            dry_run,
            summary,
            available_ids,
        )

    summary["restored"] = not dry_run and (summary["created"] > 0 or summary["updated"] > 0)
    summary["tables"] = sanitize_restore_payload(summary["tables"])
    summary["summary"] = _summary_alias(summary["tables"])
    summary["errors_detail"] = sanitize_restore_payload(summary["errors_detail"])
    return sanitize_restore_payload(summary)


def sanitize_restore_payload(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(part in lowered for part in SENSITIVE_KEY_PARTS):
                clean[key] = "***"
            else:
                clean[key] = sanitize_restore_payload(item)
        return clean
    if isinstance(value, list):
        return [sanitize_restore_payload(item) for item in value]
    if isinstance(value, str):
        return SENSITIVE_TEXT_PATTERN.sub(lambda match: f"{match.group(1)}{match.group(2)}***", value)
    return value


def _restore_mode(payload: dict[str, Any]) -> str:
    raw_mode = str(payload.get("mode") or "merge").strip().lower().replace("-", "_")
    if raw_mode in {"dry_run", "preview"}:
        return raw_mode
    if raw_mode not in {"merge", "overwrite"}:
        raise RestorePayloadError("mode must be merge, overwrite, dry_run, or preview")
    return raw_mode


def _is_dry_run(payload: dict[str, Any], mode: str) -> bool:
    if mode in {"dry_run", "preview"}:
        return True
    return bool(payload.get("dry_run") or payload.get("dryRun") or payload.get("preview"))


def _restore_data(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("data_json"), dict):
        return data["data_json"]
    if isinstance(data, dict) and _looks_like_restore_data(data):
        return data
    if isinstance(payload.get("data_json"), dict):
        return payload["data_json"]
    direct = {key: payload[key] for key, _model in (*RESTORE_TABLES, ("llm_configs", LlmConfig)) if key in payload}
    if direct:
        return direct
    if data in (None, {}):
        return {}
    raise RestorePayloadError("restore data must use backup.data_json or table arrays")


def _looks_like_restore_data(data: dict[str, Any]) -> bool:
    known_tables = {key for key, _model in RESTORE_TABLES} | {"llm_configs"}
    return bool(known_tables.intersection(data.keys()))


def _table_records(data: dict[str, Any], table_name: str) -> list[dict[str, Any]]:
    records = data.get(table_name) or []
    if not isinstance(records, list):
        return []
    return [record for record in records if isinstance(record, dict)]


def _empty_summary(mode: str, dry_run: bool, overwrite_requested: bool) -> dict[str, Any]:
    return {
        "restored": False,
        "dry_run": dry_run,
        "mode": "merge" if mode in {"dry_run", "preview"} else mode,
        "preview_mode": mode if mode in {"dry_run", "preview"} else None,
        "overwrite_requested": overwrite_requested,
        "tables": {},
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "errors": 0,
        "errors_detail": [],
    }


def _summary_alias(tables: dict[str, dict[str, int]]) -> dict[str, dict[str, int]]:
    return {
        table_name: {
            **table_summary,
            "records": int(table_summary.get("received", 0)),
            "count": int(table_summary.get("received", 0)),
        }
        for table_name, table_summary in tables.items()
    }


def _restore_table(
    session: Session,
    model: type[Any],
    table_name: str,
    records: list[dict[str, Any]],
    dry_run: bool,
    summary: dict[str, Any],
    available_ids: dict[str, set[int]] | None,
) -> None:
    table_summary = {"received": len(records), "created": 0, "updated": 0, "skipped": 0, "errors": 0}
    summary["tables"][table_name] = table_summary
    if not records:
        return

    for index, raw_record in enumerate(records):
        record = _clean_record(model, raw_record)
        if not record:
            _skip(summary, table_summary, table_name, index, "record has no restorable fields")
            continue

        missing = _missing_foreign_key(session, model, record, available_ids)
        if missing:
            _skip(summary, table_summary, table_name, index, missing)
            continue

        item_id = _coerce_int(record.get("id"))
        existing = session.get(model, item_id) if item_id is not None else None
        action = "updated" if existing is not None else "created"

        if dry_run:
            table_summary[action] += 1
            summary[action] += 1
            if item_id is not None and available_ids is not None:
                available_ids.setdefault(model.__tablename__, set()).add(item_id)
            continue

        try:
            with session.begin_nested():
                if existing is not None:
                    for key, value in record.items():
                        if key != "id":
                            setattr(existing, key, value)
                else:
                    session.add(model(**record))
                session.flush()
            table_summary[action] += 1
            summary[action] += 1
        except SQLAlchemyError as exc:
            _skip(summary, table_summary, table_name, index, _safe_error_message(exc), count_error=True)
        except (TypeError, ValueError) as exc:
            _skip(summary, table_summary, table_name, index, _safe_error_message(exc), count_error=True)


def _clean_record(model: type[Any], record: dict[str, Any]) -> dict[str, Any]:
    allowed = {column.name: column for column in model.__table__.columns}
    if model is LlmConfig:
        allowed = {key: column for key, column in allowed.items() if key in LLM_CONFIG_ALLOWED_FIELDS or key == "api_key_ref"}

    clean: dict[str, Any] = {}
    for key, value in record.items():
        if key not in allowed:
            continue
        if model is LlmConfig and key == "api_key_ref":
            clean[key] = None
            continue
        clean[key] = _coerce_column_value(allowed[key], sanitize_restore_payload(value))

    if model is LlmConfig:
        clean["api_key_ref"] = None
    return clean


def _coerce_column_value(column: Any, value: Any) -> Any:
    if value is None:
        return None
    python_type = getattr(column.type, "python_type", None)
    try:
        python_type = column.type.python_type
    except NotImplementedError:
        python_type = None
    if python_type is datetime and isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return value
    if python_type is int:
        return _coerce_int(value)
    if python_type is bool and isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return value


def _missing_foreign_key(
    session: Session,
    model: type[Any],
    record: dict[str, Any],
    available_ids: dict[str, set[int]] | None = None,
) -> str | None:
    for column in model.__table__.columns:
        if column.name not in record or record[column.name] is None:
            continue
        for foreign_key in column.foreign_keys:
            target_model = _model_for_table(foreign_key.column.table.name)
            if target_model is None:
                continue
            value = _coerce_int(record[column.name])
            if value is None:
                return f"invalid foreign key {column.name}"
            if available_ids is not None and value in available_ids.get(target_model.__tablename__, set()):
                continue
            if session.get(target_model, value) is None:
                return f"missing foreign key {column.name}={record[column.name]}"
    return None


def _collect_existing_ids(session: Session) -> dict[str, set[int]]:
    available: dict[str, set[int]] = {}
    for table_name, model in (*RESTORE_TABLES, ("llm_configs", LlmConfig)):
        table_ids: set[int] = set()
        try:
            table_ids.update(int(value) for value in session.scalars(select(model.id)) if value is not None)
        except SQLAlchemyError:
            table_ids = set()
        available[model.__tablename__] = table_ids
    return available


def _model_for_table(table_name: str) -> type[Any] | None:
    for _key, model in (*RESTORE_TABLES, ("llm_configs", LlmConfig)):
        if model.__tablename__ == table_name:
            return model
    return None


def _coerce_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _skip(
    summary: dict[str, Any],
    table_summary: dict[str, int],
    table_name: str,
    index: int,
    reason: str,
    count_error: bool = False,
) -> None:
    table_summary["skipped"] += 1
    summary["skipped"] += 1
    if count_error:
        table_summary["errors"] += 1
        summary["errors"] += 1
    if len(summary["errors_detail"]) < 50:
        summary["errors_detail"].append({"table": table_name, "index": index, "reason": reason[:500]})


def _safe_error_message(exc: Exception) -> str:
    return sanitize_restore_payload(str(exc)).splitlines()[0][:500] or exc.__class__.__name__

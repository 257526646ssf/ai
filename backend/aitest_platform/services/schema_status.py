from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from aitest_platform.db.session import Base, get_engine


def get_schema_status(engine: Engine | None = None) -> dict[str, Any]:
    checked_at = datetime.now(timezone.utc).isoformat()

    try:
        from aitest_platform import models  # noqa: F401

        resolved_engine = engine or get_engine()
        expected_tables = _expected_table_columns()
        inspector = inspect(resolved_engine)
        present_tables = set(inspector.get_table_names())

        missing_tables = sorted(set(expected_tables) - present_tables)
        missing_columns: dict[str, list[str]] = {}
        for table_name, expected_columns in expected_tables.items():
            if table_name not in present_tables:
                continue
            present_columns = {column["name"] for column in inspector.get_columns(table_name)}
            missing = sorted(expected_columns - present_columns)
            if missing:
                missing_columns[table_name] = missing

        status = "ok"
        if missing_tables or missing_columns:
            status = "warning"

        return {
            "status": status,
            "database_url_type": _database_url_type(resolved_engine),
            "database_file_exists": _sqlite_database_file_exists(resolved_engine),
            "tables_total": len(expected_tables),
            "tables_present": len(set(expected_tables) & present_tables),
            "missing_tables": missing_tables,
            "missing_columns": missing_columns,
            "extra_tables_count": len(present_tables - set(expected_tables)),
            "schema_version": _metadata_hash(expected_tables),
            "checked_at": checked_at,
        }
    except Exception as exc:
        return {
            "status": "error",
            "database_url_type": _safe_database_type(engine),
            "database_file_exists": _sqlite_database_file_exists(engine) if engine is not None else None,
            "tables_total": 0,
            "tables_present": 0,
            "missing_tables": [],
            "missing_columns": {},
            "extra_tables_count": 0,
            "schema_version": None,
            "checked_at": checked_at,
            "error": {
                "type": exc.__class__.__name__,
                "message": "schema introspection failed",
            },
        }


def _expected_table_columns() -> dict[str, set[str]]:
    return {
        table_name: {column.name for column in table.columns}
        for table_name, table in Base.metadata.tables.items()
    }


def _metadata_hash(expected_tables: dict[str, set[str]]) -> str:
    parts: list[str] = []
    for table_name in sorted(expected_tables):
        columns = ",".join(sorted(expected_tables[table_name]))
        parts.append(f"{table_name}:{columns}")
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"metadata:{digest}"


def _database_url_type(engine: Engine) -> str:
    return engine.url.drivername.split("+", 1)[0]


def _safe_database_type(engine: Engine | None) -> str | None:
    if engine is None:
        return None
    try:
        return _database_url_type(engine)
    except Exception:
        return None


def _sqlite_database_file_exists(engine: Engine | None) -> bool | None:
    if engine is None:
        return None
    if _safe_database_type(engine) != "sqlite":
        return None

    database = engine.url.database
    if not database or database == ":memory:":
        return False
    return Path(database).exists()
